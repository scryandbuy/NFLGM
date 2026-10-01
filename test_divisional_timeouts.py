import unittest
import game as G
class DivisionalTimeouts(unittest.TestCase):
 def call(self,down=1,togo=10,yards=27,**out):
  from types import SimpleNamespace as NS; dr=NS(yardline=53,score_diff=0,down=down,togo=togo)
  tos=G.Timeouts()
  result=G._timeout_call(dr,'complete',dict(yards=yards,**out),tos,'away',1800,32,plan=dict(choice='kick',hurry=False))
  return result,tos
 def test_tied_defense_does_not_fund_first_down_drive(self):
  result,tos=self.call();self.assertEqual(result,(False,None));self.assertEqual(tos.left['home'],3)
 def test_explicit_touchdown_stops_clock(self):
  result,tos=self.call(yards=15,touchdown=True);self.assertEqual(result,(False,None))
 def test_fumble_stops_clock(self):
  result,tos=self.call(yards=3,fumble_lost=True);self.assertEqual(result,(False,None))
if __name__=='__main__':unittest.main()

