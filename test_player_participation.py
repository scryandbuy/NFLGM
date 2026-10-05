"""Cards describe recorded appearances and workload, never inferred injury absences."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import views_club as VC
from test_cap_accounting import fixture, player


class ParticipationTests(unittest.TestCase):
    def setUp(self):
        self.p = NS(pid='p', pos='WR', team='MIN', career={}, injury_history=[])
        self.league = NS(year=2029, stats={2029: {'p': {'snaps': 100, 'games': 2}}},
                         team_game_stats={}, game_stats={}, inbox=[])

    def game(self, week, team, snaps, total, pos='WR', unit='offense'):
        self.league.team_game_stats[f'2029-{week}-GB-MIN'] = {
            team: {'snap_counts': {unit: {'total': total, 'players': {'p': snaps} if snaps else {}}},
                   'snap_roster': {'p': pos}}}

    def test_trades_zero_snaps_byes_and_historical_units(self):
        self.game(1, 'GB', 60, 80)
        self.game(2, 'GB', 0, 70)  # Known rostered bench/injury game stays in denominator.
        # Week 3 bye has no game record and must not count as an absence.
        self.game(4, 'MIN', 40, 50)
        self.game(5, 'MIN', 0, 60, pos='CB', unit='defense')
        self.game(19, 'MIN', 50, 50)  # Playoffs are separate from the season line.
        before = copy.deepcopy(vars(self.league))
        result = VC._participation_read(self.league, self.p)
        gb, mn = result['clubs']
        self.assertEqual(gb['units']['offense'], dict(snaps=60, total=150, games=2))
        self.assertEqual(gb['appearances'], 1)
        self.assertEqual(mn['units']['offense'], dict(snaps=40, total=50, games=1))
        self.assertEqual(mn['units']['defense'], dict(snaps=0, total=60, games=1))
        self.assertIn('GB offense roster share: 40%', result['snaps'])
        self.assertIn('1 without snaps in 2 recorded team games (all reasons, including time off roster)', result['appearances'])
        self.assertEqual(vars(self.league), before)

    def test_injury_duration_is_not_missed_games_or_injury_cause(self):
        self.game(1, 'GB', 50, 50)
        self.game(3, 'GB', 0, 60)
        self.p.injury_history = [dict(year=2028, weeks_out=8), dict(year=2029, weeks_out=7)]
        result = VC._participation_read(self.league, self.p)
        self.assertIn('1 without snaps in 2', result['appearances'])
        self.assertEqual(result['injury_note'],
                         '2029: 1 recorded injury; games missed specifically through injury are not recorded')

    def test_ir_or_time_before_trade_has_distinct_stint_and_season_denominators(self):
        self.game(1, 'GB', 60, 80)
        self.league.team_game_stats['2029-2-GB-MIN'] = {'GB': {
            'snap_counts': {'offense': {'total': 70, 'players': {'other': 70}}},
            'snap_roster': {'other': 'WR'}}}  # Player on IR or not yet with this team.
        result = VC._participation_read(self.league, self.p)
        self.assertIn('roster share: 75%', result['snaps'])
        self.assertIn('season share: 40%', result['snaps'])
        self.assertIn('1 without snaps in 2 recorded team games', result['appearances'])
        self.assertNotIn('injury', result['appearances'])

    def test_legacy_reports_deduplicate_and_do_not_use_current_team(self):
        report = dict(offense=dict(total=80, rows=[dict(pid='p', pos='WR', snaps=60)]))
        self.league.inbox = [dict(payload=dict(game_key='game-recap-2029-1-GB-MIN-0', snap_counts=report)),
                             dict(payload=dict(game_key='snap-counts-2029-1-GB-MIN-0', snap_counts=report))]
        self.league.game_stats = {'2029-1-GB-MIN': {'p': dict(team='GB', pos='WR')}}
        result = VC._participation_read(self.league, self.p)
        self.assertEqual(result['clubs'][0]['team'], 'GB')
        self.assertEqual(result['clubs'][0]['games'], 1)
        self.assertIn('75%', result['snaps'])
        self.league.game_stats = {}  # Historical affiliation missing, current MIN cannot fill it.
        self.assertEqual(VC._participation_read(self.league, self.p)['clubs'], [])
        self.assertIn('team share unavailable', VC._participation_read(self.league, self.p)['snaps'])

    def test_exact_book_overrides_old_mail_and_survives_json(self):
        self.game(1, 'GB', 30, 60)
        self.league.game_stats = {'2029-1-GB-MIN': {'p': dict(team='GB')}}
        self.league.inbox = [dict(payload=dict(game_key='game-recap-2029-1-GB-MIN-0',
            snap_counts=dict(offense=dict(total=80, rows=[dict(pid='p', pos='WR', snaps=60)]))))]
        loaded = NS(**json.loads(json.dumps(vars(self.league))))
        loaded.stats = {int(k): v for k, v in loaded.stats.items()}
        self.assertEqual(VC._participation_read(self.league, self.p), VC._participation_read(loaded, self.p))
        self.assertIn('GB offense roster share: 50%', VC._participation_read(loaded, self.p)['snaps'])

    def test_specialists_do_not_become_zero_appearance_defenders(self):
        self.p.pos = 'LS'
        self.game(1, 'GB', 0, 70, pos='LS')
        result = VC._participation_read(self.league, self.p)
        self.assertIn('team share unavailable', result['snaps'])
        self.assertNotIn('without snaps', result['appearances'])

    def test_card_retains_every_career_season(self):
        league = fixture(); p = player(league)
        league.year = 2029
        p.career = {year: dict(team='GB', games=17, pass_yds=year) for year in range(2026, 2030)}
        league.stats = {year: {p.pid: line} for year, line in p.career.items()}
        session = NS(user_team='GB', runner=None)
        with patch.object(VC, 'rail', return_value={}), patch.object(VC, 'scheme_rows', return_value=[]):
            card = VC.card(session, league, p.pid)
        self.assertEqual([row['year'] for row in card['seasons']], list(range(2026, 2030)))
        self.assertEqual([row['row'][1] for row in card['seasons']], list(range(2026, 2030)))
        self.assertIsNone(card['missed'])


if __name__ == '__main__': unittest.main()
