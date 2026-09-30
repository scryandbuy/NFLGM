import unittest
from unittest.mock import patch
from test_cap_accounting import fixture
from test_regression_aging import player, _FixedYear
from league import League
import regression
from views_club import _player_history


class RegressionHistoryTests(unittest.TestCase):
    def test_user_and_cpu_history_records_actual_changes_after_load(self):
        L = fixture(); L.set_phase('offseason')
        for team in ('GB', 'MIN'):
            p = player(team, 'MIKE', 31, team)
            L.players[p.pid] = p; L.teams[team].roster.append(p)
        regression.run(L, _FixedYear(), record_for='GB', tick_age=False)
        loaded = League.load(L.save())
        for team in ('GB', 'MIN'):
            p = loaded.player(team)
            rows = _player_history(loaded, p)
            regress = [r for r in rows if r['line'].startswith('Regression:')]
            self.assertEqual(len(regress), 1)
            self.assertIn('Speed -', regress[0]['line'])
            self.assertIn('Awareness +', regress[0]['line'])
            self.assertEqual(regress[0]['when'], '2026 · Offseason')
            p.ratings['speed_rating'] = 99
            self.assertEqual(_player_history(loaded, p), rows)

    def test_legacy_summary_and_saved_report_without_duplicate(self):
        L = fixture(); p = player('old', 'HB', 30); L.players[p.pid] = p
        L.log('regress', pid=p.pid, lost=1.25)
        rows = _player_history(L, p)
        self.assertEqual(rows[-1]['line'], 'Regression: -1.25 OVR')
        L.regression = {'2026': {p.pid: dict(before=82, after=80.75, attrs={'speed_rating': [85, 83]})}}
        rows = _player_history(L, p)
        self.assertEqual(len(rows), 1)
        self.assertIn('Speed -2', rows[0]['line'])


if __name__ == '__main__': unittest.main()
