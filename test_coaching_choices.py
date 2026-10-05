import copy
import itertools
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

import coaching_choices as CC
import gameplan_week as GW
import gameplan as GP
import halftime as HT
import views_gameplan as VG
from test_pregame_protection import team


def suggestion(text, changes, priority, side='defence'):
    return dict(text=text, why=text + ' evidence', changes=changes,
                side=side, _priority=priority)


class CoherenceChecks:
    def coherent(self, rows):
        for a, b in itertools.combinations(rows, 2):
            self.assertFalse(CC.conflicts(a, b), (a['text'], b['text']))


class ResolutionTests(CoherenceChecks, unittest.TestCase):
    def test_combined_evidence_beats_one_stronger_candidate_and_reverses(self):
        rows = [suggestion('box', {'box_bias': .12}, 4),
                suggestion('PA', {'box_bias': -.05, 'zone_aggression': -.15}, 3),
                suggestion('deep', {'shell_lean': .15}, 3),
                suggestion('shadow', {'travel': True, 'bracket': 'wr'}, 1)]
        original = copy.deepcopy(rows)
        for order in itertools.permutations(rows):
            result = CC.resolve(order)
            self.assertEqual({r['text'] for r in result}, {'PA', 'deep', 'shadow'})
            self.coherent(result)
        self.assertEqual(rows, original)
        rows[0]['_priority'] = 7
        result = CC.resolve(rows)
        self.assertEqual({r['text'] for r in result}, {'box', 'shadow'})
        self.assertEqual(len(result[0]['alternatives_weighed']), 2)
        self.assertNotIn('_priority', result[0])

    def test_direct_depth_category_and_alias_conflicts(self):
        cases = [({'depth_mix': (.05, 0, -.05)}, {'depth_mix': (-.05, 0, .05)}),
                 ({'screen_boost': .03}, {'screen_boost': -.05}),
                 ({'blitz_rate': .05}, {'blitz_lean': -.04}),
                 ({'protection': 'six'}, {'protection': 'empty'}),
                 ({'man_rate': .08}, {'man_rate': -.06})]
        for a, b in cases:
            with self.subTest(a=a):
                result = CC.resolve([suggestion('A', a, 2), suggestion('B', b, 3)])
                self.assertEqual([r['text'] for r in result], ['B'])

    def test_limit_selects_important_late_candidate(self):
        rows = [suggestion(str(i), {'motion_rate': .02}, 1, 'offence') for i in range(6)]
        rows.append(suggestion('hurry', {'tempo': .2}, 7, 'offence'))
        result = CC.resolve(rows, limit=6)
        self.assertEqual(len(result), 6)
        self.assertIn('hurry', [r['text'] for r in result])


class PregameChoices(CoherenceChecks, unittest.TestCase):
    def setUp(self):
        self.me, self.opp = team('GB'), team('KC')
        self.opp.depth['WR'][0].ovr = 97
        self.opp.depth['WR'][1].ovr = 82
        self.league = N(year=2029, teams={'GB': self.me, 'KC': self.opp},
                        tendencies={2029: {'KC': {'plays': 500, 'passes': 300, 'def_snaps': 500}}}, schedule=[])
        self.tape = dict(blitz=.10, two_high=.40, box8=.10, man=.30,
                         pa_rate=.21, deep=.26, pass_rate=.58)
        self.ranks = {'QB': (22, 32)}

    def report(self):
        with patch.object(GW, 'tendencies', return_value=self.tape), \
             patch.object(GW, 'season_underway', return_value=False), \
             patch.object(GW, 'unit_ranks', side_effect=lambda league, t, grades: self.ranks if t is self.opp else {}), \
             patch.object(GW, 'protection_suggestion', return_value=None), \
             patch.object(GW, 'game_forecast', return_value=dict(weather_risk=0, text='Clear')):
            return GW.opponent_report(self.league, 'GB', 'KC', 5)

    def test_screenshot_weak_qb_loses_to_strong_pa_and_deep_evidence(self):
        rows = self.report()['suggestions']
        self.coherent(rows)
        self.assertFalse(any(r['changes'].get('box_bias', 0) > 0 for r in rows))
        self.assertTrue(any(r['changes'].get('box_bias', 0) < 0 for r in rows))
        self.assertTrue(any(r['changes'].get('shell_lean', 0) > 0 for r in rows))
        self.assertTrue(any(r['changes'].get('bracket') for r in rows))

    def test_strong_run_threat_reverses_weak_passing_evidence(self):
        self.ranks.update(QB=(32, 32), **{'run block': (1, 32)})
        self.tape.update(pass_rate=.35, pa_rate=.17, deep=.15)
        rows = self.report()['suggestions']
        self.coherent(rows)
        self.assertTrue(any(r['changes'].get('box_bias', 0) > 0 for r in rows))
        self.assertFalse(any(r['changes'].get('shell_lean', 0) > 0 for r in rows))

    def test_user_and_cpu_apply_the_same_resolved_direction(self):
        report = self.report()
        combined = {}
        for row in report['suggestions']:
            combined = VG._merge(combined, row['changes'])
        base = GP.Gameplan()
        user = N(plan=base.copy(), base_plan=base)
        self.league.user_week_plan = dict(year=2029, week=5, changes=combined)
        GW.user_plan(self.league, user, 5)
        cpu = N(plan=base.copy(), base_plan=base, coach={})
        self.me.gm.adaptability = .8
        with patch.object(GW, 'opponent_report', return_value=report):
            GW.ai_plan(self.league, cpu, 'GB', 'KC', 5, N(random=lambda: 0.0))
        for key in combined:
            self.assertEqual(getattr(user.plan, key), getattr(cpu.plan, key), key)
        self.assertLess(user.plan.box_bias, base.box_bias)
        self.assertGreater(user.plan.shell_lean, base.shell_lean)

    def test_accept_replaces_legacy_conflict_but_preserves_manual(self):
        row = self.report()['suggestions'][0]
        self.league.user_week_plan = dict(year=2029, week=5, manual={'box_bias': .02},
            suggestions={'Old load box': {'box_bias': .12}}, changes={'box_bias': .02})
        with patch.object(VG, '_week', return_value=5), patch.object(VG, '_suggestion', return_value=row):
            result = VG.act_take(None, self.league, 'GB', 0)
        self.assertTrue(result['ok'])
        self.assertNotIn('Old load box', self.league.user_week_plan['suggestions'])
        self.assertEqual(self.league.user_week_plan['changes']['box_bias'], .02)


