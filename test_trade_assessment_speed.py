"""Request-local removal scoring must retain exact trade decisions."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import offense_roles as OR
import roster_needs as RN
import trades as TR
from test_package_roster_needs import team


def full_loss(t, p, baseline=None):
    before = RN.assess(t) if baseline is None else baseline
    return before['score'] - RN.assess(t, [q for q in t.active() if q.pid != p.pid])['score']


class TradeAssessmentSpeedTests(unittest.TestCase):
    def test_exact_removal_scores_for_every_position_and_coach_base(self):
        for front in ('4-3', '3-4', 'multiple'):
            for package in OR.PACKAGES:
                t = team(package, front)
                before = RN.assess(t)
                for p in t.roster:
                    if p.pid.endswith('-0'):
                        with self.subTest(front=front, package=package, pos=p.pos):
                            self.assertEqual(RN.departure_loss(t, p, before), full_loss(t, p, before))

    def test_sparse_roster_and_fresh_mutated_assessments(self):
        t = team('21', '3-4')
        t.roster = [p for p in t.roster if p.pos in ('HB', 'TE', 'WR', 'DT', 'CB')]
        for iteration in range(3):
            before = RN.assess(t)
            original_grades = copy.deepcopy(before['_role_grades'])
            for p in t.roster:
                self.assertEqual(RN.departure_loss(t, p, before), full_loss(t, p, before))
            self.assertEqual(before['_role_grades'], original_grades)
            t.roster.pop()
            t.roster[0].ovr -= 7
            t.roster[0].ratings['run_block_rating'] = 91
            t.gm.off_personnel = '12'

    def test_surplus_results_and_rng_identical_to_full_reassessment(self):
        t = team('12', 'multiple')
        for i, p in enumerate(t.roster):
            p.ovr = 91 - (i % 3) * 9
        league = SimpleNamespace(teams={'TST': t}, free_agents=[], week=2)
        def asset(league, t, p, pool, rng, **kwargs):
            return dict(pid=p.pid, trade_value=float(rng.random()))
        with patch.object(TR, 'starter_bar', return_value={}), \
             patch.object(TR, 'player_asset', side_effect=asset), \
             patch('morale.wants_out', return_value=False):
            for injured in (False, True):
                t.roster[0].out_until = 9 if injured else None
                old_rng = np.random.default_rng(921)
                with patch.object(RN, 'departure_loss', side_effect=full_loss):
                    expected = TR.surplus_and_needs(league, t, {}, old_rng)
                new_rng = np.random.default_rng(921)
                with patch.object(RN, 'assess', wraps=RN.assess) as assess:
                    actual = TR.surplus_and_needs(league, t, {}, new_rng)
                self.assertEqual(actual, expected)
                self.assertEqual(new_rng.bit_generator.state, old_rng.bit_generator.state)
                self.assertEqual(assess.call_count, 1)


if __name__ == '__main__':
    unittest.main()
