import unittest
from unittest.mock import patch
import game as G
import test_game_clock_decisions as clocks

class LateHalfKickSetup(unittest.TestCase):
    def replay(self, seconds=21, yards=36, live=False, air=20, own=0):
        h=clocks.ClockDecisions(); h.setUp()
        return h.drive([dict(type='complete', yards=yards, ttt=3, air=air)],
            start=54, clock=1800+seconds, diff=-4, own=own, other=3,
            down=3, live=live)

    def test_conversion_can_preserve_first_down_kick(self):
        for live in (False, True):
            for air, expected in ((20,1805), (5,1803)):
                dr,_,_=self.replay(live=live,air=air)
                kicks=[p for p in dr.log if p['type']=='field_goal']
                self.assertEqual(len(kicks),1)
                self.assertEqual((kicks[0]['clock'],kicks[0]['down'],kicks[0]['distance']),
                                 (expected,1,35))

    def test_not_enough_time_still_expires(self):
        dr,_,_=self.replay(seconds=12)
        self.assertEqual(dr.result,'End of half')
        self.assertFalse(any(p['type']=='field_goal' for p in dr.log))

    def test_coach_can_prefer_attack(self):
        real=G.end_of_half_plan
        def attack(*a,**kw):
            result=real(*a,**kw)
            if result is not None: result=dict(result,choice='shot',hurry=True)
            return result
        with patch.object(G,'end_of_half_plan',side_effect=attack):
            dr,_,_=self.replay()
        self.assertFalse(any(p['type']=='field_goal' for p in dr.log))

    def test_live_play_cannot_restore_expired_time(self):
        dr,_,_=self.replay(seconds=6)
        self.assertEqual(dr.clock,1800)
        self.assertFalse(any(p['type']=='field_goal' for p in dr.log))
