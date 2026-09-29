import unittest
from unittest.mock import patch
import numpy as np
import game as G
from plays import rate

class FieldGoalTests(unittest.TestCase):
    def kicker(self,power=90,accuracy=80):
        return dict(kick_power_rating=power,kick_acc_rating=accuracy,awareness_rating=accuracy)

    def test_probability_never_improves_with_distance(self):
        for power in (40,70,85,95,99):
            for acc in (40,70,90,99):
                k=self.kicker(power,acc)
                probs=[G.fg_probability(d,k,rate) for d in np.arange(17,101,.1)]
                self.assertTrue(all(b<=a+1e-10 for a,b in zip(probs,probs[1:])),(power,acc))

    def test_no_accuracy_jump_at_fifty_or_old_band_edges(self):
        for d in (35,39,40,44,45,49,50,54,55,59):
            k=self.kicker(95,85)
            self.assertLess(abs(G.fg_probability(d-.001,k,rate)-G.fg_probability(d+.001,k,rate)),.0002)

    def test_short_kicks_and_extra_point_baseline_unchanged(self):
        for acc in (40,70,90,99):
            for d,base in ((20,.975),(29,.975),(30,.955),(33,.955),(34,.955)):
                expected=float(np.clip(base*(1+.16*(acc/100-.7)),.005,.995))
                self.assertAlmostEqual(G.fg_probability(d,self.kicker(99,acc),rate),expected)

    def test_kicker_ability_and_range_remain_meaningful(self):
        for d in (40,50,60):
            self.assertGreater(G.fg_probability(d,self.kicker(90,95),rate),G.fg_probability(d,self.kicker(90,60),rate))
        self.assertGreater(G.fg_probability(60,self.kicker(99),rate),G.fg_probability(60,self.kicker(70),rate))
        self.assertLess(G.fg_probability(80,self.kicker(99,99),rate),.01)
        self.assertAlmostEqual(G.fg_probability(33,self.kicker(99),rate),G.fg_probability(33,self.kicker(40),rate))

    def test_attempt_draws_once_and_weather_can_turn_make_into_miss(self):
        class Draw:
            def __init__(self,x):self.x=x;self.calls=0
            def random(self):self.calls+=1;return self.x
        k=self.kicker(); p=G.fg_probability(45,k,rate)
        clear=Draw(p*.95); wet=Draw(p*.95)
        with patch.object(G.ENV,'kick_mult',1):self.assertTrue(G.attempt_field_goal(28,k,clear,rate)['made'])
        with patch.object(G.ENV,'kick_mult',.9):self.assertFalse(G.attempt_field_goal(28,k,wet,rate)['made'])
        self.assertEqual((clear.calls,wet.calls),(1,1))

if __name__=='__main__':unittest.main()
