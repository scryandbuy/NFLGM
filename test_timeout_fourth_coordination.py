import unittest
from unittest.mock import patch
import game as G
import test_game_clock_decisions as clocks

class TimeoutFourthCoordination(unittest.TestCase):
    def replay(self, live=False, decision=None):
        h=clocks.ClockDecisions(); h.setUp()
        constructor=G.Drive
        def drive(*a,**kw):
            d=constructor(*a,**kw); d.togo=16; return d
        outcomes=[dict(type='sack',yards=-10,ttt=3)]
        if decision=='go': outcomes.append(dict(type='complete',yards=45,ttt=3))
        with patch.object(G,'Drive',side_effect=drive):
            if decision:
                with patch.object(G,'fourth_down_decision',return_value=decision) as call:
                    result=h.drive(outcomes,start=35,clock=1821,diff=-27,own=1,other=3,down=3,live=live)
                    self.assertEqual(call.call_count,1)
                    return result
            return h.drive(outcomes,start=35,clock=1821,diff=-27,own=1,other=3,down=3,live=live)

    def test_reported_sack_does_not_buy_punt(self):
        for live in (False,True):
            dr,_,tos=self.replay(live)
            self.assertEqual(tos.left['home'],1)
            self.assertEqual(dr.result,'End of half')
            self.assertFalse(any(p['type'] in ('timeout','punt') for p in dr.log))

    def test_committed_attack_is_not_rerolled(self):
        for live in (False,True):
            dr,_,tos=self.replay(live,'go')
            self.assertEqual(tos.left['home'],0)
            self.assertEqual(dr.result,'Touchdown')
            self.assertTrue(any(p['type']=='timeout' and p['clock']==1815 for p in dr.log))

    def test_committed_kick_remains_available(self):
        dr,_,tos=self.replay(decision='field_goal')
        self.assertEqual(tos.left['home'],0)
        self.assertTrue(any(p['type']=='field_goal' and p['clock']==1815 for p in dr.log))
