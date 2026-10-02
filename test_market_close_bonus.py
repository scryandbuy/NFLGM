"""Automatic pre-draft signings should be cheap to release after the draft."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import market


class MarketCloseBonusTests(unittest.TestCase):
    def setUp(self):
        self.player = SimpleNamespace(pid='FA1', pos='WR', ovr=77.0,
                                      accrued=2, team=None)
        self.team = SimpleNamespace(
            abbr='AAA', cap_space=50.0, depth={},
            active=lambda: [], by_pos=lambda pos: [],
            spending_power=lambda *args: 50.0, sync_cap=lambda: None)
        self.league = SimpleNamespace(year=2028, teams={'AAA': self.team})
        self.rng = SimpleNamespace(normal=lambda *args: 0.0)

    def test_minimum_depth_signings_have_no_bonus(self):
        pool = [self.player]
        with patch('roster_needs.assess', return_value={'needs': {'WR': 1.0}}), \
             patch.object(market, 'sign') as sign:
            self.assertEqual(market.fill_out_rosters(self.league, pool, self.rng), 1)
            self.assertEqual(sign.call_args.kwargs['bonus'], 0)

    def test_discounted_market_close_veterans_keep_normal_bonus(self):
        self.player.ovr = 82.0
        with patch('roster_needs.assess', return_value={'needs': {'WR': 1.0}}), \
             patch.object(market.VAL, 'pool_from_league', return_value=[]), \
             patch.object(market.VAL, 'value_player', return_value={'apy': 6.0}), \
             patch.object(market, 'sign') as sign:
            signed = market.sign_the_leftovers(self.league, [self.player], self.rng)
            self.assertEqual(len(signed), 1)
            self.assertNotIn('bonus', sign.call_args.kwargs)

    def test_no_bonus_preserves_one_year_cap_hit(self):
        self.team.gm = SimpleNamespace(restructure_depth=0.5)
        self.team.cap = SimpleNamespace(paid_week=0)
        self.league.phase = 'free_agency'
        self.league.week = 22
        normal = market.signing_terms(self.league, self.player, self.team,
                                      6.0, 1, 300.0)
        clean = market.signing_terms(self.league, self.player, self.team,
                                     6.0, 1, 300.0, bonus=0)
        self.assertGreater(normal['signing_bonus'], 0)
        self.assertEqual(clean['signing_bonus'], 0)
        self.assertEqual(clean['cap_hits'], normal['cap_hits'])


if __name__ == '__main__':
    unittest.main()
