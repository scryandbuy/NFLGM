"""Voluntary QB endings must agree in risk, book, clock and narration."""
import copy
import unittest
import math
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import events as E
import game as G
import plays as P
import ticker
from test_qb_escape_workload import ScrambleWorkload
from test_designed_qb_runs import offense
from test_defensive_rush import unit


class QBContactIntegration(unittest.TestCase):
    def test_safe_escape_keeps_running_work_without_carrier_hit_or_fake_tackle(self):
        fixture = ScrambleWorkload()
        ordinary = fixture.drive('escape', short=True)
        def safe(out, *args, **kwargs):
            out.update(run_end='slide', contact_avoided=True,
                       ended_without_contact=True, out_of_bounds=False)
            out.pop('tackler', None)
            return out
        with patch.object(G.QC, 'apply', side_effect=safe):
            safe_result = fixture.drive('escape', short=True)
            live = fixture.drive('escape', short=True, live=True)
        state, dr, book, hits = safe_result
        self.assertEqual(state.cond.get('QB'), ordinary[0].cond.get('QB'))
        self.assertEqual(state.snaps['QB'], 1)
        self.assertEqual(hits[0][1], 1.)
        self.assertEqual(book.p['QB']['rush_att'], 1)
        self.assertEqual(sum(p.get('tackles', 0) for p in book.p.values()), 0)
        self.assertEqual(dr.log, live[1].log)
        self.assertEqual(book.p, live[2].p)

    def test_avoiding_contact_removes_forced_component_but_not_loose_ball_risk(self):
        class Draws:
            def __init__(self, values): self.values = iter(values)
            def random(self): return next(self.values)
        qb = offense()['qb']
        safe = E.fumble_check(qb, 'scramble', Draws([0., 0.]), P.rate,
                              contact=False, hit_power=1.)
        self.assertIsNotNone(safe)
        self.assertFalse(safe['forced'])
        self.assertTrue(safe['lost'])
        # A draw between the unforced and full chances distinguishes the risk.
        with patch.object(E, 'FUMBLE_RATE', {'scramble': .1}):
            rating = lambda *args: .7
            self.assertIsNone(E.fumble_check(qb, 'scramble', Draws([.05]), rating, contact=False))
            self.assertIsNotNone(E.fumble_check(qb, 'scramble', Draws([.05, .9, .1]), rating))

    def test_loose_ball_supersedes_proposed_safe_ending_and_no_forced_credit(self):
        off, deff = offense(), unit('4-3', 'nickel')
        out = dict(type='scramble', yards=6., carrier_pid=off['qb']['pid'],
                   run_end='out_of_bounds', out_of_bounds=True,
                   contact_avoided=True, ended_without_contact=True)
        with patch.object(E, 'fumble_check', return_value=dict(lost=False, forced=False)) as check:
            G._prepare_fumble(NS(yardline=50), out, off, deff, np.random.default_rng(1), P.rate)
        self.assertFalse(check.call_args.kwargs['contact'])
        self.assertEqual(out['run_end'], 'loose_ball')
        self.assertFalse(out['out_of_bounds'])
        self.assertFalse(out['fumble_forced'])

    def test_late_oob_does_not_spend_timeout_but_slide_can(self):
        dr = NS(quarter=4, clock_period=4, score_diff=-3, yardline=40,
                down=1, togo=10, _two_min=True)
        out = dict(type='scramble', yards=5.)
        tos = G.Timeouts()
        original = copy.deepcopy(tos.left)
        used, _ = G._timeout_call(dr, 'scramble', dict(out, out_of_bounds=True),
                                  tos, 'home', None, 30)
        self.assertFalse(used); self.assertEqual(tos.left, original)
        used, who = G._timeout_call(dr, 'scramble', dict(out, run_end='slide'),
                                    tos, 'home', None, 30)
        self.assertTrue(used); self.assertEqual(who, 'home')

    def test_narration_names_ending_without_tackle(self):
        league = NS(player=lambda pid: NS(name=pid))
        for kind in ('run', 'scramble'):
            for ending, text in (('slide', 'Slides'), ('out_of_bounds', 'Steps out')):
                out = dict(type=kind, run_end=ending, carrier='QB', passer='QB',
                           qb_run=True, yards=5, yardline=40)
                line = ticker.play_line(league, out, 'GB', 'CHI')['text']
                self.assertIn(text, line)
                self.assertNotIn('Tackled', line)

    def test_actual_coach_preference_reaches_breather_policy(self):
        s = G.TeamState({}, coach={'starter_protection': .9})
        self.assertEqual(s.cond.breather_policy, .9)
        restored = G.TeamState({}, coach=s.coach)
        self.assertEqual(restored.cond.breather_policy, s.cond.breather_policy)
        s.coach = {'starter_protection': .1}
        s.refresh_rotation_policy()
        self.assertEqual(s.cond.breather_policy, .1)

    def test_unflagged_actual_qb_carry_receives_running_work_once(self):
        fixture = ScrambleWorkload()
        # Fixture returns an actual QB run while the call carries no qb_run
        # flag: the same contract as a run from an empty backfield.
        actual = fixture.drive('run')
        designed = fixture.drive('designed')
        self.assertEqual(actual[0].cond.get('QB'), designed[0].cond.get('QB'))
        self.assertEqual(actual[0].snaps['QB'], 1)
        play = next(p for p in actual[1].log if p.get('type') == 'run')
        self.assertTrue(play['qb_run'])
        self.assertEqual(play['qb_run_reason'], 'called_run')

    def test_two_point_actual_qb_carry_has_one_running_workload(self):
        import health as H
        off, deff = offense(), unit('4-3', 'nickel')
        state, dst = G.TeamState(off), G.TeamState(deff)
        with patch.object(E, 'special_teams_penalty_check', return_value=None):
            G.attempt_two_point(off, deff, np.random.default_rng(1),
                lambda *args: dict(type='run', yards=2, carrier_pid=off['qb']['pid']),
                lambda *a, **kw: dict(is_pass=False, personnel='11'),
                lambda *a, **kw: dict(personnel='nickel', front_family='4-3'),
                P.rate, off_state=state, def_state=dst)
        expected = H.Condition(); expected.play(off['qb']['pid'], 'HB', off['qb'].get('stamina_rating', 70.))
        self.assertEqual(state.cond.get(off['qb']['pid']), expected.get(off['qb']['pid']))
        self.assertEqual(state.snaps[off['qb']['pid']], 1)

    def test_actual_drive_obeys_oob_clock_and_overtime_period(self):
        def first_snap(clock, quarter, end, clock_period=None, steps=1):
            off, deff = offense(), unit('4-3', 'nickel')
            tos = G.Timeouts(); tos.left = {'home': 0, 'away': 0}
            out = dict(type='scramble', yards=6., carrier_pid=off['qb']['pid'],
                       run_end=end, out_of_bounds=end == 'out_of_bounds',
                       contact_avoided=True, ended_without_contact=True)
            G.LAST_KICKOFF.clear()
            with ExitStack() as stack:
                stack.enter_context(patch.object(E, 'penalty_check', return_value=None))
                stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
                stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **kw: (oc, None)))
                gen = G.drive_steps(off, deff, 70., clock, quarter, -7,
                    np.random.default_rng(5), lambda *a: dict(out),
                    lambda *a, **kw: dict(is_pass=True, personnel='11'),
                    lambda *a, **kw: dict(personnel='nickel', front_family='4-3'),
                    P.rate, timeouts=tos, clock_period=clock_period)
                for _ in range(steps): event, dr = next(gen)
                gen.close()
            self.assertEqual(event, 'snap')
            play = next(p for p in dr.log if p.get('type') == 'scramble')
            return dr, play
        late, play = first_snap(250., 4, 'out_of_bounds')
        self.assertEqual(late.clock, math.ceil(250. - play['live_seconds']))
        self.assertFalse(late.clock_running)
        slide, _ = first_snap(250., 4, 'slide')
        self.assertLess(slide.clock, late.clock)
        self.assertTrue(slide.clock_running)
        early, play = first_snap(500., 4, 'out_of_bounds')
        self.assertLess(early.clock, 500. - play['live_seconds'])
        self.assertTrue(early.clock_running)
        playoff_first, _ = first_snap(250., 5, 'out_of_bounds', 1)
        regular, _ = first_snap(250., 5, 'out_of_bounds', 4)
        self.assertTrue(playoff_first.clock_running)
        self.assertFalse(regular.clock_running)
        crossed, _ = first_snap(904., 3, 'slide', steps=2)
        self.assertEqual(crossed.quarter, 4)
        self.assertEqual(crossed.clock_period, 4)

    def test_recovery_save_restore_preserves_participation_and_current_coach(self):
        from season import SeasonRunner
        s = G.TeamState({}, coach={'starter_protection': .2})
        s.cond.cond['edge'] = 81.
        s.recovery_events = 8; s.recovery_accounted = {'edge': 8}
        saved = SeasonRunner._state_data(s)
        restored = G.TeamState({}, coach={'starter_protection': .9})
        SeasonRunner._restore_state(restored, saved)
        self.assertEqual(restored.recovery_events, 8)
        self.assertEqual(restored.recovery_accounted, {'edge': 8})
        self.assertEqual(restored.cond.breather_policy, .2)
        before = G._recovery_start(restored)
        G._recovery_finish(before)
        self.assertEqual(restored.cond.get('edge'), 81.)


if __name__ == '__main__': unittest.main()
