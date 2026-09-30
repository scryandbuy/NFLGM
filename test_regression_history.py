import unittest
from unittest.mock import patch
from test_cap_accounting import fixture
from test_regression_aging import player, _FixedYear
from league import League
import regression
from views_club import _player_history, regression as regression_view


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
        # Without historical endpoints, membership in the report cannot be
        # established. Never reconstruct it from today's player rating.
        self.assertEqual(rows, [])
        L.regression = {'2026': {p.pid: dict(before=82, after=80.75, attrs={'speed_rating': [85, 83]})}}
        rows = _player_history(L, p)
        self.assertEqual(len(rows), 1)
        self.assertIn('Speed -2', rows[0]['line'])

    def test_history_matches_report_for_fractional_and_visible_losses(self):
        L = fixture()
        pairs = [(82.9, 82.9), (83.3, 82.8), (82.6, 82.4),
                 (83, 81), (82, 83), (82.5, 82.4)]
        L.regression = {'2026': {}}
        for i, (before, after) in enumerate(pairs):
            p = player(str(i), 'HB', 30); L.players[p.pid] = p
            L.regression['2026'][p.pid] = dict(before=before, after=after, attrs={})
            L.log('regress', pid=p.pid, lost=.14 if i == 0 else before-after,
                  before=before, after=after)
        loaded = League.load(L.save())
        with patch('views.rail', return_value={}), patch('views.club', return_value={}):
            shown = {r['pid'] for r in regression_view(None, loaded, 'GB')['rows']}
        history = {pid for pid, p in loaded.players.items()
                   if any(r['line'].startswith('Regression:') for r in _player_history(loaded, p))}
        self.assertEqual(shown, {'2', '3'})
        self.assertEqual(history, shown)

    def test_report_wins_over_conflicting_event_and_cpu_uses_same_rule(self):
        L = fixture(); p = player('p', 'HB', 30); L.players[p.pid] = p
        L.log('regress', pid=p.pid, lost=2, before=84, after=82)
        L.regression = {'2026': {p.pid: dict(before=82.9, after=82.9, attrs={})}}
        self.assertEqual(_player_history(L, p), [])
        L.regression = {}
        self.assertEqual(len(_player_history(L, p)), 1)
        L.transactions[-1].update(before=82.9, after=82.9, lost=.14)
        self.assertEqual(_player_history(L, p), [])


if __name__ == '__main__': unittest.main()
