"""SEA-GB Week 13: a Q3 illegal shift cannot stop a snap like a false start."""
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest

import numpy as np
import events as E
import game as G
import ticker
from test_penalty_discipline import rates


class PickFoul:
    def __init__(self, name):
        self.name = name

    def random(self):
        return 0.

    def choice(self, options, p):
        if isinstance(options, int):
            return 0  # select a real eligible offender
        index = E._names.index(self.name)
        assert p[list(options).index(index)] > 0, 'foul unavailable in this phase'
        return index


class IllegalShiftTests(unittest.TestCase):
    def flag(self, name='Illegal Shift', timing='live', **kw):
        return E.penalty_check(PickFoul(name), timing=timing, **kw)

    def drive(self, outcomes, *, live=False, clock=1572, quarter=3,
              half_end=None, name='Illegal Shift', start=45, down=1):
        off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                   wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        deff = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        book = G.StatBook()
        tos = G.Timeouts()
        plays = iter(outcomes)
        real_check = E.penalty_check
        phase = 'pre' if name == 'False Start' else 'live'
        sent = False
        def check(rng, **kw):
            nonlocal sent
            if sent or kw.get('timing') != phase:
                return None
            sent = True
            return real_check(PickFoul(name), **kw)
        original_drive = G.Drive
        def make(*args):
            dr = original_drive(*args)
            dr.down = down
            return dr
        G.LAST_KICKOFF.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=check))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch.object(E, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(G, 'Drive', side_effect=make))
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            stack.enter_context(patch.object(G, 'attempt_extra_point', return_value=dict(type='extra_point', points=1, made=True)))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            args = (off, deff, start, clock, quarter, 0, np.random.default_rng(81),
                    lambda *a: dict(target='wr', **next(plays)),
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                    lambda *a: .7)
            kwargs = dict(book=book, timeouts=tos, half_end=half_end)
            if live:
                steps = G.drive_steps(*args, **kwargs)
                while True:
                    try: next(steps)
                    except StopIteration as end:
                        dr = end.value
                        break
            else:
                dr = G.run_drive(*args, **kwargs)
        return dr, book

    def test_shift_only_live_for_both_run_and_pass(self):
        for is_pass in (True, False):
            with self.subTest(is_pass=is_pass):
                pre = rates(timing='pre', is_pass=is_pass)
                live = rates(timing='live', is_pass=is_pass)
                self.assertEqual(pre.get('Illegal Shift', 0), 0)
                self.assertGreater(live['Illegal Shift'], 0)
                flag = self.flag(is_pass=is_pass)
                self.assertFalse(flag['nullifies'])
                self.assertEqual(flag['yards'], 5)

    def test_rate_and_discipline_preserved_across_split_checks(self):
        for discipline in (.5, .7, .9):
            pre = rates(timing='pre', offense_discipline=discipline)
            live = rates(timing='live', offense_discipline=discipline)
            actual = (1 - sum(pre.values())) * live['Illegal Shift']
            expected = .136 / E.SCRIMMAGE_PLAYS_PER_GAME * (1 + 1.6 * (.7 - discipline))
            self.assertAlmostEqual(actual, expected, places=8)

    def test_accepted_shift_runs_play_repeats_down_erases_stats_and_charges_live_time(self):
        for live in (False, True):
            with self.subTest(live=live):
                dr, book = self.drive([dict(type='complete', yards=8), dict(type='complete', yards=50)], live=live)
                snaps = [p for p in dr.log if p.get('down')]
                self.assertTrue(snaps[0]['nullified'])
                self.assertEqual((snaps[1]['down'], snaps[1]['ydstogo'], snaps[1]['yardline']), (1, 15, 50))
                self.assertEqual(snaps[0]['clock'] - snaps[1]['clock'], 31)
                self.assertEqual(dr.plays, 1)
                self.assertEqual(book.p['qb']['pass_att'], 1)
                self.assertEqual(book.p['qb']['pass_yds'], 50)
                flag = next(p for p in dr.log if p['type'] == 'penalty')
                self.assertNotEqual(flag.get('timing'), 'before_snap')
                self.assertTrue(flag['accepted'])
                self.assertEqual(flag['offender_pid'], 'rb')
                text = ticker.play_line(NS(player=lambda pid: None), flag, 'SEA', 'GB')['text']
                self.assertNotIn('before the next snap', text)

    def test_defense_declines_shift_on_interception_and_turnover_stands(self):
        for live in (False, True):
            dr, book = self.drive([dict(type='interception', yards=0, air=10, ret=3, by='cb')], live=live)
            snap = next(p for p in dr.log if p.get('down'))
            self.assertTrue(snap['declined_penalty']['declined'])
            self.assertFalse(snap.get('nullified'))
            self.assertEqual(dr.result, 'Turnover')
            self.assertEqual(book.p['qb']['ints'], 1)
            self.assertEqual(dr.plays, 1)

    def test_failed_fourth_down_can_stand(self):
        dr = G.Drive({}, {}, 60, 600, 4, 0, None)
        dr.down = 4
        self.assertIsNone(G._resolve_live_penalty(dr, self.flag(), dict(type='incomplete', yards=0), {}))
        self.assertEqual((dr.down, dr.yardline), (4, 60))

    def test_half_distance_at_own_goal(self):
        dr = G.Drive({}, {}, 98, 600, 4, 0, None)
        flag = self.flag()
        self.assertEqual(G._resolve_live_penalty(dr, flag, dict(type='complete', yards=10), {}), 'replaced')
        self.assertEqual((dr.down, dr.togo, dr.yardline, flag['yards']), (1, 11, 99, 1))

    def test_touchdown_is_erased_not_added_to_try(self):
        dr, book = self.drive([dict(type='complete', yards=45), dict(type='complete', yards=50)])
        snaps = [p for p in dr.log if p.get('down')]
        self.assertTrue(snaps[0]['nullified'])
        self.assertEqual(book.p['qb']['pass_td'], 1)
        self.assertEqual(dr.points, 7)
        self.assertFalse(getattr(dr, 'try_penalty', None))

    def test_late_half_shift_is_still_live_and_has_no_artificial_runoff(self):
        for clock, quarter, wall in ((1860, 2, 1800), (60, 4, None)):
            for live in (False, True):
                with self.subTest(clock=clock, live=live):
                    dr, _ = self.drive([dict(type='complete', yards=8), dict(type='complete', yards=50)],
                                        clock=clock, quarter=quarter, half_end=wall, live=live)
                    snaps = [p for p in dr.log if p.get('down')]
                    self.assertEqual(snaps[1]['clock'], clock - 6)
                    flag = next(p for p in dr.log if p['type'] == 'penalty')
                    self.assertEqual(flag['penalty'], 'Illegal Shift')

    def test_false_start_path_remains_distinct_and_prevents_snap(self):
        flag = self.flag('False Start', timing='pre')
        self.assertTrue(flag['nullifies'])
        dr, book = self.drive([dict(type='complete', yards=50)], clock=60, quarter=4, name='False Start')
        snap = next(p for p in dr.log if p.get('down'))
        self.assertEqual(snap['clock'], 60)
        self.assertEqual(snap['ydstogo'], 15)
        self.assertEqual(dr.log[0]['timing'], 'before_snap')
        self.assertEqual(book.p['qb']['pass_att'], 1)


if __name__ == '__main__':
    unittest.main()
