"""A resolved catch-and-run touchdown must survive later field compression."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import game as G
import plays as P
import rosters as R
import schemes as S


class ReceivingTouchdowns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teams = R.load_league()

    def resolved_catch(self, concept, touchdown):
        seen = []
        def pursuit(carrier, tacklers, room, rng, **kw):
            seen.append((room, kw.get('gain_scale')))
            return dict(yards=room if touchdown else 4.0,
                        broken_tackles=2 if touchdown else 0, touchdown=touchdown)
        with patch.object(P, 'resolve_yards_after', side_effect=pursuit):
            for seed in range(50):
                rng = np.random.default_rng(seed)
                oc = S.call_offense(1, 10, 0, 20, rng)
                oc.update(is_pass=True, depth='short', concept=concept)
                dc = S.call_defense(oc, 1, 10, rng, yards_to_endzone=20)
                result = P._pass_play(self.teams['GB'], self.teams['SEA'], oc, dc, 20, rng)
                if seen:
                    return result, seen[-1]
        self.fail('Fixture did not reach the catch-and-run resolver')

    def test_short_receiver_crossing_goal_line_keeps_touchdown(self):
        result, (room, scale) = self.resolved_catch('curl_flat', True)
        self.assertLess(room, 26.4)
        self.assertTrue(result['touchdown'])
        self.assertEqual(result['yards'], 20)
        self.assertAlmostEqual(result['air'] + result['yac'], 20, places=1)
        book = G.StatBook()
        book.record(result, self.teams['GB'], self.teams['SEA'], np.random.default_rng(1))
        self.assertEqual(book.p[self.teams['GB']['qb']['pid']]['pass_td'], 1)
        self.assertEqual(book.p[result['target']]['rec_td'], 1)
        self.assertEqual(book.p[result['target']]['rec_yds'], 20)

    def test_screen_touchdown_survives_awareness_and_compression(self):
        result, (room, scale) = self.resolved_catch('screen', True)
        self.assertTrue(result['screen'])
        self.assertTrue(result['touchdown'])
        self.assertEqual(result['yards'], 20)
        self.assertAlmostEqual(result['air'] + result['yac'], 20, places=1)

    def test_tackled_catch_applies_compression_once_inside_pursuit(self):
        result, (room, scale) = self.resolved_catch('curl_flat', False)
        self.assertFalse(result['touchdown'])
        self.assertEqual(scale, P._compression(room))
        self.assertEqual(result['yac'], 4.0)

    def test_compression_allows_next_defender_to_stop_runner_before_goal(self):
        # The first broken tackle would cover ten yards without congestion.
        # At half distance the second defender still has a chance to stop him.
        draws = iter([0.0, 1.0])
        rng = SimpleNamespace(random=lambda: next(draws), gamma=lambda *a: 10.0,
                              normal=lambda *a: 1.0)
        out = P.resolve_yards_after({}, [{}, {}], 8, rng, gain_scale=.5)
        self.assertFalse(out['touchdown'])
        self.assertEqual(out['yards'], 5.5)
        self.assertEqual(out['broken_tackles'], 1)

    def test_beating_all_pursuers_and_winning_race_reaches_goal(self):
        rng = SimpleNamespace(random=lambda: 0.0, gamma=lambda *a: 1.0)
        out = P.resolve_yards_after({}, [{}], 8, rng, gain_scale=.5)
        self.assertTrue(out['touchdown'])
        self.assertEqual(out['yards'], 8)

    def test_default_pursuit_scale_leaves_run_resolution_unchanged(self):
        for seed in range(20):
            a = P.resolve_yards_after({}, [{}, {}], 30, np.random.default_rng(seed))
            b = P.resolve_yards_after({}, [{}, {}], 30, np.random.default_rng(seed), gain_scale=1.0)
            self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
