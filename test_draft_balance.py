import unittest

import draft_balance as DB


class DraftBalanceTest(unittest.TestCase):
    def test_large_position_roll_is_capped_and_tapers(self):
        base = [82.5 - i * 0.2 for i in range(30)]
        result = DB.variation_targets('WR', base, 1.2, 2.5)
        self.assertAlmostEqual(result[0] - base[0], 2.0)
        self.assertAlmostEqual(result[-1] - base[-1], 1.0)
        self.assertLess(sum(v >= 80 for v in result),
                        sum(v + 3.7 >= 80 for v in base))

    def test_weak_class_and_specialists_retain_variation(self):
        base = [88.0, 85.0, 82.0]
        self.assertEqual(DB.variation_targets('K', base, -2.0, -2.0),
                         [87.0, 84.25, 81.5])
        self.assertEqual(DB.variation_targets('TE', [], 1.0, 1.0), [])

    def test_top_of_each_position_is_preserved(self):
        for rank in range(6):
            self.assertEqual(DB.tail_target('TE', 74.37, rank, 30), 74.37)
        self.assertLess(DB.tail_target('WR', 74.37, 6, 30), 74.37)
        self.assertAlmostEqual(DB.tail_target('WR', 74.37, 29, 30), 67.87)

    def test_tail_never_raises_or_changes_specialists(self):
        for rank in range(30):
            target = DB.tail_target('CB', 72.0, rank, 30)
            self.assertLessEqual(target, 72.0)
            self.assertGreaterEqual(target, 65.5)
        for pos in ('K', 'P', 'LS'):
            self.assertEqual(DB.tail_target(pos, 88.0, 2, 3), 88.0)

    def test_rank_must_be_valid(self):
        with self.assertRaises(ValueError):
            DB.tail_target('QB', 70.0, 3, 3)
        with self.assertRaises(ValueError):
            DB.tail_target('QB', 70.0, -1, 3)


if __name__ == '__main__':
    unittest.main()
