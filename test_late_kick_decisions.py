"""Late short tying kicks and the live kicking-unit exchange."""
import unittest
from unittest.mock import patch
import numpy as np
import game as G
import test_game_clock_decisions as fixtures

class LateKicks(unittest.TestCase):
    def choices(self, aggression=.5, rate=.7, diff=-3, distance=7):
        return [G.fourth_down_decision(18, distance, diff, 60,
            np.random.default_rng(i), aggression=aggression, kicker={},
            rate_fn=lambda *a: rate, timeout_edge=-2, is_home=1)
            for i in range(1000)]

    def test_short_tying_kick_is_strong_default_with_coach_variation(self):
        counts = [self.choices(aggression=a).count('go') for a in (0,.5,1)]
        self.assertTrue(all(0 < n < 20 for n in counts), counts)
        self.assertLess(counts[0], counts[-1])

    def test_weaker_kicker_increases_willingness_to_go(self):
        self.assertGreater(self.choices(rate=.3).count('go'),
                           self.choices(rate=.9).count('go'))

    def test_touchdown_needed_is_not_treated_as_tying_kick(self):
        self.assertGreater(self.choices(diff=-4).count('go'), 900)

    def test_hurried_unit_reaches_field_in_live_and_batch(self):
        for live in (False, True):
            h = fixtures.ClockDecisions(); h.setUp()
            dr, _, tos = h.drive([dict(type='complete', yards=3)], start=22,
                clock=1818, diff=7, own=0, other=3, down=3, live=live)
            kicks = [p for p in dr.log if p['type'] == 'field_goal']
            self.assertEqual(len(kicks), 1)
            self.assertEqual(kicks[0]['clock'], 1802)
            self.assertEqual(dr.clock, 1800)
            self.assertEqual(tos.left['home'], 0)

    def test_long_live_play_cannot_create_time_for_exchange(self):
        h = fixtures.ClockDecisions(); h.setUp()
        with patch.object(G, 'live_play_seconds', return_value=12.):
            dr, _, _ = h.drive([dict(type='complete', yards=3)], start=22,
                clock=1818, diff=7, own=0, other=3, down=3)
        self.assertFalse(any(p['type'] == 'field_goal' for p in dr.log))
        self.assertEqual(dr.clock, 1800)

if __name__ == '__main__': unittest.main()
