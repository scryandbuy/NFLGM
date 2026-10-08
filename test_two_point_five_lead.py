import unittest
import decisions as D
import game as G

class FivePointLead(unittest.TestCase):
    def test_reported_final_touchdown(self):
        self.assertTrue(G.two_point_decision(5, 4, 25))
        for aggression in (0, .5, 1):
            self.assertEqual(D.two_point(5,25,aggression=aggression)['call'],'two')

    def test_earlier_five_point_lead_still_kicks(self):
        for seconds in (300,900,1800,3000):
            for aggression in (0,.5,1):
                self.assertEqual(D.two_point(5,seconds,aggression=aggression)['call'],'kick')

    def test_borderline_clock_preserves_coach_differences(self):
        self.assertEqual(D.two_point(5,240,aggression=0)['call'],'kick')
        self.assertEqual(D.two_point(5,240,aggression=1)['call'],'two')

    def test_conversion_chance_still_matters(self):
        self.assertEqual(D.two_point(5,25,conv_prob=.05)['call'],'kick')
        self.assertEqual(D.two_point(5,25,conv_prob=.6)['call'],'two')

    def test_take_lead_with_extra_point(self):
        for seconds in (25,120,240,900):
            self.assertFalse(G.two_point_decision(0,4,seconds))

    def test_game_already_over(self):
        self.assertEqual(D.two_point(5,0)['call'],'kick')
