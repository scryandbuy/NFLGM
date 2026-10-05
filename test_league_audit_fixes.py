"""Retained history must remain retrievable without unbounded rendered tables."""
import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

import views_league as V


class LeagueAuditFixes(unittest.TestCase):
    def setUp(self):
        self.players = {}
        self.L = N(year=2029, week=22, stats={}, awards={}, history={}, standings_history={},
                   teams={}, schedule=[], transactions=[], almanac={})
        self.L.player = self.players.get
        for a, division in [('GB', 'United North'), ('MIN', 'United North'), ('KC', 'Continental West')]:
            self.L.teams[a] = N(abbr=a, division=division, roster=[], record=[10, 7, 0])
        self.patches = [patch.object(V, 'rail', return_value={}),
                        patch.object(V, 'club', side_effect=lambda a:dict(abbr=a, name=a, display_abbr=a))]
        for p in self.patches: p.start()
        self.addCleanup(lambda:[p.stop() for p in self.patches])

    def player(self, pid, pos, line, team='GB', year=2029):
        p = N(pid=pid, name=pid, pos=pos, team=team, career={year:dict(line, team=team, pos=pos)})
        self.players[pid] = p
        self.L.stats.setdefault(year, {})[pid] = line
        self.L.teams[team].roster.append(p)
        return p

    def test_full_tables_keep_sack_and_yardage_leaders_and_old_snapshots(self):
        for year in (2028, 2029):
            for i in range(70):
                self.player('tackler'+str(i), 'MIKE', dict(tackles=100+i, sacks=1), year=year)
                self.player('receiver'+str(i), 'WR', dict(tgt=100, rec=90, rec_yds=500), year=year)
            self.player('sack leader', 'LEDG', dict(tackles=20, sacks=18), year=year)
            self.player('yardage leader', 'WR', dict(tgt=90, rec=60, rec_yds=1500), year=year)
        self.L.history['2028'] = {'stats':dict(tables={'defense':{'rows':[]}}, team=[{'preserved':True}])}
        before = copy.deepcopy(self.L.history)
        for year in (2028, 2029):
            v = V.stats(None, self.L, 'GB', year)
            self.assertEqual(len(v['tables']['defense']['rows']), 71)
            self.assertIn('sack leader', [r['pid'] for r in v['tables']['defense']['rows']])
            self.assertIn('yardage leader', [r['pid'] for r in v['tables']['receiving']['rows']])
            self.assertEqual(v['week'], 18)
        self.assertEqual(V.stats(None, self.L, 'GB', 2028)['team'], [{'preserved':True}])
        self.assertEqual(self.L.history, before)

    def test_transaction_search_and_team_filter_precede_pagination(self):
        self.player('Old signing', 'CB', {})
        self.player('New signing', 'CB', {})
        old = dict(kind='sign', year=2029, team='GB', pid='Old signing', years=3, apy=14.7)
        self.L.transactions = [old] + [dict(kind='sign', year=2029, team='KC', pid='New signing') for _ in range(6100)]
        v = V.transactions(None, self.L, 'GB', n=1, group='Signings', club_filter='mine')
        self.assertEqual((v['total'], len(v['rows']), v['rows'][0]['pid']), (1, 1, 'Old signing'))
        v = V.transactions(None, self.L, 'GB', n=1, query='old signing')
        self.assertEqual(v['rows'][0]['pid'], 'Old signing')
        v = V.transactions(None, self.L, 'GB', n=40, offset=6080)
        self.assertEqual((v['total'], len(v['rows'])), (6101, 21))
        self.assertEqual(v['rows'][-1]['pid'], 'Old signing')
        self.assertEqual(len(V.transactions(None, self.L, 'GB', n=9999)['rows']), 200)
        self.assertEqual(len(V.transactions(None, self.L, 'GB', n=None)['rows']), 6101)

    def test_receiving_and_defense_include_other_recorded_evidence(self):
        self.player('Target only', 'WR', dict(tgt=5, rec=0))
        self.player('Pressure only', 'LEDG', dict(tackles=0, pressures=3))
        v = V.stats(None, self.L, 'GB')
        self.assertEqual(v['tables']['receiving']['rows'][0]['pid'], 'Target only')
        self.assertEqual(v['tables']['defense']['rows'][0]['pid'], 'Pressure only')

    def test_historical_snapshot_keeps_identity_when_player_was_pruned(self):
        self.player('Current record', 'WR', dict(rec=80, tgt=110, rec_yds=1000), year=2028)
        old = dict(pid='Pruned', name='Retired Player', pos='WR', team='MIN', row=[100,90,1200,8,'13.3',0,17])
        self.L.history['2028'] = {'stats':dict(boxes=[{'retained':True}], tables={'receiving':{'cols':[], 'rows':[old]}}, team=[])}
        before = copy.deepcopy(self.L.history)
        v = V.stats(None, self.L, 'GB', 2028)
        self.assertEqual(v['boxes'], [{'retained':True}])
        self.assertIn(old, v['tables']['receiving']['rows'])
        self.assertEqual(self.L.history, before)

    def test_trade_search_retains_both_teams_and_division(self):
        self.L.transactions = [dict(kind='trade', year=2029, a='KC', b='GB', a_sends=[], b_sends=[])]
        v = V.transactions(None, self.L, 'GB', group='Trades', club_filter='div', query='GB')
        self.assertEqual(v['total'], 1)

    def test_coaching_paging_uses_full_ledger(self):
        self.L.transactions = [dict(kind='staff_in', year=2026, team='GB', name='Old Coach', role='oc')]
        v = V.transactions(None, self.L, 'GB', group='Coaching', query='old coach', club_filter='mine')
        self.assertEqual(v['total'], 1)
        self.assertTrue(v['rows'][0]['coaching'])

    def test_coaching_schema_preserves_actual_record_and_legacy_fields(self):
        modern = dict(name='Coach', frm=2026, to=None, w=27, l=24, t=1)
        self.assertEqual(V._coach_history_row(modern), dict(name='Coach', frm=2026, to=None, record='27–24–1'))
        legacy = dict(name='Coach', **{'from':2020}, to=2024, record='42–38')
        self.assertEqual(V._coach_history_row(legacy)['record'], '42–38')
        self.assertEqual(V._coach_history_row(legacy)['frm'], 2020)

    def test_award_evidence_repairs_snapshot_without_revoting_or_mutation(self):
        self.player('Defender', 'MIKE', dict(tackles=133, sacks=12, pressures=50, ff=8, int_def=1, pass_def=5), year=2028)
        self.L.history['2028'] = {'awards':dict(rows=[dict(pid='Defender', name='Defender', pos='MIKE', code='DPOY', team={'abbr':'GB'}, line='Old text')])}
        before = copy.deepcopy(self.L.history)
        v = V.awards(None, self.L, 'GB', 2028)
        self.assertIn('12.0 sacks, 50 pressures, 8 FF', v['rows'][0]['line'])
        self.assertEqual(v['rows'][0]['code'], 'DPOY')
        self.assertEqual(self.L.history, before)
        back = self.player('Back', 'HB', dict(rush_att=200, rush_yds=1000, rush_td=5, rec=75, rec_yds=650, rec_td=3))
        self.assertIn('75 rec, 650 rec yds, 3 rec TD', V._award_line(self.L, back, 2029))

    def test_blocking_award_reports_known_context_without_inventing_assignment_data(self):
        p = self.player('Blocker', 'LT', dict(pb_snaps=600, pb_wins=570, rb_snaps=300, rb_wins=210, sacks_allowed=4, pressures_allowed=11))
        self.player('Back', 'HB', dict(rush_yds=1200, rush_td=10, rec_td=2))
        self.L.game_stats = {'2029-1-GB-KC':{
            'Blocker':dict(team='GB', sacks_allowed=4),
            'Back':dict(team='GB', rush_yds=1200, rush_td=10, rec_td=2)}}
        line = V._award_line(self.L, p, 2029)
        self.assertIn('4 sacks, 11 pressures allowed', line)
        self.assertIn('Team: 1,200 rush yds, 12 offensive TD, 4 sacks allowed, 10–7', line)
        self.assertNotIn('Assignment evidence', line)

    def test_blocking_award_club_context_follows_games_after_trade(self):
        p = self.player('Blocker', 'LT', dict(pb_snaps=600, pb_wins=570))
        self.player('Departed back', 'HB', dict(rush_yds=1500, rush_td=12), team='KC')
        self.L.game_stats = {
            '2029-1-GB-KC':{'Departed back':dict(team='GB', rush_yds=1000, rush_td=8)},
            '2029-2-KC-MIN':{'Departed back':dict(team='KC', rush_yds=500, rush_td=4)},
            '2029-19-GB-KC':{'Departed back':dict(team='GB', rush_yds=200, rush_td=2)}}
        self.assertIn('Team: 1,000 rush yds, 8 offensive TD', V._award_line(self.L, p, 2029))
        self.L.game_stats['2029-1-GB-KC']['Departed back'].pop('team')
        self.assertNotIn('Team:', V._award_line(self.L, p, 2029))

    def test_historical_byes_follow_selected_week_and_do_not_invent_missing_weeks(self):
        game = lambda w,a,h:dict(week=w, away={'abbr':a}, home={'abbr':h}, ap=10, hp=20, done=True)
        self.L.history['2028'] = {'schedule':dict(week=5, all_games=[game(5,'GB','KC'), game(6,'MIN','KC')], games=[], byes=[])}
        before = copy.deepcopy(self.L.history)
        self.assertEqual(V.schedule(None, self.L, 'GB', year=2028)['byes'], [{'abbr':'MIN','name':'MIN','display_abbr':'MIN'}])
        self.assertEqual(V.schedule(None, self.L, 'GB', year=2028, week=6)['byes'][0]['abbr'], 'GB')
        self.assertEqual(V.schedule(None, self.L, 'GB', year=2028, week=7)['byes'], [])
        self.assertEqual(self.L.history, before)

    def test_team_cap_uses_focus_year_without_changing_record_year(self):
        t = self.L.teams['GB'];t.gm=None;t.staff={};t.active=lambda:[];t.cap_space=7.8
        focus = dict(year=2030, limit=437.8, committed=374.5, pending_offers=0, space=63.3, next=True)
        with patch('views.rail', return_value={}), patch('staff.unit_ranks', return_value={}), patch('views._division_place', return_value='1st'), \
             patch('views.next_year_cap', return_value=(437.8,374.5,0,0)), patch('views.cap_focus', return_value=focus) as f, \
             patch('valuation.pool_from_league', return_value=[]), patch('trades.surplus_and_needs', return_value=([],[])), \
             patch('practice_squad.squad', return_value=[]), patch.object(V, '_identity_names', return_value={}):
            v = V.team_page(None, self.L, 'GB', 'GB')
        f.assert_called_once_with(self.L, t)
        self.assertEqual((v['cap']['year'], v['cap']['space'], v['season_year'], v['record']), (2030, 63.3, 2029, '10–7'))


if __name__ == '__main__': unittest.main()
