import unittest
import decisions as D
import game as G

class LateTryTests(unittest.TestCase):
    def test_detroit_lead_one_should_seek_field_goal_protection(self):
        for seconds in (41,47,90,120):
            for aggression in (0.,.5,1.):
                self.assertEqual(D.two_point(1,seconds,aggression=aggression)['call'],'two')
        self.assertTrue(G.two_point_decision(1,4,41))
    def test_tie_still_kicks_to_take_lead(self):
        for seconds in (1,41,120):
            self.assertEqual(D.two_point(0,seconds)['call'],'kick')
    def test_early_game_and_no_time_remain_kicks(self):
        for seconds in (0,600,1800,3000):
            self.assertEqual(D.two_point(1,seconds)['call'],'kick')
    def test_conversion_quality_still_matters(self):
        self.assertEqual(D.two_point(1,41,conv_prob=.001)['call'],'kick')
    def test_first_and_ten_eight_yards_is_not_a_first_down(self):
        from test_penalty_yardage import PenaltyYardageTests
        f=PenaltyYardageTests();dr=f.drive(35,down=1,togo=10)
        out=dict(type='complete',yards=8,air=6)
        flag=f.flag(False,'Defensive Pass Interference',6)
        self.assertEqual(G._resolve_live_penalty(dr,flag,out,{}),'replaced')
        self.assertEqual((dr.down,dr.togo,dr.yardline),(1,10,29))
