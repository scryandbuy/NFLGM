"""Real transaction boundaries: waiver priority, bargaining refusal and promises."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

from cap_engine import Contract
from gm_engine import GM
from league import League
from session import Session
from test_cap_accounting import fixture, player
import extensions as EXT
import morale as MO
import negotiations as NG
import practice_squad as PS
import views_club as VC
import views_personnel as VP
import waivers as WV


class PersonnelBoundaries(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.user_team = 'GB'
        for t in self.L.teams.values(): t.gm = GM()
        self.s = Session.__new__(Session); self.s.L = self.L; self.s.user_team = 'GB'

    def reload(self):
        self.L = League.load(self.L.save()); self.L.user_team = 'GB'; self.s.L = self.L

    def waived(self, team='MIN'):
        p = player(self.L, 'waived', team=team, contract=Contract(2, [1, 1], signing_bonus=1))
        p.accrued = 1; self.L.release(p.pid)
        return p

    def test_pending_claim_survives_shared_and_user_squad_routes_and_reload(self):
        p = self.waived(); WV.user_claim(self.L, p.pid)
        for loaded in (False, True):
            if loaded: self.reload(); p = self.L.player(p.pid)
            before = self.L.save()
            self.assertFalse(PS.sign_to_squad(self.L, 'MIN', p.pid))
            self.assertFalse(self.s.personnel_act('sign_ps', pid=p.pid)['ok'])
            self.assertEqual(self.L.save(), before)
            with patch.object(VP, 'rail', return_value={}):
                self.assertNotIn(p.pid, [r['pid'] for r in self.s.personnel('free_agency')['rows']])
        with patch.object(WV.VAL, 'pool_from_league', return_value=[]), patch.object(WV.VAL, 'value_player', return_value={'apy': 1}), patch.object(WV, 'wants', return_value=False):
            self.assertEqual(WV.process(self.L, np.random.default_rng(3), 1), [(p.pid, 'GB')])
        self.assertIn(p, self.L.teams['GB'].active())
        self.assertEqual(p.contract.years, 2)
        self.assertEqual(p.contract.sb, 0)

    def test_cleared_own_waiver_intent_can_sign_after_other_clubs_decline(self):
        p = player(self.L, 'own', contract=Contract(1, [1])); p.accrued = 1
        result = VC.act_to_squad(self.L, 'GB', p.pid)
        self.assertTrue(result['ok']); self.assertFalse(result['now'])
        self.assertFalse(PS.sign_to_squad(self.L, 'GB', p.pid))
        with patch.object(WV.VAL, 'pool_from_league', return_value=[]), patch.object(WV.VAL, 'value_player', return_value={'apy': 1}), patch.object(WV, 'wants', return_value=False):
            WV.process(self.L, np.random.default_rng(4), 1)
        self.assertIn(p, PS.squad(self.L.teams['GB']))
        self.assertFalse(WV.pending(self.L)); self.assertIsNone(p.contract)

    def test_direct_demotion_cannot_bypass_waivers_and_vested_deadline_routes_correctly(self):
        p = player(self.L, 'veteran', contract=Contract(1, [1])); p.accrued = 5
        self.L.week = 10
        before = self.L.save()
        self.assertFalse(PS.sign_to_squad(self.L, 'GB', p.pid))
        self.assertEqual(self.L.save(), before)
        result = VC.act_to_squad(self.L, 'GB', p.pid)
        self.assertTrue(result['ok']); self.assertFalse(result['now'])
        self.assertEqual(WV.pending(self.L)[0]['pid'], p.pid)

    def test_vested_predeadline_and_cleared_free_agent_still_can_sign(self):
        p = player(self.L, 'veteran', contract=Contract(1, [1])); p.accrued = 5
        self.assertTrue(VC.act_to_squad(self.L, 'GB', p.pid)['now'])
        q = player(self.L, 'free', team=None); self.L.free_agents.append(q.pid)
        self.assertTrue(self.s.personnel_act('sign_ps', pid=q.pid)['ok'])

    def open_fa(self, pid='agent', kind='fa_inseason'):
        p = self.L.player(pid)
        if p is None: p = player(self.L, pid, team=None); self.L.free_agents.append(pid)
        with patch('valuation.value_player', return_value={'apy': 10, 'years': 2}):
            result = NG.open_talks(self.L, pid, kind)
        return p, result

    def test_lowball_break_cannot_reset_patience_but_expiry_reopens(self):
        p, opened = self.open_fa()
        result = self.s.personnel_act('offer', tid=opened['thread'], apy=1, years=1)
        self.assertEqual(result['state'], 'broken_off')
        self.reload()
        before = len(self.L.negotiations)
        self.assertFalse(self.open_fa()[1]['ok'])
        self.assertEqual(len(self.L.negotiations), before)
        self.L.week = 5
        fresh = self.open_fa()[1]
        self.assertTrue(fresh['ok']); self.assertNotEqual(fresh['thread'], opened['thread'])
        self.assertEqual(fresh['patience'], NG.PATIENCE)

    def test_other_club_or_kind_refusal_does_not_block_legitimate_talks(self):
        p, opened = self.open_fa()
        t = NG.find(self.L, opened['thread']); t.update(state='broken_off', broken_until=5, team='MIN')
        self.assertTrue(self.open_fa()[1]['ok'])
        self.L.set_phase('offseason')
        self.assertTrue(self.open_fa(kind='fa_offseason')[1]['ok'])
        rival = player(self.L, 'rival', team='MIN', contract=Contract(2, [1, 1]))
        self.assertFalse(NG.open_talks(self.L, rival.pid, 'extension')['ok'])

    def test_offseason_clock_and_new_year_do_not_preserve_old_break_forever(self):
        self.L.set_phase('offseason')
        p, opened = self.open_fa(kind='fa_offseason')
        t = NG.find(self.L, opened['thread']); t.update(state='broken_off', broken_until=104)
        self.assertFalse(self.open_fa(kind='fa_offseason')[1]['ok'])
        self.L.set_phase('regular'); self.L.week = 1
        NG.resolve(self.L)
        self.assertEqual(t['state'], 'expired')
        t.update(state='broken_off', broken_until=30, opened=1)
        self.L.year += 1
        self.assertTrue(self.open_fa()[1]['ok'])

    def test_firm_extension_refusal_does_not_reset_in_same_window(self):
        self.L.set_phase('offseason'); self.L.week = 22
        p = player(self.L, 'extension', contract=Contract(2, [1, 1], signed=self.L.year))
        with patch.object(EXT, 'terms', return_value={'ask': 10, 'years': 2, 'discount': 0}):
            opened = NG.open_talks(self.L, p.pid)
            self.assertEqual(NG.make_offer(self.L, opened['thread'], 1, 2)['state'], 'declined')
            self.assertFalse(NG.open_talks(self.L, p.pid)['ok'])
            self.L.year += 1
            self.assertTrue(NG.open_talks(self.L, p.pid)['ok'])

    def test_old_offseason_thread_refusing_inseason_uses_refusal_clock(self):
        self.L.set_phase('offseason'); self.L.week = 22
        p = player(self.L, 'extension', contract=Contract(2, [1, 1], signed=self.L.year))
        with patch.object(EXT, 'terms', return_value={'ask': 10, 'years': 2, 'discount': 0}):
            opened = NG.open_talks(self.L, p.pid)
            self.L.set_phase('regular'); self.L.week = 5
            self.assertEqual(NG.make_offer(self.L, opened['thread'], 1, 2)['state'], 'broken_off')
            self.assertFalse(NG.open_talks(self.L, p.pid)['ok'])
            self.L.week = 9
            self.assertTrue(NG.open_talks(self.L, p.pid)['ok'])

    def test_failed_contract_execution_can_be_reopened_after_problem_is_fixed(self):
        p, opened = self.open_fa(); t = NG.find(self.L, opened['thread'])
        with patch.object(NG, '_assessment', return_value={'acceptable': True}), patch.object(NG, '_accept', return_value={'ok': False, 'why': 'cap room'}):
            self.assertEqual(NG._answer(self.L, t, p, {'apy': 10, 'years': 1}, 10), 'failed')
        self.assertEqual(t['state'], 'declined')
        self.assertTrue(self.open_fa()[1]['ok'])

    def promise_player(self):
        p = player(self.L, 'promise', contract=Contract(3, [1, 1, 1], signed=self.L.year))
        MO.ensure(p)
        return p

    def test_three_to_two_countdown_never_fulfills_extension_promise_new_or_legacy(self):
        for legacy in (False, True):
            self.setUp(); p = self.promise_player()
            pr = NG.record_promise(self.L, p.pid, 'GB', 'extension_by', year=self.L.year+2)
            if legacy: pr.pop('orig_end'); pr.pop('extension_after')
            p.contract.advance(); self.L.year += 1
            self.reload(); p = self.L.player(p.pid)
            NG.check_promises(self.L, 1)
            self.assertEqual(self.L.promises[0]['status'], 'open')
            self.assertFalse(any(t['kind'] == 'promise_kept' for t in self.L.transactions))
            self.L.year += 1; p.contract.advance()
            NG.check_promises(self.L, 1)
            self.assertEqual(self.L.promises[0]['status'], 'broken')

    def test_actual_extension_fulfills_once_after_rollover_and_reload(self):
        p = self.promise_player()
        NG.record_promise(self.L, p.pid, 'GB', 'extension_by')
        p.contract.advance(); self.L.year += 1
        with patch.object(EXT, 'terms', return_value={'ask': 2, 'years': 1, 'discount': 0}):
            result = EXT.extend(self.L, p.pid, 2, 1, agreed=True)
        self.assertEqual(result['result'], 'accepted')
        self.reload()
        for _ in range(2): NG.check_promises(self.L, 1)
        self.assertEqual(self.L.promises[0]['status'], 'kept')
        self.assertEqual(sum(t['kind'] == 'promise_kept' for t in self.L.transactions), 1)

    def test_rookie_option_is_not_an_extension(self):
        p = self.promise_player(); pr = NG.record_promise(self.L, p.pid, 'GB', 'extension_by')
        p.contract.years += 1; p.contract.base.append(1); p.contract.rb.append(0)
        self.L.log('rookie_option', pid=p.pid, team='GB')
        NG.check_promises(self.L, 1)
        self.assertEqual(pr['status'], 'open')

    def test_no_tag_alias_normalizes_and_enforces_future_tag_without_replaying_history(self):
        p = self.promise_player()
        pr = NG.record_promise(self.L, p.pid, 'GB', 'no_tag')
        self.assertEqual(pr['kind'], 'no_franchise')
        self.assertIs(NG.record_promise(self.L, p.pid, 'GB', 'no_franchise'), pr)
        pr['kind'] = 'no_tag'; p.tagged_year = self.L.year
        old = dict(pr, status='broken', made=self.L.year-1)
        self.L.promises.append(old); before = copy.deepcopy(old)
        NG.check_promises(self.L, 1)
        self.assertEqual(pr['status'], 'open'); self.assertEqual(old, before)
        self.assertFalse(self.L.transactions)
        self.reload(); p = self.L.player(p.pid)
        self.L.year += 1; p.tagged_year = self.L.year
        NG.check_promises(self.L, 1)
        self.assertEqual(self.L.promises[0]['status'], 'broken')
        self.assertEqual(sum(t['kind'] == 'promise_broken' for t in self.L.transactions), 1)

    def test_new_alias_promise_breaks_on_actual_tag_and_terminal_duplicate_is_not_replayed(self):
        p = self.promise_player()
        pr = NG.record_promise(self.L, p.pid, 'GB', 'no_tag')
        p.tagged_year = self.L.year
        NG.check_promises(self.L, 1)
        self.assertEqual(pr['status'], 'broken')
        self.assertEqual(p.morale.broken, ['no_franchise'])
        old = copy.deepcopy(pr); old['kind'] = 'no_tag'
        self.L.promises = [old, dict(pr, status='open')]
        NG.check_promises(self.L, 1)
        self.assertEqual(old['kind'], 'no_tag')
        self.assertEqual(self.L.promises[1]['status'], 'superseded')
        self.assertEqual(len(p.morale.broken), 1)


if __name__ == '__main__': unittest.main()
