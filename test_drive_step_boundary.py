import unittest
from types import SimpleNamespace as NS
from test_overtime_adjustments import BreakFlowTests

class DriveBoundaryTests(unittest.TestCase):
    def test_each_click_finishes_only_one_drive(self):
        r=BreakFlowTests().runner()
        def events():
            for pos in ('away','home','away'):
                dr=NS(points=0, result=None)
                yield ('pos',pos)
                yield ('snap',dr)
                dr.result='Punt'
                yield ('snap',dr)
                yield ('drive',pos,dr,dict(home=0,away=0))
        r.live['gen']=events()
        for expected in (1,2,3):
            r.live_step('drive')
            self.assertEqual(len(r.live['drives']),expected)
            self.assertIsNone(r.live['current'])
            self.assertEqual(r.live['at'],'drive')

if __name__=='__main__': unittest.main()
