"""Week 17 blowout decisions share an intent without removing live comebacks."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import game as G
import plays
import test_game_clock_decisions as clocks


class EndgameIntentTests(unittest.TestCase):
    def setUp(self):
        self.kicker = dict(kick_power_rating=95, kick_acc_rating=80, awareness_rating=80)
        self.decline = NS(random=lambda: .999999)

    def test_same_assessment_before_and_after_consolation_score(self):
        self.assertFalse(G.comeback_viable(148, 34))
        self.assertFalse(G.comeback_viable(144, 31))
        for deficit, seconds in ((3, 1), (8, 6), (10, 60), (16, 30), (21, 120), (31, 240)):
            with self.subTest(deficit=deficit, seconds=seconds):
                self.assertTrue(G.comeback_viable(seconds, deficit))

    def test_blowout_does_not_take_desperation_range_kick(self):
        # A good kicker can tempt the old 25% desperation threshold from 63.
        rate = lambda p, w: .9 if 'kick_power_rating' in w else .8
        with patch.object(G.ENV, 'kick_mult', 1):
            self.assertGreater(G.fg_probability(63, {}, rate), .25)
            calls = {G.fourth_down_decision(46, 3, -34, 148,
                        np.random.default_rng(seed), kicker={}, rate_fn=rate)
                     for seed in range(100)}
        self.assertEqual(calls, {'punt', 'go'})

    def test_routine_consolation_kick_is_still_possible(self):
        self.assertEqual(G.fourth_down_decision(14, 8, -34, 148, self.decline,
            kicker=self.kicker, rate_fn=plays.rate), 'field_goal')

    def test_live_comeback_and_overtime_scoring_choices_survive(self):
        for margin, spot, expected in ((-3, 20, 'field_goal'), (-14, 20, 'go'),
                                       (-10, 20, 'field_goal')):
            self.assertEqual(G.fourth_down_decision(spot, 3, margin, 60, self.decline,
                kicker=self.kicker, rate_fn=plays.rate), expected)
        self.assertEqual(G.fourth_down_decision(46, 3, -34, 148, self.decline,
            kicker=self.kicker, rate_fn=plays.rate, must_score=True), 'go')

    def test_no_automatic_timeouts_for_either_side_of_decided_game(self):
        for margin in (-31, 31):
            tos = G.Timeouts()
            dr = NS(quarter=4, score_diff=margin, yardline=51, _two_min=True)
            for seconds in (120, 114, 108):
                used = G._timeout_call(dr, 'run', dict(yards=3), tos, 'home', None,
                    seconds, plan=dict(choice='play', hurry=True))
                self.assertEqual(used, (False, None))
            self.assertEqual(tos.left, dict(home=3, away=3))

    def test_close_game_defensive_timeout_is_preserved(self):
        for margin in (3, 8, 16, 21):
            tos = G.Timeouts()
            dr = NS(quarter=4, score_diff=margin, yardline=51, _two_min=True)
            self.assertEqual(G._timeout_call(dr, 'run', dict(yards=3), tos,
                'home', None, 120), (True, 'away'))
            self.assertEqual(tos.left['away'], 2)

    def test_hurry_planner_and_onside_share_finish_intent(self):
        dr = NS(quarter=4, score_diff=-31)
        self.assertIsNone(G.end_of_half_plan(dr, {}, {}, None, None, 'home', None, 120))
        self.assertFalse(G.multi_score_urgency(120, -31, 4))
        self.assertFalse(G.hurry_for_snap(120, -31, dict(choice='play', hurry=True),
                                        dict(no_huddle=True), quarter=4))
        self.assertFalse(G._onside_call(120, 31, 3, {}, None))
        self.assertTrue(G._onside_call(60, 10, 0, {}, None))
        self.assertTrue(G.hurry_for_snap(120, -21, quarter=4))

    def test_three_score_chase_uses_the_play_call_clock_budget(self):
        # LV began this drive down 17 with 7:43 left. The pass lean already
        # started at 9:00; the clock must not wait until 4:30 to speed up.
        self.assertEqual(G.comeback_clock_budget(17), 540)
        self.assertFalse(G.multi_score_urgency(541, -17, 4))
        self.assertTrue(G.multi_score_urgency(463, -17, 4))
        # The helper takes remaining GAME time, not the quarter clock.
        self.assertFalse(G.multi_score_urgency(900 + 463, -17, 3))
        helper = clocks.ClockDecisions()
        helper.setUp()
        outcomes = [dict(type='complete', yards=10),
                    dict(type='interception', yards=0, air=0, ret=0)]
        intervals = []
        for remaining in (600, 463):
            with self.subTest(seconds=remaining):
                dr, _, _ = helper.drive(outcomes, start=78, clock=remaining,
                                        quarter=4, wall=None, diff=-17)
                snaps = [p for p in dr.log if p.get('down')]
                intervals.append(snaps[0]['clock'] - snaps[1]['clock'])
        # Gradual catch-up now precedes the full urgency threshold.
        self.assertTrue(14 < intervals[0] < 34)
        self.assertEqual(intervals[1], 14)

    def test_live_and_batch_kneels_keep_unused_timeouts(self):
        helper = clocks.ClockDecisions()
        helper.setUp()
        for live in (False, True):
            with self.subTest(live=live):
                dr, _, tos = helper.drive(start=50, clock=120, quarter=4,
                    wall=None, diff=31, own=3, other=3, live=live)
                self.assertEqual([p['clock'] for p in dr.log if p['type'] == 'kneel'],
                                 [120, 78, 36])
                self.assertFalse(any(p['type'] == 'timeout' for p in dr.log))
                self.assertEqual(dr.clock, 0)
                self.assertEqual(tos.left, dict(home=3, away=3))

    def test_blowout_offense_plays_without_forced_hurry_or_timeouts(self):
        helper = clocks.ClockDecisions()
        helper.setUp()
        dr, _, tos = helper.drive([dict(type='complete', yards=10),
            dict(type='interception', yards=0, air=0, ret=0)], start=70, clock=120,
            quarter=4, wall=None, diff=-31, own=3, other=3)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertGreaterEqual(snaps[0]['clock'] - snaps[1]['clock'], 30)
        self.assertEqual(tos.left, dict(home=3, away=3))


if __name__ == '__main__':
    unittest.main()
