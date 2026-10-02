"""Trade decisions use future pay and net cap room, not sunk bonuses."""
import unittest
from unittest.mock import patch

import trade_engine as TE
import trades as TR
from cap_engine import Contract
from test_cap_casualty_trades import setup_market


class TradeDeadMoneyRealismTests(unittest.TestCase):
    def test_paid_bonus_is_not_part_of_keep_or_acquire_salary(self):
        league, seller, player, _ = setup_market()
        player.contract = Contract(3, [8, 8, 8], signing_bonus=30)
        player.contract.earned_base = 4
        with patch.object(TR.VAL, 'value_player', return_value={'apy': 28}):
            asset = TR.player_asset(league, seller, player, None, None)
        self.assertAlmostEqual(asset['inherited_apy'], 20 / 3, places=2)
        self.assertGreater(asset['apy'], asset['inherited_apy'])
        self.assertEqual(asset['trade_value'], asset['trade_value_buyer'])
        self.assertEqual(asset['dead'], 30)

    def test_high_dead_charge_can_still_create_cap_room(self):
        player = dict(kind='player', age=28, need=False, trade_value=12,
                      apy=18, inherit=8, out_hit=25, dead_now=20, dead=30)
        offer = dict(a_sends=[player], a_gets=[])
        self.assertIsNone(TE.cap_blocks(offer, 10, 100))
        self.assertIsNone(TE.cap_blocks(offer, 2, 100))
        player['dead_now'] = 29
        self.assertEqual(TE.cap_blocks(offer, 2, 100), 'a_cannot_fit')


if __name__ == '__main__':
    unittest.main()
