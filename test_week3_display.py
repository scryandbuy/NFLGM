"""Display arithmetic stays consistent without changing raw game results."""
import copy
import re
import unittest
from types import SimpleNamespace as NS
import numpy as np
import game
import ticker
import gameday
import kick_returns


class Week3Display(unittest.TestCase):
    league = NS(player=lambda pid: None)

    def test_half_yard_penalty_movement_is_exact(self):
        for yardline in (65.5, 60.5, 44.5, 19.5):
            self.assertEqual(ticker._spot_yards(yardline) - ticker._spot_yards(yardline - 5), 5)
            self.assertEqual(gameday._spot(yardline, 'GB', 'CHI'), ticker._spot(yardline, 'GB', 'CHI'))
        self.assertEqual(ticker._spot(65.5, 'GB', 'CHI'), 'GB 34')
        self.assertEqual(ticker._spot(60.5, 'GB', 'CHI'), 'GB 39')

    def test_field_goal_distance_matches_displayed_spot_without_mutation(self):
        for y in (19.5, 20.5, 12.49, 12.51):
            p = dict(type='field_goal', distance=y + 17, yardline=y, made=True)
            before = copy.deepcopy(p)
            text = ticker.play_line(self.league, p, 'GB', 'CHI')['text']
            self.assertTrue(text.startswith(f'{ticker._spot_yards(y) + 17}-yard'), text)
            self.assertEqual(p, before)

    def test_overwritten_return_distance_is_reconstructed_from_endpoints(self):
        p = dict(type='punt', origin=83, yardline=83, gross=54.4,
                 display_gross=54, ret=5.6, display_ret=6, how='return',
                 return_start=70.9, new_yardline=65.3)
        before = copy.deepcopy(p)
        text = ticker.play_line(self.league, p, 'CHI', 'GB')['text']
        self.assertIn('Punt, 54 yards, returned 6 yards', text)
        p['new_yardline'] = 65.5
        text = ticker.play_line(self.league, p, 'CHI', 'GB')['text']
        self.assertIn('Punt, 54 yards, returned 5 yards', text)
        self.assertEqual(p['display_ret'], before['display_ret'])

    def test_real_return_pipeline_and_return_penalties_reconcile(self):
        rng = np.random.default_rng(193)
        returns = 0
        for i in range(500):
            p = game.punt(60.5 + i % 25, {}, {'pid': 'returner'}, rng, lambda *a: .7)
            if p.get('blocked') or p.get('touchback') or not p.get('return_start'):
                continue
            returns += 1
            if i % 2:
                kick_returns.enforce_return_flag(p, dict(yards=10, penalty='Holding'))
            before = copy.deepcopy(p)
            text = ticker.play_line(self.league, p, 'GB', 'CHI')['text']
            gross = int(re.search(r'Punt, (\d+) yards', text)[1])
            match = re.search(r'returned (\d+) yard', text)
            ret = int(match[1]) if match else 0
            end = p['return_start'] - p['ret'] if p.get('penalty') else p['new_yardline']
            self.assertEqual(ticker._spot_yards(p['origin']) - gross + ret,
                             100 - ticker._spot_yards(end))
            self.assertEqual(p, before)
        self.assertGreater(returns, 40)


if __name__ == '__main__':
    unittest.main()
