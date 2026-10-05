"""Rule 4-3-2(e) penalty restarts follow the effective overtime period."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import events as E
import game as G


class OvertimePenaltyRestart(unittest.TestCase):
    def apply(self, period, clock=240, *, result='complete', before_snap=False,
              was_running=True, timeout=False):
        dr = G.Drive({}, {}, 61, clock, 5, 0, None)
        dr.clock_period = period
        dr.clock_running = was_running
        pen = dict(on_offense=True)
        G._penalty_ready_clock(dr, pen, before_snap=before_snap,
                              was_running=was_running, result=result, timeout=timeout)
        return dr, pen

    def test_live_foul_at_four_minutes_restarts_except_fourth_period(self):
        for period in (1, 2, 3, 4):
            for result in ('complete', 'run'):
                with self.subTest(period=period, result=result):
                    dr, pen = self.apply(period, result=result)
                    self.assertEqual(dr.clock, 240 if period == 4 else 215)
                    self.assertEqual(dr.clock_running, period != 4)
                    self.assertEqual(pen.get('ready_seconds', 0), 0 if period == 4 else 25)

    def test_late_half_threshold_does_not_apply_to_first_third_ot(self):
        for period in (1, 2, 3, 4):
            for clock in (120, 100):
                with self.subTest(period=period, clock=clock):
                    dr, _ = self.apply(period, clock)
                    should_run = period in (1, 3)
                    self.assertEqual(dr.clock, clock - 25 if should_run else clock)
                    self.assertEqual(dr.clock_running, should_run)

    def test_second_ot_ready_interval_stops_at_real_warning(self):
        dr, pen = self.apply(2, 130)
        self.assertEqual(dr.clock, 120)
        self.assertEqual(pen['ready_seconds'], 10)
        self.assertFalse(dr.clock_running)

    def test_offensive_presnap_foul_at_700_follows_period_not_raw_ot_quarter(self):
        for period in (1, 2, 3, 4):
            with self.subTest(period=period):
                dr, _ = self.apply(period, 700, before_snap=True)
                self.assertEqual(dr.clock, 700 if period == 4 else 675)
                self.assertEqual(dr.clock_running, period != 4)

    def test_stopped_clock_incompletion_and_timeout_do_not_gain_ready_runoff(self):
        for period in (1, 2, 3, 4):
            for kwargs in (dict(before_snap=True, was_running=False),
                           dict(result='incomplete'), dict(result='drop'), dict(timeout=True)):
                with self.subTest(period=period, kwargs=kwargs):
                    dr, pen = self.apply(period, **kwargs)
                    self.assertEqual(dr.clock, 240)
                    self.assertFalse(dr.clock_running)
                    self.assertEqual(pen.get('ready_seconds', 0), 0)

    def drive(self, period, result, live):
        off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                   wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        defense = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        outcomes = iter([dict(type=result, yards=8, target='wr'),
                         dict(type='interception', yards=0, air=0, ret=0, target='wr')])
        sent = False
        def flag(rng, **kw):
            nonlocal sent
            if not sent and kw.get('timing') == 'live':
                sent = True
                return dict(penalty='Offensive Holding', yards=10., rule_yards=10.,
                            on_offense=True, auto_first=False, nullifies=True)
            return None
        G.LAST_KICKOFF.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            stack.enter_context(patch.object(G, '_timeout_call', return_value=(False, None)))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            stack.enter_context(patch.object(G, 'live_play_seconds', return_value=6.))
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=flag))
            stack.enter_context(patch.object(E, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            args = (off, defense, 61, 240, 5, 0, np.random.default_rng(11),
                    lambda *a: dict(next(outcomes)),
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'), lambda *a: .7)
            kw = dict(timeouts=G.Timeouts(), clock_period=period, book=G.StatBook())
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

    def test_accepted_holding_drive_keeps_live_seconds_plus_legal_ready_interval(self):
        for live in (False, True):
            for period in (1, 2, 3, 4):
                for result in ('run', 'complete'):
                    with self.subTest(live=live, period=period, result=result):
                        dr = self.drive(period, result, live)
                        self.assertEqual((dr.quarter, dr.clock_period), (5, period))
                        snaps = [p for p in dr.log if p.get('down')]
                        self.assertTrue(snaps[0]['nullified'])
                        self.assertEqual(snaps[1]['yardline'], 71)
                        self.assertEqual((snaps[1]['down'], snaps[1]['ydstogo']), (1, 20))
                        self.assertEqual(snaps[1]['clock'], 234 if period == 4 else 209)
                        self.assertFalse(any(p['type'] in ('timeout', 'two_minute') for p in dr.log))


if __name__ == '__main__':
    unittest.main()
