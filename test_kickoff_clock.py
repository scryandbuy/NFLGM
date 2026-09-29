import unittest
from unittest.mock import patch

import numpy as np

import game


class KickoffClockTest(unittest.TestCase):
    def test_return_runs_clock_but_touchback_does_not(self):
        self.assertEqual(game.kickoff_clock(3600, {'touchback': False}), 3594)
        self.assertEqual(game.kickoff_clock(3600, {'touchback': True}), 3600)

    def test_return_stops_at_period_boundary(self):
        self.assertEqual(game.kickoff_clock(2703, {'touchback': False}), 2700)
        self.assertEqual(game.kickoff_clock(1804, {'touchback': False}), 1800)
        self.assertEqual(game.kickoff_clock(4, {'touchback': False}), 0)

    def test_return_that_ends_half_does_not_create_empty_drive(self):
        kicks = iter(({'touchback': True, 'new_yardline': 65},
                      {'touchback': False, 'new_yardline': 70}))
        calls = []

        def fake_drive(offense, defense, start, clock, quarter, score_diff, rng,
                       *args, **kwargs):
            calls.append(clock)
            drive = game.Drive(offense, defense, start, clock, quarter, score_diff, rng)
            drive.clock = 1804
            drive.result = 'Touchdown'
            drive.points = 7
            if False:
                yield None
            return drive

        with patch.object(game, 'kickoff_booked', side_effect=lambda *a, **kw: next(kicks)), \
             patch.object(game, 'drive_steps', side_effect=fake_drive), \
             patch.object(game.W, 'draw', return_value=game.W.CLEAR):
            gen = game.game_steps({}, {}, np.random.default_rng(1), None, None, None, None)
            self.assertEqual(next(gen)[0], 'drive')
            self.assertEqual(next(gen)[0], 'halftime')
        self.assertEqual(calls, [3600])

    def test_scoring_drive_at_halftime_does_not_add_a_first_half_kickoff(self):
        kicks = []

        def fake_kick(*args, **kwargs):
            kicks.append(1)
            return {'touchback': True, 'new_yardline': 65}

        def fake_drive(offense, defense, start, clock, quarter, score_diff, rng,
                       *args, **kwargs):
            drive = game.Drive(offense, defense, start, clock, quarter, score_diff, rng)
            drive.clock = 1800
            drive.result = 'Touchdown'
            drive.points = 7
            if False:
                yield None
            return drive

        with patch.object(game, 'kickoff_booked', side_effect=fake_kick), \
             patch.object(game, 'drive_steps', side_effect=fake_drive), \
             patch.object(game.W, 'draw', return_value=game.W.CLEAR):
            gen = game.game_steps({}, {}, np.random.default_rng(1), None, None, None, None)
            self.assertEqual(next(gen)[0], 'drive')
            self.assertEqual(next(gen)[0], 'halftime')
        self.assertEqual(len(kicks), 1)


if __name__ == '__main__':
    unittest.main()
