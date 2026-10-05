"""Compare negotiation results to a small exhaustive market, not search internals."""
import itertools
import random
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import trades as TR
import trade_engine as TE


class Roll:
    def __init__(self, value=.999):
        self.value, self.calls = value, 0

    def random(self):
        self.calls += 1
        return self.value


def pick(i, paid, received=None, spent=None):
    return dict(kind='pick', pick=i, years_out=0, market=paid,
                buy=paid if spent is None else spent,
                sell=paid if received is None else received,
                obj=SimpleNamespace(year=2028, round=i, original='A'))


def player(pid, value, contribution=1, pos='LB', inherit=0):
    return dict(kind='player', pid=pid, trade_value=value, buy=value, sell=value,
                inherit=inherit, obj=SimpleNamespace(pid=pid, pos=pos, contribution=contribution))


class PackageSearchTests(unittest.TestCase):
    def negotiate(self, bank, surplus=(), gain=6, incoming=30, ask=12,
                  market=12, recipient=None, max_nodes=None, roll=None,
                  years=2, wants_out=False, user=False, seller_gm=None):
        target = player('target', market)
        target['obj'].contract_years_left = years
        target.update(package_gain=gain, buy=ask, sell=incoming, wants_out=wants_out)
        ctx = dict(win_pct=.7, avg_age=26)
        gm = dict(aggression=.5)
        team = SimpleNamespace(active=lambda: [target['obj']]) if recipient is None else recipient
        roll = roll or Roll()
        def quote(asset, ctx, space, gm, owns=False):
            return asset['buy' if owns else 'sell']
        # A player must improve a distinct role. Two identical reserves
        # cannot both pad the price after one has filled that role.
        def score(team, players):
            roles = {}
            for p in players:
                roles[p.pos] = max(roles.get(p.pos, 0), p.contribution)
            return dict(score=sum(roles.values()))
        with ExitStack() as stack:
            stack.enter_context(patch.object(TR, '_picks_by_price', return_value=list(bank)))
            costs = {p['pick']: p['market'] for p in bank}
            stack.enter_context(patch.object(TE, 'pick_value_dollars', side_effect=lambda i, y=0, **kw: costs[i]))
            stack.enter_context(patch.object(TE, 'team_price', side_effect=quote))
            if recipient is None:
                stack.enter_context(patch('roster_needs.assess', side_effect=score))
            # This exhaustive search fixture has no contracts or league ledger;
            # cap/future-funding behavior is covered by the integration tests.
            stack.enter_context(patch.object(TR, '_financial_trade', return_value=True))
            if max_nodes is not None:
                stack.enter_context(patch.object(TR, 'MAX_PACKAGE_SEARCH', max_nodes))
            team.abbr = 'B'
            result = TR._negotiate(SimpleNamespace(user_team='B') if user else None, team, team, target, gm, seller_gm or dict(gm, pick_lens=.3), ctx, ctx,
                                   100, 100, list(surplus), roll, needs_b={'LB': 50})
        return result

    def test_rejected_package_is_not_selected_again(self):
        with patch.object(TR, 'trade_was_rejected', return_value=True):
            offer, result = self.negotiate([pick(1, 10, received=10)], market=10, user=True)
        self.assertIsNone(offer)
        self.assertIsNone(result)

    def test_user_offer_does_not_require_simulated_seller_acceptance(self):
        bank = [pick(1, 10, received=10)]
        self.assertIsNone(self.negotiate(bank, ask=100)[0])
        offer, result = self.negotiate(bank, market=10, ask=100, user=True)
        self.assertIsNotNone(offer)
        self.assertGreaterEqual(result['search']['package_market'], result['search']['market_floor'])
        self.assertLessEqual(result['search']['package_market'], result['search']['market_ceiling'])

    def test_two_later_picks_before_first_and_no_forced_player(self):
        offer, result = self.negotiate([pick(1, 16), pick(2, 5, 7), pick(3, 5, 7)],
                                       [player('filler', 2, 0)], market=10)
        self.assertEqual({a['pick'] for a in offer['a_sends']}, {2, 3})
        self.assertEqual(result['search']['package_market'], 10)
        self.assertEqual(result['search']['target_gain'], 6)

    def test_player_alone_can_close_without_a_sweetener(self):
        p = player('needed', 13)
        offer, _ = self.negotiate([pick(1, 16)], [p])
        self.assertEqual(offer['a_sends'], [p])

    def test_redundant_players_cannot_pad_combined_offer(self):
        a, b = player('a', 7), player('b', 7)
        offer, _ = self.negotiate([pick(1, 15)], [a, b])
        self.assertEqual(offer['a_sends'][0]['kind'], 'pick')
        self.assertEqual(len(offer['a_sends']), 1)

    def test_cap_invalid_player_offer_does_not_hide_legal_pick_offer(self):
        p = player('too_expensive', 13, inherit=150)
        offer, _ = self.negotiate([pick(1, 15)], [p])
        self.assertEqual(offer['a_sends'][0]['kind'], 'pick')

    def test_complete_package_cap_can_work_when_individual_player_cannot(self):
        p = player('needed', 7, inherit=110)
        p['out_hit'] = 0
        # Seller sheds the target's salary, so 110 fits after the exchange.
        # Exercise this path with real cap checks in a separately patched target.
        original = TE.cap_blocks
        def cap(offer, *args, **kwargs):
            offer = dict(offer, a_gets=[dict(offer['a_gets'][0], out_hit=20)])
            return original(offer, *args, **kwargs)
        with patch.object(TE, 'cap_blocks', side_effect=cap):
            offer, _ = self.negotiate([pick(1, 6, 7)], [p])
        self.assertEqual(len(offer['a_sends']), 2)

    def test_washington_sized_upgrade_cannot_unlock_first(self):
        bank = [pick(1, 16.70, 17.869, 10.9125)]
        for ask in (17.35, 14.70):  # before/after buyer-only need pricing
            offer, _ = self.negotiate(bank, gain=2.225, incoming=25.60,
                                      ask=ask, market=15.88)
            self.assertIsNone(offer)
        offer, _ = self.negotiate(bank, gain=6, incoming=25.60,
                                  ask=14.70, market=15.88)
        self.assertIsNotNone(offer)  # no blanket first-round ban

    def test_budget_curve_continuous_monotone_and_bounded(self):
        values = [TR._upgrade_budget(x / 100) for x in range(0, 1001)]
        self.assertEqual(values, sorted(values))
        self.assertEqual((values[200], values[600]), (.4, 1.0))
        self.assertLess(max(b-a for a,b in zip(values, values[1:])), .003)

    def test_search_budget_exhaustion_declines_instead_of_overpaying(self):
        offer, result = self.negotiate([pick(1, 16), pick(2, 5, 7), pick(3, 5, 7)], max_nodes=1)
        self.assertIsNone(offer)
        self.assertIsNone(result)

    def test_role_assignment_budget_also_fails_closed(self):
        with patch.object(TR, 'MAX_PACKAGE_ROSTER_CHECKS', 1):
            offer, result = self.negotiate([pick(1, 16)], [player('needed', 13)])
        self.assertIsNone(offer)
        self.assertIsNone(result)

    def test_inventory_order_does_not_change_choice_or_willingness_draws(self):
        bank = [pick(1, 16), pick(2, 5, 7), pick(3, 5, 7)]
        for order in itertools.permutations(bank):
            roll = Roll(.35)
            offer, _ = self.negotiate(order, roll=roll, market=10)
            self.assertEqual([p['pick'] for p in offer['a_sends']], [2, 3])
            self.assertEqual(roll.calls, 2)

    def test_duplicate_assets_never_count_twice(self):
        p = pick(1, 7)
        offer, _ = self.negotiate([p, p])
        self.assertIsNone(offer)

    def test_private_pick_enthusiasm_cannot_bypass_neutral_floor(self):
        bank = [pick(1, 3, 20), pick(2, 7, 20), pick(3, 16, 20)]
        offer, _ = self.negotiate(bank, market=20, ask=19)
        self.assertGreaterEqual(sum(p['market'] for p in offer['a_sends']), 20)

    def test_rental_and_wants_out_have_discount_but_not_free_giveaway(self):
        bank = [pick(1, 3, 20), pick(2, 7, 20), pick(3, 16, 20)]
        for options in (dict(years=1), dict(wants_out=True)):
            offer, _ = self.negotiate(bank, market=20, ask=19, **options)
            self.assertGreaterEqual(sum(p['market'] for p in offer['a_sends']), 20)

    def test_marginal_controlled_upgrade_walks_when_budget_below_seller_floor(self):
        offer, _ = self.negotiate([pick(1, 7, 20)], gain=2.225,
                                  incoming=25.60, ask=14.70, market=15.88)
        self.assertIsNone(offer)

    def test_five_asset_limit_and_willingness_rolls_are_fixed(self):
        roll = Roll()
        offer, _ = self.negotiate([pick(i, 2) for i in range(6)], ask=11, roll=roll)
        self.assertIsNone(offer)
        self.assertEqual(roll.calls, 2)

    def test_small_random_markets_match_exhaustive_minimum(self):
        rng = random.Random(301)
        for trial in range(35):
            bank = [pick(i, rng.randint(1, 12), rng.randint(1, 15), rng.randint(1, 12)) for i in range(9)]
            valid = []
            for count in range(1, 6):
                for combo in itertools.combinations(bank, count):
                    paid = sum(p['market'] for p in combo)
                    cost = sum(p['buy'] for p in combo)
                    value = sum(p['sell'] for p in combo)
                    if (25 <= paid <= 25*1.25+.35 and 30-cost > -TR.ACCEPT_WINDOW
                            and TR.will_accept(round(30-cost, 2), Roll(), .5)):
                        valid.append((paid, count, cost))
            offer, _ = self.negotiate(bank, market=25, user=True)
            with self.subTest(trial=trial):
                if not valid:
                    self.assertIsNone(offer)
                else:
                    outs = offer['a_sends']
                    self.assertEqual((sum(p['market'] for p in outs), len(outs), sum(p['buy'] for p in outs)), min(valid))

    def test_seller_counter_is_optional_and_uses_only_seller_quotes(self):
        original = [pick(3, 5, 7), pick(4, 5, 7)]
        higher = pick(1, 10.8, 14.6)
        def quote(a, ctx, space, gm, owns=False):
            self.assertIs(ctx, context)
            self.assertFalse(owns)
            return a['sell'] + (1 if a['pick'] == 1 and gm['pick_lens'] > .6 else 0)
        context = dict(win_pct=.5, avg_age=27)
        with patch.object(TE, 'market_price', side_effect=lambda a:a['market']), patch.object(TE, 'team_price', side_effect=quote):
            self.assertIsNone(TR.seller_pick_counter(original, [higher], context, dict(pick_lens=.2), 100))
            result = TR.seller_pick_counter(original, [higher], context, dict(pick_lens=.9), 100)
            self.assertEqual(result, [higher])
            self.assertIsNone(TR.seller_pick_counter(original, [pick(1, 10.8, 13.8)], context, dict(pick_lens=.9), 100))

    def test_buyer_independently_accepts_or_declines_seller_counter(self):
        for spend, expected in ((10.8, [1]), (100, [3, 4])):
            offer, result = self.negotiate([pick(1, 10.8, 16, spend), pick(3, 5, 7), pick(4, 5, 7)], seller_gm=dict(aggression=.5, pick_lens=.9), market=10)
            self.assertEqual([a['pick'] for a in offer['a_sends']], expected)
            self.assertTrue(result['search']['seller_counter_proposed'])
            self.assertEqual(result['search']['seller_counter_accepted'], spend < 100)

    def test_seller_can_request_addition_then_buyer_decides(self):
        bank = [pick(2, 6), pick(3, 6), pick(4, 3)]
        offer, result = self.negotiate(bank, ask=14, market=12)
        self.assertIsNotNone(offer)
        self.assertFalse(result['search']['initial_offer_accepted'])
        self.assertTrue(result['search']['seller_counter_accepted'])
        self.assertEqual({a['pick'] for a in offer['a_sends']}, {2, 3, 4})
        # Same seller request, but the buyer places greater value on that pick.
        bank[-1]['buy'] = 100
        self.assertIsNone(self.negotiate(bank, ask=14, market=12)[0])

    def test_initial_proposal_does_not_know_seller_private_strategy(self):
        originals = []
        def inspect(original, *args, **kwargs):
            originals.append([a['pick'] for a in original])
            return None
        bank = [pick(1, 14), pick(2, 6), pick(3, 6)]
        with patch.object(TR, 'seller_pick_counter', side_effect=inspect):
            for ask, name in ((10, 'analytics'), (100, 'traditional')):
                self.negotiate(bank, ask=ask, seller_gm=TE.GM_ARCHETYPES[name])
        self.assertEqual(originals, [[2, 3], [2, 3]])

    def test_real_pick_chart_produces_optional_strategy_dependent_counters(self):
        bank = [dict(kind='pick', pick=6+(rd-1)*32, years_out=y, cap=400,
                     obj=SimpleNamespace(year=2029+y, round=rd, original='A'))
                for y in range(2) for rd in range(1, 8)]
        counts = []
        for name in ('analytics', 'traditional'):
            results = [TR.seller_pick_counter(list(original), bank,
                       dict(win_pct=.25, avg_age=29), TE.GM_ARCHETYPES[name], 100)
                       for original in itertools.combinations(bank, 2)]
            counts.append(sum(r is not None for r in results))
            self.assertTrue(any(r is None for r in results))
            self.assertTrue(any(r is not None for r in results))
        self.assertNotEqual(*counts)

    def test_real_roster_rejects_extra_linebacker_despite_needs_label(self):
        from test_package_roster_needs import team, player as roster_player
        t = team('11', '4-3')
        spare = roster_player('WILL', 'incoming', 60)
        asset = player(spare.pid, 13)
        asset['obj'] = spare
        offer, _ = self.negotiate([pick(1, 15)], [asset], recipient=t)
        self.assertEqual([p['kind'] for p in offer['a_sends']], ['pick'])


if __name__ == '__main__':
    unittest.main()
