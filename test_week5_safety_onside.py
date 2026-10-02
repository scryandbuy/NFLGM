import unittest
import numpy as np
import game as G
import ticker
from test_game_clock_decisions import ClockDecisions


class WeekFiveTests(unittest.TestCase):
    def test_safety_stops_at_whistle_and_ends_at_goal(self):
        for live in (False, True):
            for kind in ('sack', 'run'):
                h = ClockDecisions(); h.setUp()
                dr, _, tos = h.drive([dict(type=kind, yards=-7)], start=93,
                    clock=299, quarter=4, wall=None, diff=28, own=3, other=3, live=live)
                self.assertEqual((dr.result, dr.points, dr.clock), ('Safety', -2, 293))
                self.assertEqual(ticker.offensive_drive_end(dr), 100)
                self.assertFalse(dr.clock_running)
                self.assertEqual(tos.left, {'home': 3, 'away': 3})
                # Original drive began at own13 before the earlier holding.
                dr.start = 87
                self.assertEqual(dr.start - ticker.offensive_drive_end(dr), -13)

    def test_reported_onside_situation(self):
        for aggression in (0, .5, 1):
            coach = dict(fourth_down=aggression, adjust_willingness=aggression)
            self.assertTrue(G._onside_call(134, 23, 3, coach, np.random.default_rng(1)))

    def test_deep_kick_with_timeouts_and_one_score(self):
        self.assertFalse(G._onside_call(134, 7, 3, None, np.random.default_rng(1)))

    def test_no_desperation_when_ahead_or_decided(self):
        for clock, deficit in ((134, 0), (134, -7), (30, 42)):
            self.assertFalse(G._onside_call(clock, deficit, 3, None, np.random.default_rng(1)))


if __name__ == '__main__': unittest.main()
