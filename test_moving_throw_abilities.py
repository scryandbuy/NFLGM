"""Situational passing abilities reach live man and zone resolution."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import game as G
import matchups as M
import plays as P
import rosters as R
import coverage as CV
import schemes as S


class ThrowAbilityTests(unittest.TestCase):
    def probability(self, man, qb, **flags):
        rng = np.random.default_rng(5)
        if man:
            return P.resolve_throw(qb, 'medium', .42, .2, rng, **flags)['p']
        return M.resolve_zone({}, [], qb, 'cover_3', 'medium', .2, rng,
                              P.rate, **flags)['raw'] * M.ZONE_SCALE['medium']

    def test_extreme_attributes_change_only_relevant_throw(self):
        for man in (False, True):
            for attribute, flag in [('throw_on_run_rating', 'on_run'),
                                    ('play_action_rating', 'play_action')]:
                low, high = {attribute: 20}, {attribute: 99}
                with self.subTest(man=man, attribute=attribute):
                    self.assertEqual(self.probability(man, low), self.probability(man, high))
                    self.assertGreater(self.probability(man, high, **{flag: True}),
                                       self.probability(man, low, **{flag: True}) + .01)

    def test_neutral_abilities_preserve_probability(self):
        for man in (False, True):
            base = self.probability(man, {})
            for flags in ({'on_run': True}, {'play_action': True},
                          {'on_run': True, 'play_action': True}):
                self.assertEqual(base, self.probability(man, {}, **flags))

    def test_movement_requires_a_called_action(self):
        boot = dict(concept='flood', play_action=True, shotgun=False)
        self.assertTrue(P.moving_throw(boot))
        self.assertFalse(P.moving_throw(dict(boot, shotgun=True)))
        self.assertFalse(P.moving_throw(dict(boot, play_action=False)))
        self.assertFalse(P.moving_throw(dict(boot, concept='levels')))
        self.assertFalse(P.moving_throw(dict(concept='levels', pressure=1)))
        self.assertFalse(P.moving_throw(dict(boot, on_run=False)))
        self.assertTrue(P.moving_throw(dict(concept='levels', shotgun=True, on_run=True)))
        self.assertFalse(P.moving_throw(dict(boot, on_run=True, qb_movement='boot', concept='levels')))
        self.assertFalse(P.moving_throw(dict(boot, on_run=True, qb_movement='boot', shotgun=True)))
        for flag in ('screen', 'swing', 'hot'):
            self.assertFalse(P.moving_throw(boot, **{flag: True}))

    def test_actual_caller_marks_boot_action(self):
        rng = np.random.default_rng(123)
        boots = 0
        for _ in range(2000):
            call = S.call_offense(1, 10, 0, 60, rng)
            if call.get('on_run'):
                boots += 1
                self.assertEqual(call.get('qb_movement'), 'boot')
                self.assertTrue(call['play_action'])
                self.assertFalse(call['shotgun'])
                self.assertEqual(call['concept'], 'flood')
                self.assertTrue(P.moving_throw(call))
        self.assertGreater(boots, 0)


class LivePassingAbilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rosters = R.load_league()
        rng = np.random.default_rng(5)
        cls.off, _ = G.field_units(rosters['GB'], None, rng, True, '11')
        cls.defense, _ = G.field_units(rosters['DEN'], None, rng, False, 'nickel', front_family='3-4')

    def attempts(self, man, attribute, rating, *, pa=True, concept='flood'):
        off = copy.deepcopy(self.off)
        off['qb'][attribute] = rating
        off['qb']['play_action_rating' if attribute == 'throw_on_run_rating' else 'throw_on_run_rating'] = 70
        call = dict(is_pass=True, personnel='11', concept=concept, depth='medium',
                    down=1, ydstogo=10, play_action=pa, shotgun=False)
        dc = dict(rushers=4, coverage='cover_1' if man else 'cover_3',
                  shell='cover_1' if man else 'cover_3', man=man, box=6,
                  front_family='3-4', personnel='nickel')
        original = CV.assign_coverage
        def assigned(*args, **kwargs):
            pairs, travelled = original(*args, **kwargs)
            for pair in pairs: pair['man'] = man
            return pairs, travelled
        protection = dict(time=100., pressure=0., beaten_by=None, beaten=None, pb_reps=[], pr_reps=[])
        probabilities = []
        with patch.object(P, 'resolve_protection', return_value=protection), \
             patch.object(CV, 'assign_coverage', side_effect=assigned), \
             patch('zones.contest', return_value=(None, None, False, False)):
            for seed in range(24):
                with patch.object(P, 'resolve_throw', wraps=P.resolve_throw) as man_throw, \
                     patch.object(P, 'resolve_zone', wraps=P.resolve_zone) as zone_throw:
                    result = P._pass_play(off, self.defense, call, dc, 90, np.random.default_rng(seed))
                self.assertNotEqual(result['type'], 'sack')
                called = man_throw if man else zone_throw
                self.assertTrue(called.called)
                self.assertEqual(called.call_args.kwargs['on_run'], bool(pa and concept == 'flood'))
                self.assertEqual(called.call_args.kwargs['play_action'], pa)
                probabilities.append(P.LAST_XCOMP)
        return probabilities

    def test_live_rating_effects_in_both_coverages(self):
        for man in (False, True):
            for attribute, concept in [('throw_on_run_rating', 'flood'), ('play_action_rating', 'levels')]:
                with self.subTest(man=man, attribute=attribute):
                    low = self.attempts(man, attribute, 20, concept=concept)
                    high = self.attempts(man, attribute, 99, concept=concept)
                    self.assertGreater(float(np.mean(high)), float(np.mean(low)) + .005)
                    self.assertTrue(all(h >= l for l, h in zip(low, high)))

    def test_live_pocket_non_pa_throws_ignore_unrelated_ratings(self):
        for man in (False, True):
            for attribute in ('throw_on_run_rating', 'play_action_rating'):
                self.assertEqual(self.attempts(man, attribute, 20, pa=False, concept='levels'),
                                 self.attempts(man, attribute, 99, pa=False, concept='levels'))


if __name__ == '__main__':
    unittest.main()
