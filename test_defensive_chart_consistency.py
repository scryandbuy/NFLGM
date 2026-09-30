"""Every club's highlighted defensive chart follows its on-field role plan."""

import unittest

import defense_roles as DR
import targets as TG
import views_club as VC
from session import Session


class DefensiveChartConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session.new('GB', seed=23)

    def test_all_clubs_and_packages_show_assigned_starters(self):
        s = self.session
        for abbr, team in s.L.teams.items():
            front = DR.coach_front(team.gm)
            pins = getattr(team, 'depth_pins', None) or {}
            depth = {pos: sorted(men, key=lambda p: -TG.position_score(
                p.ratings, pos, team.scheme)) for pos, men in team.depth.items()}
            for package in DR.PACKAGE_NAMES:
                with self.subTest(team=abbr, front=front, package=package):
                    expected = {row['player'].pid for row in DR.assign(
                        depth, front, package, pins) if row['player'] is not None}
                    chart = VC.depth(s, s.L, abbr, package)
                    selected = {p['pid'] for col in chart['sides']['defense']
                                for p in col['slots'] if p['start']}
                    self.assertEqual(selected, expected)
                    self.assertEqual(len(selected), 11)
                    self.assertEqual(chart['defense_shape'],
                                     DR.shape_label(front, package))


if __name__ == '__main__':
    unittest.main()
