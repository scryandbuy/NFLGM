"""Week 9 NY at GB: keep the recovery chance when drive estimates hit zero."""
import unittest
from unittest.mock import patch

import numpy as np
import game as G


class LastChanceOnsideTests(unittest.TestCase):
    def test_reported_nine_point_deficit_with_one_timeout(self):
        for aggression in (0, .5, 1):
            coach = dict(fourth_down=aggression, adjust_willingness=aggression)
            with self.subTest(aggression=aggression):
                self.assertTrue(G._onside_call(52, 9, 1, coach, None))

    def test_shorter_clock_does_not_abandon_two_score_recovery(self):
        for seconds in (30, 45, 51, 52, 57, 58, 60):
            for deficit in (9, 10, 16):
                with self.subTest(seconds=seconds, deficit=deficit):
                    self.assertTrue(G._onside_call(seconds, deficit, 1, {}, None))

    def test_deep_kick_remains_available_with_time_and_stops(self):
        for seconds, deficit in ((134, 7), (123, 15), (300, 9)):
            with self.subTest(seconds=seconds, deficit=deficit):
                self.assertFalse(G._onside_call(seconds, deficit, 3, {}, None))

    def test_no_desperation_when_tied_ahead_expired_or_out_of_reach(self):
        for seconds, deficit in ((52, 0), (52, -7), (0, 9), (52, 31)):
            with self.subTest(seconds=seconds, deficit=deficit):
                self.assertFalse(G._onside_call(seconds, deficit, 1, {}, None))

    def test_game_loop_attempts_onside_after_failed_conversion(self):
        calls = 0
        kick_after_score = None

        def drive(off, defense, start, clock, quarter, diff, rng, *args, **kwargs):
            nonlocal calls, kick_after_score
            calls += 1
            dr = G.Drive(off, defense, start, clock, quarter, diff, rng)
            if calls == 1:
                dr.result, dr.points, dr.clock = 'Touchdown', 33, 1800
            elif calls == 2:
                # The score is already 33-24 after the unsuccessful try.
                dr.result, dr.points, dr.clock = 'Touchdown', 24, 52
                kwargs['timeouts'].left[kwargs['pos']] = 1
            else:
                kick_after_score = dict(G.LAST_KICKOFF.get('r', {}))
                dr.result, dr.points, dr.clock = 'End of half', 0, 0
            if False:
                yield
            return dr

        with patch.object(G, 'drive_steps', side_effect=drive), \
                patch.object(G, 'kickoff_booked', return_value=dict(touchback=True, new_yardline=65)), \
                patch.dict(G.LAST_KICKOFF, {}, clear=True), \
                patch.object(G.W, 'draw', return_value=G.W.CLEAR):
            list(G.game_steps({}, {}, np.random.default_rng(1), None, None, None, None))
        self.assertIsNotNone(kick_after_score)
        self.assertTrue(kick_after_score.get('onside'))


if __name__ == '__main__':
    unittest.main()
