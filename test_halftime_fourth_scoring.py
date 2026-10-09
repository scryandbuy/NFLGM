import unittest
from types import SimpleNamespace as NS
import game as G
import plays

class HalftimeFourthScoring(unittest.TestCase):
    def calls(self, spot=38, distance=1, seconds=7, tos=0, aggression=.5):
        k=dict(kick_power_rating=95,kick_acc_rating=80,awareness_rating=80)
        return [G.fourth_down_decision(spot,distance,0,1800+seconds,
            NS(random=lambda i=i:(i+.5)/1000), aggression=aggression,
            kicker=k,rate_fn=plays.rate,half_seconds_left=seconds,
            offense_timeouts=tos) for i in range(1000)]
    def test_cleveland_last_timeout_spent(self):
        for a in (0,.5,1):
            self.assertEqual(self.calls(aggression=a).count('field_goal'),1000)
    def test_goal_line_touchdown_remains_available(self):
        self.assertGreater(self.calls(spot=1).count('go'),900)
    def test_timeout_and_clock_restore_conversion_value(self):
        self.assertGreater(self.calls(seconds=12,tos=1).count('go'),self.calls(seconds=7).count('go'))
        self.assertGreater(self.calls(seconds=12,tos=1).count('go'),self.calls(seconds=12,tos=0).count('go'))
    def test_coach_differences_survive_close_choices(self):
        self.assertGreater(self.calls(seconds=12,tos=1,aggression=1).count('go'),self.calls(seconds=12,tos=1,aggression=0).count('go'))
if __name__=='__main__': unittest.main()
