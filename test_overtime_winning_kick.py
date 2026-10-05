"""Winning overtime kicks retain their clock and legal opportunity context."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G

RATE = lambda *args: .7

class OvertimeWinningKick(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                        wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k=dict(pid='k'), p={})
        self.deff = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        G.LAST_KICKOFF.clear()

    def plan(self, *, winning=True, quarter=5, seconds=24, down=2,
             yardline=3.363813951328183, diff=0, mode='bleed', coach=None):
        dr = NS(quarter=quarter, score_diff=diff, yardline=yardline,
                down=down, field_goal_wins=winning, _plan_mode=mode)
        tos = G.Timeouts(); tos.left = dict(home=0, away=0)
        return G.end_of_half_plan(dr, self.off, self.deff, RATE, tos,
                                 'home', None, seconds, coach=coach)

    def test_sudden_death_kick_has_no_answering_possession_cost(self):
        for quarter in (5, 6):  # regular OT and a postseason continuation
            for coach in ({'fourth_down': 0., 'adjust_willingness': 0.},
                          {'fourth_down': 1., 'adjust_willingness': 1.}):
                p = self.plan(quarter=quarter, coach=coach)
                self.assertEqual(p['choice'], 'kick')
                self.assertTrue(p['hurry'])
                self.assertEqual(p['cost_hurry'], 0)
                self.assertLess(p['p_fg'], 1)

    def test_nonwinning_opening_ot_and_regulation_retain_bleed(self):
        for quarter in (4, 5):
            p = self.plan(winning=False, quarter=quarter)
            self.assertEqual(p['choice'], 'kick')
            self.assertFalse(p['hurry'])
            self.assertGreater(p['cost_hurry'], 0)

    def test_reply_kick_that_takes_lead_is_a_win_not_a_tie(self):
        p = self.plan(diff=-2)
        self.assertEqual(p['choice'], 'kick')
        self.assertEqual(p['evs']['kick'], p['p_fg'])
        regulation = self.plan(winning=False, quarter=4, diff=-2)
        self.assertAlmostEqual(regulation['evs']['kick'],
                               .5 * regulation['p_fg'], delta=.001)

    def test_winning_flag_does_not_force_implausible_long_kick(self):
        for coach in ({'fourth_down': 0.}, {'fourth_down': 1.}):
            p = self.plan(yardline=85, coach=coach)
            self.assertNotEqual(p['choice'], 'kick')

    def drive(self, *, running=False, made=True, live=False, late_conversion=False):
        tos = G.Timeouts(); tos.left = dict(home=0, away=0)
        original = G.Drive
        def constructor(*a):
            dr = original(*a); dr.clock_running = running
            return dr
        resolves = []
        def resolve(*a):
            resolves.append(1)
            return dict(type='complete', yards=-.2, target='wr', touchdown=False)
        def selected_plan(dr, *a, **kw):
            # Isolate the handoff: an actual play was chosen, then its result
            # makes the planner request the winning kick. Existing hurry time
            # must fit without restoring live seconds or requiring a timeout.
            if late_conversion and dr.down == 2:
                return dict(choice='play', hurry=False, quick_play=False)
            return dict(choice='kick', hurry=False, quick_play=False)
        with ExitStack() as stack:
            stack.enter_context(patch.object(G, 'Drive', side_effect=constructor))
            stack.enter_context(patch.object(G, 'kick_flag', return_value=None))
            stack.enter_context(patch.object(G, 'kick_injuries', return_value=[]))
            stack.enter_context(patch.object(G, 'attempt_field_goal', return_value=
                dict(type='field_goal', made=made, points=3 if made else 0, distance=20.4)))
            if late_conversion:
                stack.enter_context(patch.object(G, 'end_of_half_plan', side_effect=selected_plan))
                stack.enter_context(patch('events.penalty_check', return_value=None))
                stack.enter_context(patch('events.fumble_check', return_value=None))
                stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
                stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            args = (self.off, self.deff, 3.363813951328183, 24, 5, 0,
                    np.random.default_rng(11), resolve,
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'), RATE)
            kw = dict(timeouts=tos, pos='home', field_goal_wins=True,
                      clock_period=4, start_state=(2, 3))
            if live:
                gen = G.drive_steps(*args, **kw)
                while True:
                    try: next(gen)
                    except StopIteration as end: dr = end.value; break
            else:
                dr = G.run_drive(*args, **kw)
        return dr, resolves, tos

    def test_selected_kick_before_stopped_or_running_clock_bleed(self):
        for running in (False, True):
            dr, resolves, _ = self.drive(running=running)
            self.assertEqual(resolves, [])
            self.assertEqual(dr.result, 'Field goal')
            self.assertEqual(dr.log[-1]['clock'], 24)
            self.assertEqual(dr.clock, 20)

    def test_six_second_live_play_can_still_reach_kick_without_timeout(self):
        for live in (False, True):
            dr, resolves, tos = self.drive(late_conversion=True, live=live)
            self.assertEqual(len(resolves), 1)
            self.assertEqual(dr.result, 'Field goal')
            self.assertEqual(dr.log[0]['live_seconds'], 6)
            self.assertEqual(dr.log[-1]['type'], 'field_goal')
            self.assertEqual(dr.log[-1]['clock'], 3)
            self.assertEqual(dr.clock, 0)
            self.assertEqual(tos.left, dict(home=0, away=0))

    def test_miss_preserves_remaining_time_and_does_not_award_points(self):
        dr, resolves, _ = self.drive(made=False)
        self.assertEqual(resolves, [])
        self.assertEqual(dr.result, 'Missed field goal')
        self.assertEqual(dr.points, 0)
        self.assertEqual(dr.clock, 20)

    def test_missed_sudden_death_kick_continues_normal_ot(self):
        seen = []
        def drive(*args, **kw):
            seen.append((kw['pos'], args[3], kw['field_goal_wins']))
            if len(seen) == 1:
                return NS(result='Punt', points=0, clock=100, yardline=60,
                          next_yardline=70, log=[], plays=3)
            if len(seen) == 2:
                return NS(result='Missed field goal', points=0, clock=20,
                          yardline=25, log=[], plays=3)
            return NS(result='End of half', points=0, clock=0,
                      yardline=70, down=2, togo=8, log=[], plays=1)
        with patch.object(G, 'kickoff_for', return_value={'new_yardline': 65, 'touchback': True}), \
             patch.object(G, 'run_drive', side_effect=drive):
            score, drives, ending = G.play_overtime(self.off, self.deff,
                dict(home=20, away=20), np.random.default_rng(2), None, None, None,
                RATE, first='away')
        self.assertEqual(seen, [('away',600,False), ('home',100,True), ('away',20,True)])
        self.assertEqual(score, dict(home=20, away=20))
        self.assertEqual(ending, 'tie')

if __name__ == '__main__': unittest.main()

