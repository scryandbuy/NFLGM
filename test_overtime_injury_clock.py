"""Post-warning injury administration follows the overtime clock period."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import events
import game as G


class OvertimeInjuryClock(unittest.TestCase):
    def injury(self, quarter, period=None, *, side='off', available=1,
               warning=True, foul=False, kind='complete'):
        wall = 1800 if quarter == 2 else 0
        dr = G.Drive({}, {}, 53, wall + 90, quarter, -3, None)
        if period is not None:
            dr.clock_period = period
        dr._two_min = warning
        tos = G.Timeouts()
        tos.left = dict(home=available, away=available)
        half_end = None if quarter == 5 else wall
        applied = G._injury_timeout(dr, [dict(side=side)], dict(type=kind),
                                    tos, 'home', half_end, wall + 84, foul=foul)
        return dr, tos, applied, wall

    def test_regulation_second_and_fourth_periods_still_charge_injury_timeout(self):
        for quarter in (2, 4):
            for period in (None, quarter):
                with self.subTest(quarter=quarter, period=period):
                    dr, tos, applied, wall = self.injury(quarter, period)
                    self.assertTrue(applied)
                    self.assertEqual(tos.left, dict(home=0, away=1))
                    self.assertEqual(dr.clock, wall + 84)
                    self.assertFalse(dr.clock_running)
                    self.assertEqual(dr.log[0]['reason'], 'injury')

    def test_regular_overtime_charges_available_timeout_to_injured_side(self):
        for side, charged in (('off', 'home'), ('def', 'away')):
            dr, tos, applied, _ = self.injury(5, 4, side=side)
            self.assertTrue(applied)
            self.assertEqual(tos.left[charged], 0)
            self.assertEqual(sum(tos.left.values()), 1)
            self.assertEqual(dr.clock, 84)
            self.assertFalse(dr.log[0]['excess'])

    def test_regular_overtime_excess_offensive_injury_has_runoff_and_repeat_penalty(self):
        dr, tos, applied, _ = self.injury(5, 4, available=0)
        self.assertTrue(applied)
        self.assertTrue(dr.log[0]['excess'])
        self.assertEqual([p['seconds'] for p in dr.log if p['type'] == 'injury_runoff'], [10])
        self.assertLessEqual(dr.clock, 74)
        self.assertTrue(G._injury_timeout(dr, [dict(side='off')], dict(type='complete'),
                                        tos, 'home', None, 50))
        self.assertEqual((dr.yardline, dr.togo, dr.down), (58, 15, 1))
        self.assertEqual(len([p for p in dr.log if p['type'] == 'penalty']), 1)

    def test_excess_defense_and_stopped_clock_have_no_offensive_runoff(self):
        for kwargs in (dict(side='def'), dict(kind='incomplete'), dict(foul=True)):
            dr, _, applied, _ = self.injury(5, 4, available=0, **kwargs)
            self.assertTrue(applied)
            self.assertFalse(any(p['type'] == 'injury_runoff' for p in dr.log))
            self.assertEqual(dr.clock, 84)

    def test_postseason_effective_first_third_and_pre_warning_are_exempt(self):
        for quarter, period, warning in ((5, 1, True), (5, 3, True), (5, 4, False)):
            dr, tos, applied, _ = self.injury(quarter, period, warning=warning)
            self.assertFalse(applied)
            self.assertEqual(tos.left, dict(home=1, away=1))
            self.assertEqual(dr.log, [])

    def test_postseason_effective_second_and_fourth_administer_injury_rule(self):
        for period in (2, 4):
            dr, tos, applied, _ = self.injury(5, period)
            self.assertTrue(applied)
            self.assertEqual(tos.left['home'], 0)
            self.assertEqual(dr.log[0]['reason'], 'injury')

    def drive(self, *, live, period=4, available=1, side='def'):
        off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                   wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        defense = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        states = G.TeamState(off), G.TeamState(defense)
        tos = G.Timeouts()
        tos.left = dict(home=available, away=available)
        outcomes = iter([dict(type='complete', yards=8, target='wr'),
                         dict(type='interception', yards=0, air=0, ret=0, target='wr')])
        hurt_once = iter([dict(kind='ankle', weeks_out=1)])

        def hurt(*args, **kwargs):
            return next(hurt_once, None)

        G.LAST_KICKOFF.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(states[0], 'hurt', side_effect=hurt if side == 'off' else None,
                                             return_value=None))
            stack.enter_context(patch.object(states[1], 'hurt', side_effect=hurt if side == 'def' else None,
                                             return_value=None))
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            stack.enter_context(patch.object(G, '_timeout_call', return_value=(False, None)))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            stack.enter_context(patch.object(events, 'penalty_check', return_value=None))
            stack.enter_context(patch.object(events, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(events, 'fumble_check', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            # The production OT driver always uses raw quarter=5, including
            # later playoff periods, and does not pass a regulation half wall.
            args = (off, defense, 61, 90, 5, -3, np.random.default_rng(11),
                    lambda *a: dict(next(outcomes)),
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'), lambda *a: .7)
            kwargs = dict(book=G.StatBook(), timeouts=tos,
                          off_state=states[0], def_state=states[1], clock_period=period)
            if live:
                steps = G.drive_steps(*args, **kwargs)
                while True:
                    try:
                        next(steps)
                    except StopIteration as done:
                        dr = done.value
                        break
            else:
                dr = G.run_drive(*args, **kwargs)
        return dr, tos

    def test_new_regular_ot_possession_below_warning_administers_actual_injury(self):
        for live in (False, True):
            with self.subTest(live=live):
                dr, tos = self.drive(live=live)
                injuries = [p for p in dr.log if p['type'] == 'injury']
                self.assertEqual([(p['pid'], p['side'], p['weeks']) for p in injuries], [('cb', 'def', 1)])
                self.assertEqual(tos.left, dict(home=1, away=0))
                charged = [p for p in dr.log if p['type'] == 'timeout']
                self.assertEqual([(p['reason'], p['clock']) for p in charged], [('injury', 84)])
                snaps = [p for p in dr.log if p.get('down')]
                self.assertEqual(snaps[1]['clock'], 84)

    def test_actual_overtime_drive_excess_injury_runoff_live_and_fast(self):
        for live in (False, True):
            dr, tos = self.drive(live=live, available=0, side='off')
            self.assertTrue(any(p['type'] == 'injury' and p['pid'] == 'qb' for p in dr.log))
            self.assertEqual(tos.left, dict(home=0, away=0))
            self.assertEqual([p['seconds'] for p in dr.log if p['type'] == 'injury_runoff'], [10])
            snaps = [p for p in dr.log if p.get('down')]
            self.assertLessEqual(snaps[1]['clock'], 74)

    def test_postseason_drive_charges_only_effective_second_or_fourth(self):
        for period in (1, 2, 3, 4):
            for live in (False, True):
                dr, tos = self.drive(live=live, period=period)
                self.assertEqual((dr.quarter, dr.clock_period), (5, period))
                self.assertTrue(any(p['type'] == 'injury' for p in dr.log))
                expected = 0 if period in (2, 4) else 1
                self.assertEqual(tos.left['away'], expected)
                self.assertEqual(len([p for p in dr.log if p['type'] == 'timeout']), 1 - expected)


if __name__ == '__main__':
    unittest.main()
