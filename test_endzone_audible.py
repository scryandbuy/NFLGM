import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import plays
import playcall as PC
import rosters

class EndzoneAudible(unittest.TestCase):
    def call(self, intent=True):
        return dict(is_pass=True,depth='deep',concept='four_verts',play_action=False,
                    plan_depth=True,end_zone_attempt=intent,down=1,ydstogo=3)
    def audible(self, call, box=8, shell='cover_3'):
        return PC.audible(call,dict(box=box,shell=shell),{},None,NS(random=lambda:0),
                          latitude=1,score_diff=0,secs_left=1811)
    def test_heavy_and_light_boxes_keep_scoring_intent(self):
        for box in (4,8):
            call,kind=self.audible(self.call(),box)
            self.assertTrue(call['is_pass']);self.assertEqual(call['concept'],'four_verts')
            self.assertIsNone(kind)
    def test_compatible_man_adjustment_survives(self):
        with patch.object(PC,'call_pass',return_value='go'):
            call,kind=self.audible(self.call(),shell='cover_1')
        self.assertEqual(call['concept'],'go');self.assertEqual(kind,'depth')
    def test_short_man_adjustment_does_not_override_shot(self):
        with patch.object(PC,'call_pass',return_value='flood'):
            call,kind=self.audible(self.call(),shell='cover_1')
        self.assertEqual(call['concept'],'four_verts')
    def test_ordinary_screen_remains_available(self):
        with patch.object(PC,'call_pass',return_value='screen'):
            call,kind=self.audible(self.call(False))
        self.assertEqual(call['concept'],'screen');self.assertEqual(kind,'protect')
    def test_real_halftime_planner_and_drive_pass_intent_to_audible(self):
        from season import _deps
        teams=rosters.load_league();off,deff=teams['GB'],teams['BUF']
        tos=G.Timeouts();tos.left['away']=0
        d=G.Drive(off,deff,3,1811,2,0,np.random.default_rng(1))
        self.assertEqual(G.end_of_half_plan(d,off,deff,plays.rate,tos,'away',1800,11)['choice'],'shot')
        co,cd=_deps();seen=[]
        class ReachedResolver(Exception):pass
        def resolve(*args,**kwargs):
            raise ReachedResolver()
        original=PC.audible
        def observe(call,*args,**kwargs):
            seen.append(dict(call))
            return original(call,dict(box=8,shell='cover_3'),off,plays.rate,NS(random=lambda:0),latitude=1)
        with patch.object(PC,'audible',side_effect=observe):
            with self.assertRaises(ReachedResolver):
                G.run_drive(off,deff,3,1811,2,0,np.random.default_rng(12),resolve,co,cd,plays.rate,.5,
                            timeouts=tos,pos='away',half_end=1800)
        self.assertTrue(seen);self.assertTrue(seen[0]['end_zone_attempt'])

if __name__=='__main__':unittest.main()
