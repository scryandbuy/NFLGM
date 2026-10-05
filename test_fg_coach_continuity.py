"""Coordinator consistency must not reverse a reliable kicker's advantage."""
import unittest
from unittest.mock import patch
import game as G
from plays import rate
from weather import Env


class FieldGoalCoachContinuity(unittest.TestCase):
    def kicker(self, noise=1., accuracy=90., power=95.):
        return dict(kick_acc_rating=accuracy, awareness_rating=accuracy,
                    kick_power_rating=power, st_noise=noise)

    def test_good_coordinator_does_not_reduce_high_probability_short_kick(self):
        with patch.object(G, 'ENV', Env()):
            neutral = G.kick_probability(25, self.kicker(), rate)
            self.assertEqual(neutral, .995)
            for noise in (.999999, .95, .85):
                self.assertGreaterEqual(G.kick_probability(25, self.kicker(noise), rate), neutral)
            self.assertLess(G.kick_probability(25, self.kicker(1.15), rate), neutral)

    def test_weather_distance_and_accuracy_still_matter_below_the_ceiling(self):
        with patch.object(G, 'ENV', Env()):
            clear = G.kick_probability(49, self.kicker(.95), rate)
            self.assertGreater(clear, G.kick_probability(54, self.kicker(.95), rate))
            self.assertGreater(clear, G.kick_probability(49, self.kicker(.95, accuracy=60.), rate))
            self.assertGreater(clear, G.kick_probability(49, self.kicker(1.15), rate))
        with patch.object(G, 'ENV', Env(wind=20, rain=.8, temp=25)):
            self.assertLess(G.kick_probability(49, self.kicker(.95), rate), clear)

    def test_unclipped_kicks_keep_existing_probability(self):
        with patch.object(G, 'ENV', Env()):
            for noise in (.85, .95, 1., 1.15):
                kicker = self.kicker(noise)
                for distance in (44, 49, 54, 59):
                    base = G.fg_probability(distance, kicker, rate)
                    expected = base if noise == 1 else min(.99, max(.02, .5 + (base - .5) / noise))
                    self.assertAlmostEqual(G.kick_probability(distance, kicker, rate), expected)


if __name__ == '__main__':
    unittest.main()
