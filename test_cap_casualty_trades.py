"""A cap trade replaces a decided release; it must never choose the release."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import contracts as CT
import trades as TR
import targets as TG
from cap_engine import Contract
from league import Team, DraftPick, contract_to_dict
from test_cap_accounting import fixture, player


def setup_market():
    L = fixture(); L.user_team = 'GB'; L.set_phase('offseason')
    for abbr in ('DEN', 'KC'):
        t = Team(abbr, 'Continental West', 'Continental'); t.league = L
        t.phase = 'offseason'; L.teams[abbr] = t
    seller = L.teams['MIN']; seller.cap.cap = 15; seller.cap.rollover = 0
    p = player(L, 'casualty', 'MIN', Contract(1, [20], signing_bonus=2))
    p.ratings = {k: 85 for k in TG.DEPTH_WEIGHTS['QB']}
    keep = player(L, 'keeper', 'MIN', Contract(1, [1]))
    keep.ratings = {k: 86 for k in TG.DEPTH_WEIGHTS['QB']}
    for abbr in ('GB', 'DEN', 'KC'):
        L.teams[abbr].picks = [DraftPick(2026, r, abbr, abbr) for r in range(1, 8)]
    return L, seller, p, keep


class CapCasualtyTradeTests(unittest.TestCase):
    def setUp(self):
        # Fix market comps, while retaining real buyer needs, GM prices, pick
        # prices, contracts, cleanup decisions and League.trade accounting.
        self.market = patch.object(TR.VAL, 'value_player', return_value={'apy': 28})
        self.market.start(); self.addCleanup(self.market.stop)
        self.rng = np.random.default_rng(71)

    def test_cleanup_shops_exactly_the_player_it_would_otherwise_cut(self):
        for path in ('run', 'enforce'):
            with self.subTest(path=path):
                baseline, _, _, _ = setup_market()
                with patch.object(TR, 'shop_cap_casualty', return_value=False):
                    getattr(CT, path)(baseline, np.random.default_rng(71))
                cut_ids = [x['pid'] for x in baseline.transactions if x['kind'] == 'release']
                L, seller, p, keep = setup_market()
                before_keep = contract_to_dict(keep.contract)
                with patch.object(TR, 'shop_cap_casualty', wraps=TR.shop_cap_casualty) as shop:
                    result = getattr(CT, path)(L, self.rng)
                self.assertEqual(cut_ids, ['casualty'])
                self.assertEqual([c.args[2].pid for c in shop.call_args_list], cut_ids)
                self.assertIn(p.team, ('DEN', 'KC'))
                self.assertEqual(keep.team, 'MIN')
                self.assertEqual(contract_to_dict(keep.contract), before_keep)
                self.assertGreaterEqual(seller.cap_space, 0)
                self.assertFalse(any(x['kind'] in ('release', 'june1_cut') for x in L.transactions))
                if path == 'run': self.assertEqual(result[0], [])

    def test_restructure_winner_is_not_shopped(self):
        for path in ('run', 'enforce'):
            with self.subTest(path=path):
                L, seller, p, keep = setup_market()
                p.contract = Contract(3, [20]*3, signing_bonus=2)
                keep.ratings = {k: 60 for k in TG.DEPTH_WEIGHTS['QB']}
                seller.cap.cap = 25.5 if path == 'run' else 15
                with patch.object(TR, 'shop_cap_casualty') as shop:
                    getattr(CT, path)(L, self.rng)
                shop.assert_not_called()
                self.assertEqual(p.team, 'MIN')
                self.assertLess(p.contract.base[0], 20)
                self.assertGreaterEqual(seller.cap_space, 0)

    def test_affordable_roster_is_never_shopped(self):
        L, seller, _, _ = setup_market(); seller.cap.cap = 100
        with patch.object(TR, 'shop_cap_casualty') as shop:
            CT.run(L, self.rng); CT.enforce(L, self.rng)
        shop.assert_not_called()

    def test_user_is_neither_forced_seller_nor_automatic_buyer(self):
        L, seller, p, _ = setup_market(); L.user_team = 'MIN'
        with patch.object(TR, 'shop_cap_casualty') as shop:
            CT.run(L, self.rng); CT.enforce(L, self.rng)
        shop.assert_not_called()
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))
        L.user_team = 'GB'
        for abbr in ('DEN', 'KC'): L.teams[abbr].picks = []
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))
        self.assertEqual(p.team, 'MIN')

    def test_no_buyer_means_the_original_cut(self):
        L, seller, p, _ = setup_market()
        for abbr in ('DEN', 'KC'): L.teams[abbr].cap.cap = 1
        CT.enforce(L, self.rng)
        self.assertIsNone(p.team)
        self.assertFalse(seller.picks)
        self.assertTrue(any(x['kind'] == 'release' and x['pid'] == p.pid for x in L.transactions))

    def test_best_bid_wins_instead_of_first_low_offer(self):
        L, seller, p, _ = setup_market()
        L.teams['DEN'].picks = [DraftPick(2026, 7, 'DEN', 'DEN')]
        L.teams['KC'].picks = [DraftPick(2026, 3, 'KC', 'KC')]
        self.assertTrue(TR.shop_cap_casualty(L, seller, p, self.rng))
        self.assertEqual(p.team, 'KC')
        self.assertEqual([pk.round for pk in seller.picks], [3])
        self.assertEqual(L.teams['DEN'].picks[0].owner, 'DEN')

    def test_discount_only_when_already_over_cap(self):
        for cap, succeeds in ((15, True), (24, False)):
            with self.subTest(cap=cap):
                L, seller, p, _ = setup_market(); seller.cap.cap = cap
                L.teams['DEN'].picks = [DraftPick(2026, 7, 'DEN', 'DEN')]
                L.teams['KC'].picks = []
                self.assertEqual(TR.shop_cap_casualty(L, seller, p, self.rng), succeeds)
                if succeeds:
                    event = next(x for x in L.transactions if x['kind'] == 'cap_casualty_trade')
                    self.assertTrue(event['discounted'])

    def test_no_need_no_trade_even_with_money_and_picks(self):
        L, seller, p, _ = setup_market()
        for abbr in ('DEN', 'KC'):
            for n in range(3):
                q = player(L, f'{abbr}{n}', abbr, Contract(1, [1]))
                q.ratings = {k: 95 for k in TG.DEPTH_WEIGHTS['QB']}
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))

    def test_buyer_wont_pay_for_negative_value_contract(self):
        L, seller, p, _ = setup_market()
        with patch.object(TR.VAL, 'value_player', return_value={'apy': 1}):
            self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))

    def test_roster_limit_and_deadline_are_respected(self):
        for reason in ('full', 'deadline', 'playoffs', 'injured'):
            with self.subTest(reason=reason):
                L, seller, p, _ = setup_market()
                if reason == 'full':
                    for abbr in ('DEN', 'KC'):
                        L.teams[abbr].phase = 'season'
                        for n in range(53):
                            q = player(L, f'{abbr}{n}', abbr, Contract(1, [1])); q.pos = 'WR'
                elif reason == 'deadline': L.set_phase('regular'); L.week = 10
                elif reason == 'playoffs': L.set_phase('playoffs')
                else: p.out_until = 99
                self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))

    def test_trade_retains_same_dead_money_and_relief_as_offseason_cut(self):
        L, seller, p, _ = setup_market()
        p.contract = Contract(3, [20]*3, signing_bonus=6)
        baseline = copy.deepcopy(L)
        baseline.release(p.pid)
        self.assertTrue(TR.shop_cap_casualty(L, seller, p, self.rng))
        expected = baseline.teams['MIN']
        self.assertEqual(seller.cap_space, expected.cap_space)
        self.assertEqual((seller.cap.dead, seller.cap.dead_next), (2, 4))
        self.assertEqual((seller.cap.dead, seller.cap.dead_next),
                         (expected.cap.dead, expected.cap.dead_next))
        self.assertEqual(p.contract.annual_proration, 0)
        self.assertGreaterEqual(L.teams[p.team].cap_space, 0)

    def test_regular_trade_cannot_replace_more_effective_june1_cut(self):
        L, seller, p, _ = setup_market(); L.set_phase('regular'); L.week = 2
        p.contract = Contract(3, [20]*3, signing_bonus=6)
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng, june1=True))

    def test_partial_relief_allowed_when_multiple_casualties_needed(self):
        L, seller, p, _ = setup_market(); seller.cap.dead = 40
        self.assertTrue(TR.shop_cap_casualty(L, seller, p, self.rng))
        self.assertLess(seller.cap_space, 0)
        self.assertAlmostEqual(seller.cap_space, -28)

    def test_emergency_no_replacement_release_also_gets_last_chance(self):
        L, seller, p, keep = setup_market()
        seller.roster.remove(keep); keep.team = None
        with patch.object(TR, 'shop_cap_casualty', wraps=TR.shop_cap_casualty) as shop:
            CT._fix_one(L, seller, self.rng, .5)
        self.assertEqual([c.args[2].pid for c in shop.call_args_list], [p.pid])
        self.assertTrue(shop.call_args.kwargs['june1'])
        self.assertIn(p.team, ('DEN', 'KC'))

    def test_spent_foreign_and_stale_picks_are_never_offered(self):
        L, seller, p, _ = setup_market()
        for abbr in ('DEN', 'KC'):
            L.teams[abbr].picks = [DraftPick(2026, 3, abbr, abbr, used_on='taken'),
                                   DraftPick(2026, 4, abbr, 'GB'),
                                   DraftPick(2023, 2, abbr, abbr)]
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))

    def test_run_june1_fallback_also_shops_only_selected_casualty(self):
        L, seller, p, keep = setup_market()
        keep.contract = None
        keep.ratings = {k: 80 for k in TG.DEPTH_WEIGHTS['QB']}
        with patch.object(TR, 'shop_cap_casualty', wraps=TR.shop_cap_casualty) as shop:
            cuts, _ = CT.run(L, self.rng)
        self.assertEqual([c.args[2].pid for c in shop.call_args_list], [p.pid])
        self.assertTrue(shop.call_args.kwargs['june1'])
        self.assertEqual(cuts, [])
        self.assertIn(p.team, ('DEN', 'KC'))
        self.assertEqual(keep.team, 'MIN')

    def test_buyer_keeps_cleanup_reserve_instead_of_immediately_recutting(self):
        L, seller, p, _ = setup_market()
        for abbr in ('DEN', 'KC'):
            L.teams[abbr].cap.cap = 25; L.teams[abbr].cap.rollover = 0
        self.assertFalse(TR.shop_cap_casualty(L, seller, p, self.rng))

    def test_labeled_previous_season_upcoming_pick_is_available(self):
        L, seller, p, _ = setup_market()
        L.season_closed_year = 2025
        L.last_draft = {'year': 2024}
        L.teams['DEN'].picks = [DraftPick(2025, 5, 'DEN', 'DEN')]
        L.teams['KC'].picks = []
        self.assertTrue(TR.shop_cap_casualty(L, seller, p, self.rng))
        self.assertEqual(seller.picks[0].year, 2025)


class RealMarketIntegrationTests(unittest.TestCase):
    def test_full_league_market_changes_only_the_preselected_casualty(self):
        from session import Session
        s = Session.new('GB', seed=47)
        L = s.L; L.set_phase('free_agency'); seller = L.teams['MIN']
        p, keep = seller.by_pos('WR')[:2]
        # Controlled cap problem in a real 32-team league. All other clubs,
        # valuations, coach needs, cap ledgers and draft assets are unchanged.
        for q in seller.roster: q.contract = Contract(1, [1])
        p.ratings = {key: 85 for key in TG.DEPTH_WEIGHTS['WR']}
        keep.ratings = {key: 86 for key in TG.DEPTH_WEIGHTS['WR']}
        p.contract = Contract(1, [10], signing_bonus=2)
        seller.sync_cap()
        seller.cap.cap = seller.cap.charges(seller.phase) - 5
        seller.cap.rollover = 0
        baseline = copy.deepcopy(L)
        with patch.object(TR, 'shop_cap_casualty', return_value=False) as cuts:
            CT._fix_one(baseline, baseline.teams['MIN'], np.random.default_rng(71), .5)
        self.assertEqual([c.args[2].pid for c in cuts.call_args_list], [p.pid])
        owners = {pid: q.team for pid, q in L.players.items()}
        with patch.object(TR, 'shop_cap_casualty', wraps=TR.shop_cap_casualty) as shops:
            CT._fix_one(L, seller, np.random.default_rng(71), .5)
        self.assertEqual([c.args[2].pid for c in shops.call_args_list], [p.pid])
        self.assertNotIn(p.team, (None, 'MIN', 'GB'))
        self.assertEqual([pid for pid, q in L.players.items() if q.team != owners[pid]], [p.pid])
        self.assertEqual(seller.cap_space, baseline.teams['MIN'].cap_space)
        self.assertGreaterEqual(L.teams[p.team].cap_space, CT.TARGET_ROOM)
        self.assertTrue(any(pk.original == p.team for pk in seller.picks))
        self.assertEqual(keep.team, 'MIN')


if __name__ == '__main__':
    unittest.main()
