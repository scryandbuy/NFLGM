"""Regression cases from GB at NY, Week 4."""
import unittest
import numpy as np
import game as G
import plays as P


class WeekFourComebackTests(unittest.TestCase):
    def decision(self, seconds=181, deficit=-26, yardline=76, distance=4, seed=0):
        return G.fourth_down_decision(yardline, distance, deficit, seconds,
            np.random.default_rng(seed), kicker={}, rate_fn=P.rate, is_home=0)

    def test_late_possession_not_randomly_surrendered(self):
        self.assertEqual({self.decision(seed=s) for s in range(1000)}, {'go'})

    def test_useful_last_play_kick_preserved(self):
        self.assertEqual(self.decision(seconds=5, deficit=-3, yardline=10), 'field_goal')

    def test_ordinary_and_decided_games_can_punt(self):
        for seconds, deficit in ((2000, 0), (60, -26)):
            self.assertIn('punt', {self.decision(seconds=seconds, deficit=deficit, seed=s) for s in range(50)})

    def test_pace_is_gradual_and_crosses_quarter_boundary(self):
        self.assertEqual(G.comeback_pace(1800, -23, 3), 0)
        early = G.comeback_pace(1319, -20, 3)
        late = G.comeback_pace(1129, -23, 3)
        self.assertTrue(0 < early < late < 1)
        self.assertAlmostEqual(G.comeback_pace(900, -23, 3), G.comeback_pace(900, -23, 4))
        ordinary = G.play_seconds('run')
        accelerated = G.play_seconds('run', catchup=late)
        urgent = G.play_seconds('run', urgent=True)
        self.assertTrue(urgent < accelerated < ordinary)

    def test_no_unrequested_urgency(self):
        for seconds, diff, quarter in ((120, -23, 2), (1100, 23, 3), (1100, -7, 3), (60, -26, 4)):
            self.assertEqual(G.comeback_pace(seconds, diff, quarter), 0)
        self.assertEqual(G.play_seconds('run', timeout=True, catchup=1), 6)
        self.assertEqual(G.play_seconds('incomplete', catchup=1), G.play_seconds('incomplete'))


if __name__ == '__main__': unittest.main()
