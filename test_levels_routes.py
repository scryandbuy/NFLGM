"""A levels call has an intermediate in-breaker and a shallow outlet."""
import unittest
from unittest.mock import patch

import numpy as np

import plays as P
import schemes as S
import targets as TG
from test_coverage_recording import offense
from test_defensive_rush import unit, call


class LevelsRoutesTests(unittest.TestCase):
    def test_intermediate_and_shallow_routes_keep_distinct_depths(self):
        self.assertEqual(S.CONCEPTS['levels']['depth'], 'medium')
        observed = {}
        for role in ('deep_in', 'shallow'):
            def choose(pairs, *args, **kwargs):
                pair = next(p for p in pairs if p.get('concept_role') == role)
                return (pair['receiver'], pair.get('defender'), 'first',
                        pair.get('separation', .42))

            passes = []
            with patch.object(TG, 'select_target', side_effect=choose):
                for seed in range(80):
                    result = P.resolve_play(
                        offense(), unit('4-3', 'nickel'),
                        dict(is_pass=True, depth='medium', concept='levels',
                             personnel='11', protection='five'),
                        dict(call('4-3', 'nickel'), coverage='cover_3', shell='cover_3'),
                        70, np.random.default_rng(seed))
                    if result.get('type') == 'complete':
                        passes.append(result)
            self.assertGreater(len(passes), 8)
            observed[role] = passes
        self.assertTrue(all(p['depth'] == 'medium' for p in observed['deep_in']))
        self.assertTrue(all(p['depth'] == 'short' for p in observed['shallow']))
        middle_air = sum(p['air'] for p in observed['deep_in']) / len(observed['deep_in'])
        shallow_air = sum(p['air'] for p in observed['shallow']) / len(observed['shallow'])
        self.assertGreater(middle_air - shallow_air, 5.0)


if __name__ == '__main__':
    unittest.main()
