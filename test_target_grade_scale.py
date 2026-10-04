"""Receiving ability and tactical modifiers remain on compatible scales."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import plays as P
import targets as T


def pairs(grades):
    return [dict(receiver=dict(pid=str(i), pos=pos, **{k: grade for k in T.RECV_GRADE}),
                 defender={}, separation=.42) for i, (pos, grade) in enumerate(grades)]


class DesignedRead:
    """Expose the coach's weighted order while removing random draw noise."""
    def choice(self, choices, size=None, replace=True, p=None):
        if size is None: return 'designed'
        self.weights = np.asarray(p)
        return np.argsort(-self.weights)


def order(rows, **kwargs):
    rng = DesignedRead()
    chosen = T.select_target(rows, {}, 'dagger', rng, P.rate, **kwargs)
    return chosen[0]['pid'], rng.weights


class TargetGrades(unittest.TestCase):
    def test_weak_tight_end_cannot_outrank_elite_receiver_by_position_alone(self):
        rows = pairs([('WR', 95), ('WR', 80), ('WR', 75), ('TE', 50), ('HB', 70)])
        chosen, weights = order(rows)
        self.assertEqual(chosen, '0')
        self.assertGreater(weights[0], weights[3])

    def test_elite_tight_end_can_still_be_primary_read(self):
        chosen, weights = order(pairs([('WR', 70), ('WR', 65), ('TE', 95)]))
        self.assertEqual(chosen, '2')
        self.assertGreater(weights[2], weights[0])

    def test_receiving_back_talent_can_overcome_outlet_preference(self):
        rows = pairs([('WR', 60), ('WR', 55), ('WR', 50), ('TE', 50), ('HB', 99)])
        elite = order(rows)[1]
        self.assertGreater(elite[4], elite[3])
        rows[-1]['receiver'].update({k: 50 for k in T.RECV_GRADE})
        self.assertGreater(elite[4], order(rows)[1][4])

    def test_bracket_late_release_and_priority_remain_effective(self):
        rows = pairs([('WR', 95), ('WR', 80), ('TE', 75), ('HB', 70)])
        _, baseline = order(rows)
        for key in ('bracket', 'late'):
            changed = copy.deepcopy(rows); changed[0][key] = True
            self.assertLess(order(changed)[1][0], baseline[0])
        _, preferred = order(rows, plan=NS(target_priority={'1': 1.0}))
        self.assertGreater(preferred[1], baseline[1])

    def test_red_zone_still_increases_tight_end_preference(self):
        rows = pairs([('WR', 80), ('WR', 75), ('TE', 75), ('HB', 70)])
        self.assertGreater(order(rows, red_zone=True)[1][2], order(rows)[1][2])

    def test_qb_processing_and_mobility_keep_normalized_inputs(self):
        qb = {k: 70 for k in ('awareness_rating', 'play_rec_rating',
                              'throw_under_pressure_rating', 'speed_rating', 'agility_rating')}
        self.assertAlmostEqual(T.read_profile(qb, P.rate)['first'], .530)
        high = dict(qb, awareness_rating=95, play_rec_rating=95, throw_under_pressure_rating=95)
        self.assertLess(T.read_profile(high, P.rate)['first'], T.read_profile(qb, P.rate)['first'])
        self.assertGreater(T.read_profile(high, P.rate)['second'], T.read_profile(qb, P.rate)['second'])
        self.assertGreater(T.read_profile(dict(qb, speed_rating=95, agility_rating=95), P.rate)['scramble'],
                           T.read_profile(qb, P.rate)['scramble'])
        with patch.object(T, 'read_profile', wraps=T.read_profile) as profile:
            T.select_target(pairs([('WR', 80), ('TE', 70)]), qb, 'dagger', np.random.default_rng(1), P.rate)
        self.assertIs(profile.call_args.args[1], P.rate)

    def test_read_kinds_remain_varied_and_input_is_unchanged(self):
        rows = pairs([('WR', 95), ('WR', 80), ('WR', 75), ('TE', 50), ('HB', 80)])
        original = copy.deepcopy(rows)
        rng = np.random.default_rng(811)
        results = [T.select_target(rows, {}, 'dagger', rng, P.rate) for _ in range(400)]
        self.assertEqual({r[2] for r in results}, set(T.READ_MIX))
        self.assertEqual({r[0]['pid'] for r in results}, {str(i) for i in range(5)})
        self.assertEqual(rows, original)


if __name__ == '__main__': unittest.main()
