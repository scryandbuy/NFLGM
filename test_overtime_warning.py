"""Effective OT periods control warnings without erasing live play time."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import events as E
import game as G


class OvertimeWarning(unittest.TestCase):
    def state(self, period, clock=130, quarter=5):
        dr = G.Drive({}, {}, 61, clock, quarter, -3, None)
        dr.clock_period = period
        dr.clock_running, dr.play_clock, dr.runoff_charged = True, 40, 0
        return dr

    def test_delay_boundary_exact_and_crossed_with_no_duplicate(self):
        for period in (2, 4):
            for start in (120, 130):
                dr = self.state(period, start)
                self.assertFalse(G._delay_clock_expired(dr))
                self.assertEqual(dr.clock, 120)
                self.assertTrue(dr._two_min)
                self.assertEqual(len(dr.log), 1)
                self.assertTrue(G._delay_clock_expired(dr))
                self.assertEqual(len(dr.log), 1)

    def test_delay_does_not_invent_warning_in_first_third_ot(self):
        for period in (1, 3):
            dr = self.state(period)
            self.assertTrue(G._delay_clock_expired(dr))
            self.assertEqual(dr.clock, 90)
            self.assertFalse(getattr(dr, '_two_min', False))
            self.assertEqual(dr.log, [])

    def test_regulation_warning_walls_unchanged(self):
        for quarter, wall in ((2, 1800), (4, 0)):
            dr = self.state(quarter, wall + 130, quarter)
            self.assertFalse(G._delay_clock_expired(dr, wall))
            self.assertEqual(dr.clock, wall + 120)
            self.assertEqual(dr.log, [dict(type='two_minute', clock=wall + 120)])

    def test_kneel_planning_does_not_add_nonexistent_warning(self):
        for period in (1, 2, 3, 4):
            dr = self.state(period)
            pending = G._has_two_minute_warning(dr)
            end, stopped, warning = G._kneel_interval(130, 1, 0, warning_pending=pending)
            self.assertEqual((end, stopped, warning), (120, False, True) if pending else (88, False, False))
            # A live knee crossing the warning still consumes both seconds.
            end, _, warning = G._kneel_interval(121, 1, 0, warning_pending=pending)
            self.assertEqual(end, 119 if pending else 79)

    def test_timeout_choice_cannot_rely_on_nonexistent_free_warning(self):
        for period in (1, 2, 3, 4):
            dr = self.state(period, 123)
            dr.score_diff = 3
            timeouts = G.Timeouts()
            used, side = G._timeout_call(dr, 'complete', dict(type='complete', yards=1),
                                         timeouts, 'home', None, 123)
            self.assertEqual((used, side), (False, None) if period in (2, 4) else (True, 'away'))

    def drive(self, *, period=4, clock=123, live=False, penalty=False, kickoff=None):
        off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                   wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        defense = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        outcomes = iter([dict(type='complete', yards=1, target='wr'),
                         dict(type='complete', yards=1, target='wr'),
                         dict(type='interception', yards=0, air=0, ret=0, target='wr')])
        sent = False
        def flag(rng, **kw):
            nonlocal sent
            if penalty and not sent and kw.get('timing') == 'live':
                sent = True
                return dict(penalty='Offensive Holding', yards=10., rule_yards=10.,
                            on_offense=True, auto_first=False, nullifies=True)
            return None
        G.LAST_KICKOFF.clear()
        if kickoff is not None:
            G.LAST_KICKOFF['r'] = dict(new_yardline=61, clock=kickoff)
        with ExitStack() as stack:
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            stack.enter_context(patch.object(G, '_timeout_call', return_value=(False, None)))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            stack.enter_context(patch.object(G, 'live_play_seconds', return_value=6.))
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=flag))
            stack.enter_context(patch.object(E, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            args = (off, defense, 61, clock, 5, -3, np.random.default_rng(11),
                    lambda *a: dict(next(outcomes)),
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'), lambda *a: .7)
            kw = dict(timeouts=G.Timeouts(), clock_period=period)
            if live:
                steps = G.drive_steps(*args, **kw)
                while True:
                    try:
                        next(steps)
                    except StopIteration as done:
                        dr = done.value
                        break
            else:
                dr = G.run_drive(*args, **kw)
        return dr

    def test_live_play_and_huddle_crossings_use_actual_live_end(self):
        for live in (False, True):
            for period in (2, 4):
                for start, expected in ((123, 117), (126, 120), (140, 120)):
                    with self.subTest(live=live, period=period, start=start):
                        dr = self.drive(period=period, clock=start, live=live)
                        warnings = [p for p in dr.log if p['type'] == 'two_minute']
                        self.assertEqual(warnings, [dict(type='two_minute', clock=expected)])
                        snaps = [p for p in dr.log if p.get('down')]
                        self.assertEqual(snaps[1]['clock'], expected)

    def test_live_and_nullified_plays_do_not_warn_in_first_third_ot(self):
        for live in (False, True):
            for period in (1, 3):
                for penalty in (False, True):
                    dr = self.drive(period=period, live=live, penalty=penalty)
                    self.assertFalse(any(p['type'] == 'two_minute' for p in dr.log))
                    self.assertFalse(getattr(dr, '_two_min', False))

    def test_nullified_live_play_keeps_live_time_and_one_warning(self):
        for live in (False, True):
            for period in (2, 4):
                dr = self.drive(period=period, live=live, penalty=True)
                self.assertTrue(any(p.get('nullified') for p in dr.log))
                self.assertEqual([p for p in dr.log if p['type'] == 'two_minute'],
                                 [dict(type='two_minute', clock=117)])

    def test_kickoff_crossing_only_warns_in_eligible_period_once(self):
        for live in (False, True):
            for period in (1, 2, 3, 4):
                for clock in (120, 117):
                    dr = self.drive(period=period, clock=clock, live=live, kickoff=123)
                    warnings = [p for p in dr.log if p['type'] == 'two_minute']
                    self.assertEqual(warnings, [dict(type='two_minute', clock=clock)] if period in (2, 4) else [])


if __name__ == '__main__':
    unittest.main()
