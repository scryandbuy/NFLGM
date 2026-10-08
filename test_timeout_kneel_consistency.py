import unittest
from types import SimpleNamespace as NS
import game as G
import test_game_clock_decisions as clocks

class TimeoutKneelConsistency(unittest.TestCase):
    def test_tied_sack_does_not_buy_a_kneel(self):
        for live in (False, True):
            h = clocks.ClockDecisions(); h.setUp()
            dr, _, tos = h.drive([dict(type='sack', yards=-5, ttt=3)],
                start=71, clock=9, quarter=4, wall=None, diff=0,
                own=3, other=3, live=live)
            self.assertFalse(any(p['type'] == 'timeout' for p in dr.log))
            self.assertEqual(tos.left, dict(home=3, away=3))
            self.assertEqual(dr.clock, 0)

    def test_explicit_attack_can_still_stop_clock(self):
        for choice in ('shot', 'kick', 'play'):
            tos = G.Timeouts()
            dr = NS(down=1, togo=10, yardline=71, score_diff=0)
            used, who = G._timeout_call(dr, 'sack',
                dict(type='sack', yards=-5, ttt=3), tos, 'home', None, 9,
                plan=dict(choice=choice, hurry=True))
            self.assertTrue(used)
            self.assertEqual(who, 'home')

    def test_kneel_plan_does_not_spend_timeout_even_if_hurry_is_set(self):
        for diff in (0, -3):
            tos = G.Timeouts()
            dr = NS(down=1, togo=10, yardline=71, score_diff=diff)
            used, _ = G._timeout_call(dr, 'sack',
                dict(type='sack', yards=-5, ttt=3), tos, 'home', None, 9,
                plan=dict(choice='kneel', hurry=True))
            self.assertFalse(used)
            self.assertEqual(tos.left['home'], 3)
