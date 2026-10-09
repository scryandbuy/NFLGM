import unittest
from types import SimpleNamespace as NS
import game as G

class TimeoutAfterConversion(unittest.TestCase):
    def call(self, seconds=76, down=3, togo=18, gain=26, spot=73, stops=1, aggression=.5):
        dr=NS(yardline=spot, score_diff=6, quarter=4, down=down, togo=togo, _two_min=True)
        tos=G.Timeouts(); tos.left['away']=stops
        result=G._timeout_call(dr, 'complete', dict(type='complete', yards=gain), tos,
            'home', None, seconds, dcoach=dict(fourth_down=aggression, adjust_willingness=aggression))
        return result, tos.left['away']

    def test_la_conversion_makes_last_timeout_futile(self):
        for a in (0,.5,1):
            self.assertEqual(self.call(aggression=a), ((False,None),1))

    def test_failed_third_down_still_saves_time_for_punt(self):
        self.assertEqual(self.call(gain=10), ((True,'away'),0))

    def test_more_time_or_timeouts_can_force_possession(self):
        self.assertEqual(self.call(seconds=156), ((True,'away'),0))
        self.assertEqual(self.call(stops=3), ((True,'away'),2))

    def test_cannot_assume_safe_kneels_near_own_goal(self):
        self.assertEqual(self.call(down=1,togo=10,gain=0,spot=99), ((True,'away'),0))

if __name__=='__main__': unittest.main()
