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
            self.assertIn('Awareness +1', regress[0]['line'])
            self.assertNotRegex(regress[0]['line'], r'\d+\.\d+')
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

    def test_old_ol_history_uses_whole_endpoints_and_relevant_attributes(self):
        L = fixture(); p = player('ol', 'LT', 32); L.players[p.pid] = p
        attrs = {
            'pass_block_rating': [90.8, 89.4],
            'run_block_rating': [90.8, 89.2],
            'strength_rating': [90.8, 89.6],
            'speed_rating': [70.1, 70.0],
            'awareness_rating': [80.4, 80.7],
            'tackle_rating': [50.8, 49.3],
            'play_rec_rating': [50.4, 51.7],
            'kick_power_rating': [40.8, 39.6],
            'throw_power_rating': [40.8, 39.6],
            'carry_rating': [40.8, 39.6],
            'block_shed_rating': [40.8, 39.6],
        }
        L.log('regress', pid=p.pid, pos='LT', lost=1.27,
              before=90.8, after=89.5, attrs=attrs)
        loaded = League.load(L.save())
        line = _player_history(loaded, loaded.player(p.pid))[0]['line']
        self.assertEqual(line, 'Regression: -1 OVR (91 → 90) · Strength -1'
                         ' · Pass Block -2 · Run Block -2 · Awareness +1')
        self.assertEqual(loaded.transactions[-1]['attrs'], attrs)

    def test_history_uses_report_attributes_and_historical_position(self):
        L = fixture(); p = player('p', 'LT', 32); L.players[p.pid] = p
        L.log('regress', pid=p.pid, pos='LT', lost=2, before=84, after=82,
              attrs={'pass_block_rating': [84, 82]})
        L.regression = {'2026': {p.pid: dict(pos='TE', before=83.8, after=82.2,
            attrs={'catch_rating': [84.3, 82.8], 'tackle_rating': [70, 68]})}}
        line = _player_history(L, p)[0]['line']
        self.assertEqual(line, 'Regression: -2 OVR (84 → 82) · Catching -1')

    def test_history_and_report_match_for_every_position(self):
        from views_club import ATTR, FAM
        attrs = {key: [82.7, 81.3] for group in ATTR.values() for key, _ in group}
        for pos in FAM:
            with self.subTest(pos=pos):
                L = fixture(); p = player('p', pos, 32); L.players[p.pid] = p
                rec = dict(pos=pos, before=82.7, after=81.3, attrs=attrs)
                L.regression = {'2026': {p.pid: rec}}
                L.log('regress', pid=p.pid, **rec)
                with patch('views.rail', return_value={}), patch('views.club', return_value={}):
                    report = regression_view(None, L, 'GB')['rows'][0]
                expected = ['Regression: -2 OVR (83 → 81)']
                for col in report['cols']:
                    for group in (col, col.get('extra') or {}):
                        expected += [f"{r['label']} {r['delta']:+d}" for r in group.get('rows', []) if r.get('delta')]
                self.assertEqual(_player_history(L, p)[0]['line'], ' · '.join(expected))


if __name__ == '__main__': unittest.main()
