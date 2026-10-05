import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import game as G
import test_game_clock_decisions as clocks

class QuickKickTests(unittest.TestCase):
    def plan(self, seconds, tos, spot=41):
        t=G.Timeouts(); t.left=dict(home=tos,away=3)
        return G.end_of_half_plan(NS(quarter=2,score_diff=-4,yardline=spot,down=2),
            {'k':{}},{},lambda *a:.8,t,'home',1800,seconds)

    def test_timeout_opens_quick_play_but_kick_remains_viable(self):
        self.assertEqual(self.plan(9,1)['choice'], 'play')
        self.assertTrue(self.plan(9,1)['quick_play'])
        self.assertEqual(self.plan(9,0)['choice'], 'kick')
        self.assertNotIn('play', self.plan(8,1)['evs'])
        self.assertEqual(self.plan(9,1,10)['choice'], 'kick')

    def test_live_and_batch_use_short_call_timeout_and_kick(self):
        original=G.fg_probability
        for live in (False,True):
            h=clocks.ClockDecisions();h.setUp(); calls=[]
            with patch.object(G,'fg_probability',side_effect=lambda d,k,r:original(d,k,lambda *a:.8)):
                dr,_,tos=h.drive([dict(type='complete',yards=8)], start=41,clock=1809,
                    diff=-4,own=1,down=2,live=live,calls=calls)
            self.assertEqual(calls[0]['depth'],'short')
            self.assertFalse(calls[0]['play_action'])
            kicks=[p for p in dr.log if p['type']=='field_goal']
            self.assertEqual((kicks[0]['distance'],kicks[0]['clock']),(50,1803))
            self.assertEqual(tos.left['home'],0)

    def test_sack_risk_can_make_kicking_better(self):
        with patch.object(G,'PLAY_BAD',.4):
            self.assertEqual(self.plan(9,1)['choice'],'kick')

    def test_halftime_kneel_intent_survives_opponent_timeouts(self):
        for live in (False,True):
            h=clocks.ClockDecisions();h.setUp();calls=[]
            dr,_,tos=h.drive([dict(type='run',yards=1)]*4,start=62,clock=1809,
                diff=17,own=3,other=3,live=live,calls=calls)
            self.assertTrue(calls)
            self.assertTrue(all(not c['is_pass'] and c['scheme']=='inside_zone' for c in calls))
            self.assertEqual(dr.result,'End of half')

    def test_no_timeouts_still_allows_safe_halftime_knee(self):
        h=clocks.ClockDecisions();h.setUp()
        dr,_,_=h.drive(start=62,clock=1809,diff=17,own=3,other=0)
        self.assertEqual(dr.log[0]['type'],'kneel')
