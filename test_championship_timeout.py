import unittest
from types import SimpleNamespace
from unittest.mock import patch
import game
import ticker
from test_game_clock_decisions import ClockDecisions


class ChampionshipTimeout(unittest.TestCase):
    def test_scoring_safeguard_cannot_override_protecting_clock(self):
        for live in (False, True):
            h = ClockDecisions(); h.setUp()
            # A low-value future shot can remain in the planner even when the
            # failed-third-down decision correctly elects to protect the clock.
            with patch.object(game, 'end_of_half_plan', return_value={
                    'choice': 'shot', 'hurry': False}):
                dr, _, tos = h.drive([dict(type='sack', yards=-9)],
                    start=79, clock=1833, diff=13, own=3, other=3,
                    down=3, live=live)
            self.assertEqual(tos.left['home'], 3)
            self.assertFalse(any(p['type'] == 'timeout' and p['side'] == 'home'
                                 for p in dr.log))

    def test_interception_return_singular(self):
        text = ticker.play_line(SimpleNamespace(player=lambda pid: None),
            dict(type='interception', ret=1), 'PIT', 'GB')['text']
        self.assertIn('returned 1 yard.', text)


if __name__ == '__main__':
    unittest.main()
