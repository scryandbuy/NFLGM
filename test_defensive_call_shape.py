"""A defensive call and its on-field role package describe the same eleven."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import defense_roles as DR
import schemes as SC


class DefensiveCallShapeTests(unittest.TestCase):
    def test_coach_front_and_each_standard_package(self):
        expected = {
            '4-3': {
                'base': {'dl': 4, 'lb': 3, 'db': 4},
                'nickel': {'dl': 4, 'lb': 2, 'db': 5},
                'dime': {'dl': 4, 'lb': 1, 'db': 6},
                'heavy': {'dl': 5, 'lb': 3, 'db': 3},
            },
            '3-4': {
                'base': {'dl': 3, 'lb': 4, 'db': 4},
                'nickel': {'dl': 4, 'lb': 2, 'db': 5},
                'dime': {'dl': 4, 'lb': 1, 'db': 6},
                'heavy': {'dl': 5, 'lb': 3, 'db': 3},
            },
        }
        fronts = {'4-3': ['4-3 over', '4-3 under'],
                  '3-4': ['3-4 one', '3-4 two', 'tite']}
        for family, packages in expected.items():
            gm = SimpleNamespace(def_front=family, aggression=.5, board_trust=.5)
            for package, counts in packages.items():
                with self.subTest(family=family, package=package):
                    with patch.object(SC, 'defensive_personnel', return_value=package):
                        call = SC.call_defense(
                            {'personnel': '11'}, 2, 7, np.random.default_rng(11),
                            gm=gm, lean={'front_pref': fronts[family]})
                    self.assertEqual(call['front_family'], family)
                    self.assertEqual(call['personnel'], package)
                    self.assertEqual(DR.counts(call['front_family'], package), counts)
                    self.assertEqual(sum(counts.values()), 11)


if __name__ == '__main__':
    unittest.main()
