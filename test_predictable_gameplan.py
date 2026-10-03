"""Successful self-scout counters must reach the caller without forcing calls."""
import unittest
from types import SimpleNamespace

import numpy as np

import adjust as AD
import game
import gameplan as GP
import schemes


class ResponseRolls:
    """Select a successful response while leaving its production payload intact."""
    def random(self):
        return 0.0


class PredictableGameplanTests(unittest.TestCase):
    def counter(self, tendency):
        return AD.respond(
            {'predictable': dict(kind='predictable', value=tendency,
                                 rate=.9, n=12, conf=.8)},
            skill=.8, aggressiveness=.7, rng=ResponseRolls())

    def adjusted(self, tendency, bias=0.0):
        original = GP.Gameplan(pass_bias=bias)
        updated, applied = GP.adjust_plan(original, self.counter(tendency),
                                          skill=.8, quarter=2)
        self.assertEqual(applied, ['pass_bias'])
        self.assertEqual(original.pass_bias, bias)
        self.assertEqual(original.changes, [])
        return updated

    def lean(self, plan):
        return game.offensive_leans(SimpleNamespace(plan=plan, seq=None))

    def calls(self, lean, *, down=1, togo=10, score=0, secs=2700):
        # Re-seed per snap: personnel and the pass/run draw are paired even
        # when the selected concept consumes different subsequent draws.
        return [schemes.call_offense(down, togo, score, 50,
                                    np.random.default_rng(seed),
                                    secs_left=secs, lean=lean)['is_pass']
                for seed in range(256)]

    def test_response_target_moves_actual_caller_away_from_tendency(self):
        base = self.calls(self.lean(GP.Gameplan()))
        for tendency, direction in [('pass', -1), ('run', 1)]:
            with self.subTest(tendency=tendency):
                plan = self.adjusted(tendency)
                lean = self.lean(plan)
                self.assertGreater(direction * lean['pass_bias'], 0)
                changed = self.calls(lean)
                self.assertGreater(direction * (sum(changed) - sum(base)), 0)
                # A nudge changes some choices, not an alternating/forced call.
                self.assertGreater(sum(changed), 0)
                self.assertLess(sum(changed), len(changed))
                for before, after in zip(base, changed):
                    self.assertGreaterEqual(direction * (int(after) - int(before)), 0)

    def test_distinct_coach_identities_survive_same_read(self):
        run_coach = self.adjusted('pass', bias=-.15)
        pass_coach = self.adjusted('pass', bias=.15)
        self.assertAlmostEqual(pass_coach.pass_bias - run_coach.pass_bias, .30)
        self.assertGreater(sum(self.calls(self.lean(pass_coach))),
                           sum(self.calls(self.lean(run_coach))))

    def test_failed_unknown_and_unaffordable_changes_do_nothing(self):
        plan = GP.Gameplan()
        for counter, skill in [
            (dict(self.counter('pass'), works=False), .8),
            (dict(self.counter('pass'), target=None), .8),
            (dict(self.counter('pass'), target='unknown'), .8),
            (self.counter('pass'), 0.0),
        ]:
            updated, applied = GP.adjust_plan(plan, counter, skill)
            self.assertIs(updated, plan)
            self.assertEqual(applied, [])
        self.assertEqual(plan.changes, [])

    def test_repeat_is_not_reapplied_each_series(self):
        plan = self.adjusted('pass', .10)
        updated, applied = GP.adjust_plan(plan, self.counter('pass'), .8)
        self.assertIs(updated, plan)
        self.assertEqual(applied, [])
        self.assertEqual(len(updated.changes), 1)

    def test_bias_bounds_have_truthful_change_records(self):
        for tendency, bound in [('pass', -.45), ('run', .45)]:
            with self.subTest(tendency=tendency):
                plan = GP.Gameplan(pass_bias=bound)
                updated, applied = GP.adjust_plan(plan, self.counter(tendency), .8)
                self.assertIs(updated, plan)
                self.assertEqual(applied, [])
                self.assertEqual(updated.changes, [])
                start = bound - np.sign(bound) * .01
                near = self.adjusted(tendency, start)
                self.assertEqual(near.pass_bias, bound)
                self.assertAlmostEqual(near.changes[-1]['value'], bound - start)

    def test_down_and_clock_preferences_remain_situational(self):
        for tendency in ['pass', 'run']:
            lean = self.lean(self.adjusted(tendency))
            early = sum(self.calls(lean))
            self.assertGreater(sum(self.calls(lean, down=3, togo=12)), early)
            self.assertGreater(sum(self.calls(lean, score=-14, secs=90)), early)
            self.assertLess(sum(self.calls(lean, score=14, secs=90)), early)

    def test_large_live_clock_overrides_dominate_small_plan_change(self):
        # game.run_drive adds these leans after offensive_leans; the real
        # caller should give the same capped rates with or without this nudge.
        # Explicit late-game forced throws/kneels remain downstream in game.py.
        for tendency in ['pass', 'run']:
            changed = self.lean(self.adjusted(tendency))
            original = self.lean(GP.Gameplan())
            for late_lean, score in [(6.5, -7), (-3.5, 7)]:
                before = dict(original, pass_bias=original['pass_bias'] + late_lean)
                after = dict(changed, pass_bias=changed['pass_bias'] + late_lean)
                self.assertEqual(self.calls(before, score=score, secs=90),
                                 self.calls(after, score=score, secs=90))


if __name__ == '__main__':
    unittest.main()
