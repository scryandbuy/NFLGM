"""A deadline rental buys the remaining run, not another full contract year."""
import copy
import unittest
from unittest.mock import patch

from cap_engine import Contract
from cap_accounting import transfer_contract
from test_cap_casualty_trades import setup_market
from test_trade_package_search import Roll
import trades as TR
import trade_engine as TE


class RemainingControlTests(unittest.TestCase):
    def setUp(self):
        self.L, self.seller, self.player, _ = setup_market()
        self.L.phase = 'regular'
        self.L.week = 9
        self.player.contract = Contract(1, [6.0])
        self.quote = patch.object(TR.VAL, 'value_player', return_value={'apy': 28.0})
        self.quote.start()
        self.addCleanup(self.quote.stop)

    def asset(self, paid):
        self.seller.cap.paid_week = paid
        self.player.contract.earned_base = 6.0 * paid / 18
        return TR.player_asset(self.L, self.seller, self.player, None, None)

    def test_rental_price_falls_with_remaining_service_for_young_and_old_players(self):
        for age in (25, 31, 35):
            self.player.age = age
            whole, half = self.asset(0), self.asset(9)
            self.assertGreater(half['trade_value'], 0)
            self.assertAlmostEqual(half['trade_value'], whole['trade_value'] / 2, delta=.01)
            self.assertEqual(self.asset(18)['trade_value'], 0)

    def test_transferring_or_signing_midseason_does_not_restore_full_season_value(self):
        half = self.asset(9)
        self.player.contract = transfer_contract(self.player.contract, 9)
        self.assertEqual(self.player.contract.earned_base, 0)
        transferred = TR.player_asset(self.L, self.seller, self.player, None, None)
        self.assertEqual(transferred['trade_value'], half['trade_value'])
        self.assertEqual(transferred['first_year_fraction'], .5)
        # A new contract for the same remaining pay has the same service.
        self.player.contract = Contract(1, [3.0], pay_start=9)
        self.assertEqual(TR.player_asset(self.L, self.seller, self.player, None, None)['trade_value'],
                         half['trade_value'])

    def test_full_future_years_are_not_prorated_like_the_rental_year(self):
        row = dict(age=27, ovr=88, madden_position='WR', apy=6,
                   contract_years_left=3, contract_costs=[6, 9, 12])
        value = lambda r: TE.trade_value(r, {'apy': 28})
        full = value(row)
        half = value(dict(row, first_year_fraction=.5, contract_costs=[3, 9, 12]))
        current_only = value(dict(row, contract_years_left=1, contract_costs=[6]))
        self.assertAlmostEqual(full - half, current_only / 2, delta=.02)
        self.assertGreater(half, current_only)

    def test_remaining_cash_is_charged_in_its_actual_year(self):
        row = dict(age=27, ovr=84, madden_position='WR', apy=10,
                   contract_years_left=2, first_year_fraction=.5)
        front = TE.trade_value(dict(row, contract_costs=[15, 5]), {'apy': 28})
        back = TE.trade_value(dict(row, contract_costs=[5, 15]), {'apy': 28})
        self.assertGreater(back, front)
        # Equal annual cash and full service retain the established prices.
        row['first_year_fraction'] = 1.
        self.assertEqual(TE.trade_value(row, {'apy': 28}),
                         TE.trade_value(dict(row, contract_costs=[10, 10]), {'apy': 28}))

    def test_completed_season_rights_have_no_fake_free_year(self):
        self.L.phase = 'offseason'
        self.L.season_closed_year = self.L.year
        self.asset(18)
        self.assertIsNone(TR.player_asset(self.L, self.seller, self.player, None, None))

    def test_completed_or_future_start_stub_matches_advanced_contract(self):
        self.L.phase = 'offseason'
        self.L.season_closed_year = self.L.year
        for stub in (False, True):
            self.player.contract = Contract(3, [0 if stub else 6, 9, 12],
                                            earned_base=0 if stub else 6,
                                            start_offset=int(stub))
            before = TR.player_asset(self.L, self.seller, self.player, None, None)
            self.player.contract.advance()
            self.L.year += 1
            after = TR.player_asset(self.L, self.seller, self.player, None, None)
            self.assertEqual(before['trade_value'], after['trade_value'])
            self.assertEqual(before['valued_contract_years'], 2)
            self.L.year -= 1

    def test_current_cap_room_and_dead_charges_still_use_full_ledger(self):
        self.player.contract = Contract(2, [6, 10], signing_bonus=16)
        before = copy.deepcopy(vars(self.player.contract))
        half = self.asset(9)
        self.assertEqual(half['dead'], 16)
        self.assertEqual(half['inherit'], 3)
        self.assertEqual(half['out_hit'], 11)
        self.assertEqual(self.player.contract.base, before['base'])
        self.assertEqual(self.player.contract.bonus_schedule, before['bonus_schedule'])

    def test_seller_floor_counts_playing_seasons_not_calendar_stubs(self):
        self.L.phase = 'offseason'
        self.L.season_closed_year = self.L.year
        for stub in (False, True):
            for future_years in (1, 2):
                self.player.contract = Contract(future_years + 1,
                    [0 if stub else 6] + [6] * future_years,
                    earned_base=0 if stub else 6, start_offset=int(stub))
                before = TR.player_asset(self.L, self.seller, self.player, None, None)
                before_floor = TR._market_floor(before)
                self.player.contract.advance()
                self.L.year += 1
                after = TR.player_asset(self.L, self.seller, self.player, None, None)
                self.assertEqual(before['trade_value'], after['trade_value'])
                self.assertEqual(before_floor, TR._market_floor(after))
                fraction = .5 if future_years == 1 else .75
                self.assertEqual(before_floor, before['trade_value'] * fraction)
                # A concrete retention ask still binds independently of the
                # minimum concession permitted by remaining service.
                retained = dict(after, retention_floor=after['trade_value'])
                self.assertEqual(TR._market_floor(retained), after['trade_value'])
                self.L.year -= 1

    def test_public_development_credit_uses_actual_future_control(self):
        self.L.phase = 'offseason'
        self.L.season_closed_year = self.L.year
        self.player.age = 23
        self.player.dev = 'xfactor'
        for stub in (False, True):
            self.player.contract = Contract(2, [0 if stub else 6, 6],
                earned_base=0 if stub else 6, start_offset=int(stub))
            saved_contract = copy.deepcopy(vars(self.player.contract))
            before = TR.player_asset(self.L, self.seller, self.player, None, None)
            self.assertEqual(vars(self.player.contract), saved_contract)
            self.player.contract.advance()
            self.L.year += 1
            after = TR.player_asset(self.L, self.seller, self.player, None, None)
            self.assertEqual(before['trade_value'], after['trade_value'])
            self.player.dev = 'normal'
            ordinary = TR.player_asset(self.L, self.seller, self.player, None, None)
            self.assertGreater(after['trade_value'], ordinary['trade_value'])
            self.player.dev = 'xfactor'
            self.L.year -= 1
        from development_value import player_credit
        self.assertGreater(player_credit(self.player, years=3),
                           player_credit(self.player, years=1))

    def test_lower_rental_price_allows_cheap_help_but_rejects_full_season_price(self):
        row = dict(age=31, ovr=88, madden_position='WR', apy=6,
                   contract_years_left=1, contract_costs=[3], first_year_fraction=.5)
        value = TE.trade_value(row, {'apy': 28})
        target = dict(kind='player', age=31, need=True, apy=6, inherit=3,
                      trade_value=value, trade_value_buyer=value)
        context = dict(win_pct=.7, avg_age=27)
        gm = TE.GM_ARCHETYPES['win_now']
        price = TE.team_price(target, context, 30, gm)
        whole = dict(target, trade_value=value*2, trade_value_buyer=value*2)
        whole_price = TE.team_price(whole, context, 30, gm)
        def pick_cost(slot):
            return TE.team_price(dict(kind='pick', pick=slot, years_out=0, cap=401.583),
                                 context, 30, gm, owns=True)
        # Concrete draft alternatives: a contender still buys the rental for
        # a second, but will not pay the top-ten price it pays for full control.
        self.assertTrue(TR.will_accept(price - pick_cost(48), Roll(0), gm['aggression']))
        self.assertTrue(TR.will_accept(whole_price - pick_cost(7), Roll(0), gm['aggression']))
        self.assertFalse(TR.will_accept(price - pick_cost(7), Roll(0), gm['aggression']))
        prices = [TE.team_price(target, context, 30, g) for g in TE.GM_ARCHETYPES.values()]
        self.assertGreater(max(prices) - min(prices), 1)


if __name__ == '__main__':
    unittest.main()
