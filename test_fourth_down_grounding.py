"""Accepted loss of down must finish a fourth-down possession."""
import unittest
from unittest.mock import patch

import numpy as np

import events
import game
import plays
import rosters
import schemes


class FourthDownGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.league = rosters.load_league()

    def drive(self, *, down=4, spot=50.0, clock=2900.0, quarter=1,
              half_end=None, decline=False, book=None, throwback=8.4):
        calls = {'flags': 0}

        def resolve(off, deff, off_call, def_call, yards_to_endzone, rng):
            if calls['flags']:
                return plays.resolve_play(off, deff, off_call, def_call, yards_to_endzone, rng)
            return dict(type='incomplete', yards=0.0, throwaway=True,
                        pressured=True, throwback=throwback, target=None)

        def flag(pen, out, call, rng, *args, **kwargs):
            if calls['flags']:
                return None
            calls['flags'] += 1
            return dict(penalty='Intentional Grounding', yards=10.0,
                        rule_yards=10.0, on_offense=True, auto_first=False,
                        nullifies=False)

        original_resolution = game._resolve_live_penalty

        def resolve_flag(dr, pen, out, call):
            if decline and pen['penalty'] == 'Intentional Grounding':
                return None
            return original_resolution(dr, pen, out, call)

        call_off = lambda d, di, sd, ytg, r, secs_left=None, **kw: schemes.call_offense(
            d, di, sd, ytg, r, secs_left=secs_left, **kw)
        call_def = lambda oc, d, di, r, ytg=50, **kw: schemes.call_defense(
            oc, d, di, r, yards_to_endzone=ytg, **kw)
        with (patch.object(events, 'penalty_check', return_value=None),
              patch.object(events, 'contextual_penalty', side_effect=flag),
              patch.object(game, '_resolve_live_penalty', side_effect=resolve_flag),
              patch.object(game, 'fourth_down_decision', return_value='go'),
              patch.object(game, 'end_of_half_plan', return_value=None)):
            dr = game.run_drive(self.league['HOU'], self.league['DEN'], spot,
                clock, quarter, -14, np.random.default_rng(1), resolve,
                call_off, call_def, plays.rate, aggression=1.0,
                book=book, start_state=(down, 1 if down == 4 else 10),
                pos='away', half_end=half_end)
        return dr, calls

    @staticmethod
    def snaps(dr):
        return [p for p in dr.log if p.get('type') in
                ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception')]

    def test_accepted_fourth_down_grounding_ends_drive_with_one_snap(self):
        for with_book in (False, True):
            with self.subTest(statbook=with_book):
                book = game.StatBook() if with_book else None
                dr, calls = self.drive(book=book)
                self.assertEqual(dr.result, 'Turnover on downs')
                self.assertEqual(calls['flags'], 1)
                self.assertEqual([(p['type'], p['down']) for p in self.snaps(dr)],
                                 [('incomplete', 4)])
                flag = [p for p in dr.log if p.get('type') == 'penalty']
                self.assertEqual(len(flag), 1)
                self.assertEqual(flag[0]['penalty'], 'Intentional Grounding')
                self.assertTrue(flag[0]['accepted'])
                self.assertAlmostEqual(dr.yardline, 60.0)
                self.assertLess(dr.clock, 2900.0)
                self.assertGreater(dr.clock, 2885.0)  # no new-offense huddle charged
                if book is not None:
                    qb = self.league['HOU']['qb']
                    self.assertEqual(book.p[qb['pid']]['pass_att'], 1)

    def test_declined_grounding_leaves_play_result(self):
        dr, _ = self.drive(decline=True)
        self.assertEqual(dr.result, 'Turnover on downs')
        self.assertEqual([(p['type'], p['down']) for p in self.snaps(dr)],
                         [('incomplete', 4)])
        self.assertAlmostEqual(dr.yardline, 50.0)
        self.assertFalse(any(p.get('type') == 'penalty' for p in dr.log))
        self.assertEqual(self.snaps(dr)[0]['declined_penalty']['penalty'],
                         'Intentional Grounding')

    def test_grounding_on_second_down_allows_third_down(self):
        dr, _ = self.drive(down=2)
        snaps = self.snaps(dr)
        self.assertGreaterEqual(len(snaps), 2)
        self.assertEqual(snaps[0]['down'], 2)
        self.assertEqual(snaps[1]['down'], 3)
        self.assertAlmostEqual(snaps[1]['yardline'], 60.0)

    def test_grounding_in_own_end_zone_remains_safety(self):
        dr, _ = self.drive(down=2, spot=99.0, throwback=3.0)
        self.assertEqual((dr.result, dr.points), ('Safety', -2))
        self.assertEqual(len(self.snaps(dr)), 1)

    def test_grounding_as_half_expires_has_no_next_possession(self):
        dr, _ = self.drive(clock=1801.0, quarter=2, half_end=1800.0)
        self.assertEqual(dr.result, 'End of half')
        self.assertEqual(dr.clock, 1800.0)
        self.assertEqual(len(self.snaps(dr)), 1)
        self.assertTrue(any(p.get('type') == 'penalty' and p.get('accepted')
                            for p in dr.log))


if __name__ == '__main__':
    unittest.main()
