"""Late third-and-long preserves the caller's chance to throw for a first."""
import unittest
from unittest.mock import patch

import numpy as np

import events
import game
import schemes


class LateLeadPlaycallingTests(unittest.TestCase):
    def capture(self, down=3, distance=8, score=7, clock=180, spot=60, plan_bias=0):
        class Captured(Exception):
            pass
        original = game.Drive
        class Situation(original):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.down, self.togo = down, distance
        observed = {}
        def call(down, distance, margin, spot, rng, secs_left=None, lean=None, **kw):
            observed.update(lean=lean or {}, probability=schemes.pass_rate(
                down, distance, margin, spot, '11', (lean or {}).get('pass_bias', 0), secs_left))
            raise Captured
        off = dict(qb={'pid': 'qb'}, rb={'pid': 'hb'}, wr=[], ol=[])
        with patch.object(game, 'Drive', Situation), \
             patch.object(game, 'offensive_leans', return_value={'pass_bias': plan_bias}), \
             patch.object(events, 'penalty_check', return_value=None):
            with self.assertRaises(Captured):
                game.run_drive(off, {}, spot, clock, 4, score,
                               np.random.default_rng(1), None, call, None,
                               lambda *a: .7)
        return observed

    def test_third_and_long_preserves_clock_table(self):
        row = self.capture()
        self.assertGreater(row['probability'], .65)
        self.assertAlmostEqual(row['probability'], schemes.pass_rate(3, 8, 7, 60, '11', 0, 180))

    def test_early_down_clock_burning_behavior_is_preserved(self):
        row = self.capture(down=1, distance=10)
        self.assertAlmostEqual(row['probability'], schemes.pass_rate(1, 10, 7, 60, '11', -3.5, 180))

    def test_trailing_two_minute_drill_keeps_urgency(self):
        row = self.capture(score=-7, clock=110)
        self.assertGreaterEqual(row['probability'], .95)

    def test_coachs_saved_pass_preference_still_reaches_caller(self):
        row = self.capture(plan_bias=.1)
        self.assertAlmostEqual(row['probability'], schemes.pass_rate(3, 8, 7, 60, '11', .1, 180))


if __name__ == '__main__':
    unittest.main()
