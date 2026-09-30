"""Lower occurrence must retain injury type/duration and risk relationships."""
import unittest
from unittest.mock import patch
import numpy as np
import health as H
import plays


class InjuryFrequencyTests(unittest.TestCase):
    def test_occurrence_is_thirty_percent_lower_across_positions_and_workloads(self):
        for pos in H.INJURY_SHARE:
            for cond in (100, 85, 65, 40):
                for durable in (60, 90):
                    p = dict(pid='p', injury_rating=durable, tough_rating=durable)
                    args = (p, pos, 1.3, plays.rate, cond, .4)
                    current = H.injury_chance(*args)
                    with patch.object(H, '_RULED_OUT_SHARE', .0146):
                        previous = H.injury_chance(*args)
                    self.assertAlmostEqual(current, previous * .7)

    def test_type_and_duration_are_identical_when_an_injury_occurs(self):
        for seed in range(500):
            # Force the same occurrence gate, then compare every duration/type draw.
            with patch.object(H, 'injury_chance', return_value=1):
                before = H.roll_injury({'pid': 'p'}, 'WR', 1, np.random.default_rng(seed), plays.rate)
                with patch.object(H, '_RULED_OUT_SHARE', .0146):
                    after = H.roll_injury({'pid': 'p'}, 'WR', 1, np.random.default_rng(seed), plays.rate)
            self.assertEqual(before, after)
            self.assertEqual(after['ir_eligible'], after['weeks_out'] >= 4)
            self.assertEqual(after['season_ending'], after['weeks_out'] >= 8)

    def test_fatigue_durability_and_jadedness_still_affect_risk(self):
        p = dict(pid='p', injury_rating=90, tough_rating=90)
        fresh = H.injury_chance(p, 'HB', 1, plays.rate)
        self.assertGreater(H.injury_chance(p, 'HB', 1, plays.rate, 70), fresh)
        self.assertGreater(H.injury_chance(p, 'HB', 1, plays.rate, 100, .8), fresh)
        frail = dict(p, injury_rating=60, tough_rating=60)
        self.assertGreater(H.injury_chance(frail, 'HB', 1, plays.rate), fresh)


if __name__ == '__main__': unittest.main()
