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

    def test_penalty_rounding_explains_exact_spots_without_changing_save(self):
        import copy
        log = [dict(type='run', yardline=52.5, yards=0),
               dict(type='penalty', penalty='Unnecessary Roughness',
                    yards=15, on_offense=False, auto_first=True)]
        original = copy.deepcopy(log)
        dr = SimpleNamespace(log=log, start=52.5, yardline=37.5,
                             result='End of half', points=0, quarter=4)
        rows = ticker.write_game(SimpleNamespace(player=lambda pid: None),
                                 {'drives': [('home', dr)]}, 'GB', 'PIT')
        text = rows[0]['lines'][1]['text']
        self.assertIn('15 yards', text)
        self.assertIn('GB 47.5 to PIT 37.5', text)
        self.assertEqual(log, original)
        direct = dict(log[1], enforcement_start=60, enforcement_end=45)
        self.assertNotIn('Enforced from', ticker.play_line(
            SimpleNamespace(player=lambda pid: None), direct, 'GB', 'PIT')['text'])


if __name__ == '__main__':
    unittest.main()
