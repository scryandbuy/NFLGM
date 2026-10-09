import unittest
from types import SimpleNamespace as NS
import game as G

class TimeoutReserve(unittest.TestCase):
    def call(self, seconds=68, spot=65, gain=16, tos=1, diff=-2, a=.5, kind='complete', quarter=4):
        dr=NS(quarter=quarter, score_diff=diff, yardline=spot, down=1, togo=10, _two_min=True)
        t=G.Timeouts(); t.left['home']=tos
        used=G._timeout_call(dr,kind,dict(type=kind,yards=gain),t,'home',1800 if quarter == 2 else None,seconds,
            coach=dict(fourth_down=a,adjust_willingness=a),plan=dict(choice='play',hurry=True))
        return used[0],t.left['home']
    def test_atlanta_last_stop_saved(self):
        for a in (0,.5,1): self.assertEqual(self.call(a=a),(False,1))
    def test_urgent_gain_and_sack_spend_last_stop(self):
        self.assertEqual(self.call(seconds=12),(True,0))
        self.assertEqual(self.call(seconds=35,spot=35,gain=-8,kind='sack'),(True,0))
    def test_touchdown_drive_needs_more_clock(self):
        self.assertFalse(self.call()[0])
        self.assertTrue(self.call(diff=-7)[0])
    def test_coaches_differ_near_margin(self):
        self.assertFalse(self.call(seconds=40,a=0)[0])
        self.assertTrue(self.call(seconds=40,a=1)[0])
    def test_incomplete_never_spends(self):
        self.assertEqual(self.call(seconds=12,gain=0,kind='incomplete'),(False,1))
    def test_halftime_sf_preserves_last_stop(self):
        for a in (0,.5,1):
            self.assertEqual(self.call(quarter=2, seconds=41, spot=37, gain=13, diff=-3, a=a),(False,1))
    def test_halftime_urgent_sack_and_gain_use_timeout(self):
        self.assertEqual(self.call(quarter=2, seconds=35, spot=24, gain=-6, kind='sack'),(True,0))
        self.assertEqual(self.call(quarter=2, seconds=15, spot=30, gain=22),(True,0))
    def test_halftime_score_margin_does_not_require_touchdown(self):
        for diff in (-14,0,7):
            self.assertEqual(self.call(quarter=2, seconds=41, spot=37, gain=13, diff=diff),(False,1))
    def test_halftime_coaches_can_differ(self):
        self.assertFalse(self.call(quarter=2, seconds=40,a=0)[0])
        self.assertTrue(self.call(quarter=2, seconds=40,a=1)[0])
if __name__=='__main__': unittest.main()
