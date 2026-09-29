"""Checks that personnel decisions follow the coach's actual roles."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import draft
import roster_construction as RC
import roster_needs as RN
import trades


class GM(SimpleNamespace):
    def shift(self, _team):
        return self


class Team:
    def __init__(self, front='4-3', offense='11', players=()):
        self.gm = GM(def_front=front, off_personnel=offense, box=0.5,
                     risk=0.5, patience=0.5, aggression=0.5, youth=0.5)
        self.scheme = None
        self.roster = list(players)

    def active(self):
        return self.roster

    @property
    def depth(self):
        depth = {}
        for p in self.roster:
            depth.setdefault(p.pos, []).append(p)
        return depth


def player(pos, n):
    return SimpleNamespace(pid=f'{pos}-{n}', pos=pos, ovr=78.0, ratings={})


class RosterNeedsTests(unittest.TestCase):
    def test_front_and_offense_change_the_roster_floor(self):
        four, four_groups = RN.roster_floors(Team('4-3', '11'))
        three, three_groups = RN.roster_floors(Team('3-4', '21'))
        self.assertEqual((four['DT'], four_groups['DL'], four_groups['LB']), (4, 10, 4))
        self.assertEqual((three['DT'], three_groups['DL'], three_groups['LB']), (3, 9, 5))
        self.assertEqual((four['FB'], three['FB']), (0, 0))

    def test_one_player_cannot_cover_two_starting_jobs(self):
        team = Team('3-4', players=[player('LEDG', 1), player('REDG', 1),
                                    player('DT', 1), player('MIKE', 1), player('WILL', 1)])
        report = RN.assess(team)
        self.assertIn('34LE', report['uncovered'])
        self.assertIn('34RE', report['uncovered'])
        self.assertEqual(report['needs']['DT'], 1.0)
        self.assertEqual(report['needs']['K'], 1.0)
        self.assertGreater(RN.move_gain(team, player('DT', 2)), 0.0)

    def test_draft_and_cutdown_read_the_same_needs_and_floors(self):
        team = Team('3-4', '21', [player('QB', 1), player('HB', 1), player('HB', 2)])
        self.assertNotIn('FB', RN.assess(team)['uncovered'])
        self.assertEqual(draft.needs(team, {})['FB'], 0.0)
        floors, groups = RN.roster_floors(team)
        pool = [dict(pid=f'{pos}-{i}', pos=pos, ovr=75.0 + i, age=25, dead=0)
                for pos in RN.POSITIONS for i in range(5)]
        kept, counts = RC.allocate(pool, {}, team.gm, minimums=floors,
                                   group_minimums=groups)
        self.assertEqual(len(kept), 53)
        self.assertGreaterEqual(counts['DT'], 3)
        self.assertGreaterEqual(sum(counts.get(p, 0) for p in RN.GROUPS['DL']), 9)
        self.assertEqual(floors['FB'], 0)

    def test_trade_search_sees_an_empty_position(self):
        team = Team()
        league = SimpleNamespace(teams={'TST': team}, free_agents=[], week=0)
        with patch.object(trades, 'starter_bar', return_value={'QB': 80.0}):
            _, needs = trades.surplus_and_needs(league, team, {}, None)
        self.assertIn('QB', needs)


if __name__ == '__main__':
    unittest.main()
