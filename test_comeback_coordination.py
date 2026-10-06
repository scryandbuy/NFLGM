import unittest
from types import SimpleNamespace as NS
import game as G
import game_substitutions as S
from late_game import pursuing_comeback

class Coordination(unittest.TestCase):
    def check(self, seconds, deficit, aggression, expected):
        coach = dict(fourth_down=aggression, adjust_willingness=aggression)
        self.assertEqual(pursuing_comeback(seconds, deficit, coach), expected)
        self.assertEqual(G.hurry_for_snap(seconds,-deficit,quarter=4,coach=coach),expected)
        self.assertEqual(G.multi_score_urgency(seconds,-deficit,4,coach=coach),expected)
        self.assertEqual(G.comeback_pace(seconds,-deficit,4,coach=coach)>0,expected)
        if seconds < 180:
            dr=NS(quarter=4,clock_period=4,score_diff=deficit,down=2,togo=10,yardline=45)
            tos=G.Timeouts()
            used,_=G._timeout_call(dr,'run',dict(type='run',yards=4),tos,'home',None,seconds,dcoach=coach)
            self.assertEqual(used,expected)

    def test_miami_remote_comeback(self):
        for secs, deficit in [(253,28),(157,22),(151,22),(145,22),(104,25)]:
            self.check(secs,deficit,.5,False)
            self.assertGreater(S.opportunity(secs,-deficit),.6)

    def test_aggressive_coach_can_keep_competing(self):
        self.check(157,22,1,True)
        self.check(157,22,0,False)

    def test_two_scores_still_compete(self):
        self.check(157,16,.5,True)

    def test_earlier_three_score_comeback(self):
        self.assertTrue(pursuing_comeback(600,21))
        self.assertGreater(G.comeback_pace(600,-21,4),0)
        self.assertLess(S.opportunity(600,-21),.1)

if __name__ == '__main__': unittest.main()
