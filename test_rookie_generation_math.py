"""Check shared rookie inputs and attainable rating targets, without seasons."""
import collections
import unittest
import numpy as np
import pandas as pd

import draft_class as DC
import rookie_baseline as RB
import targets as TG
from league import build_league


class RookieBaselineTests(unittest.TestCase):
    def test_imputed_rookie_correction_is_shared_with_live_league(self):
        league = build_league(rng=np.random.default_rng(93))
        frame = RB.load_active_seed()
        targets = DC.rookie_targets()
        expected = collections.defaultdict(list)
        for _, row in frame[frame.draft_year == 2026].iterrows():
            p = league.players[row.pid]
            expected[p.pos].append(p.ovr)
        self.assertEqual(set(expected), set(targets))
        for pos in expected:
            np.testing.assert_allclose(sorted(expected[pos], reverse=True), targets[pos], atol=1e-9)
        self.assertAlmostEqual(league.players['P1519'].ovr, 73.44, places=2)

    def test_correction_preserves_input_and_non_rating_fields(self):
        raw = pd.read_csv('league_seed_2026.csv', low_memory=False)
        original = raw.copy(deep=True)
        corrected = RB.correct_rookie_ratings(raw, 2026)
        pd.testing.assert_frame_equal(raw, original)
        untouched = [c for c in raw if not c.endswith('_rating') or c == 'src_rating']
        pd.testing.assert_frame_equal(raw[untouched], corrected[untouched])
        veterans = raw.draft_year != 2026
        pd.testing.assert_frame_equal(raw[veterans], corrected[veterans])

    def test_small_rookie_samples_keep_actual_top_ratings(self):
        for sample in ([88.55, 86.3, 83.95], [74.0, 68.0], [71.0]):
            result = DC.target_curve(sample, len(sample) + 2)
            self.assertEqual(result[:len(sample)], sample)
            self.assertLess(result[-1], sample[-1])
            self.assertEqual(result[0], max(sample))


class RatingTargetTests(unittest.TestCase):
    def test_lower_targets_hit_actual_overall_at_every_position(self):
        for pos in DC.COUNTS:
            ratings = {key: 82.0 for key in TG.DEPTH_WEIGHTS[pos]}
            ratings.update({k: 91.0 for k in DC.PHYSICAL | DC.TOOLS})
            original = dict(ratings)
            target = TG.position_score(ratings, pos) - 7.3
            adjusted = DC.reshape_ratings(ratings, pos, target)
            with self.subTest(pos=pos):
                self.assertAlmostEqual(TG.position_score(adjusted, pos), target, places=7)
                self.assertEqual(ratings, original)
                self.assertTrue(all(adjusted[k] == ratings[k] for k in DC.PHYSICAL | DC.TOOLS))

    def test_clipped_skills_still_reach_target(self):
        ratings = {key: 80.0 for key in TG.DEPTH_WEIGHTS['QB']}
        ratings.update(awareness_rating=22.0, speed_rating=93.0, throw_power_rating=99.0)
        adjusted = DC.reshape_ratings(ratings, 'QB', 55)
        self.assertAlmostEqual(TG.position_score(adjusted, 'QB'), 55, places=7)
        self.assertEqual(adjusted['awareness_rating'], 20)
        self.assertEqual(adjusted['throw_power_rating'], 99)

    def test_unattainable_target_stops_at_floor_without_destroying_tools(self):
        ratings = {key: 70.0 for key in TG.DEPTH_WEIGHTS['P']}
        ratings['kick_power_rating'] = 99.0
        result = DC.reshape_ratings(ratings, 'P', 20)
        self.assertGreater(TG.position_score(result, 'P'), 20)
        self.assertEqual(result['kick_power_rating'], 99)
        self.assertEqual(result['kick_acc_rating'], 20)
        self.assertTrue(all(20 <= value <= 99 for value in result.values()))


if __name__ == '__main__':
    unittest.main()
