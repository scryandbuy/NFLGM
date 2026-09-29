import unittest

import numpy as np

import league
import trade_engine
import valuation
import views_club


class PlayerCardMarketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.league = league.build_league(rng=np.random.default_rng(2026))

    def test_elite_quarterback_card_matches_trade_price(self):
        player = self.league.player('P0210')
        quote = valuation.value_player(self.league, player, side='team')
        label, read = views_club._market_words(self.league, player, quote)
        row = dict(age=player.age, apy=player.apy, ovr=player.ovr,
                   contract_years_left=player.contract_years_left,
                   madden_position=player.pos)
        price = trade_engine.trade_value(row, quote)

        self.assertGreater(price, 2 * trade_engine.pick_price_dollars(16))
        self.assertEqual(label, 'Multiple 1sts')
        self.assertIn('multiple first-round picks', read)
        self.assertIn('market-level deal', read)


if __name__ == '__main__':
    unittest.main()
