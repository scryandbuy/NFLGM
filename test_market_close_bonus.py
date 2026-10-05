"""Routine depth deals wait for the draft and carry no signing bonus."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import market
import session
from cap_engine import Contract
from test_draft_planning import fixture as roster_fixture


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
             patch.object(market.VAL, 'pool_from_league', return_value=[]), \
             patch('replacement_contracts.minimum_acceptance', return_value={'accepts': True}), \
             patch.object(market, 'sign') as sign:
            self.assertEqual(market.fill_out_rosters(self.league, pool, self.rng), 1)
            self.assertEqual(sign.call_args.kwargs['bonus'], 0)

    def test_discounted_market_close_veterans_keep_normal_bonus(self):
        self.player.ovr = 82.0
        with patch('roster_needs.assess', return_value={
                 'needs': {'WR': 1.0}, 'players': (), 'package_assignments': []}), \
             patch('roster_needs.move_gain', return_value=(12, [])), \
             patch('financial_plan.evaluate', return_value={'approved': True}), \
             patch('financial_plan.retention_market', return_value={}), \
             patch('financial_plan.snapshot', return_value={}), \
             patch.object(market, 'power', return_value=50), \
             patch.object(market, 'offer_contract', return_value=Contract(1,[4.2])), \
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

    def test_market_waits_for_rookies_before_filling_depth(self):
        league, team = roster_fixture()
        removed = team.by_pos('WR')[-2:]
        for p in removed:
            team.roster.remove(p)
            league.players.pop(p.pid)
        team.sync_cap()
        self.assertEqual(len(team.active()), 51)

        street = copy.deepcopy(removed[0])
        street.pid = 'street-WR'
        street.team = None
        street.contract = None
        street.ratings = {key: 70 for key in street.ratings}
        league.players[street.pid] = street
        league.free_agents.append(street.pid)

        with patch('player_age.offseason'), \
             patch('negotiations.resolve'), \
             patch('negotiations._threads', return_value=[]), \
             patch.object(market, 'sign_the_leftovers', return_value=[]), \
             patch.object(market, 'resolve_offer_sheets'), \
             patch('contracts.enforce'):
            market.close_market(league, np.random.default_rng(2), user_team='GB')
        self.assertEqual(len(team.active()), 51)
        self.assertIsNone(street.team)

        rookie = copy.deepcopy(removed[1])
        rookie.pid = 'drafted-WR'
        rookie.team = None
        rookie.contract = None
        league.players[rookie.pid] = rookie

        def sign_rookie(*_args):
            league.sign(rookie.pid, team.abbr, Contract(4, [1.0] * 4))

        game = session.Session.__new__(session.Session)
        game.L = league
        game.user_team = league.user_team
        game.rng = np.random.default_rng(3)
        with patch.object(session.PSQ, 'udfa_camp', side_effect=sign_rookie), \
             patch.object(session.NG, 'build'), \
             patch.object(session.SC, 'scout'):
            game.step_camp()
        self.assertEqual(len(team.active()), 53)
        self.assertEqual(rookie.team, team.abbr)
        self.assertEqual(street.team, team.abbr)
        self.assertEqual(street.contract.sb, 0)


if __name__ == '__main__':
    unittest.main()
