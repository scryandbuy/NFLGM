import unittest
from types import SimpleNamespace as NS
import gameplan_week as G

class Rankings(unittest.TestCase):
    def league(self):
        return NS(year=2027, teams=dict(A=None,B=None,C=None), schedule=[], team_game_stats={})
    def game(self,l,w,a,h,ap,hp,p=100,r=50):
        l.schedule.append((w,a,h,ap,hp))
        l.team_game_stats[f'2027-{w}-{h}-{a}']={h:dict(pass_yds=p,rush_yds=r),a:dict(pass_yds=200,rush_yds=80)}
    def test_rates_ties_and_defense(self):
        l=self.league();self.game(l,1,'A','B',20,10);self.game(l,2,'A','C',20,10)
        rows=G.performance_table(l,'A','B')
        self.assertEqual(rows[1]['mine_value'],200)
        self.assertEqual(rows[1]['mine'],1)
        self.assertEqual(rows[1]['theirs'],2)
        self.assertEqual(rows[5]['mine'],1)
        self.assertEqual(rows[5]['theirs'],2)
        self.assertEqual(rows[3]['mine_value'],20)
    def test_no_games_and_missing_legacy(self):
        l=self.league();self.assertTrue(all(r['mine'] is None for r in G.performance_table(l,'A','B')))
        l.schedule=[(1,'A','B',7,10)]
        rows=G.performance_table(l,'A','B')
        self.assertIsNone(rows[0]['mine']);self.assertEqual(rows[3]['mine'],2)
    def test_postseason_excluded_and_year_key(self):
        l=self.league();self.game(l,1,'A','B',20,10);self.game(l,19,'A','B',0,90,p=900)
        self.assertEqual(G.performance_table(l,'A','B')[3]['mine_value'],20)
        l.year=2028
        self.assertIsNone(G.performance_table(l,'A','B')[0]['mine'])
    def test_log_accounting_and_idempotency(self):
        l=self.league()
        log=[dict(type='complete',yards=40),dict(type='sack',yards=-8),dict(type='scramble',yards=7),dict(type='kneel',yards=-1),dict(type='penalty',yards=15),dict(type='complete',yards=99,nullified=True),dict(type='interception',yards=50)]
        res=dict(drives=[('home',NS(log=log,result="Punt"))])
        for _ in range(2):G.record_team_performance(l,'A','B',1,res)
        self.assertEqual(l.team_game_stats['2027-1-A-B']['A'],dict(pass_yds=32,rush_yds=6,touchdowns=0))
    def test_exact_tie_and_rounding(self):
        l=self.league();self.game(l,1,'A','B',20,20,p=200,r=80)
        rows=G.performance_table(l,'A','B');self.assertEqual(rows[0]['mine'],rows[0]['theirs'])

if __name__=='__main__':unittest.main()
