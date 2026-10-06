import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

import league_notes as LN
import standings_and_seeding as SS
import views_league as V
from test_standings_report_performance import fixture


class ClinchTests(unittest.TestCase):
    def view(self, league, year=None):
        with patch.object(V, 'rail', return_value={}), patch.object(V, 'club', side_effect=lambda a: {'abbr': a, 'name': a}):
            return V.standings(N(L=league, runner=None), league, next(iter(league.teams)), year)

    def completed(self):
        league = fixture()
        league.week = 18
        # Every team plays 17 games, with ties to exercise final tiebreaks.
        for conf in ('Continental', 'United'):
            names = [a for a,t in league.teams.items() if t.conf == conf]
            games = [(h,a,20,20 if (i+j)%3 == 0 else 17)
                     for i,h in enumerate(names) for j,a in enumerate(names) if j > i]
            games += [(names[i],names[i+1],10,20) for _ in range(2) for i in range(0,16,2)]
            for h,a,hp,ap in games:
                league.schedule.append((18,a,h,ap,hp))
                league.teams[h].record[0 if hp > ap else 1 if hp < ap else 2] += 1
                league.teams[a].record[0 if ap > hp else 1 if ap < hp else 2] += 1
        return league

    def test_preseason_and_unsettled_race_not_clinched(self):
        league = fixture()
        self.assertFalse(any(any(f.values()) for f in LN.clinch_status(league,0).values()))
        for t in league.teams.values(): t.record=[9,7,0]
        self.assertFalse(any(any(f.values()) for f in LN.clinch_status(league,17).values()))

    def test_midseason_strict_clinch_and_no_notifications_from_view(self):
        league=fixture(); league.week=16
        for t in league.teams.values(): t.record=[8,7,0]
        first=next(iter(league.teams)); league.teams[first].record=[15,0,0]
        before=copy.deepcopy(vars(league))
        flags=LN.clinch_status(league,16)
        self.assertTrue(flags[first]['bye'])
        self.assertEqual(V._clinch_marker(flags[first]),'z')
        self.assertEqual(vars(league),before)
        self.view(league)
        self.assertFalse(hasattr(league,'league_notes_sent'))
        self.assertFalse(hasattr(league,'inbox'))

    def test_all_three_views_match_final_bracket_including_ties(self):
        league=self.completed(); v=self.view(league)
        rows={r['club']['abbr']:r['clinch'] for r in v['league_rows']}
        for conf, group in v['conferences'].items():
            seeds=V._state(N(L=league,runner=None)).seeds()[conf]
            for r in group:
                a=r['club']['abbr']; expected='e'
                if a in seeds:
                    rank=seeds.index(a)+1
                    expected='z' if rank==1 else 'y' if rank<=4 else 'x'
                self.assertEqual(rows[a],expected)
                self.assertEqual(r['clinch'],expected)
        for d in v['divisions']:
            for r in d['rows']: self.assertEqual(r['clinch'],rows[r['club']['abbr']])
        self.assertEqual(list(rows.values()).count('z'),2)
        self.assertEqual(list(rows.values()).count('y'),6)
        self.assertEqual(list(rows.values()).count('x'),6)
        self.assertEqual(list(rows.values()).count('e'),18)

    def test_notifications_share_flags_and_remain_once_only(self):
        league=self.completed(); league.user_team=next(iter(league.teams))
        flags=LN.clinch_status(league,18)
        LN.standings(league,18)
        before = copy.deepcopy(league.inbox)
        LN.standings(league,18)
        self.assertEqual(league.inbox,before)
        self.assertEqual(len([m for m in league.inbox if (m.get('payload') or {}).get('clinched')]),1)
        for a, status in flags.items():
            for field,prefix in [('division','div'),('playoffs','po'),('bye','bye'),('eliminated','out')]:
                self.assertEqual(f'{prefix}-2026-{a}' in league.league_notes_sent,status[field])

    def test_legacy_full_snapshot_uses_its_own_final_seeds_without_mutation(self):
        league=self.completed(); original=self.view(league)
        expected={r['club']['abbr']:r['clinch'] for r in original['league_rows']}
        for r in original['league_rows']: r.pop('clinch')
        league.history={'2026':{'standings':original}}
        before=copy.deepcopy(league.history)
        league.year=2027; league.week=0
        for t in league.teams.values(): t.record=[0,0,0]
        past=self.view(league,2026)
        self.assertEqual({r['club']['abbr']:r['clinch'] for r in past['league_rows']},expected)
        self.assertEqual(league.history,before)


if __name__ == '__main__': unittest.main()
