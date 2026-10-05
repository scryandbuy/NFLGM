"""Competing sellers price present losses rather than vetoing future value."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from test_trade_integrity import roster,league,player
import trades as TR
import roster_needs as RN

class SellerLineupTests(unittest.TestCase):
    def case(self,window='race'):
        a,b=roster('GB'),roster('ARI'); L=league(a,b); L.user_team='GB';L.phase='regular';L.week=9
        b.ctx=lambda:dict(win_pct=.375,avg_age=28,phase='regular',games_played=8,
                         division_gap=2.,wildcard_gap=1. if window=='race' else 3.)
        target=next(p for p in b.roster if p.pos=='TE');target.ovr=95
        return L,a,b,target

    def test_competing_seller_can_consider_pick_return_for_star(self):
        L,a,b,target=self.case()
        sends=[next(p.pid for p in a.roster if p.pos==pos) for pos in ('HB','WR')]
        r=TR.package_football(L,a,b,sends,[target.pid])
        self.assertTrue(r['approved']);self.assertLess(r['gains']['ARI'],-TR.UPGRADE_GAP)
        self.assertGreater(r['reserves']['ARI'],0)

    def test_trade_check_prices_star_sale_instead_of_vetoing_it(self):
        L,a,b,target=self.case()
        pick=NS(year=2029,round_=1)
        with patch.object(TR.VAL,'pool_from_league',return_value={}), \
             patch('cap_accounting.require_trade_room', return_value=None) as legal_room, \
             patch.object(TR,'player_asset',return_value=dict(kind='player')), \
             patch.object(TR,'pick_asset',return_value=dict(kind='pick')), \
             patch.object(TR,'_financial_trade',return_value=True) as funding:
            with patch.object(TR.TE,'evaluate',return_value=dict(a_gain=0,b_gain=0,blocked=None)):
                low=TR.cpu_trade_check(L,a,b,[pick],[target.pid])
            with patch.object(TR.TE,'evaluate',return_value=dict(a_gain=0,b_gain=100,blocked=None)):
                high=TR.cpu_trade_check(L,a,b,[pick],[target.pid])
        self.assertFalse(low['approved']);self.assertTrue(low['needs_more'])
        self.assertTrue(high['approved']);funding.assert_called_once()
        self.assertEqual(legal_room.call_count, 2)

    def test_genuine_seller_can_take_future_value(self):
        L,a,b,target=self.case('seller')
        r=TR.package_football(L,a,b,[],[target.pid])
        self.assertTrue(r['approved']);self.assertLess(r['gains']['ARI'],-TR.UPGRADE_GAP)

    def test_any_starter_costs_more_than_depth_and_contender_adds_premium(self):
        L,a,b,target=self.case()
        b.ctx=lambda:dict(win_pct=.75,avg_age=27,phase='regular',games_played=8,
                          division_gap=0.,wildcard_gap=0.,in_playoff_position=True)
        race=TR.package_football(L,a,b,[],[target.pid])['reserves']['ARI']
        bench=next(p for p in b.roster if p.pos=='TE' and p is not target)
        depth=TR.package_football(L,a,b,[],[bench.pid])['reserves']['ARI']
        b.ctx=lambda:dict(win_pct=.25,avg_age=29,phase='regular',games_played=8,
                          division_gap=4.,wildcard_gap=4.)
        seller=TR.package_football(L,a,b,[],[target.pid])['reserves']['ARI']
        self.assertGreater(race,depth)
        self.assertGreater(race,seller)

    def test_competing_seller_can_receive_equivalent_starter(self):
        L,a,b,target=self.case();replacement=next(p for p in a.roster if p.pos=='TE');replacement.ovr=95
        self.assertTrue(TR.package_football(L,a,b,[replacement.pid],[target.pid])['approved'])

    def test_user_can_choose_to_trade_own_star(self):
        L,a,b,target=self.case();L.user_team='ARI'
        self.assertTrue(TR.package_football(L,a,b,[],[target.pid])['approved'])

    def offseason_tight_end(self, *, window='rebuilding', starter=95, backup=70):
        buyer, seller = roster('GB'), roster('ARI')
        L = league(buyer, seller)
        L.user_team, L.phase, L.week = 'GB', 'free_agency', 22
        seller.gm.off_personnel = '12'
        seller.ctx = lambda: dict(win_pct=.25 if window == 'rebuilding' else .75,
                                  avg_age=28, phase='free_agency', games_played=17)
        tight_ends = [p for p in seller.roster if p.pos == 'TE']
        for index, p in enumerate(tight_ends):
            p.ovr = starter if index == 0 else backup
        target = tight_ends[0]
        # A public, cheap two-year contract is valuable because replacing the
        # starter would use cap room as well as a pick or another player.
        target.contract = NS(years=2)
        target.cap_hit = lambda: 3.0
        return L, buyer, seller, target

    def test_cheap_controlled_starter_requires_more_than_single_second_value(self):
        L, buyer, seller, target = self.offseason_tight_end()
        report = TR.package_football(L, buyer, seller, [], [target.pid])
        self.assertLess(report['gains']['ARI'], -20)
        self.assertGreater(report['reserves']['ARI'], 5.0)
        pick = NS(year=2029, round_=2)
        with patch.object(TR.VAL, 'pool_from_league', return_value={}), \
             patch('cap_accounting.require_trade_room', return_value=None), \
             patch.object(TR, 'player_asset', return_value=dict(kind='player')), \
             patch.object(TR, 'pick_asset', return_value=dict(kind='pick')), \
             patch.object(TR, '_financial_trade', return_value=True):
            with patch.object(TR.TE, 'evaluate', return_value=dict(a_gain=0, b_gain=3.79, blocked=None)):
                thin = TR.cpu_trade_check(L, buyer, seller, [pick], [target.pid])
            with patch.object(TR.TE, 'evaluate', return_value=dict(a_gain=0, b_gain=7.5, blocked=None)):
                rich = TR.cpu_trade_check(L, buyer, seller, [pick], [target.pid])
        self.assertFalse(thin['approved'])
        self.assertTrue(thin['needs_more'])
        self.assertTrue(rich['approved'])

    def test_price_reflects_actual_role_loss_and_gm_window(self):
        L, buyer, seller, target = self.offseason_tight_end()
        rebuilding = TR.package_football(L, buyer, seller, [], [target.pid])['reserves']['ARI']
        seller.ctx = lambda: dict(win_pct=.75, avg_age=28, phase='free_agency', games_played=17)
        contender = TR.package_football(L, buyer, seller, [], [target.pid])['reserves']['ARI']
        self.assertGreater(contender, rebuilding)
        seller.ctx = lambda: dict(win_pct=.25, avg_age=28, phase='free_agency', games_played=17)
        target.ovr = 80
        for p in seller.roster:
            if p.pos == 'TE' and p is not target: p.ovr = 77
        marginal = TR.package_football(L, buyer, seller, [], [target.pid])
        self.assertLess(marginal['gains']['ARI'] * -1, 8)
        self.assertLess(marginal['reserves']['ARI'], rebuilding)

    def test_control_bonus_belongs_to_the_starter_who_causes_the_loss(self):
        L, buyer, seller, target = self.offseason_tight_end()
        target.contract = None
        depth_corner = next(p for p in seller.roster if p.pos == 'CB')
        depth_corner.ovr = 80
        depth_corner.contract = NS(years=2)
        depth_corner.cap_hit = lambda: 3.0
        baseline = RN.assess(seller)['score']
        solo = RN.assess(seller, [p for p in seller.roster if p is not depth_corner],
                         score_only=True)
        self.assertLess(baseline - solo, 8)
        sent = [target.pid, depth_corner.pid]
        with_depth_contract = TR.package_football(L, buyer, seller, [], sent)['reserves']['ARI']
        depth_corner.contract = None
        without_depth_contract = TR.package_football(L, buyer, seller, [], sent)['reserves']['ARI']
        self.assertEqual(with_depth_contract, without_depth_contract)

    def test_single_target_search_does_not_add_solo_roster_scoring(self):
        L, buyer, seller, target = self.offseason_tight_end()
        with patch.object(RN, 'assess', wraps=RN.assess) as assess:
            TR.package_football(L, buyer, seller, [], [target.pid])
        self.assertFalse(any(call.kwargs.get('score_only') for call in assess.call_args_list))

if __name__=='__main__':unittest.main()
