"""Renewal intent is a soft roster preference, never a sunk-bonus trade ban."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import extensions as EXT
import retention_plan as RP
import roster_needs as RN
import trades as TR
from cap_engine import Contract
from league import League
from test_draft_planning import fixture, set_grade
from test_trade_integrity import roster, league


class RenewalTradePlanTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = roster('GB'), roster('ARI')
        self.L = league(self.a, self.b)
        self.L.user_team = 'GB'
        self.p = next(p for p in self.b.roster if p.pos == 'DT')
        self.p.ovr = 77
        spare = [p for p in self.b.roster if p.pos == 'DT'][4:]
        self.b.roster = [p for p in self.b.roster if p not in spare]
        for p in self.b.roster:
            if p.pos == 'DT' and p is not self.p: p.ovr = 80
        self.b.gm.patience, self.b.gm.loyalty, self.b.gm.aggression = .4, .5, .45
        self.intent = RP.committed_role(self.b, self.p)
        self.tx = dict(kind='extension', year=self.L.year, week=22,
                       phase='free_agency', team='ARI', pid=self.p.pid,
                       role_intent=self.intent)

    def read(self):
        return RP.extension_continuity(self.L, self.b, {self.p.pid}, RN.assess(self.b))

    def football(self):
        return TR.package_football(self.L, self.a, self.b, [], [self.p.pid])

    def check(self, gain):
        # Synthetic seller surplus isolates willingness, not a made-up real bid.
        # Actual package accounting and portfolio tests run separately.
        with patch.object(TR.VAL, 'pool_from_league', return_value={}), \
             patch('cap_accounting.require_trade_room', return_value=None), \
             patch.object(TR, 'player_asset', return_value=dict(kind='player')), \
             patch.object(TR, 'pick_asset', return_value=dict(kind='pick')), \
             patch.object(TR, '_financial_trade', return_value=True), \
             patch.object(TR.TE, 'evaluate', return_value=dict(a_gain=0, b_gain=gain, blocked=None)):
            return TR.cpu_trade_check(self.L, self.a, self.b,
                                      [NS(year=2029, round_=2)], [self.p.pid])

    def test_rotation_renewal_prices_marginal_flip_but_allows_strong_offer(self):
        base = self.football()['reserves']['ARI']
        self.assertLess(self.intent['role_share'], .15)
        self.assertTrue(self.check(base + .3)['approved'])
        self.L.transactions.append(self.tx)
        extra = self.read()['reserve']
        self.assertGreater(extra, .3)
        self.assertFalse(self.check(base + .3)['approved'])
        self.assertTrue(self.check(base + extra + 1)['approved'])
        # A just-extended player remains a candidate, unlike an arrival ban.
        self.assertNotIn(self.p.pid, TR.recent_acquisitions(self.L, self.b))

    def test_gm_preferences_change_reserve_without_changing_player(self):
        self.L.transactions.append(self.tx)
        self.b.gm.patience, self.b.gm.loyalty, self.b.gm.aggression = .1, .1, .9
        aggressive = self.read()['reserve']
        self.b.gm.patience, self.b.gm.loyalty, self.b.gm.aggression = .9, .9, .1
        patient = self.read()['reserve']
        self.assertGreater(patient, aggressive)
        self.assertGreater(aggressive, 0)

    def test_starting_role_replaced_by_real_new_player_reduces_preference(self):
        L, t = fixture(); L.user_team = None; t.cap.cap = 500
        p = t.by_pos('FS')[0]; set_grade(p, 85)
        set_grade(t.by_pos('SS')[0], 95)
        intent = RP.committed_role(t, p)
        L.transactions.append(dict(self.tx, pid=p.pid, team=t.abbr,
                                   year=L.year, role_intent=intent))
        before = RP.extension_continuity(L, t, {p.pid}, RN.assess(t))['reserve']
        replacement = copy.deepcopy(p); replacement.pid = 'new-safety'
        set_grade(replacement, 95); t.roster.append(replacement)
        L.players[replacement.pid] = replacement
        after = RP.extension_continuity(L, t, {p.pid}, RN.assess(t))['reserve']
        self.assertGreater(intent['role_share'], .15)
        self.assertLess(after, before / 2)
        self.assertIn(p, t.active())

    def test_same_package_replacement_is_accounted_for(self):
        self.p = next(p for p in self.b.roster if p.pos == 'QB'); self.p.ovr = 90
        replacement = next(p for p in self.a.roster if p.pos == 'QB'); replacement.ovr = 99
        self.L.transactions.append(dict(self.tx, pid=self.p.pid,
            role_intent=RP.committed_role(self.b, self.p)))
        unchanged = self.football()['extension_continuity']['ARI']['reserve']
        exchanged = TR.package_football(self.L, self.a, self.b,
            [replacement.pid], [self.p.pid])['extension_continuity']['ARI']['reserve']
        self.assertLess(exchanged, unchanged)

    def test_request_or_current_cap_problem_can_override_intent(self):
        self.L.transactions.append(self.tx)
        self.assertGreater(self.read()['reserve'], 0)
        self.p.xp_spent['_request'] = dict(reason='role')
        self.assertEqual(self.read()['reserve'], 0)
        self.p.xp_spent.clear(); self.b.cap_space = -1
        self.assertEqual(self.read()['reserve'], 0)

    def test_sunk_bonus_and_hidden_ceiling_do_not_reprice_plan(self):
        self.L.transactions.append(self.tx)
        before = self.read()
        self.p.name, self.p.potential = 'Different Name', 99
        self.p.contract = Contract(3, [4]*3, signing_bonus=80)
        self.assertEqual(self.read(), before)

    def test_missing_legacy_intent_is_not_invented_but_saved_assessment_is_used(self):
        self.L.transactions.append({k:v for k,v in self.tx.items() if k != 'role_intent'})
        self.assertEqual(self.read()['reserve'], 0)
        self.L.transactions.insert(0, dict(self.tx, kind='cpu_retention_decision', **self.intent))
        self.assertGreater(self.read()['reserve'], 0)

    def test_time_window_and_no_double_charge_for_arrival(self):
        self.L.transactions.append(self.tx)
        self.assertGreater(self.read()['reserve'], 0)
        self.L.transactions.append(dict(self.tx, kind='sign'))
        expected = self.football()['reserves']['ARI']
        self.L.transactions = self.L.transactions[1:]
        self.assertEqual(self.football()['reserves']['ARI'], expected)
        self.L.transactions = [self.tx]
        self.L.phase, self.L.week = 'regular', 4
        self.assertEqual(self.read()['reserve'], 0)

    def test_user_controls_own_roster(self):
        self.L.transactions.append(self.tx); self.L.user_team = 'ARI'
        self.assertEqual(self.football()['reserves']['ARI'], 0)

    def test_successful_extension_records_intent_and_save_reload_preserves_it(self):
        with patch.dict('cap_engine.CAP'):
            L, t = fixture(); t.cap.cap = 500; t.sync_cap()
            p = t.by_pos('LT')[0]; p.contract = Contract(1, [1], signed=2026)
            p.accrued = 4
            with patch.object(EXT, 'terms', return_value=dict(ask=10, offer=10, years=2, discount=.07)):
                result = EXT.extend(L, p.pid, 10, 2, by_ai=True, agreed=True)
            self.assertEqual(result['result'], 'accepted')
            tx = next(x for x in L.transactions if x['kind'] == 'extension')
            self.assertEqual(tx['role_intent'], RP.committed_role(t, p))
            before = RP.extension_continuity(L, t, {p.pid}, RN.assess(t))
            saved = L.save(); restored = League.load(saved)
            after = RP.extension_continuity(restored, restored.teams[t.abbr],
                {p.pid}, RN.assess(restored.teams[t.abbr]))
            self.assertEqual(after['reserve'], before['reserve'])
            self.assertEqual(after['players'][0]['prior'], before['players'][0]['prior'])
            self.assertEqual(L.save(), saved)


if __name__ == '__main__': unittest.main()
