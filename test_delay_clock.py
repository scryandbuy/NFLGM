import unittest
from types import SimpleNamespace as NS
import game as G

class DelayClockTests(unittest.TestCase):
    def drive(self, clock=3072, quarter=1, running=True, charged=17):
        return NS(clock=clock,quarter=quarter,clock_running=running,runoff_charged=charged,
                  play_clock=40.,_two_min=False,log=[])
    def test_remaining_clock_before_flag(self):
        d=self.drive()
        self.assertTrue(G._delay_clock_expired(d,1800))
        self.assertEqual(d.clock,3049)
        self.assertEqual(d.runoff_charged,40)
    def test_stopped_clock_does_not_move(self):
        d=self.drive(running=False)
        self.assertTrue(G._delay_clock_expired(d,1800))
        self.assertEqual(d.clock,3072)
    def test_quarter_ends_before_delay(self):
        d=self.drive(clock=2710)
        self.assertFalse(G._delay_clock_expired(d,1800))
        self.assertEqual(d.clock,2700)
    def test_warning_preempts_flag(self):
        d=self.drive(clock=1930,quarter=2,charged=0)
        self.assertFalse(G._delay_clock_expired(d,1800))
        self.assertEqual(d.clock,1920)
        self.assertTrue(d._two_min)
        self.assertEqual(d.log[0]['type'],'two_minute')
    def test_half_ends_before_delay(self):
        d=self.drive(clock=1808,quarter=2)
        d._two_min=True
        self.assertFalse(G._delay_clock_expired(d,1800))
        self.assertEqual(d.clock,1800)
