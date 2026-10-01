"""Schedule-only checks: no multi-season gameplay simulation required."""
import csv
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import schedule as S


class ScheduleSpacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with Path(__file__).with_name('schedule_2026.csv').open() as f:
            cls.rows = list(csv.DictReader(f))
        cls.div = {r['home_team']: r['home_div'] for r in cls.rows}
        cls.rank = {t: i + 1 for d in S.DIVS
                    for i, t in enumerate(sorted(t for t, v in cls.div.items() if v == d))}

    def assert_schedule(self, league, expected):
        self.assertEqual(S.validate(league), [])
        self.assertEqual(Counter((h, a) for _, a, h, _, _ in league.schedule),
                         Counter((h, a) for h, a, _ in expected))
        occupied = Counter((w, t) for w, a, h, _, _ in league.schedule for t in (a, h))
        self.assertEqual(set(occupied.values()), {1})
        for t in self.div:
            missing = set(range(1, 19)) - {w for w, a, h, _, _ in league.schedule if t in (a, h)}
            self.assertEqual(missing, {league.byes[t]})
            self.assertIn(league.byes[t], S.BYE_WEEKS)

    def league(self, year):
        return NS(year=year, teams={t: NS(division=d) for t, d in self.div.items()}, schedule=[])

    def test_new_save_opening_slate_already_obeys_minimum(self):
        games = [(r['home_team'], r['away_team'], '') for r in self.rows]
        weeks = {i: int(r['week']) for i, r in enumerate(self.rows)}
        self.assertEqual(S.rematch_violations(games, weeks), [])

    def test_one_intervening_week_allowed_consecutive_weeks_rejected(self):
        games = [('GB', 'CHI', 'div'), ('CHI', 'GB', 'div')]
        self.assertEqual(S.rematch_violations(games, {0: 14, 1: 16}), [])
        self.assertTrue(S.rematch_violations(games, {0: 14, 1: 15}))
        league = self.league(2027)
        league.schedule = [(14, 'CHI', 'GB', None, None), (15, 'GB', 'CHI', None, None)]
        self.assertTrue(any('rematch' in f for f in S.validate(league)))

    def test_whole_week_repair_preserves_games_and_bye_window(self):
        games = [(r['home_team'], r['away_team'], '') for r in self.rows]
        weeks = {i: int(r['week']) for i, r in enumerate(self.rows)}
        # Deliberately permute a valid full week until a consecutive rematch exists.
        bad = None
        for a in S.FULL_WEEKS:
            for b in S.FULL_WEEKS:
                if 18 in (a, b): continue
                candidate = {i: b if w == a else a if w == b else w for i, w in weeks.items()}
                if S.rematch_violations(games, candidate): bad = candidate; break
            if bad is not None: break
        self.assertIsNotNone(bad)
        repaired = S.space_rematches(games, bad)
        self.assertIsNotNone(repaired)
        self.assertEqual(S.rematch_violations(games, repaired), [])
        self.assertEqual(sorted(Counter(repaired.values()).values()),
                         sorted(Counter(weeks.values()).values()))
        for i, old in bad.items():
            self.assertEqual(old == 18, repaired[i] == 18)
            self.assertEqual(old in S.BYE_WEEKS, repaired[i] in S.BYE_WEEKS)
        self.assertIsNone(S.space_rematches(games, bad, node_limit=0))

    def test_future_seasons_across_rotations_and_distant_year(self):
        # Twelve years cover both rotation cycles; 2066 checks distant saves.
        for year in (*range(2027, 2039), 2066):
            with self.subTest(year=year):
                league = self.league(year)
                S.new_season(league, self.rank, np.random.default_rng(year))
                self.assert_schedule(league, S.build_matchups(year, self.div, self.rank))

    def test_known_failing_seed_and_reproducibility(self):
        games = S.build_matchups(2028, self.div, self.rank)
        # Previously produced five consecutive-week rematches, including DEN/KC 17/18.
        first = S.assign_weeks(games, self.div, seed=42)
        self.assertEqual(S.rematch_violations(games, first[0]), [])
        self.assertEqual(S.assign_weeks(games, self.div, seed=42), first)

    def test_invalid_solver_result_cannot_replace_existing_schedule(self):
        league = self.league(2028)
        old = [(1, 'CHI', 'GB', 14, 21)]
        league.schedule = old
        games = S.build_matchups(2028, self.div, self.rank)
        with patch.object(S, 'assign_weeks', return_value=({i: 1 for i in range(len(games))}, {})):
            with self.assertRaisesRegex(RuntimeError, 'rematches'):
                S.new_season(league, self.rank, np.random.default_rng(42))
        self.assertIs(league.schedule, old)

    def test_loaded_existing_save_generates_a_valid_next_season(self):
        from league import League, Team
        league = League(2027)
        league.ls_reserve_version = 1
        league.teams = {t: Team(t, d, d.split()[0], league.year) for t, d in self.div.items()}
        # Loading must preserve historical results even if their old spacing was bad.
        league.schedule = [(15, 'GB', 'MIN', 27, 25), (16, 'MIN', 'GB', 10, 14)]
        restored = League.load(league.save())
        self.assertEqual(restored.schedule, league.schedule)
        restored.year += 1
        S.new_season(restored, self.rank, np.random.default_rng(42))
        self.assert_schedule(restored, S.build_matchups(2028, self.div, self.rank))
        reloaded = League.load(restored.save())
        self.assertEqual(reloaded.schedule, restored.schedule)
        self.assertFalse(any('rematch' in f for f in S.validate(reloaded)))


if __name__ == '__main__': unittest.main()
