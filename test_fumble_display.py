"""Fumble narration follows exact field movement without changing statistics."""
import copy
import unittest
from types import SimpleNamespace as NS
import ticker
import game

class FumbleDisplay(unittest.TestCase):
    league = NS(player=lambda pid: None)

    def test_fractional_sack_matches_new_possession(self):
        p = dict(type='sack', yardline=11.4, yards=-4.2, carrier_yards=-4.2,
                 fumble=True, fumble_lost=False, fumble_dead_spot=15.6,
                 fumble_advancement_restricted=True)
        before = copy.deepcopy(p)
        text = ticker.play_line(self.league, p, 'BUF', 'GB')['text']
        self.assertIn('loss of 5', text)
        self.assertEqual(ticker._spot(100-15.6, 'GB', 'BUF'), 'GB 16')
        self.assertEqual(p, before)

    def test_exact_movement_and_possession_flip_across_field(self):
        for off, defense in [('BUF','GB'), ('GB','BUF')]:
            for spot in (11.4, 11.5, 49.5, 50.5, 85.4):
                for gain in (-4.2, -4.5, 3.2, 3.5):
                    dr = game.Drive({}, {}, spot, 100, 4, 0, None)
                    game._advance(dr, gain, exact=True)
                    shown = ticker._display_gain(spot, gain, off, defense, exact=True)
                    self.assertEqual(shown, ticker.display_drive_yards(spot, dr.yardline, off, defense))
                    self.assertEqual(ticker._spot(dr.yardline, off, defense),
                                     ticker._spot(100-dr.yardline, defense, off))

    def test_backward_loose_ball_has_separate_spot(self):
        p = dict(type='sack', yardline=90, carrier_yards=-4, yards=-6,
                 fumble=True, fumble_lost=False, fumble_dead_spot=96,
                 fumble_advancement_restricted=True)
        text = ticker.play_line(self.league,p,'BUF','GB')['text']
        self.assertIn('loss of 4', text)
        self.assertIn('Ball at BUF 4.', text)

    def test_ordinary_play_still_uses_engine_rounded_gain(self):
        self.assertEqual(ticker._display_gain(11.4,-4.2,'BUF','GB'), -4)

if __name__ == '__main__': unittest.main()
