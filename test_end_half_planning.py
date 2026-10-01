import unittest
from types import SimpleNamespace as N
import game as G
class EndHalfPlanning(unittest.TestCase):
 def test_fourth_down_does_not_budget_more_regular_snaps(self):
  t=G.Timeouts();d=N(down=4,yardline=52,quarter=2,score_diff=3)
  p=G.end_of_half_plan(d,{'k':{}},{},lambda *a:.5,t,'away',1800,63)
  self.assertNotIn('play',p['evs']);self.assertNotEqual(p['choice'],'play')
 def test_leading_failed_third_does_not_call_timeout_for_punt(self):
  t=G.Timeouts();d=N(down=3,togo=4,yardline=55,score_diff=3)
  r=G._timeout_call(d,'complete',dict(yards=3),t,'away',1800,69,plan=dict(choice='play',hurry=True))
  self.assertEqual(r,(False,None));self.assertEqual(t.left['away'],3)
 def test_thirty_seconds_no_timeouts_can_continue(self):
  t=G.Timeouts();t.left={'home':0,'away':1}
  d=N(down=1,yardline=40,quarter=2,score_diff=-3)
  p=G.end_of_half_plan(d,{'k':{}},{},lambda *a:.5,t,'home',1800,30)
  self.assertIn('play',p['evs']);self.assertEqual(p['choice'],'play')
if __name__=='__main__':unittest.main()
