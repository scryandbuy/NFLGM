"""Save live-ball time before the warning without spending a free stoppage."""
import unittest
from types import SimpleNamespace as NS
import game as G


class WarningTimeoutTests(unittest.TestCase):
    def call(self, seconds, kind='run', yards=5, *, timeouts=3):
        dr = NS(yardline=38,score_diff=13,quarter=4,down=3,togo=34,_two_min=False)
        tos = G.Timeouts(); tos.left['away'] = timeouts
        result = G._timeout_call(dr,kind,dict(type=kind,yards=yards),tos,
                                 'home',None,seconds)
        return result,tos

    def test_washington_run_at_235_saves_huddle(self):
        result,tos=self.call(155)
        self.assertEqual(result,(True,'away'))
        self.assertEqual(tos.left['away'],2)

    def test_boundary_just_before_and_at_warning(self):
        for seconds,expected in ((127,True),(126,False),(123,False)):
            with self.subTest(seconds=seconds):
                result,tos=self.call(seconds)
                self.assertEqual(result[0],expected)
                self.assertEqual(tos.left['away'],2 if expected else 3)

    def test_long_live_play_reaches_warning(self):
        # A completion's flight and travel, not a fixed six seconds, matter.
        dr=NS(yardline=90,score_diff=13,quarter=4,down=1,togo=10,_two_min=False)
        tos=G.Timeouts()
        out=dict(type='complete',yards=80,air=0,ttt=2.7)
        self.assertEqual(G._timeout_call(dr,'complete',out,tos,'home',None,130),(False,None))
        self.assertEqual(tos.left['away'],3)

    def test_incompletion_and_exhausted_timeouts(self):
        self.assertEqual(self.call(155,'incomplete',0)[0],(False,None))
        self.assertEqual(self.call(155,timeouts=0)[0],(False,None))

if __name__=='__main__': unittest.main()
