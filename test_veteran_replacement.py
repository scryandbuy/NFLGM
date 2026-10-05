"""Football decisions: keep productive youth, but still allow worthwhile change."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cap_engine import Contract
from league import Player
import gm_engine as GM
import veteran_market as VM
from test_draft_planning import fixture, set_grade


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.L, self.t = fixture()
        self.L.set_phase('regular'); self.L.week = 5
        self.t.record = [4, 1, 0]
        self.old = self.t.by_pos('LT')[0]
        self.old.contract = Contract(1, [20.])
        self.new = copy.deepcopy(self.old)
        self.new.pid = 'arrival'; self.new.team = self.new.contract = None
        self.new.xp_spent = {}; self.new.age = 30
        set_grade(self.old, 88); set_grade(self.new, 90)
        self.contract = Contract(1, [20.])
        self.quote = dict(apy=30., years=1)

    def read(self, gain=1.5):
        with patch.object(VM.MK.VAL, 'value_player', return_value=self.quote):
            return VM.replacement_read(self.L, self.t, self.new, self.old,
                self.contract, gain, VM.RN.assess(self.t), self.quote)

    def test_campbell_darrisaw_saved_case_not_name_exception(self):
        data = json.loads((Path(__file__).parent / 'research/ne_tackle_replacement_2029.json').read_text())
        self.old = Player.from_dict(data['players']['P1735'])
        self.new = Player.from_dict(data['players']['P1656'])
        self.old.team = 'MIN'
        self.old.contract = Contract(1, [28.], signed=2025)
        self.old.contract.earned_base = 28. - data['release']['saved']
        self.contract = Contract(1, [10.21], signing_bonus=10.342)
        self.t.roster = [p for p in self.t.roster if p.pid != 'LT0'] + [self.old]
        self.L.players[self.old.pid] = self.old
        self.t.gm = GM.GM(**{k:v for k,v in data['gm'].items() if k in GM.GM.__dataclass_fields__})
        self.L.stats[self.L.year] = data['stats']
        read = self.read(data['sign']['planning_gain'])
        self.assertFalse(read['approved'], read)
        self.assertGreater(read['continuity_cost'], 0)
        self.assertGreater(read['released_asset_value'], 0)
        self.assertAlmostEqual(read['current_cap_change'], .33, places=3)
        self.old.name = self.new.name = 'Unrelated Name'
        self.assertEqual(self.read(data['sign']['planning_gain']), read)
        # A major improvement is a different decision, even for this incumbent.
        self.assertTrue(self.read(18.)['approved'])

    def test_young_controlled_successor_changes_actual_verdict(self):
        self.old.age = 22; self.old.accrued = 0
        self.old.dev = 'superstar'; self.old.potential_range = (95, 99)
        self.old.contract = Contract(4, [1.]*4)
        young = self.read(4.)
        self.old.age = 34; self.old.accrued = 10
        self.old.dev = 'normal'; self.old.contract = Contract(1, [20.])
        older = self.read(4.)
        self.assertFalse(young['approved'], young)
        self.assertTrue(older['approved'], older)
        self.assertLess(young['net_gain'], older['net_gain'])

    def test_gm_preferences_change_borderline_choice(self):
        self.t.gm.aggression = 0.; self.t.gm.patience = 1.; self.t.gm.youth = 1.
        conservative = self.read(3.)
        self.t.gm.aggression = 1.; self.t.gm.patience = 0.; self.t.gm.youth = 0.
        aggressive = self.read(3.)
        self.assertLess(conservative['net_gain'], aggressive['net_gain'])
        self.assertFalse(conservative['approved'], conservative)
        self.assertTrue(aggressive['approved'], aggressive)

    def test_hidden_ceiling_and_longevity_do_not_affect_assessment(self):
        a = self.read(4.)
        self.old.potential = 99; self.new.potential = 60
        self.old.longevity = .1; self.new.longevity = 8.
        self.assertEqual(self.read(4.), a)

    def test_public_evidence_rewards_production_without_inventing_missing_stats(self):
        self.L.stats[self.L.year] = {}
        missing = self.read(4.)
        good = dict(pb_snaps=400, pb_wins=390, pressures_allowed=2, sacks_allowed=0,
                    rb_snaps=250, rb_wins=220)
        self.L.stats[self.L.year] = {self.old.pid: good}
        for i in range(5):
            p = copy.deepcopy(self.old); p.pid = f'peer{i}'; self.L.players[p.pid] = p
            self.L.stats[self.L.year][p.pid] = dict(good, pb_wins=350, pressures_allowed=20)
        productive = self.read(4.)
        self.L.stats[self.L.year][self.old.pid] = dict(good, pb_wins=250, pressures_allowed=60, sacks_allowed=12)
        struggling = self.read(4.)
        self.assertEqual(missing['performance_confidence'], 0)
        self.assertGreater(productive['continuity_cost'], struggling['continuity_cost'])
        self.assertLess(productive['net_gain'], struggling['net_gain'])

    def test_read_does_not_mutate_players_contracts_or_transactions(self):
        before = copy.deepcopy((self.old.to_dict(), self.new.to_dict(), self.L.transactions))
        self.read(4.)
        self.assertEqual((self.old.to_dict(), self.new.to_dict(), self.L.transactions), before)

    def test_deadline_removes_hypothetical_current_trade_return(self):
        before = self.read(4.)
        self.L.week = 10
        after = self.read(4.)
        self.assertGreater(before['asset_cost'], 0)
        self.assertEqual(after['asset_cost'], 0)
        self.assertLess(after['immediate_gain'], before['immediate_gain'])

    def test_public_production_survives_empty_new_season_but_current_form_wins(self):
        line = dict(pb_snaps=400, pb_wins=390, pressures_allowed=2, sacks_allowed=0,
                    rb_snaps=250, rb_wins=220)
        self.L.stats[self.L.year] = {self.old.pid: line}
        self.L.set_phase('offseason')
        self.L.season_closed_year = self.L.year
        before = self.read(4.)
        self.L.year += 1
        self.L.stats[self.L.year] = {}
        after = self.read(4.)
        self.assertGreater(before['performance_confidence'], 0)
        self.assertEqual(before['performance_confidence'], after['performance_confidence'])
        self.assertEqual(before['continuity_cost'], after['continuity_cost'])
        # A played current season is authoritative; do not cherry-pick the
        # stronger old season to resist a replacement despite current form.
        self.L.set_phase('regular')
        self.L.stats[self.L.year] = {self.old.pid:dict(line, pb_snaps=1, rb_snaps=0)}
        current = self.read(4.)
        self.assertLess(current['performance_confidence'], after['performance_confidence'])

    def test_complete_replacement_preference_has_no_calendar_stub_year(self):
        self.L.set_phase('offseason')
        for stub in (False, True):
            for future_years in (1, 2):
                self.L.season_closed_year = self.L.year
                self.old.age = 23.; self.old.accrued = 1; self.old.dev = 'superstar'
                self.old.contract = Contract(future_years+1,
                    [0 if stub else 6]+[6]*future_years,
                    start_offset=int(stub), earned_base=0 if stub else 6)
                self.contract = Contract(2,[0,20],start_offset=1)
                before_contracts = copy.deepcopy([p.to_dict() for p in self.t.roster])
                before = self.read(8.)
                self.assertEqual([p.to_dict() for p in self.t.roster], before_contracts)
                for p in self.t.roster:
                    if p.contract: p.contract.advance()
                self.contract.advance()
                self.L.year += 1
                after = self.read(8.)
                for key in ('approved','net_gain','retention_change','aging_cost',
                            'released_asset_value','asset_cost','immediate_gain'):
                    self.assertEqual(before[key], after[key], (stub, future_years, key))

    def test_completed_production_resists_marginal_change_but_allows_upgrade(self):
        self.L.set_phase('offseason')
        self.L.season_closed_year = self.L.year-1
        self.L.stats[self.L.year] = {}
        self.L.stats[self.L.year-1] = {self.old.pid: dict(
            pb_snaps=400, pb_wins=390, pressures_allowed=2, sacks_allowed=0,
            rb_snaps=250, rb_wins=220)}
        productive = self.read(4.)
        self.assertFalse(productive['approved'], productive)
        self.assertTrue(self.read(8.)['approved'])
        # With no public completed-season evidence, the same marginal move
        # may be sensible. Missing evidence is not fabricated production.
        self.L.stats[self.L.year-1] = {}
        unknown = self.read(4.)
        self.assertTrue(unknown['approved'], unknown)
        self.assertEqual(unknown['performance_confidence'], 0.)

    def test_release_option_uses_same_remaining_service_and_cash_as_trade(self):
        import trades as TR
        self.L.week = 9; self.t.cap.paid_week = 9
        self.old.contract = Contract(2,[6,15],earned_base=3)
        with patch.object(VM.MK.VAL,'value_player',return_value=self.quote):
            read=self.read(8.)
            expected=TR.player_asset(self.L,self.t,self.old,None,None)
        self.assertEqual(read['released_asset_value'],expected['trade_value'])
        self.old.contract = Contract(1,[6],earned_base=6)
        self.t.cap.paid_week = 18
        self.assertEqual(self.read(8.)['released_asset_value'],0)


if __name__ == '__main__': unittest.main()
