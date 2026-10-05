import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import events as E
import game as G
import plays as P
import qb_contact as QC
import fumble_resolution as F
import ticker
import test_defensive_returns as DR


class Draws:
    def __init__(self, distance=1., burst=3., escape=0.):
        self.values = iter((distance, burst)); self.escape = escape; self.calls = 0
    def gamma(self, *args): return next(self.values)
    def choice(self, *args, **kwargs): self.calls += 1; return 0
    def random(self): self.calls += 1; return self.escape


class ScrambleGoalContact(unittest.TestCase):
    def setUp(self):
        self.qb = dict(pid='qb', pos='QB')
        self.front = dict(pid='edge', pos='LEDG')
        self.fixture = DR.DefensiveReturns(); self.fixture.setUp()

    def scramble(self, **kwargs):
        return E.resolve_scramble(self.qb, [self.front], 3, Draws(**kwargs), lambda *a:.7)

    def test_contact_short_of_plane_can_be_broken_for_score(self):
        out = self.scramble()
        self.assertTrue(out['touchdown'])
        self.assertEqual(out['pre_goal_contact_yards'], 1.)
        self.assertEqual(out['pre_goal_contact_by'], 'edge')
        self.assertEqual(out['broken_tackles'], 1)
        self.assertIsNone(out['tackler'])

    def test_stopped_contact_keeps_initial_gain(self):
        out = self.scramble(escape=.99)
        self.assertFalse(out['touchdown']); self.assertEqual(out['yards'], 1.)
        self.assertEqual(out['tackler'], 'edge')

    def test_untouched_crossing_has_no_contact_or_fumble_draw(self):
        rng = Draws(distance=7)
        out = E.resolve_scramble(self.qb, [self.front], 3, rng, lambda *a:.7)
        self.assertEqual(rng.calls, 0)
        self.assertNotIn('pre_goal_contact_yards', out)
        dr = NS(yardline=3)
        with patch.object(E, 'fumble_check') as check:
            G._prepare_fumble(dr, out, self.fixture.off, self.fixture.defense, np.random.default_rng(1), lambda *a:.7)
        check.assert_not_called()

    def test_break_tackle_ability_changes_contest_not_free_distance(self):
        low, high = dict(self.qb, break_tackle_rating=40, strength_rating=40), dict(self.qb, break_tackle_rating=95, strength_rating=95)
        a = E.resolve_scramble(low, [self.front], 3, Draws(escape=.18), P.rate)
        b = E.resolve_scramble(high, [self.front], 3, Draws(escape=.18), P.rate)
        self.assertEqual(a['pre_goal_contact_yards'], b['pre_goal_contact_yards'])
        self.assertFalse(a['touchdown']); self.assertTrue(b['touchdown'])

    def test_only_on_field_defenders_and_order_independent(self):
        db = dict(pid='cb', pos='CB')
        a = E.resolve_scramble(self.qb, [self.front, db, self.front], 30, np.random.default_rng(5), P.rate)
        b = E.resolve_scramble(self.qb, [db, self.front], 30, np.random.default_rng(5), P.rate)
        self.assertEqual(a, b)
        self.assertIn(a['pre_goal_contact_by'], ('cb', 'edge'))

    def test_full_drive_contact_fumble_touchback_book_and_text(self):
        original = self.scramble()
        with patch.object(F, 'near_goal_recovery', return_value=(-1., True)):
            dr, book, _ = self.fixture.drive([original], start=3, quarter=1,
                                            fumble=dict(lost=False, forced=True))
        out = next(p for p in dr.log if p.get('fumble'))
        self.assertEqual((dr.result, dr.yardline, dr.points), ('Turnover', 20., 0))
        self.assertEqual((book.p['qb']['rush_att'], book.p['qb']['rush_yds'], book.p['qb']['rush_td']), (1, 1., 0))
        self.assertEqual(book.p['qb']['fumbles_lost'], 1)
        self.assertEqual((book.p['edge']['ff'], book.p['edge']['tackles']), (1, 1))
        self.assertEqual(out['fumble_spot'], 2.)
        league = NS(player=lambda pid: NS(name=pid) if pid else None)
        text = ticker.play_line(league, out, 'GB', 'NY')['text']
        self.assertIn('FUMBLE out of bounds', text)
        self.assertIn('Touchback', text)
        self.assertNotIn('TOUCHDOWN', text)

    def test_full_drive_defender_recovery_and_own_recovery(self):
        for lost, expected in ((True, 'Turnover'), (False, 'Touchdown')):
            with patch.object(F, 'near_goal_recovery', return_value=(-1., False)), \
                 patch.object(G, '_offensive_fumble_recoverer', return_value=self.fixture.off['qb']), \
                 patch.object(P, 'defensive_return', return_value=dict(end_spot=20., touchback=True, ret=0., defensive_td=False, returner='edge')):
                dr, book, _ = self.fixture.drive([self.scramble()], start=3,
                            quarter=1, fumble=dict(lost=lost, forced=True))
            self.assertEqual(dr.result, expected)
            self.assertEqual(book.p['qb']['rush_td'], 0 if lost else 1)
            self.assertEqual(book.p['qb']['rush_yds'], 1 if lost else 3)

    def test_safe_ending_must_precede_contact_and_cancels_hit_evidence(self):
        source = E.resolve_scramble(self.qb, [self.front], 40, Draws(distance=6, burst=3), lambda *a:.7)
        self.assertEqual(source['pre_goal_contact_yards'], 6.)
        seen = False
        for seed in range(100):
            out = copy.deepcopy(source)
            QC.apply(out, self.qb, dict(down=1, ydstogo=10, seconds=500, quarter=4, yardline=40),
                     np.random.default_rng(seed), lambda *a:.7, coach={'starter_protection': 1.})
            if out.get('contact_avoided'):
                seen = True
                self.assertLess(out['yards'], 6.)
                self.assertNotIn('pre_goal_contact_yards', out)
                self.assertNotIn('pre_goal_contact_by', out)
                self.assertFalse(out['scramble_contact']['broken'])
        self.assertTrue(seen)


if __name__ == '__main__': unittest.main()
