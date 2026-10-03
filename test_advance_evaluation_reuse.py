"""Outcome and lifetime guards for batch-only evaluation reuse."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import roster_needs as RN
import valuation as VAL
from test_package_roster_needs import team, player


class ComparisonReuseTests(unittest.TestCase):
    def setUp(self):
        self.pool = VAL.UNI.copy()
        self.row = self.pool.iloc[0].to_dict()

    def test_identical_prices_and_random_stream_with_repeated_reads(self):
        a, b = np.random.default_rng(927), np.random.default_rng(927)
        expected = [VAL.value(self.row, pool=self.pool, rng=a) for _ in range(15)]
        with patch.object(VAL, '_weights', wraps=VAL._weights) as weights:
            with VAL.comparison_batch():
                actual = [VAL.value(self.row, pool=self.pool, rng=b) for _ in range(15)]
                calls = weights.call_count
                VAL.raw_value(self.row, self.pool, window=actual[-1]['window'])
                self.assertEqual(weights.call_count, calls)
        self.assertEqual(expected, actual)
        self.assertEqual(a.bit_generator.state, b.bit_generator.state)
        self.assertIsNone(VAL._COMPARISONS.get())

    def test_new_pool_and_next_batch_reprice_and_results_are_independent(self):
        with VAL.comparison_batch():
            original = VAL.raw_value(self.row, self.pool, 5)
            again = VAL.raw_value(self.row, self.pool, 5)
            original[0]['cappct'] = -1
            original[2]['prod_f'] = -999
            self.assertEqual(VAL.raw_value(self.row, self.pool, 5), again)
            new_pool = self.pool.copy()
            new_pool['cappct'] *= 2
            self.assertNotEqual(VAL.raw_value(self.row, new_pool, 5)[0], again[0])
        # Editing a pool between independent batches must never reuse its old read.
        self.pool['cappct'] *= 3
        with VAL.comparison_batch():
            self.assertNotEqual(VAL.raw_value(self.row, self.pool, 5)[0], again[0])

    def test_nested_batches_exception_cleanup_and_bounded_pool_retention(self):
        with self.assertRaisesRegex(RuntimeError, 'stop'):
            with VAL.comparison_batch():
                cache = VAL._COMPARISONS.get()
                with VAL.comparison_batch():
                    self.assertIs(cache, VAL._COMPARISONS.get())
                    for _ in range(7):
                        VAL.raw_value(self.row, self.pool.copy(), 5)
                self.assertLessEqual(len(cache), 4)
                raise RuntimeError('stop')
        self.assertIsNone(VAL._COMPARISONS.get())


class CandidateReuseTests(unittest.TestCase):
    def test_additions_swaps_and_removals_match_reassessment_without_mutation(self):
        for front, offense in [('4-3', '11'), ('3-4', '21'), ('multiple', '12')]:
            t = team(offense, front)
            # Exercise blocking fullbacks, thin rooms, specialist grades and ties.
            t.roster = [p for p in t.roster if p.pos != 'FB']
            before = RN.assess(t)
            old_depth = copy.deepcopy(before['_planning_depth'])
            for pos in RN.POSITIONS:
                incoming = player(pos, 'new', 86, 93)
                outgoing = next(p for p in t.roster if p.pos == ('TE' if pos == 'FB' else pos))
                for departure in (None, outgoing):
                    proposal = [p for p in t.roster if p is not departure] + [incoming]
                    expected = RN.assess(t, proposal)['score'] - before['score']
                    self.assertAlmostEqual(RN.move_gain(t, incoming, departure, before), expected, places=10)
                expected_loss = before['score'] - RN.assess(t, [p for p in t.roster if p is not outgoing])['score']
                self.assertAlmostEqual(RN.departure_loss(t, outgoing, before), expected_loss, places=10)
            self.assertEqual(before['_planning_depth'], old_depth)

    def test_new_assessment_picks_up_rating_and_coaching_changes(self):
        t = team()
        before = RN.assess(t)
        for p in t.roster:
            if p.pos == 'QB':
                p.ovr = 40
                p.ratings['awareness_rating'] = 40
        t.gm.def_front = '3-4'
        t.gm.off_personnel = '22'
        fresh = RN.assess(t)
        self.assertNotEqual(before['score'], fresh['score'])
        self.assertNotEqual(before['_planning_depth'], fresh['_planning_depth'])
        self.assertEqual(fresh['front'], '3-4')


if __name__ == '__main__':
    unittest.main()
