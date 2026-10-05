"""A defender cannot intercept a ball caught on or beyond the end line."""
import copy
import math
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import coverage as CV
import events as E
import game as G
import plays as P
import targets as T
from test_coverage_recording import offense
from test_defensive_rush import unit, call


class FlightRng:
    """Force flight distance only; all other draws retain a real seeded RNG."""
    def __init__(self, air):
        self.air = air
        self.rng = np.random.default_rng(917)

    def normal(self, loc=0., scale=1., size=None):
        return self.air if size is None else self.rng.normal(loc, scale, size)

    def __getattr__(self, name):
        return getattr(self.rng, name)


class InterceptionEndlineTests(unittest.TestCase):
    def setUp(self):
        self.off = offense()
        self.defense = unit('4-3', 'nickel')
        self.receiver = self.off['wr'][0]
        self.cover = self.defense['db'][0]

    def resolve(self, field, air, return_mode='touchback', exact=True):
        """Reach the real picked-pass branch after controlled catch/coverage."""
        oc = dict(is_pass=True, personnel='11', depth='medium', concept='levels',
                  down=1, ydstogo=10, shotgun=True)
        if exact:
            oc['field_yardline'] = field
        dc = dict(call('4-3', 'nickel'), shell='cover_1', coverage='cover_1', man=True)
        protection = dict(time=10., beaten_by=self.cover['pid'], beaten='LT',
                          pb_reps=[('LT', True)], pb_opportunities=[('LT', 'solo')],
                          pr_reps=[('LE', False)], rush_arrivals=[('LE', 10.)])
        def returned(start, kind, who, chasers, rng, rate):
            # Use the actual return resolver: a stopped end-zone catch is a
            # touchback; a legal long return can still score for the defense.
            from types import SimpleNamespace
            rr = SimpleNamespace(random=lambda: 0. if return_mode == 'touchback' else .99,
                                 exponential=lambda scale: 200.)
            return original(start, kind, who, chasers, rr, rate)
        original = P.defensive_return
        with ExitStack() as stack:
            stack.enter_context(patch.object(P, 'resolve_protection', return_value=protection))
            stack.enter_context(patch.object(CV, 'assign_coverage', return_value=([
                dict(receiver=self.receiver, defender=self.cover, man=True, spot='X')], False)))
            stack.enter_context(patch.object(P, 'resolve_man', return_value=.5))
            stack.enter_context(patch.object(T, 'select_target', return_value=(self.receiver, self.cover, 'first', .5)))
            stack.enter_context(patch.object(E, 'pocket_run_chance', return_value=0.))
            stack.enter_context(patch.object(P, 'throwaway_probability', return_value=0.))
            stack.enter_context(patch.object(P, 'resolve_throw', return_value=dict(
                result='interception', contested=True, p=.6, base=.5, int_roll=0., p_int=1.)))
            returns = stack.enter_context(patch.object(P, 'defensive_return', side_effect=returned))
            result = P.resolve_play(self.off, self.defense, oc, dc, math.ceil(field), FlightRng(air))
        return result, returns

    def test_reported_impossible_catches_are_incomplete_before_return(self):
        for field, air in ((8., 24.), (18.4, 31.), (6.6, 25.8), (24.2, 35.)):
            with self.subTest(field=field, air=air):
                out, ret = self.resolve(field, air)
                ret.assert_not_called()
                self.assertEqual(out['type'], 'incomplete')
                self.assertTrue(out['end_line_incomplete'])
                self.assertTrue(out['out_of_bounds'])
                self.assertFalse(out['throwaway'])
                self.assertIsNone(out['pass_def'])
                self.assertFalse(out['touchdown'])
                self.assertAlmostEqual(out['intended_air'], air)
                for key in ('by', 'ret', 'returner', 'return_start', 'end_spot', 'defensive_td', 'touchback'):
                    self.assertNotIn(key, out)
                for key in ('target', 'passer', 'coverage_evidence', 'pb_reps', 'pr_reps', 'pb_award', 'rush_pressures'):
                    self.assertIn(key, out)

    def test_raw_fractional_boundary_not_rounded_air_decides_legality(self):
        for air, legal in ((23.999, True), (24., False), (24.001, False)):
            with self.subTest(air=air):
                out, ret = self.resolve(14., air)
                self.assertEqual(out['air'], 24.)  # same displayed distance
                self.assertEqual(out['type'], 'interception' if legal else 'incomplete')
                self.assertEqual(ret.call_count, int(legal))
                if legal:
                    self.assertAlmostEqual(ret.call_args.args[0], -9.999)
        # Selection distance ceil(24.2)=25 would wrongly admit this catch.
        out, ret = self.resolve(24.2, 34.3)
        self.assertEqual(out['type'], 'incomplete')
        ret.assert_not_called()

    def test_legacy_direct_resolver_without_exact_spot_uses_supplied_distance(self):
        out, ret = self.resolve(14., 24., exact=False)
        self.assertEqual(out['type'], 'incomplete')
        ret.assert_not_called()

    def test_legal_endzone_interception_can_be_touchback_or_return_td(self):
        for mode in ('touchback', 'touchdown'):
            with self.subTest(mode=mode):
                out, ret = self.resolve(18.4, 23., return_mode=mode)
                self.assertEqual(out['type'], 'interception')
                self.assertAlmostEqual(ret.call_args.args[0], -4.6)
                self.assertEqual(out['by'], self.cover['pid'])
                self.assertNotIn('end_line_incomplete', out)
                self.assertEqual(out['touchback'], mode == 'touchback')
                self.assertEqual(out['defensive_td'], mode == 'touchdown')
                self.assertEqual(out['ret'], 0. if mode == 'touchback' else 100.)

    def test_statbook_records_attempt_without_interception_or_return_score(self):
        out, _ = self.resolve(8., 24.)
        book = G.StatBook()
        book.record(out, self.off, self.defense, np.random.default_rng(1))
        q = book.p[self.off['qb']['pid']]
        self.assertEqual((q['pass_att'], q['pass_cmp'], q['ints'], q['pass_td']), (1, 0, 0, 0))
        for p in book.p.values():
            self.assertEqual(p.get('int_def', 0), 0)
            self.assertEqual(p.get('int_ret_td', 0), 0)
            self.assertEqual(p.get('def_td', 0), 0)

    def drive(self, live=False, flag=None):
        out, _ = self.resolve(18.4, 31.)
        if flag:
            # Independent pass-contact context makes the forced roughing
            # flag eligible; end-line legality must not suppress that foul.
            out['pressured'] = True
        seen, contexts = [], []
        def resolution(off, defense, oc, dc, ytg, rng):
            seen.append((oc.get('field_yardline'), ytg))
            return copy.deepcopy(out)
        def penalty(rng, **kw):
            contexts.append(kw)
            if kw.get('timing') == 'live' and flag and sum(x.get('timing') == 'live' for x in contexts) == 1:
                return copy.deepcopy(flag)
            return None
        book = G.StatBook()
        with ExitStack() as stack:
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=penalty))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros,*a,**k: (ros, {})))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc,*a,**k: (oc, None)))
            args = (self.off, self.defense, 18.4, 1., 4, -7, np.random.default_rng(18),
                    resolution, lambda *a,**k: dict(is_pass=True,personnel='11',depth='medium'),
                    lambda *a,**k: dict(personnel='nickel',front_family='4-3'), P.rate)
            if live:
                gen = G.drive_steps(*args, book=book)
                while True:
                    try: next(gen)
                    except StopIteration as done:
                        dr = done.value
                        break
            else:
                dr = G.run_drive(*args, book=book)
        return dr, book, seen, contexts

    def test_exact_spot_reaches_live_and_fast_and_incompletion_ends_clock(self):
        fast = self.drive(); live = self.drive(live=True)
        self.assertEqual(fast[2][0], (18.4, 19))
        self.assertEqual(fast[0].log, live[0].log)
        self.assertEqual(fast[1].p, live[1].p)
        self.assertEqual(fast[0].points, 0)
        self.assertFalse(any(p.get('type') == 'interception' for p in fast[0].log))
        self.assertEqual(fast[1].p['Q']['ints'], 0)

    def test_live_defensive_foul_still_gets_its_normal_enforcement(self):
        flag = dict(penalty='Roughing the Passer', on_offense=False, yards=15,
                    rule_yards=15, auto_first=True, nullifies=False)
        dr, book, seen, contexts = self.drive(flag=flag)
        self.assertTrue(any(p.get('type') == 'penalty' and p.get('penalty') == flag['penalty'] for p in dr.log))
        self.assertEqual(book.p['Q']['ints'], 0)
        self.assertEqual(dr.points, 0)
        self.assertTrue(all(x['outcome']['type'] == 'incomplete' for x in contexts if x.get('timing') == 'live'))

    def test_two_point_try_passes_exact_fractional_field_distance(self):
        seen = []
        def resolve(off, defense, oc, dc, ytg, rng):
            seen.append((oc.get('field_yardline'), ytg))
            return dict(type='incomplete', yards=0., touchdown=False, end_line_incomplete=True)
        with patch.object(E, 'special_teams_penalty_check', return_value=None), \
             patch.object(G, 'field_units', side_effect=lambda ros,*a,**k: (ros, {})):
            result = G.attempt_two_point(self.off, self.defense, np.random.default_rng(14),
                resolve, lambda *a,**k: dict(is_pass=True,personnel='11'),
                lambda *a,**k: dict(personnel='nickel'), P.rate, start_yardline=1.4)
        self.assertEqual(seen, [(1.4, 2)])
        self.assertFalse(result.get('good'))


if __name__ == '__main__':
    unittest.main()
