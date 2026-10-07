import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import kick_returns as K
import plays as P

class KickoffReachability(unittest.TestCase):
    def man(self, pid, speed):
        return dict(pid=pid, speed_rating=speed, accel_rating=speed, tackle_rating=90, pursuit_rating=90, awareness_rating=90)
    def test_slower_trailing_players_cannot_contact(self):
        out=K._kickoff_breakaway(95,30,self.man('r',99),[self.man('a',50),self.man('b',50)],None,np.random.default_rng(1),P.rate)
        self.assertEqual(out['yards'],95)
        self.assertTrue(all(not x['reachable'] for x in out['contacts']))
    def test_faster_trailing_players_can_contact(self):
        out=K._kickoff_breakaway(95,15,self.man('r',50),[self.man('a',99)],None,np.random.default_rng(1),P.rate)
        self.assertLess(out['yards'],95)
        self.assertEqual(out['tackler']['pid'],'a')
    def test_slower_defender_with_leverage_can_reach(self):
        self.assertIsNotNone(K._punt_intercept(9,7,15,0))
        self.assertIsNone(K._punt_intercept(9,7,-10,0))
    def test_actual_kicker_can_stop_return(self):
        out=K._kickoff_breakaway(95,25,self.man('r',70),[],self.man('k',90),np.random.default_rng(3),P.rate)
        self.assertLess(out['yards'],95)
        self.assertEqual(out['tackler']['pid'],'k')
    def test_slower_outside_contain_still_stops_fast_runner(self):
        rng=NS(uniform=lambda low,high:high,random=lambda:1.,normal=lambda *args:0.)
        out=K._kickoff_breakaway(95,12,self.man('r',99),[self.man(str(i),70) for i in range(4)],None,rng,P.rate)
        self.assertLess(out['yards'],95)
        self.assertTrue(any(x['leverage']=='contain' and x['reachable'] for x in out['contacts']))
    def test_kicker_can_miss_reachable_tackle(self):
        rng=NS(uniform=lambda low,high:0.,random=lambda:0.,normal=lambda *args:0.)
        out=K._kickoff_breakaway(95,25,self.man('r',70),[],self.man('k',90),rng,P.rate)
        self.assertEqual(out['yards'],95)
        self.assertTrue(out['contacts'][0]['missed'])
    def test_passed_slower_contain_is_not_teleported_ahead(self):
        rng=NS(uniform=lambda low,high:high,random=lambda:1.,normal=lambda *args:0.)
        out=K._kickoff_breakaway(95,50,self.man('r',99),[self.man(str(i),70) for i in range(4)],None,rng,P.rate)
        self.assertEqual(out['yards'],95)
        self.assertTrue(all(not x['reachable'] for x in out['contacts']))
    def test_short_return_never_enters_new_geometry(self):
        with patch.object(K,'_kickoff_breakaway') as chase, patch.object(K.events,'fumble_check',return_value=None):
            K.resolve(95,8,self.man('r',90),np.random.default_rng(2),P.rate,[self.man('c',90)])
            chase.assert_not_called()

if __name__=='__main__': unittest.main()
