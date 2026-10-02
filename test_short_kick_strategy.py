"""Focused checks for deliberate short kickoffs and staff choices."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import events
import game
import staff
import ticker


def rate(player, weights):
    player = player or {}
    return sum(player.get(key, 70) * weight for key, weight in weights.items()) / (100 * sum(weights.values()))


class ShortKickTests(unittest.TestCase):
    def setUp(self):
        self.kicker = {'pid': 'k', 'kick_power_rating': 96, 'kick_acc_rating': 90}
        self.returner = {'pid': 'kr', 'kick_ret_rating': 80, 'speed_rating': 80, 'juke_move_rating': 80}
        self.coverage = [dict(pid=f'c{i}', tackle_rating=80, speed_rating=80) for i in range(10)]
        self.blockers = [dict(pid=f'b{i}', run_block_rating=70, speed_rating=70) for i in range(10)]

    def kicks(self, bias, count=4000):
        rng = np.random.default_rng(344)
        with patch.object(events, 'fumble_check', return_value=None):
            return [game.kickoff(self.returner, rng, rate, kicker=self.kicker,
                                 kicking=self.coverage, receiving=self.blockers,
                                 short_kick_bias=bias) for _ in range(count)]

    def test_short_kicks_lower_touchbacks_and_leave_a_return_risk(self):
        deep = self.kicks(None)
        mixed = self.kicks(0.0)
        short = [kick for kick in mixed if kick.get('short_kick')]
        self.assertGreater(len(short), 700)
        self.assertLess(sum(k['touchback'] for k in mixed), sum(k['touchback'] for k in deep))
        self.assertTrue(all(not k['touchback'] for k in short))
        own_spots = [100 - k['new_yardline'] for k in short]
        self.assertLess(np.mean(own_spots), 35)
        self.assertTrue(any(spot > 35 for spot in own_spots))

    def test_staff_and_coverage_change_strategy(self):
        good = SimpleNamespace(staff={'st': SimpleNamespace(rating=85, disgruntled=0,
                                                            effective=lambda: 85, specialty='coverage units')})
        poor = SimpleNamespace(staff={'st': SimpleNamespace(rating=45, disgruntled=0,
                                                            effective=lambda: 45, specialty='kicker management')})
        strong_bias = staff.short_kick_bias(good)
        weak_bias = staff.short_kick_bias(poor)
        self.assertGreater(strong_bias, weak_bias)
        self.assertGreater(sum(k.get('short_kick', False) for k in self.kicks(strong_bias)),
                           sum(k.get('short_kick', False) for k in self.kicks(weak_bias)))
        good_coverage = self.kicks(0.0)
        self.coverage = [dict(pid=f'c{i}', tackle_rating=45, speed_rating=45) for i in range(10)]
        weak_coverage = self.kicks(0.0)
        self.assertGreater(sum(k.get('short_kick', False) for k in good_coverage),
                           sum(k.get('short_kick', False) for k in weak_coverage))

    def test_live_kick_uses_staff_plan_and_marks_short_kick(self):
        kicking = {'k': self.kicker, 'kr': self.returner}
        receiving = {'kr': self.returner}
        state = SimpleNamespace(staff_fx={'short_kick_bias': 0.12}, out=set())
        with patch.object(game, 'kickoff_booked', return_value={'touchback': False}) as booked:
            game.kickoff_for(kicking, receiving, state, None, np.random.default_rng(4), rate, None)
        self.assertEqual(booked.call_args.kwargs['short_kick_bias'], 0.12)
        # The play log can tell the user why this kickoff was returned.
        text = ticker.play_line(None, dict(type='kickoff', short_kick=True, ret=18,
                                            new_yardline=70), 'GB', 'DET')['text']
        self.assertIn('Short kickoff', text)


if __name__ == '__main__':
    unittest.main()
