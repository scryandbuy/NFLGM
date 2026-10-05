"""Decision-score continuity without removing roster or succession choices."""
import unittest
from unittest.mock import patch

import draft as D
import draft_plan as DP
import roster_needs as RN
from test_draft_planning import fixture, set_grade


class DraftPolicySmoothingTests(unittest.TestCase):
    def test_tiny_usage_change_cannot_add_a_whole_depth_opening(self):
        league, team = fixture()
        report = RN.assess(DP._Roster(team, DP.projected_players(team)), strict_roles=True)
        prospect = league.player('rookie-HB0')
        capacities, penalties = [], []
        for demand in (0.9999, 1.0001, 1.9999, 2.0001):
            observed = dict(report, package_demand=dict(report['package_demand'], HB=demand))
            with patch.object(RN, 'assess', return_value=observed):
                plan = DP.assess(league, 'MIN')
            capacities.append(plan['positions']['HB']['retention']['capacity'])
            penalties.append(DP.redundancy_penalty(plan, prospect, grade=75, gain=0))
        for low, high in ((0, 1), (2, 3)):
            self.assertLess(abs(capacities[high] - capacities[low]), .001)
            self.assertLess(abs(penalties[high] - penalties[low]), .1)
        self.assertGreater(capacities[2], capacities[0])

    def _board_scores(self, league, selection):
        # Expose the precise score, avoiding the economic chart's plateaus.
        with patch.object(D, 'slot_value', side_effect=lambda slot: -slot):
            return {p.pid: value for value, p in D.board(league, 'MIN', selection, {}, set())}

    def test_controlled_qb_room_has_no_round_three_score_cliff(self):
        league, _ = fixture()
        set_grade(league.player('QB0'), 95)
        set_grade(league.player('QB1'), 82)
        scores = {pick: self._board_scores(league, pick) for pick in (80, 95, 96, 97, 112, 128)}
        pid = 'rookie-QB0'
        self.assertGreater(scores[97][pid], scores[96][pid])
        self.assertLess(scores[97][pid] - scores[96][pid], 3)
        self.assertLess(scores[96][pid] - scores[95][pid], 3)
        self.assertGreater(scores[112][pid], scores[80][pid])
        self.assertEqual(scores[112][pid], scores[128][pid])
        # No penalty change is applied to the other available positions.
        for other in scores[96]:
            if league.player(other).pos != 'QB':
                self.assertEqual(scores[96][other], scores[97][other])

    def test_true_qb_vacancy_bypasses_reserve_spending_policy(self):
        league, team = fixture()
        team.roster = [p for p in team.roster if p.pos != 'QB']
        with patch.object(D, '_reserve_qb_penalty', side_effect=AssertionError('vacancy penalized')):
            early = self._board_scores(league, 80)
            later = self._board_scores(league, 112)
        self.assertEqual(early['rookie-QB0'], later['rookie-QB0'])

    def test_expiring_qb_succession_bypasses_reserve_spending_policy(self):
        league, team = fixture()
        starter = league.player('QB0')
        starter.age = 36
        starter.contract.years = 1
        team.roster = [p for p in team.roster if p.pos != 'QB' or p is starter]
        self.assertGreaterEqual(DP.assess(league, 'MIN')['positions']['QB']['future'], 6)
        with patch.object(D, '_reserve_qb_penalty', side_effect=AssertionError('succession penalized')):
            self._board_scores(league, 96)


if __name__ == '__main__':
    unittest.main()
