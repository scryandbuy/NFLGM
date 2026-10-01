"""A buyer's roster need must not inflate the seller's asking price."""

import unittest

import trade_engine as TE


class TradeNeedPricingTests(unittest.TestCase):
    def test_need_changes_buyer_price_only(self):
        team = dict(win_pct=0.65, avg_age=27.0)
        base = dict(kind='player', trade_value=15.0, trade_value_buyer=15.0,
                    age=23, apy=2.0, inherit=2.0, dead=0.0)
        gm = TE.GM_ARCHETYPES['balanced']
        ordinary = dict(base, need=False)
        needed = dict(base, need=True)

        self.assertEqual(
            TE.team_price(ordinary, team, 30.0, gm, owns=True),
            TE.team_price(needed, team, 30.0, gm, owns=True))
        self.assertGreater(
            TE.team_price(needed, team, 30.0, gm, owns=False),
            TE.team_price(ordinary, team, 30.0, gm, owns=False))


if __name__ == '__main__':
    unittest.main()
