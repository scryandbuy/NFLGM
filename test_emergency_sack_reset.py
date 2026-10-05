import unittest
from unittest.mock import patch
import game as G
from test_game_clock_decisions import ClockDecisions

class EmergencyReset(unittest.TestCase):
    def test_fast_and_slow_reset(self):
        out=dict(type='sack', yards=0, ttt=2.7)
        self.assertLess(G.emergency_sack_elapsed(out,14,14,reset_draw=0),14)
        self.assertEqual(G.emergency_sack_elapsed(out,14,14,reset_draw=1),14)
        self.assertEqual(G.emergency_sack_elapsed(dict(out,ttt=14),14,23),23)
        self.assertEqual(G.emergency_sack_elapsed(dict(out,yards=-12,depth='deep'),14,14,reset_draw=.5),14)

    def drive(self, reset, seconds=14, down=2, diff=-4, live=False, loss=0):
        h=ClockDecisions();h.setUp()
        original=G.emergency_sack_elapsed
        with patch.object(G,'emergency_sack_elapsed',side_effect=lambda *a,**kw:original(*a,**dict(kw,reset_draw=reset))):
            return h.drive([dict(type='sack',yards=loss,ttt=2.7),dict(type='complete',yards=30)],start=3,clock=seconds,quarter=4,wall=None,diff=diff,own=0,down=down,live=live)[0]

    def test_live_and_batch_allow_final_snap(self):
        for live in (False,True):
            dr=self.drive(0,live=live)
            self.assertEqual(dr.result,'Touchdown')
            snaps=[p for p in dr.log if p.get('type') in ('sack','complete')]
            self.assertEqual([p['clock'] for p in snaps],[14,4])

    def test_slow_reset_and_deep_loss_can_end_game(self):
        self.assertEqual(self.drive(1).result,'End of half')
        self.assertEqual(self.drive(.5,loss=-15).result,'End of half')

    def test_fourth_down_still_surrenders_possession(self):
        self.assertEqual(self.drive(0,down=4).result,'Turnover on downs')

    def test_normal_reset_is_unchanged(self):
        self.assertEqual(G.emergency_sack_elapsed(dict(type='sack',yards=0),18,14,reset_draw=0),14)

if __name__=='__main__': unittest.main()
