"""Read-only preparation must keep tiebreaks and report rankings intact."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import gameplan_week as GW
import season as SN
import standings_and_seeding as SS
import views_league as VL


def fixture():
    teams = {}
    for conf in ('AFC', 'NFC'):
        for division in ('East', 'North', 'South', 'West'):
            for i in range(4):
                a = f'{conf}_{division}_{i}'
                teams[a] = SimpleNamespace(abbr=a, division=f'{conf} {division}',
                    conf=conf, record=[0, 0, 0], depth={}, gm=None)
    return SimpleNamespace(teams=teams, schedule=[], year=2026, week=0)


class StandingsPreparationTests(unittest.TestCase):
    def test_no_simulation_is_created_and_live_runner_is_reused(self):
        league = fixture()
        with patch.object(SN.SeasonRunner, '__init__', side_effect=AssertionError('simulation built')):
            view = VL._state(SimpleNamespace(L=league, runner=None))
            self.assertIsInstance(view, SN.StandingsView)
            self.assertEqual(32, len(view.standings()))
            self.assertEqual({'AFC', 'NFC'}, set(view.seeds()))
        runner = object()
        self.assertIs(runner, VL._state(SimpleNamespace(L=league, runner=runner)))

    def test_live_updates_ties_and_playoffs_match_tiebreak_engine(self):
        league = fixture()
        keys = list(league.teams)
        games = [(keys[0], keys[1], 20, 20), (keys[0], keys[4], 24, 10),
                 (keys[1], keys[4], 17, 10), (keys[16], keys[17], 7, 14)]
        view = SN.StandingsView(league)
        for week, (home, away, hp, ap) in enumerate(games, 1):
            league.schedule.append((week, away, home, ap, hp))
            league.teams[home].record[0 if hp > ap else 1 if hp < ap else 2] += 1
            league.teams[away].record[0 if ap > hp else 1 if ap < hp else 2] += 1
        league.schedule += [(19, keys[0], keys[1], 0, 99), (5, keys[2], keys[3], None, None)]
        expected = SS.Season.live({a:t.division for a,t in league.teams.items()},
                                 {a:t.conf for a,t in league.teams.items()}, games, league.year)
        self.assertEqual(games, view.completed())
        self.assertEqual({c:SS.seed_conference(expected,c) for c in ('AFC','NFC')}, view.seeds())
        for a, row in view.standings().items():
            self.assertEqual(SS.division_ranks(expected)[a], row['div_rank'])
            self.assertEqual(round(expected.wpct(a),3), row['pct'])
            self.assertEqual(expected.pf[a], row['pf'])
        # The same helper must see results arriving after its construction.
        league.schedule.append((6, keys[1], keys[0], 0, 40))
        self.assertEqual(84, view.standings()[keys[0]]['pf'])


class OpponentRankingPreparationTests(unittest.TestCase):
    def test_one_grade_pass_exact_ranks_and_no_stale_cache(self):
        league = fixture()
        keys = list(league.teams)
        league.teams[keys[0]].record = [1,0,0]
        grades = {a:{u:(None if u == 'backs' else 60 + i//2) for u in GW.UNITS}
                  for i,a in enumerate(keys)}
        def grade(_league, team): return grades[team.abbr]
        with patch.object(GW,'unit_grades',side_effect=grade) as calls:
            report = GW.opponent_report(league,keys[0],keys[1],1)
            self.assertEqual(32,calls.call_count)
            for a, field in ((keys[0],'my_units'),(keys[1],'units')):
                for u,v in grades[a].items():
                    vals = sorted((g[u] for g in grades.values() if g[u] is not None),reverse=True)
                    self.assertEqual(None if v is None else (vals.index(v)+1,len(vals),v),report[field][u])
            grades[keys[0]]['QB'] = 99
            calls.reset_mock()
            updated = GW.opponent_report(league,keys[0],keys[1],1)
            self.assertEqual((1,32,99),updated['my_units']['QB'])
            self.assertEqual(32,calls.call_count)

    def test_preseason_ranks_hidden_without_grading_rosters(self):
        league = fixture(); keys = list(league.teams)
        with patch.object(GW,'unit_grades',side_effect=AssertionError('preseason ranking')):
            report = GW.opponent_report(league,keys[0],keys[1],1)
        self.assertEqual(dict.fromkeys(GW.UNITS),report['units'])
        self.assertEqual(dict.fromkeys(GW.UNITS),report['my_units'])

if __name__ == '__main__': unittest.main()
