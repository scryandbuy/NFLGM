"""Weather affects loose-ball incidence, preserving security and recovery."""
import unittest

import numpy as np
import events as E


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


class QBFumbleRiskTests(unittest.TestCase):
    def check(self, event, rolls, security=.7, **kwargs):
        return E.fumble_check({'pid': 'QB'}, event, Rolls(*rolls),
                              lambda player, weights: security, **kwargs)

    def test_wet_ball_can_fumble_when_dry_ball_is_retained(self):
        for event, base in E.FUMBLE_RATE.items():
            with self.subTest(event=event):
                self.assertIsNone(self.check(event, [base * 1.15]))
                wet = self.check(event, [base * 1.15, .9, .2], env_mult=1.3)
                self.assertTrue(wet['fumble'])
                self.assertFalse(wet['lost'])
                self.assertIsNone(self.check(event, [base * 1.31], env_mult=1.3))

    def test_weather_does_not_change_conditional_recovery_or_forcing(self):
        for event, loss_share in E.FUMBLE_LOST.items():
            for recovery_roll in (loss_share - .01, loss_share + .01):
                dry = self.check(event, [0., recovery_roll, .8])
                wet = self.check(event, [0., recovery_roll, .8], env_mult=1.3)
                self.assertEqual(dry, wet)
                self.assertEqual(dry['lost'], recovery_roll < loss_share)
                self.assertFalse(dry['forced'])

    def test_security_hit_power_and_staff_still_distinguish_risk(self):
        for event in ('run', 'scramble', 'sack'):
            base = E.FUMBLE_RATE[event]
            self.assertIsNotNone(self.check(event, [base, .9, .9], security=.5))
            self.assertIsNone(self.check(event, [base], security=.9))
            self.assertIsNotNone(self.check(event, [base, .9, .9], hit_power=.9))
            self.assertIsNone(self.check(event, [base], hit_power=.5))
            self.assertIsNone(self.check(event, [base * .95], rate_mult=.9))
            self.assertIsNotNone(self.check(event, [base * .95, .9, .9]))

    def test_dry_rng_stream_and_results_match_previous_model(self):
        for event, base in E.FUMBLE_RATE.items():
            actual_rng = np.random.default_rng(9730)
            old_rng = np.random.default_rng(9730)
            for _ in range(5000):
                old = None
                probability = base * (1. + 2.4 * (.7 - .65)) * (1. + 1.3 * (.82 - .7)) * .9
                if old_rng.random() < probability:
                    old = dict(fumble=True, lost=bool(old_rng.random() < E.FUMBLE_LOST[event]),
                               forced=old_rng.random() < E.FORCED_SHARE, by='QB')
                actual = E.fumble_check({'pid': 'QB'}, event, actual_rng,
                    lambda player, weights: .65, hit_power=.82, rate_mult=.9)
                self.assertEqual(actual, old)
            self.assertEqual(actual_rng.random(), old_rng.random())


if __name__ == '__main__':
    unittest.main()
