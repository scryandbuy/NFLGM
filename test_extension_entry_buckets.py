import unittest
from types import SimpleNamespace as NS
from views_personnel import _extension_years_left

class ExtensionEntryBuckets(unittest.TestCase):
    def test_entering_step_one_matches_completed_rollover(self):
        session = NS(stop=('offseason', 1), offseason_progress={})
        player = NS(contract=NS(years=1))
        self.assertEqual(_extension_years_left(session, None, player), 0)
        self.assertEqual(player.contract.years, 1)
        player.contract.years = 2
        self.assertEqual(_extension_years_left(session, None, player), 1)
        player.contract.years = 1
        session.offseason_progress['contracts_advanced'] = True
        self.assertEqual(_extension_years_left(session, None, player), 1)
        session.stop = ('offseason', 2)
        self.assertEqual(_extension_years_left(session, None, player), 1)

    def test_in_season_and_expired_contracts(self):
        session = NS(stop=('week', 18), offseason_progress={})
        self.assertEqual(_extension_years_left(session, None, NS(contract=NS(years=1))), 1)
        session.stop = ('offseason', 1)
        self.assertEqual(_extension_years_left(session, None, NS(contract=None)), 0)
