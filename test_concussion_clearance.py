"""Concussion clearance is mandatory for both user and CPU teams."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np
import injury_status as IS
import inbox as IB


class ConcussionClearanceTests(unittest.TestCase):
    def setup_case(self, abbr='GB', until=6, kind='Concussion'):
        p = NS(pid='hurt', name='Test Player', pos='WR', team=abbr, retired=False,
               out_until=until, xp_spent={'_inj_kind': kind, '_inj_week': 3},
               ratings={'tough_rating': 99}, contract=True, fa_class='under_contract')
        t = NS(abbr=abbr, roster=[p], ir=[], depth={'WR': [p]})
        L = NS(players={p.pid: p}, teams={abbr: t}, user_team='GB', week=4,
               year=2032, phase='regular', schedule=[(4, 'GB', 'CHI', None, None)], inbox=[],
               log=Mock(), player=lambda pid: p if pid == p.pid else None)
        return L, t, p, IS.InjuryDesk()

    def test_every_active_week_is_out_for_user_and_cpu(self):
        for abbr in ('GB', 'CHI'):
            for until in (5, 6, 7):
                with self.subTest(team=abbr, until=until):
                    L, t, p, desk = self.setup_case(abbr, until)
                    with patch.object(IS, 'designation') as roll:
                        desk.set_week(L, t, 4, np.random.default_rng(1))
                    self.assertEqual(desk.status[p.pid], 'out')
                    self.assertFalse(desk.pending)
                    self.assertFalse(desk.playing_hurt)
                    self.assertFalse(L.inbox)
                    self.assertFalse(desk.available(p, 4))
                    roll.assert_not_called()

    def test_direct_play_through_cannot_clear_concussion(self):
        L, t, p, desk = self.setup_case()
        desk.pending[p.pid] = 'doubtful'
        self.assertFalse(desk.play_through(L, t, p, 'doubtful'))
        self.assertEqual(p.out_until, 6)
        self.assertEqual(desk.status[p.pid], 'out')
        self.assertFalse(desk.pending)
        self.assertFalse(desk.playing_hurt)
        L.log.assert_not_called()

    def test_manual_action_reports_out_and_does_not_refresh_as_playing(self):
        from views_club import act_hurt_decision
        L, t, p, desk = self.setup_case()
        desk.status[p.pid] = 'out'
        runner = NS(desks={'GB': desk}, refresh=Mock())
        result = act_hurt_decision(L, 'GB', p.pid, session=NS(runner=runner))
        self.assertFalse(result['ok'])
        self.assertIn('out until medically cleared', result['why'])
        self.assertEqual(p.out_until, 6)
        runner.refresh.assert_not_called()

    def test_unanswered_legacy_prompt_cannot_randomly_allow_play(self):
        L, t, p, desk = self.setup_case()
        desk.pending[p.pid] = 'doubtful'
        with patch.object(IS, 'will_play', return_value=True) as roll:
            desk.resolve_pending(L, t, np.random.default_rng(1))
        roll.assert_not_called()
        self.assertEqual(p.out_until, 6)
        self.assertFalse(desk.available(p, 4))
        self.assertFalse(desk.pending)

    def test_legacy_play_hurt_state_repairs_without_rng_or_other_desks(self):
        L, t, p, desk = self.setup_case()
        p.out_until = None
        p.xp_spent.update(_hurt_until=6, _hurt_desig='doubtful')
        desk.playing_hurt[p.pid] = desk.status[p.pid] = 'doubtful'
        self.assertFalse(desk.available(p, 4))
        other = IS.InjuryDesk()
        IS.clear_recovered(L, 4, {'GB': desk, 'CHI': other})
        self.assertEqual(p.out_until, 6)
        self.assertEqual(desk.status[p.pid], 'out')
        self.assertFalse(desk.playing_hurt)
        self.assertFalse(other.status)
        self.assertNotIn('_hurt_until', p.xp_spent)
        before = copy.deepcopy((p.__dict__, desk.__dict__))
        IS.clear_recovered(L, 4, {'GB': desk})
        self.assertEqual(before, (p.__dict__, desk.__dict__))

    def test_old_prompt_is_not_an_open_decision_even_before_weekly_relisting(self):
        L, t, p, desk = self.setup_case()
        msg = IB.post(L, 'injury_decision', 'Play or sit?', '',
                      payload={'pid': p.pid}, expires_week=4)
        IB.reconcile(L)
        self.assertEqual(msg['status'], 'done')
        self.assertFalse(IB.is_decision(msg))

    def test_clearance_week_allows_return_and_keeps_history(self):
        L, t, p, desk = self.setup_case()
        desk.status[p.pid] = 'out'
        IS.clear_recovered(L, 6, {'GB': desk})
        self.assertIsNone(p.out_until)
        self.assertTrue(desk.available(p, 6))
        self.assertFalse(desk.status)
        self.assertEqual(p.xp_spent['_inj_kind'], 'Concussion')
        self.assertFalse(IS.concussion_restricted(p))

    def test_ir_and_season_ending_restrictions_are_preserved(self):
        L, t, p, desk = self.setup_case(until=99)
        t.ir = [p]
        desk.status[p.pid] = 'ir'
        IS.clear_recovered(L, 19, {'GB': desk})
        self.assertEqual(desk.status[p.pid], 'ir')
        self.assertEqual(p.out_until, 99)
        self.assertFalse(desk.available(p, 19))

    def test_copy_does_not_recommend_playing_or_claim_clearance(self):
        L, t, p, desk = self.setup_case()
        for mentions in (True, False):
            text = IS.hurt_words(L, t, p, 'doubtful', mentions=mentions)
            self.assertIn('is out', text)
            self.assertIn('cannot play until medically cleared', text)
            self.assertNotIn('is cleared', text)
            self.assertNotIn('doubtful', text)

    def test_non_concussion_play_hurt_still_works(self):
        L, t, p, desk = self.setup_case(kind='Ankle')
        self.assertTrue(desk.play_through(L, t, p, 'doubtful'))
        self.assertIsNone(p.out_until)
        self.assertTrue(desk.available(p, 4))
        self.assertEqual(p.xp_spent['_hurt_until'], 6)


class ConcussionSaveTests(unittest.TestCase):
    def test_session_reload_removes_prompt_and_restores_medical_unavailability(self):
        from session import Session
        from season import SeasonRunner
        import game_availability as GA
        s = Session.new('GB', seed=23)
        s.L.set_phase('regular')
        s.L.week = 4
        s.stop = ('week', 4)
        s.runner = SeasonRunner(s.L, s.rng)
        p = s.L.teams['GB'].roster[0]
        p.out_until = None
        p.xp_spent.update(_inj_kind='Concussion', _hurt_until=6, _hurt_desig='doubtful')
        desk = s.runner.desks['GB']
        desk.status[p.pid] = desk.playing_hurt[p.pid] = desk.pending[p.pid] = 'doubtful'
        m = IB.post(s.L, 'injury_decision', 'Play or sit?', '',
                    payload={'pid': p.pid}, expires_week=4)
        rng = copy.deepcopy(s.rng.bit_generator.state)
        loaded = Session.load(s.save())
        q = loaded.L.player(p.pid)
        other = loaded.runner.desks['GB']
        self.assertEqual(q.out_until, 6)
        self.assertEqual(other.status[q.pid], 'out')
        self.assertFalse(other.pending)
        self.assertNotIn(q, GA.dressed(loaded.L.teams['GB'], other, 4))
        self.assertEqual(next(x for x in loaded.L.inbox if x['id'] == m['id'])['status'], 'done')
        self.assertEqual(rng, loaded.rng.bit_generator.state)


if __name__ == '__main__':
    unittest.main()
