import unittest
from unittest.mock import patch
import game as G

class Probe:
    def __init__(self): self.chance=None
    def random(self): return self
    def __lt__(self,chance): self.chance=float(chance); return False

def evaluate(distance=11,aggression=.5,seconds=1389,margin=0,kick=.955,edge=-.0442):
    rng=Probe()
    with patch.object(G,'fg_probability',return_value=kick), patch('decisions.fourth_down',
        return_value=dict(optimal='field_goal',go_boost=edge,wp_fg=.60,wp_punt=.50)):
        call=G.fourth_down_decision(13,distance,margin,seconds,rng,aggression=aggression)
    return call,rng.chance

class FourthLongKickValue(unittest.TestCase):
    def test_reported_situation_strongly_favors_kick_without_ban(self):
        for aggression in (0,.5,1):
            call,chance=evaluate(aggression=aggression)
            self.assertEqual(call,'field_goal')
            self.assertGreater(chance,0)
            self.assertLess(chance,.001)
    def test_short_yardage_stays_aggressive(self):
        self.assertGreater(evaluate(distance=2)[1],.05)
    def test_close_evaluation_keeps_discretion(self):
        self.assertGreater(evaluate(edge=-.01)[1],.02)
    def test_unreliable_kicker_keeps_discretion(self):
        self.assertGreater(evaluate(kick=.60)[1],.02)
    def test_need_touchdown_remains(self):
        self.assertEqual(evaluate(seconds=30,margin=-7)[0],'go')
    def test_coach_differences_remain(self):
        self.assertGreater(evaluate(aggression=1)[1],evaluate(aggression=0)[1])
