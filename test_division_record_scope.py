import copy
import unittest
from types import SimpleNamespace as NS
import views_league as V

class DivisionRecordScope(unittest.TestCase):
    def test_live_excludes_postseason(self):
        a, b = NS(abbr='A', division='D'), NS(abbr='B', division='D')
        league=NS(teams={'A':a,'B':b}, schedule=[(1,'A','B',10,3),(2,'B','A',7,7),(19,'A','B',0,30)])
        self.assertEqual(V._div_record(league,a),'1–0–1')

    def test_archive_repaired_without_changing_snapshot_or_using_current_divisions(self):
        row=dict(club={'abbr':'A'},w=1,l=0,t=0,div_rec='1–1')
        past=dict(divisions=[dict(name='Old',rows=[row,dict(club={'abbr':'B'},w=0,l=1,t=0)])],league_rows=[row],conferences={'C':[row]})
        before=copy.deepcopy(past)
        games=[dict(week=w,away={'abbr':'A'},home={'abbr':'B'},ap=a,hp=b) for w,a,b in [(1,10,3),(19,0,30)]]
        league=NS(history={'2031':{'schedule':{'all_games':games}}})
        fixed=V._past_division_records(league,2031,past)
        self.assertEqual(fixed['league_rows'][0]['div_rec'],'1–0')
        self.assertEqual(fixed['conferences']['C'][0]['div_rec'],'1–0')
        self.assertEqual(past,before)
        league.history={}
        self.assertEqual(V._past_division_records(league,2031,past),before)
