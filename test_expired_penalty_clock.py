import unittest
from unittest.mock import patch
import numpy as np
import game as G


class ExpiredPenaltyClockTests(unittest.TestCase):
    def run_boundary(self, quarter=4, stale=True, seconds=0):
        wall = 1800 if quarter == 2 else 0
        dr = G.Drive({}, {}, 31, wall + seconds, quarter, -10, np.random.default_rng(1))
        dr.down, dr.togo = 4, 5
        dr.log = [dict(type='penalty'), dict(type='pass', complete=False)]
        dr.untimed = stale is not None
        dr.untimed_at = 1 if stale else len(dr.log)
        class ReachedDecision(Exception):
            pass
        with patch.object(G, 'Drive', return_value=dr), patch.object(G, 'end_of_half_plan', side_effect=ReachedDecision), patch.dict(G.LAST_KICKOFF, {}, clear=True):
            try:
                G.run_drive({}, {}, 31, wall + seconds, quarter, -10,
                            np.random.default_rng(1), None, None, None, None,
                            half_end=wall if quarter == 2 else None)
                reached = False
            except ReachedDecision:
                reached = True
        return dr, reached

    def test_consumed_flag_cannot_allow_another_snap_at_expiration(self):
        for quarter in (2, 4, 5):
            with self.subTest(quarter=quarter):
                dr, reached = self.run_boundary(quarter)
                self.assertFalse(reached)
                self.assertEqual(dr.result, 'End of half')
                self.assertEqual(dr.points, 0)

    def test_valid_untimed_down_remains_available(self):
        for quarter in (2, 4, 5):
            with self.subTest(quarter=quarter):
                dr, reached = self.run_boundary(quarter, stale=False)
                self.assertTrue(reached)
                self.assertFalse(dr.untimed)

    def test_consumed_flag_with_time_remaining_does_not_end_drive(self):
        dr, reached = self.run_boundary(seconds=2)
        self.assertTrue(reached)
        self.assertFalse(dr.untimed)

    def test_expiration_without_flag_still_ends_drive(self):
        dr, reached = self.run_boundary(stale=None)
        self.assertFalse(reached)
        self.assertEqual(dr.result, 'End of half')


if __name__ == '__main__':
    unittest.main()
