"""Batch season runs must settle claims and verify the final CPU roster gate."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import franchise


class FranchiseRosterGateTests(unittest.TestCase):
    def test_claims_trigger_another_roster_pass_before_season_opens(self):
        league = SimpleNamespace()
        rng = object()
        with patch.object(franchise.CD, 'finalize', side_effect=[(['first'], 1), (['second'], 2)]) as finalize, \
                patch.object(franchise.CD, 'violations', return_value=[], create=True) as violations, \
                patch.object(franchise.WV, 'pending', side_effect=[[{'pid': 'rookie'}], []]), \
                patch.object(franchise.WV, 'notify_user'), \
                patch.object(franchise.WV, 'process', return_value=['claim']) as process:
            cuts, filled, claims = franchise.settle_final_rosters(league, rng)
        self.assertEqual((cuts, filled, claims), (['first', 'second'], 3, 1))
        self.assertEqual(finalize.call_count, 2)
        process.assert_called_once_with(league, rng, 0, entries=[{'pid': 'rookie'}])
        violations.assert_called_once_with(league)

    def test_unplayable_roster_blocks_batch_season(self):
        league = SimpleNamespace()
        with patch.object(franchise.CD, 'finalize', return_value=([], 0)), \
                patch.object(franchise.WV, 'pending', return_value=[]), \
                patch.object(franchise.CD, 'violations', return_value=[{'team': 'GB', 'missing': ['LS']}], create=True):
            with self.assertRaisesRegex(RuntimeError, 'Unresolved CPU rosters'):
                franchise.settle_final_rosters(league, object())


if __name__ == '__main__':
    unittest.main()
