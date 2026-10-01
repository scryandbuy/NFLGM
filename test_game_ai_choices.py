"""Regression checks for coach choices reaching the live game."""
import unittest
from unittest.mock import patch

import numpy as np

import coverage_call
import defense_roles
import game
import gameplan
import playcall
import plays
import schemes


class GameAiChoicesTests(unittest.TestCase):
    def test_run_family_changes_roster_aware_call_weights(self):
        old = dict(playcall.SCHEME_BASE)
        try:
            playcall.SCHEME_BASE.update({name: .7 for name in playcall.SCHEME_WANTS})
            offense = {'ol': [{} for _ in range(5)]}
            def zone_share(mix):
                rng = np.random.default_rng(12)
                calls = [playcall.call_run(offense, 'chains', plays.rate, rng,
                                           family_mix=mix) for _ in range(1200)]
                return sum(schemes.RUN_SCHEMES[c]['family'] == 'zone' for c in calls)
            self.assertGreater(zone_share({'zone': .8, 'gap': .2}),
                               zone_share({'zone': .2, 'gap': .8}) + 250)
        finally:
            playcall.SCHEME_BASE.clear()
            playcall.SCHEME_BASE.update(old)

    def test_defensive_plan_changes_live_coverage_preferences(self):
        plan = gameplan.Gameplan()
        base = gameplan.defensive_leans(plan)
        plan.blitz_rate += .05
        plan.shell_weights['cover_4'] = .60
        changed = gameplan.defensive_leans(plan)
        self.assertGreater(changed['blitz'], base['blitz'])
        defense = {'db': [{'pos': 'CB'} for _ in range(3)] +
                         [{'pos': 'FS'}, {'pos': 'SS'}],
                   'lb': [{'pos': 'MIKE'} for _ in range(3)]}
        def cover_four(lean):
            rng = np.random.default_rng(9)
            return sum(coverage_call.call_coverage(1, 10, 0, 1800, '11',
                       defense, plays.rate, rng, lean=lean)['coverage'] == 'cover_4'
                       for _ in range(1200))
        self.assertGreater(cover_four(changed), cover_four(base) + 80)

    def test_tempo_changes_no_huddle_and_clock(self):
        def calls(tempo):
            rng = np.random.default_rng(22)
            return sum(schemes.call_offense(1, 10, 0, 50, rng,
                       lean={'tempo': tempo})['no_huddle'] for _ in range(1200))
        self.assertGreater(calls(1.0), calls(0.0) + 100)
        self.assertLess(game.play_seconds('run', hurry=True), game.play_seconds('run'))

    def test_kicker_changes_fourth_down_range(self):
        class NeverGo:
            def random(self): return .999
        strong = {'kick_power_rating': 95, 'kick_acc_rating': 80}
        weak = {'kick_power_rating': 40, 'kick_acc_rating': 80}
        args = (40, 7, 0, 1800, NeverGo())
        self.assertEqual(game.fourth_down_decision(*args, use_wp=False,
                         kicker=strong, rate_fn=plays.rate), 'field_goal')
        self.assertEqual(game.fourth_down_decision(*args, use_wp=False,
                         kicker=weak, rate_fn=plays.rate), 'punt')

    def test_multiple_front_answers_the_offensive_grouping(self):
        def calls(personnel, down, distance):
            rng = np.random.default_rng(7)
            return [schemes.call_defense({'personnel': personnel}, down,
                    distance, rng, lean={'front_pref': ['4-3 over', 'tite']})
                    for _ in range(1000)]
        heavy, spread = calls('12', 2, 2), calls('10', 3, 10)
        # Odd-coach nickel/dime keep their 3-4 identity but align four rush-front
        # players. Check the actual package rather than counting that label.
        def three_lineman_count(rows):
            return sum(defense_roles.counts(c['front_family'], c['personnel'])['dl'] == 3
                       for c in rows)
        self.assertGreater(three_lineman_count(heavy), three_lineman_count(spread) + 150)
        self.assertGreater(sum(c['personnel'] == 'base' for c in heavy), 600)
        self.assertTrue(all(c['personnel'] == 'dime' for c in spread))
        for call in heavy + spread:
            shape = defense_roles.counts(call['front_family'], call['personnel'])
            self.assertEqual(sum(shape.values()), 11)
            self.assertEqual(schemes.FRONTS[call['front']]['dl'], shape['dl'])

    def test_multiple_front_situation_changes_choice_with_same_package(self):
        # Isolate front selection from personnel selection: removing the
        # run-threat weighting must fail even if package substitutions work.
        def tite_count(personnel, down, distance):
            rng = np.random.default_rng(7)
            with patch.object(schemes, 'defensive_personnel', return_value='base'):
                return sum(schemes.call_defense({'personnel': personnel}, down,
                           distance, rng, lean={'front_pref': ['4-3 over', 'tite']})
                           ['front'] == 'tite' for _ in range(1000))
        self.assertGreater(tite_count('12', 2, 2), tite_count('10', 3, 10) + 150)


if __name__ == '__main__':
    unittest.main()
