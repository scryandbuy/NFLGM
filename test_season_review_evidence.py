import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import dev_evaluation as DE
import gameplan_week as GW
import views_frontoffice as V


class SeasonReviewEvidence(unittest.TestCase):
    def league(self):
        players = {}
        return NS(year=2027, teams={'A': None, 'B': None}, schedule=[(1, 'A', 'B', 24, 10)],
                  team_game_stats={'2027-1-B-A': {'A': dict(pass_yds=250, rush_yds=100),
                                                'B': dict(pass_yds=150, rush_yds=80)}},
                  stats={2027: {}}, game_stats={}, history={}, player=players.get, players=players)

    def add(self, league, pid, pos, line, ovr=80):
        player = NS(pid=pid, pos=pos, team='A', name=pid, number=10, ovr=ovr,
                    age=27, retired=False, career={}, xp_spent={})
        league.players[pid] = player
        league.stats[2027][pid] = line
        return player

    def qbs(self, league):
        for i in range(4):
            self.add(league, f'q{i}', 'QB', dict(pass_att=500, pass_plays=500,
                     pass_epa=i*50, pass_yds=2000+i*500, pass_td=10+i*5))

    def test_same_regular_season_performance_as_opponent_report(self):
        league = self.league()
        league.schedule.append((19, 'A', 'B', 0, 90))
        with patch.object(GW, 'unit_ranks', side_effect=AssertionError('roster grades')):
            units, sides = V._review_performance(league, 'A', 2027)
        expected = GW.performance_table(league, 'A', 'B')
        self.assertEqual([u['rank'] for u in units], [r['mine'] for r in expected])
        self.assertEqual(sides['offense'], units[0]['rank'])
        self.assertEqual(sides['defense'], units[4]['rank'])
        self.assertEqual(units[3]['value'], 24)

    def test_missing_records_never_fall_back_to_roster_rating(self):
        league = self.league(); league.team_game_stats = {}
        units, _ = V._review_performance(league, 'A', 2027)
        self.assertIsNone(units[0]['rank'])
        self.assertEqual(units[3]['rank'], 1)

    def test_historical_schedule_used_instead_of_current(self):
        league = self.league(); league.year = 2028
        league.history = {'2027': {'schedule': {'all_games': [
            dict(week=1, away={'abbr': 'A'}, home={'abbr': 'B'}, ap=24, hp=10)]}}}
        league.schedule = [(1, 'A', 'B', 0, 70)]
        units, _ = V._review_performance(league, 'A', 2027)
        self.assertEqual(units[3]['value'], 24)
        self.assertEqual(units[0]['value'], 350)

    def test_old_snapshot_refreshed_without_mutating_history(self):
        league = self.league()
        old = dict(units=[dict(label='Pass Block', rank=31)], sides={}, exceeded=[{'pid': 'bad'}], short=[])
        before = copy.deepcopy(old)
        result = V._refresh_review_evidence(league, 'A', 2027, old)
        self.assertEqual(old, before)
        self.assertEqual(result['evidence_version'], 2)
        self.assertEqual(result['units'][0]['rank'], 1)
        self.assertEqual(result['exceeded'], [])

    def test_role_comparisons_include_defenders_and_ir_without_overlap(self):
        league = self.league(); self.qbs(league)
        for i in range(4):
            self.add(league, f'd{i}', 'DT', dict(snaps=700, pr_reps=300,
                     pr_wins=20+i*15, sacks=i*4+.5, tackles=30, def_epa=-9999))
        league.players['d3'].ir = True
        before = copy.deepcopy(league.stats)
        above, below = V._review_players(league, 'A', 2027)
        self.assertTrue({'q3', 'd3'} <= {p['pid'] for p in above})
        self.assertTrue({'q0', 'd0'} <= {p['pid'] for p in below})
        self.assertFalse({p['pid'] for p in above} & {p['pid'] for p in below})
        self.assertIn('12.5 sk', next(p for p in above if p['pid'] == 'd3')['line'])
        self.assertEqual(before, league.stats)

    def test_no_forced_losers_or_quiet_corner_penalty(self):
        league = self.league()
        for i in range(4):
            self.add(league, f'c{i}', 'CB', dict(snaps=800, int_def=i, tackles=20))
        _, below = V._review_players(league, 'A', 2027)
        self.assertEqual(below, [])
        league.stats[2027] = {'c0': dict(snaps=10)}
        self.assertEqual(V._review_players(league, 'A', 2027), ([], []))

    def test_split_team_totals_not_assigned_to_one_club(self):
        league = self.league(); self.qbs(league)
        league.game_stats = {'2027-1-B-A': {'q3': {'team': 'A'}},
                             '2027-2-B-A': {'q3': {'team': 'B'}}}
        above, _ = V._review_players(league, 'A', 2027)
        self.assertNotIn('q3', [p['pid'] for p in above])

    def test_historical_expectations_require_saved_evidence(self):
        league = self.league(); self.qbs(league)
        evidence, ranks = DE.season_comparisons(league, 2027)
        for p in league.players.values(): p.career = {2027: {'team': 'A', 'pos': 'QB'}}
        league.year = 2028
        self.assertEqual(V._review_players(league, 'A', 2027), ([], []))
        p = league.players['q3']; actual, expected, confidence = ranks[p.pid]
        p.xp_spent = {'_dev_review': [dict(year=2027, group=evidence[p.pid]['group'],
                        production=actual, expected=expected, confidence=confidence)]}
        p.ovr = 40
        above, below = V._review_players(league, 'A', 2027)
        self.assertEqual([c['pid'] for c in above], ['q3'])
        self.assertIsNone(above[0]['ovr'])
        self.assertEqual(below, [])


if __name__ == '__main__': unittest.main()
