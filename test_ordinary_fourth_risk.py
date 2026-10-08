import unittest
from unittest.mock import patch
import game as G

class Probe:
    def __init__(self): self.chance=None
    def random(self): return self
    def __lt__(self, chance): self.chance=float(chance); return False

def chance(yards=72,distance=8,seconds=2340,aggression=.5,edge=-.0457,optimal='punt'):
    rng=Probe()
    with patch('decisions.fourth_down',return_value=dict(go_boost=edge,optimal=optimal)):
        G.fourth_down_decision(yards,distance,-3,seconds,rng,aggression=aggression)
    return rng.chance

class OrdinaryFourthRisk(unittest.TestCase):
    def test_reported_situation_rare_without_ban(self):
        for aggression in (0,.5,1):
            self.assertGreater(chance(aggression=aggression),0)
            self.assertLess(chance(aggression=aggression),.0002)
    def test_short_yardage_and_midfield_remain_available(self):
        self.assertGreater(chance(distance=1),.01)
        self.assertGreater(chance(yards=50),.01)
    def test_close_or_favorable_comparison_keeps_discretion(self):
        self.assertGreater(chance(edge=-.01),chance())
        self.assertGreater(chance(edge=.03,optimal='go'),chance(edge=-.01))
    def test_desperation_remains(self):
        self.assertEqual(G.fourth_down_decision(72,8,-3,60,Probe()),'go')
    def test_personalities_remain(self):
        self.assertGreater(chance(aggression=1),chance(aggression=0))
