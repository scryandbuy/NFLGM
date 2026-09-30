import copy
import unittest
from types import SimpleNamespace

import numpy as np

from cap_engine import CAP, Contract
from league import League, contract_from_dict, contract_to_dict
from test_cap_accounting import fixture
import valuation as VAL


class CapMarketInflationTests(unittest.TestCase):
    def setUp(self):
        self.caps = CAP.copy()

    def tearDown(self):
        CAP.clear()
        CAP.update(self.caps)
        VAL._RA_CACHE.clear()
        VAL._MT_CACHE.clear()

    def test_old_contracts_keep_dollars_while_new_quotes_follow_cap(self):
        league = League(2026)
        players = []
        for n in range(12):
            contract = Contract(3, [20.0] * 3, signed=2026)
            p = SimpleNamespace(pid=str(n), name=str(n), pos='QB', age=28,
                                ovr=80 + n, team='A', retired=False,
                                apy=20.0, contract=contract, draft_overall=None,
                                draft_year=None, draft_round=None)
            players.append(p)
        league.players = {p.pid: p for p in players}
        league.teams = {'A': SimpleNamespace(active=lambda: players)}
        before = VAL.value_player(league, players[-1], side='team')['apy']
        league.year = 2027
        league.cap_history[2027] = round(CAP[2026] * 1.075, 3)
        after = VAL.value_player(league, players[-1], side='team')['apy']
        self.assertEqual(players[-1].apy, 20.0)
        self.assertAlmostEqual(VAL.pool_from_league(league).iloc[0].cappct,
                               20.0 / CAP[2026])
        self.assertGreater(after, before * 1.03)
        self.assertLess(after, before * 1.12)

    def test_projected_cap_history_survives_reload_and_next_draw(self):
        league = fixture()
        rng = np.random.default_rng(42)
        league.roll_year(rng)
        saved = league.save()
        self.assertEqual(League.load(saved).cap_history, league.cap_history)
        state = copy.deepcopy(rng.bit_generator.state)
        reloaded = League.load(saved)
        other_rng = np.random.default_rng()
        other_rng.bit_generator.state = state
        self.assertEqual(league.roll_year(rng), reloaded.roll_year(other_rng))
        self.assertEqual(reloaded.cap_history[2027], league.cap_history[2027])

    def test_legacy_save_recovers_current_cap_without_stale_global_values(self):
        league = fixture()
        rng = np.random.default_rng(17)
        for _ in range(3):
            league.roll_year(rng)
        saved = league.to_dict()
        saved.pop('cap_history')
        current = league.cap_history[2029]
        CAP[2027], CAP[2028], CAP[2029] = 999, 999, 999
        loaded = League.load(saved)
        self.assertEqual(loaded.cap_history[2029], current)
        self.assertEqual(CAP[2029], current)
        self.assertLess(CAP[2026], loaded.cap_history[2027])
        self.assertLess(loaded.cap_history[2027], loaded.cap_history[2028])
        self.assertLess(loaded.cap_history[2028], current)

    def test_advance_signed_deal_keeps_cap_used_for_its_price(self):
        contract = Contract(3, [12.0] * 3, signed=2028, market_cap=323.0)
        restored = contract_from_dict(contract_to_dict(contract))
        player = SimpleNamespace(contract=restored)
        league = League(2028)
        league.cap_history[2028] = 350.0
        self.assertEqual(VAL._signed_cap(league, player), 323.0)


if __name__ == '__main__':
    unittest.main()
