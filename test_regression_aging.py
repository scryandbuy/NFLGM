"""Regression presentation and offseason aging invariants."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import league
import regression
import targets
import views_club


class _FixedYear:
    def normal(self, *_args):
        return 1.0


def player(pid, pos, age, team='GB'):
    ratings = {k: 80.0 for k in targets.DEPTH_WEIGHTS[pos]}
    ratings.update(speed_rating=82.0, awareness_rating=80.0,
                   play_rec_rating=80.0, injury_rating=72.0)
    return league.Player(pid, pid, pos, age, ratings, team=team)


class RegressionAgingTests(unittest.TestCase):
    def test_curve_uses_displayed_age_and_late_qbs_decline(self):
        self.assertGreaterEqual(regression.curve_factor('QB', 24.9), 1.0)
        self.assertGreaterEqual(regression.curve_factor('QB', 36.9), 1.0)
        self.assertLess(regression.curve_factor('QB', 37.1), 1.0)
        self.assertLess(regression.curve_factor('K', 37.1), 1.0)
        self.assertGreaterEqual(regression.curve_factor('HB', 26.9), 1.0)
        self.assertLess(regression.curve_factor('HB', 27.1), 1.0)

    def test_physical_decline_and_recognition_gain(self):
        p = player('v', 'MIKE', 30.2)
        speed, recognition, injury = (p.ratings[k] for k in
                                      ('speed_rating', 'play_rec_rating', 'injury_rating'))
        regression.decline(p, _FixedYear())
        self.assertLess(p.ratings['speed_rating'], speed)
        self.assertGreater(p.ratings['play_rec_rating'], recognition)
        self.assertEqual(p.ratings['injury_rating'], injury)

    def test_one_age_tick_and_prospects_keep_scouted_ratings(self):
        veteran = player('v', 'HB', 28.4)
        prospect = player('p', 'HB', 22.4, team=None)
        prospect.draft_year = 2027
        before = dict(prospect.ratings)
        events = []
        L = SimpleNamespace(players={'v': veteran, 'p': prospect}, next_class=[prospect],
                            draft_pool=[], year=2026, log=lambda *a, **kw: events.append((a, kw)))
        regression.run(L, np.random.default_rng(5), tick_age=True)
        self.assertAlmostEqual(veteran.age, 29.4)
        self.assertAlmostEqual(prospect.age, 23.4)
        self.assertEqual(prospect.ratings, before)
        self.assertLess(veteran.ratings['speed_rating'], 82.0)
        regression.run(L, np.random.default_rng(5), tick_age=False)
        self.assertAlmostEqual(veteran.age, 29.4)

    def test_report_includes_positive_recognition(self):
        p = player('v', 'MIKE', 30.2)
        rec = dict(before=82, after=80, age=30, pos='MIKE', name='Veteran',
                   attrs={'speed_rating': (82, 80), 'play_rec_rating': (80, 81)},
                   ratings_after=dict(p.ratings))
        L = SimpleNamespace(year=2026, regression={'2026': {'v': rec}},
                            player=lambda pid: p if pid == 'v' else None)
        with patch('views.rail', return_value={}), patch('views.club', return_value={}):
            row = views_club.regression(None, L, 'GB')['rows'][0]
        shown = {a['key']: a['delta'] for col in row['cols']
                 for group in (col, col.get('extra') or {}) for a in group.get('rows', [])
                 if 'delta' in a}
        self.assertEqual(shown['play_rec_rating'], 1)


if __name__ == '__main__':
    unittest.main()
