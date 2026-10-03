"""Real team/drive boundaries for scouting perspective and coordinator skill."""
import copy
import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import adjust as AD
import game as G
import gm_engine as GM
from season import SeasonRunner, make_coach


class FixedRoll:
    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value


def state(prefix='A', skill=.5):
    roster = dict(qb=dict(pid=prefix+'QB', pos='QB'),
                  rb=dict(pid=prefix+'HB', pos='HB'),
                  wr=[dict(pid=prefix+'WR', pos='WR')], te=[], ol=[], k={}, p={},
                  db=[dict(pid=prefix+'CB', pos='CB')], lb=[], dl=[])
    return G.TeamState(roster, coach=dict(adjust_skill=skill, adjust_willingness=1.0))


def watch(st, unit, *, count=10, outcome=None, passes=True, series=2):
    for _ in range(series):
        st.new_series(unit=unit)
    for _ in range(count):
        st.observe(dict(is_pass=passes, depth='deep', scheme='inside_zone'),
                   dict(rushers=5, shell='cover_3'),
                   outcome or dict(type='complete', yards=12, target='AWR'), unit=unit)


class CoachingPerspectiveTests(unittest.TestCase):
    def drive(self, offense, defense):
        G.LAST_KICKOFF.clear()
        outcomes = iter([dict(type='complete', yards=10, target='AWR') for _ in range(5)]
                        + [dict(type='complete', yards=30, target='AWR')])
        with ExitStack() as stack:
            # Only football outcomes/side events are controlled; observe,
            # memory, detection and actual drive boundaries remain live.
            for name in ('penalty_check', 'special_teams_penalty_check', 'fumble_check'):
                stack.enter_context(patch('events.' + name, return_value=None))
            stack.enter_context(patch('health.roll_injury', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda roster, *a, **k: (roster, {})))
            return G.run_drive(offense.roster, defense.roster, 80, 3500, 1, 0,
                    np.random.default_rng(22), lambda *a: dict(next(outcomes)),
                    lambda *a, **k: dict(is_pass=True, depth='deep', personnel='11'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3', shell='cover_3'),
                    lambda *a: .7, off_state=offense, def_state=defense)

    def test_real_drives_only_defense_brackets_opposing_receiver(self):
        a, b = state('A'), state('B')
        self.drive(a, b)
        self.drive(a, b)
        self.assertEqual(a.memories['offense'].recent('targets'),
                         b.memories['defense'].recent('targets'))
        self.assertEqual(len(a.memories['offense'].recent('targets')), 12)
        self.assertEqual(a.memories['defense'].series, 0)
        self.assertEqual(b.memories['offense'].series, 0)
        a.adjust(rng=FixedRoll(), unit='offense')
        b.adjust(rng=FixedRoll(), unit='defense')
        self.assertIsNone(a.plan.bracket)
        self.assertEqual(b.plan.bracket, 'AWR')
        self.assertNotEqual(a.plan.pass_bias, a.base_plan.pass_bias)
        self.assertEqual(b.plan.pass_bias, b.base_plan.pass_bias)

    def test_sacks_change_own_protection_not_defenders_offense(self):
        a, b = state('A'), state('B')
        for st, unit in ((a, 'offense'), (b, 'defense')):
            watch(st, unit, outcome=dict(type='sack', yards=-6))
        a.adjust(rng=FixedRoll(), unit='offense')
        b.adjust(rng=FixedRoll(), unit='defense')
        self.assertNotEqual(a.plan.protection, a.base_plan.protection)
        self.assertEqual(b.plan.protection, b.base_plan.protection)
        self.assertEqual(AD.detect(b.memories['defense'], unit='defense'), {})

    def test_run_and_predictability_have_opposite_perspectives(self):
        a, b = state('A'), state('B')
        for st, unit in ((a, 'offense'), (b, 'defense')):
            watch(st, unit, passes=False, outcome=dict(type='run', yards=8))
        a.adjust(rng=FixedRoll(), unit='offense')
        b.adjust(rng=FixedRoll(), unit='defense')
        self.assertGreater(a.plan.pass_bias, a.base_plan.pass_bias)
        self.assertEqual(a.plan.box_bias, a.base_plan.box_bias)
        self.assertGreater(b.plan.box_bias, b.base_plan.box_bias)
        self.assertEqual(b.plan.pass_bias, b.base_plan.pass_bias)

    def test_sample_gate_window_and_reset_are_per_unit(self):
        st = state()
        watch(st, 'defense', series=1)
        for _ in range(5):
            st.new_series(unit='offense')
        self.assertEqual(AD.detect(st.memories['defense'], unit='defense'), {})
        st.new_series(unit='defense')
        self.assertIn('target', AD.detect(st.memories['defense'], unit='defense'))
        for _ in range(4):
            st.new_series(unit='defense')
        self.assertEqual(AD.detect(st.memories['defense'], unit='defense'), {})
        watch(st, 'offense', outcome=dict(type='sack', yards=-6))
        st.end_game(np.random.default_rng(1))
        self.assertTrue(all(m.series == 0 and not m.by_series for m in st.memories.values()))
        self.assertIsNone(st.last_adjustment)

    def test_save_roundtrip_keeps_perspective_and_ignores_legacy_memory(self):
        st = state()
        st.coach.update(adjust_skill_off=.65, adjust_skill_def=.5)
        st.seq = {'run_hot': 0.0}
        watch(st, 'offense', outcome=dict(type='sack', yards=-6))
        watch(st, 'defense')
        st.adjust(rng=FixedRoll(), unit='defense')
        data = json.loads(json.dumps(SeasonRunner._state_data(st)))
        restored = state()
        SeasonRunner._restore_state(restored, data)
        self.assertEqual(SeasonRunner._state_data(restored), data)
        self.assertEqual(restored.adjustment_skill('offense'), .65)
        self.assertEqual(restored.adjustment_skill('defense'), .5)
        legacy = copy.deepcopy(data)
        legacy['mem'] = legacy.pop('memories')['defense']
        SeasonRunner._restore_state(restored, legacy)
        self.assertTrue(all(m.series == 0 and not m.by_series for m in restored.memories.values()))
        self.assertIsNone(restored.last_adjustment)

    def test_legacy_live_restore_rebuilds_bonuses_before_staff_refresh(self):
        saved = SeasonRunner._state_data(state())
        saved['mem'] = saved.pop('memories')['offense']
        saved['coach_base'] = dict(adjust_skill=.42)
        saved['coach']['adjust_skill'] = .57
        saved['staff_fx'] = dict(sharp_def=True)
        restored = state(skill=.3)
        original = copy.deepcopy(saved)
        SeasonRunner._restore_state(restored, saved)
        self.assertEqual(saved, original)
        self.assertEqual(restored.coach['adjust_skill'], .42)
        self.assertEqual(restored.adjustment_skill('offense'), .42)
        self.assertAlmostEqual(restored.adjustment_skill('defense'), .57)
        # Empty old base must use the caller's GM-derived identity, never the
        # already-boosted legacy total or a hardcoded .5.
        saved['coach_base'] = {}
        restored = state(skill=.3)
        SeasonRunner._restore_state(restored, saved)
        self.assertEqual(restored.adjustment_skill('offense'), .3)
        self.assertAlmostEqual(restored.adjustment_skill('defense'), .45)

    def staff_runner(self, st):
        runner = SeasonRunner.__new__(SeasonRunner)
        runner.states = {'A': st}
        runner.L = NS(teams={'A': NS(gm=None)})
        return runner

    def terms(self, runner, **terms):
        with patch('staff.game_terms', return_value=terms), patch('staff.short_kick_bias', return_value=0):
            runner._staff_terms('A')

    def test_sharp_bonus_is_unit_specific_nonstacking_and_removable(self):
        st = state(); runner = self.staff_runner(st)
        for unit, suffix in (('offense', 'off'), ('defense', 'def')):
            with self.subTest(unit=unit):
                self.terms(runner, **{'sharp_' + suffix: True})
                self.terms(runner, **{'sharp_' + suffix: True})
                self.assertEqual(st.coach['adjust_skill'], .5)
                self.assertEqual(st.adjustment_skill(unit), .65)
                other = 'defense' if unit == 'offense' else 'offense'
                self.assertEqual(st.adjustment_skill(other), .5)
                watch(st, unit, count=4, outcome=dict(type='sack', yards=-6))
                with patch.object(AD, 'detect', wraps=AD.detect) as detection, \
                     patch.object(AD, 'respond', wraps=AD.respond) as response:
                    st.adjust(unit=unit, rng=FixedRoll())
                self.assertEqual(detection.call_args.kwargs['skill'], .65)
                self.assertEqual(response.call_args.kwargs['skill'], .65)
                self.assertEqual(detection.call_args.kwargs['unit'], unit)
        self.terms(runner)
        self.assertEqual(st.adjustment_skill('offense'), .5)
        self.assertEqual(st.adjustment_skill('defense'), .5)

    def test_bonus_changes_detection_threshold_and_success_only_for_its_unit(self):
        threshold = state(skill=.4)
        watch(threshold, 'offense', count=5, outcome=dict(type='sack', yards=-6))
        self.assertEqual(threshold.adjust(unit='offense', rng=FixedRoll()), [])
        self.terms(self.staff_runner(threshold), sharp_off=True)
        self.assertIn('protection', threshold.adjust(unit='offense', rng=FixedRoll()))
        st = state(); runner = self.staff_runner(st)
        self.terms(runner, sharp_off=True)
        # .52 succeeds at .65 skill (threshold .557), fails at .5 (.47).
        trend = {'protection': dict(kind='protection', value='failing', conf=.97, rate=1)}
        with patch.object(AD, 'detect', return_value=trend):
            st.adjust(unit='offense', rng=FixedRoll(.52))
        self.assertNotEqual(st.plan.protection, st.base_plan.protection)
        baseline = state()
        with patch.object(AD, 'detect', return_value=trend):
            baseline.adjust(unit='offense', rng=FixedRoll(.52))
        self.assertEqual(baseline.plan.protection, baseline.base_plan.protection)

    def test_real_drive_counter_punch_uses_offensive_skill(self):
        for sharp, expected in (('sharp_off', .65), ('sharp_def', .5)):
            with self.subTest(sharp=sharp):
                a, b = state('A'), state('B')
                self.terms(self.staff_runner(a), **{sharp: True})
                b.last_adjustment = dict(cost='deep_ball', works=True)
                with patch.object(a, 'adjust', return_value=[]), \
                     patch.object(b, 'adjust', return_value=[]), \
                     patch.object(a, 'adjustment_skill', wraps=a.adjustment_skill) as skill:
                    self.drive(a, b)
                self.assertGreater(skill.call_count, 0)
                self.assertTrue(all(call.args == ('offense',) for call in skill.call_args_list))
                self.assertEqual(a.adjustment_skill('offense'), expected)

    def test_empty_legacy_base_uses_gm_identity_not_old_staff_total(self):
        st = state(skill=.9); st.coach_base = {}
        runner = self.staff_runner(st); runner.L.teams['A'].gm = GM.GM()
        baseline = make_coach(runner.L.teams['A'].gm)['adjust_skill']
        self.terms(runner, sharp_def=True)
        self.assertEqual(st.coach['adjust_skill'], baseline)
        self.assertEqual(st.adjustment_skill('offense'), baseline)
        self.assertEqual(st.adjustment_skill('defense'), min(1, baseline + .15))

    def test_offensive_change_does_not_erase_defensive_counter_punch_context(self):
        st = state()
        watch(st, 'defense')
        st.adjust(unit='defense', rng=FixedRoll())
        defensive_counter = copy.deepcopy(st.last_adjustment)
        watch(st, 'offense', outcome=dict(type='sack', yards=-6))
        st.adjust(unit='offense', rng=FixedRoll())
        self.assertEqual(st.last_adjustment, defensive_counter)
        self.assertEqual(defensive_counter['target'], 'AWR')


if __name__ == '__main__':
    unittest.main()
