"""Minimum-pay roster repairs require player consent before any outgoing cut."""
import copy
import unittest
from unittest.mock import patch

import cutdown as CD
import practice_squad as PS
import targets as TG
from league import Player
from replacement_contracts import minimum_acceptance
from test_draft_planning import fixture


class ReplacementConsentTests(unittest.TestCase):
    def setUp(self):
        self.L, self.t = fixture()
        self.L.set_phase('regular'); self.L.week = 9
        self.p = Player('street-veteran', 'Street Veteran', 'QB', 29,
                        {k: 85. for k in TG.DEPTH_WEIGHTS['QB']})
        self.L.players[self.p.pid] = self.p
        self.L.free_agents.append(self.p.pid)

    def test_valuable_player_refuses_minimum_before_any_roster_change(self):
        before = list(self.t.roster)
        with patch('valuation.value_player', return_value={'apy': 20.}), \
             patch.object(PS, '_active_move') as move:
            self.assertFalse(PS.minimum_fits(self.L, self.t, self.p))
            self.assertFalse(PS.sign_minimum(self.L, self.t.abbr, self.p))
        move.assert_not_called()
        self.assertEqual(before, self.t.roster)
        self.assertIn(self.p.pid, self.L.free_agents)
        self.assertIsNone(self.p.team)

    def test_direct_repair_helper_cannot_bypass_consent(self):
        with patch('valuation.value_player', return_value={'apy': 20.}):
            self.assertFalse(CD._sign_replacement(self.L, self.t, self.p,
                                                 PS.minimum_contract(self.L, self.t, self.p)))
        self.assertIsNone(self.p.team)

    def test_recent_release_cannot_be_rehired_at_minimum(self):
        self.p.xp_spent['_released_by'] = {self.t.abbr: 9}
        with patch('valuation.value_player', return_value={'apy': .5}):
            answer = minimum_acceptance(self.L, self.t, self.p)
        self.assertFalse(answer['accepts'])
        self.assertEqual(answer['reason'], 'recent_release')

    def test_old_release_does_not_permanently_ban_willing_player(self):
        self.p.xp_spent['_released_by'] = {self.t.abbr: 0}
        with patch('valuation.value_player', return_value={'apy': .5}):
            self.assertTrue(minimum_acceptance(self.L, self.t, self.p)['accepts'])

    def test_willing_minimum_player_still_signs(self):
        self.t.cap.cap = 500.; self.t.sync_cap()
        with patch('valuation.value_player', return_value={'apy': .5}), \
             patch.object(PS, '_active_move', return_value=(True, None)):
            self.assertTrue(PS.sign_minimum(self.L, self.t.abbr, self.p))
        self.assertEqual(self.p.team, self.t.abbr)
        self.assertEqual(self.p.contract.years, 1)
        self.assertNotIn(self.p.pid, self.L.free_agents)

    def test_late_season_zero_cash_does_not_erase_annual_reservation(self):
        self.L.week = 18; self.t.cap.paid_week = 18
        with patch('valuation.value_player', return_value={'apy': 20.}):
            answer = minimum_acceptance(self.L, self.t, self.p)
        self.assertFalse(answer['accepts'])
        self.assertGreater(answer['annual_offer'], 0)

    def test_consent_is_repeatable_without_consuming_simulation_rng(self):
        import numpy as np
        self.L.rng = np.random.default_rng(123)
        state = copy.deepcopy(self.L.rng.bit_generator.state)
        player_state = copy.deepcopy(self.p.xp_spent)
        with patch('valuation.value_player', return_value={'apy': 3.}):
            first = minimum_acceptance(self.L, self.t, self.p)
            second = minimum_acceptance(self.L, self.t, self.p)
        self.assertEqual(first, second)
        self.assertEqual(state, self.L.rng.bit_generator.state)
        self.assertEqual(player_state, self.p.xp_spent)

    def test_market_price_not_rating_cutoff_controls_acceptance(self):
        with patch('valuation.value_player', return_value={'apy': .5}):
            self.assertTrue(minimum_acceptance(self.L, self.t, self.p)['accepts'])
        self.p.ratings = {k: 55. for k in TG.DEPTH_WEIGHTS['QB']}
        with patch('valuation.value_player', return_value={'apy': 20.}):
            self.assertFalse(minimum_acceptance(self.L, self.t, self.p)['accepts'])


if __name__ == '__main__':
    unittest.main()