class HalftimeChoices(CoherenceChecks, unittest.TestCase):
    def recs(self, own=None, opp=None, margin=0, period='halftime'):
        empty = HT.first_half([], 'home')[0]
        with patch.object(HT, 'first_half', return_value=(dict(empty, **(own or {})), dict(empty, **(opp or {})))):
            result = HT.recommendations(None, 'GB', 'KC', [], 'home',
                {'home': max(0, margin), 'away': max(0, -margin)}, GP.Gameplan(), GP.Gameplan(), period=period)
        self.coherent(result)
        return result

    def test_run_and_pass_defense_choose_larger_problem(self):
        run = self.recs(opp=dict(runs=24, run_yds=192, passes=8, pass_yds=69, pressures=3))
        self.assertIn('run_defense', [r['review_key'] for r in run])
        self.assertNotIn('pass_defense', [r['review_key'] for r in run])
        passing = self.recs(opp=dict(runs=6, run_yds=30, passes=24, pass_yds=288, pressures=8))
        self.assertIn('pass_defense', [r['review_key'] for r in passing])
        self.assertNotIn('run_defense', [r['review_key'] for r in passing])

    def test_protection_does_not_resurrect_failed_screens(self):
        rows = self.recs(own=dict(passes=24, pressures=9, screens=9, screen_yds=-18))
        keys = {r['review_key'] for r in rows}
        self.assertIn('screens_stalled', keys)
        self.assertIn('protection', keys)
        protect = next(r for r in rows if r['review_key'] == 'protection')
        self.assertNotIn('screens', protect['text'])
        self.assertNotIn('screen_boost', protect['changes'])

    def test_hurry_overrules_successful_run_and_survives_display_limit(self):
        rows = self.recs(own=dict(runs=8, run_yds=48, passes=20, third=6, third_conv=1,
                                  screens=4, screen_yds=0, deep=4, deep_cmp=0),
                          opp=dict(runs=8,run_yds=50,passes=20,pass_yds=180,screens=4,screen_yds=40), margin=-21)
        keys = {r['review_key'] for r in rows}
        self.assertIn('hurry', keys)
        self.assertNotIn('run_working', keys)
        self.assertLessEqual(len(rows), 6)

    def test_selected_pressure_changes_reach_engine_and_reverse(self):
        for opp, sign in [(dict(passes=20, pass_yds=100), 1),
                          (dict(passes=20, pass_yds=100, pressures=5, screens=6, screen_yds=60), -1)]:
            base = GP.Gameplan(); plan = base.copy()
            rows = self.recs(opp=opp)
            for row in rows:
                GW.apply_changes(plan, base, row['changes'])
            self.assertGreater(sign*(plan.blitz_lean-base.blitz_lean), 0)

    def test_overtime_does_not_claim_evidence_is_only_first_half(self):
        rows = self.recs(own=dict(runs=10,run_yds=20,int=2,snaps=30),period='overtime')
        self.assertTrue(rows)
        self.assertFalse(any('in the half' in r['why'] or 'at the half' in r['why'] for r in rows))

    def test_old_live_save_keeps_original_choices_and_ignored_blitz(self):
        from test_overtime_adjustments import BreakFlowTests
        empty = HT.first_half([], 'home')[0]
        against = dict(empty, passes=20, pass_yds=100, screens=4, screen_yds=36)
        for version in (1, 2, 3):
            with self.subTest(version=version), patch.object(HT, 'first_half', return_value=(empty, against)):
                runner = BreakFlowTests().runner()
                runner.live['start']['adjustment_version'] = version
                base = runner.states['GB'].plan.blitz_lean
                runner.live_step('finish')
                rows = runner.live['half_recs']
                if version < 3:
                    self.assertEqual([r['review_key'] for r in rows], ['pressure_defense', 'screens_defense'])
                else:
                    self.coherent(rows)
                    self.assertEqual(len(rows), 1)
                runner.half_take(0, True)
                if version < 3:
                    self.assertEqual(runner.states['GB'].plan.blitz_lean, base)
                else:
                    self.assertNotEqual(runner.states['GB'].plan.blitz_lean, base)
                restored = BreakFlowTests().runner()
                restored.live['start']['adjustment_version'] = version
                restored.replay_live(copy.deepcopy(runner.live['actions']), copy.deepcopy(runner.rng.bit_generator.state))
                self.assertEqual(restored.states['GB'].plan.__dict__, runner.states['GB'].plan.__dict__)
                self.assertEqual(restored.live['half_recs'], runner.live['half_recs'])
                runner.half_take(0, False)
                self.assertEqual(runner.states['GB'].plan.blitz_lean, base)


if __name__ == '__main__':
    unittest.main()
