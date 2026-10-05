import unittest
from unittest.mock import patch
import game as G
import test_game_clock_decisions as clocks

class LastHalftimeTimeout(unittest.TestCase):
    def replay(self,aggression,ttt=3,own=2,live=False):
        h=clocks.ClockDecisions();h.setUp()
        real=G.end_of_half_plan
        def plan(*args,**kw):
            kw['coach']=dict(fourth_down=aggression,adjust_willingness=aggression)
            return real(*args,**kw)
        with patch.object(G,'end_of_half_plan',side_effect=plan):
            return h.drive([dict(type='sack',yards=-9,ttt=ttt),dict(type='incomplete',yards=0,ttt=3,intended_air=50)],start=52,clock=1810,diff=-14,own=own,other=3,down=2,live=live)
    def test_aggressive_coach_can_buy_final_shot_with_four_seconds(self):
        for live in (False,True):
            dr,_,t=self.replay(1,live=live)
            timeout=[p for p in dr.log if p['type']=='timeout']
            self.assertEqual(timeout[0]['clock'],1804)
            self.assertEqual(t.left['home'],1)
            snaps=[p for p in dr.log if p.get('down')]
            self.assertEqual((snaps[1]['clock'],snaps[1]['yardline']),(1804,61))
    def test_conservative_coach_can_end_half(self):
        dr,_,t=self.replay(0)
        self.assertEqual(t.left['home'],2)
        self.assertFalse(any(p['type']=='timeout' for p in dr.log))
    def test_long_sack_cannot_create_time(self):
        dr,_,t=self.replay(1,ttt=10)
        self.assertEqual(dr.clock,1800)
        self.assertEqual(t.left['home'],2)
        self.assertEqual(len([p for p in dr.log if p.get('down')]),1)
    def test_no_timeout_cannot_stop_running_clock(self):
        dr,_,t=self.replay(1,own=0)
        self.assertFalse(any(p['type']=='timeout' for p in dr.log))
        self.assertEqual(dr.clock,1800)
