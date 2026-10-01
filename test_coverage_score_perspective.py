"""The drive's offense-relative score reaches the defensive coordinator."""
import unittest

import numpy as np

import coverage_call as CC
from season import _deps


class CoverageScorePerspectiveTests(unittest.TestCase):
    def test_late_coverage_protects_defensive_lead_only(self):
        for score, expected in ((-10, 'no_chunk'), (10, 'base'), (0, 'base')):
            with self.subTest(offense_lead=score):
                self.assertEqual(CC.pick_job(2, 8, score, 180, '11',
                                             np.random.default_rng(1)), expected)

    def test_early_game_and_third_down_keep_situation_priority(self):
        self.assertEqual(CC.pick_job(2, 8, -10, 900, '11',
                                     np.random.default_rng(1)), 'base')
        self.assertEqual(CC.pick_job(3, 5, -10, 180, '11',
                                     np.random.default_rng(1)), 'sticks')

    def test_season_caller_preserves_offense_relative_score(self):
        _, call_defense = _deps()
        defense = {'db': [], 'lb': []}
        for score, expected in ((-10, 'no_chunk'), (10, 'base')):
            with self.subTest(offense_lead=score):
                call = call_defense({'personnel': '11'}, 2, 8,
                                    np.random.default_rng(1), 50,
                                    defense=defense, rate_fn=lambda p, w: .7,
                                    score_diff=score, secs_left=180)
                self.assertEqual(call['job'], expected)
                self.assertIn(call['coverage'], CC.JOBS[expected])


if __name__ == '__main__':
    unittest.main()
