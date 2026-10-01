"""Defensive scores keep the right scorer and offensive drive yardage."""
import unittest
from types import SimpleNamespace as NS

import gameday
import ticker


class DefensiveReturnDisplayTests(unittest.TestCase):
    def setUp(self):
        names = {'qb': 'Alex North', 'wr': 'Eli West', 'cb': 'Milo Vale',
                 'rb': 'Tariq Rivers', 'lb': 'Noah Stone'}
        self.league = NS(player=lambda pid: NS(name=names[pid]) if pid in names else None)

    def test_pick_six_is_a_defensive_score_in_ticker_and_replay(self):
        play = dict(type='interception', passer='qb', target='wr', by='cb',
                    yardline=60, air=10, ret=50, defensive_td=True,
                    touchdown=True, clock=1850, down=2, ydstogo=8)
        line = gameday.write_play(self.league, play, 'qb', 'GB', 'DEN')
        self.assertIn('INTERCEPTED by Vale', line['text'])
        self.assertIn('TOUCHDOWN, DEN', line['text'])
        self.assertEqual(line['kind'], 'score')
        self.assertTrue(line['td'])
        self.assertTrue(line['defensive_td'])
        self.assertEqual(line['scoring_side'], 'defense')

    def test_scoop_and_score_does_not_read_as_offensive_rushing_td(self):
        play = dict(type='run', carrier='rb', yards=5, yardline=60,
                    fumble=True, fumble_lost=True, fumble_recovered_by='lb',
                    ret=55, defensive_td=True, touchdown=True,
                    clock=900, down=3, ydstogo=7)
        line = gameday.write_play(self.league, play, 'qb', 'GB', 'DEN')
        self.assertIn('FUMBLE, recovered by Stone (DEN)', line['text'])
        self.assertIn('Returned 55 yards. TOUCHDOWN, DEN', line['text'])
        self.assertNotIn('Rivers runs it in', line['text'])
        self.assertEqual(line['scoring_side'], 'defense')

    def test_return_yards_do_not_become_offensive_drive_yards(self):
        fumble = dict(type='run', fumble_lost=True, yardline=60, yards=5,
                      return_start=55, end_spot=100, defensive_td=True)
        drive = NS(result='Defensive touchdown', start=60, yardline=100,
                   log=[fumble])
        self.assertEqual(ticker.offensive_drive_end(drive), 55)
        interception = dict(type='interception', yardline=42, air=15, ret=73,
                            defensive_td=True)
        drive.log = [interception]
        self.assertEqual(ticker.offensive_drive_end(drive), 42)


if __name__ == '__main__':
    unittest.main()
