"""Regressions for observed bad trades; no full-season simulation required."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from unittest.mock import Mock

import draft_day
import trade_engine as TE
import trades as TR
from test_package_roster_needs import team, player
from test_trade_package_search import Roll


def roster(abbr):
    t = team()
    t.abbr = abbr
    t.cap_space = 100.
    t.ctx = lambda: dict(win_pct=.5, avg_age=26)
    for p in t.roster:
        p.pid = abbr + '-' + p.pid
        p.team = abbr
        p.retired = False
        p.xp_spent = {}
    t.picks = []
    return t


def league(a, b):
    players = {p.pid:p for t in (a,b) for p in t.roster}
    return NS(year=2028, week=22, phase='free_agency', season_closed_year=2027,
              last_draft={}, cap_history={2028:348.042}, user_team=None,
              transactions=[], teams={a.abbr:a,b.abbr:b}, player=players.get)


def pk(slot, owner='A', year=2027):
    return NS(year=year, selection=slot, round=(slot-1)//32+1, original=owner,
              owner=owner, used_on=None)


class TradeIntegrityTests(unittest.TestCase):
    def draft(self, slot=39):
        a,b = roster('A'),roster('B')
        L = league(a,b)
        D = object.__new__(draft_day.Draft)
        D.L, D.year = L,2027
        return D, pk(slot,'B')

    def test_ten_cannot_buy_pick39_with_108_140_204_even_if_gm_loves_late_picks(self):
        D, target = self.draft()
        bank = [D._pick_asset(pk(n)) for n in (108,140,204)]
        def subjective(asset,*args,owns=False,**kwargs):
            if asset['obj'] is target: return 10 if owns else 100
            return 1 if owns else 30
        with patch.object(D,'_bank',return_value=bank), patch.object(TE,'team_price',side_effect=subjective), \
             patch.object(TE,'evaluate',return_value={'accepted':True}), \
             patch.object(TR,'_financial_trade',return_value=True):
            self.assertEqual(D._offer_for('A','B',target,1.1), (None,None))

    def test_fair_draft_exchange_keeps_subjective_preferences(self):
        D,target = self.draft(36)
        bank = [D._pick_asset(pk(n)) for n in (48,80)]
        def subjective(asset,*args,owns=False,**kwargs):
            if asset['obj'] is target: return 10 if owns else 100
            return 2 if owns else 30
        with patch.object(D,'_bank',return_value=bank), patch.object(TE,'team_price',side_effect=subjective), \
             patch.object(TE,'evaluate',return_value={'accepted':True}), \
             patch.object(TR,'_financial_trade',return_value=True):
            offer,_ = D._offer_for('A','B',target,1.1)
        self.assertIsNotNone(offer)
        self.assertEqual(len(offer['a_sends']),2)

    def test_draft_financial_guard_can_reject_fair_pick_swap(self):
        D,target = self.draft(36)
        offer = dict(a_sends=[D._pick_asset(pk(n)) for n in (48,80)])
        with patch.object(TR,'_financial_trade',return_value=False) as funding:
            self.assertFalse(D._package_valid('A','B',offer,target))
        funding.assert_called_once()
        self.assertIs(funding.call_args.args[4][0],target)

    def test_seattle_package_cannot_leave_two_receivers_after_drafting_linebacker(self):
        a,b = roster('SEA'),roster('TB')
        wr=[p for p in a.roster if p.pos=='WR']
        a.roster=[p for p in a.roster if p.pos!='WR']+wr[:4]
        L=league(a,b)
        prospect=player('WILL','prospect',90);prospect.retired=False
        result=TR.package_football(L,a,b,[wr[2].pid,wr[3].pid],[],prospect=prospect)
        self.assertTrue(result['approved'])
        self.assertGreater(result['reserves']['SEA'],0)

    def test_rational_seller_may_lose_score_without_losing_coverage(self):
        a,b=roster('A'),roster('B'); L=league(a,b)
        target=next(p for p in b.roster if p.pos=='WR');target.ovr=90
        result=TR.package_football(L,a,b,[],[target.pid])
        self.assertTrue(result['approved'])
        self.assertLess(result['gains']['B'],0)

    def test_ordinary_acquisition_rejects_new_linebacker_hole(self):
        a,b=roster('PHI'),roster('JAX')
        lbs=[p for p in a.roster if p.pos in ('MIKE','WILL','SAM')]
        a.roster=[p for p in a.roster if p not in lbs]+lbs[:4]
        L=league(a,b);L.phase='regular';L.week=9
        incoming=next(p for p in b.roster if p.pos=='CB');incoming.ovr=90
        result=TR.package_football(L,a,b,[lbs[3].pid],[incoming.pid])
        self.assertTrue(result['approved'])
        self.assertGreater(result['reserves']['PHI'],0)

    def test_miami_cannot_flip_new_arrival_next_window_but_can_after_trial(self):
        a,b=roster('MIA'),roster('LV');L=league(a,b)
        p=a.roster[0]
        L.transactions=[dict(kind='trade',year=2028,week=22,phase='free_agency',
                             a='MIA',b='LA',a_sends=[],b_sends=[p.pid])]
        self.assertIn(p.pid,TR.recent_acquisitions(L,a))
        self.assertGreater(TR.package_football(L,a,b,[p.pid],[])['reserves']['MIA'],0)
        L.phase='regular';L.week=4
        self.assertNotIn(p.pid,TR.recent_acquisitions(L,a))

    def test_rookie_cannot_be_collateral_same_draft_even_with_request(self):
        a,b=roster('SEA'),roster('TB');L=league(a,b);p=a.roster[0]
        p.xp_spent['_request']={'reason':'contract'}
        L.transactions=[dict(kind='draft',year=2028,week=22,phase='free_agency',team='SEA',pid=p.pid)]
        self.assertIn(p.pid,TR.recent_acquisitions(L,a))

    def test_explicit_request_is_exception_for_recent_veteran(self):
        a,b=roster('A'),roster('B');L=league(a,b);p=a.roster[0]
        L.transactions=[dict(kind='sign',year=2028,week=22,phase='free_agency',team='A',pid=p.pid)]
        self.assertIn(p.pid,TR.recent_acquisitions(L,a))
        p.xp_spent['_request']={'reason':'role'}
        self.assertNotIn(p.pid,TR.recent_acquisitions(L,a))

    def test_acquisition_protection_survives_calendar_rollover(self):
        a,b=roster('A'),roster('B');L=league(a,b);p=a.roster[0]
        L.transactions=[dict(kind='sign',year=2027,week=22,phase='offseason',team='A',pid=p.pid)]
        self.assertIn(p.pid,TR.recent_acquisitions(L,a))

    def test_pick_currency_scales_market_and_belief_but_keeps_discount(self):
        D,p= self.draft(16); a=D._pick_asset(p)
        self.assertEqual(a['years_out'],0)
        cheap=dict(a,cap=301.0);rich=dict(a,cap=602.0)
        self.assertAlmostEqual(TE.market_price(rich),2*TE.market_price(cheap),delta=.02)
        ctx=dict(win_pct=.5,avg_age=26)
        self.assertAlmostEqual(TE.team_price(rich,ctx,100),2*TE.team_price(cheap,ctx,100),delta=.02)
        future=D._pick_asset(pk(16,year=2029))
        self.assertEqual(future['years_out'],2)
        self.assertAlmostEqual(TE.market_price(future),TE.market_price(a)*.86**2,delta=.02)

    def test_ordinary_bank_includes_upcoming_draft_after_year_roll(self):
        D,_=self.draft();L=D.L;a=L.teams['A']
        a.picks=[pk(16,year=y) for y in (2027,2028,2029,2030)]
        assets=TR._picks_by_price(L,a,TE.GM_ARCHETYPES['balanced'],a.ctx(),100)
        self.assertEqual({x['obj'].year for x in assets},{2027,2028,2029})

    def test_pit_budget_counts_receiver_surrendered_not_just_edge_gain(self):
        a,b=roster('PIT'),roster('NYG');L=league(a,b)
        p=next(p for p in b.roster if p.pos=='LEDG')
        target=dict(kind='player',pid=p.pid,obj=p,trade_value=50.4,package_gain=5.965,
                    age=24,apy=1.773,need=True,dead=0,inherit=1.773,trade_value_buyer=74.188)
        # Aggregate the observed neutral package price so this isolates the
        # decision budget from subjective bargaining and search complexity.
        asset=dict(kind='pick',pick=16,years_out=0,obj=pk(16),cap=301.)
        with patch.object(TR,'_picks_by_price',return_value=[asset]), \
             patch.object(TE,'market_price',return_value=56.92), \
             patch.object(TE,'team_price',side_effect=lambda x,*args,owns=False,**kw: 60 if x is target and owns else 80 if x is target else 62), \
             patch.object(TR,'_financial_trade',return_value=True), \
             patch.object(TR,'package_football',return_value=dict(approved=True,gains={'PIT':2.662})):
            self.assertIsNone(TR._negotiate(L,a,b,target,{'aggression':.5},{'aggression':.5},
                               dict(win_pct=.7,avg_age=26),dict(win_pct=.5,avg_age=26),100,100,[],Roll())[0])

    def test_draft_trade_checks_real_future_rookie_commitments(self):
        from session import Session
        from cap_accounting import require_trade_room
        import financial_plan as FP
        from league import DraftPick
        s=Session.new('GB',seed=45);L=s.L;L.user_team=None
        a,b=L.teams['GB'],L.teams['DEN']
        # Both clubs own next spring's selections. Trading picks is legal on
        # today's ledger. The existing future deficit is not a second charge
        # against a modest upgrade, but its actual extra rookie cost is priced.
        outgoing=next(p for p in a.picks if p.year==2026 and p.round==2)
        incoming=next(p for p in b.picks if p.year==2026 and p.round==2)
        outgoing.selection=43;incoming.selection=36
        require_trade_room(L,a.abbr,b.abbr,[outgoing],[incoming],{})
        decisions=[]; evaluate=FP.evaluate
        def capture(*args,**kw):
            result=evaluate(*args,**kw);decisions.append(result);return result
        # This isolates incremental rookie funding. The deliberately unequal
        # picks need not pass the separate portfolio/willingness assessment,
        # which has its own complete-package entry-path tests.
        with patch.dict(L.cap_history,{2027:100.}), patch.object(FP,'evaluate',side_effect=capture), \
             patch.object(TR,'_portfolio_trade_check',return_value=dict(approved=True,costs={})):
            self.assertTrue(TR._financial_trade(L,a,b,[outgoing],[incoming]))
            upgrade=decisions[0]
            before,after=upgrade['before']['years'][1],upgrade['after']['years'][1]
            self.assertLess(before['funded_room'],0)
            self.assertGreater(after['rookie_reserve'],before['rookie_reserve'])
            self.assertLess(after['funded_room'],before['funded_room'])
            self.assertGreater(upgrade['forecast_risk'],0)
            # A controlled inventory with eight early firsts establishes the
            # restraint boundary; it is not a claim that anyone offered it.
            expensive=[DraftPick(2026,1,f'origin-{n}',b.abbr,selection=n+1) for n in range(8)]
            b.picks.extend(expensive);decisions.clear()
            self.assertFalse(TR._financial_trade(L,a,b,[outgoing],expensive))
            self.assertGreater(decisions[0]['forecast_risk'],upgrade['forecast_risk'])
            self.assertEqual(decisions[0]['reason'],'trade_financial_preference')
        self.assertIn(outgoing,a.picks);self.assertIn(incoming,b.picks)

    def test_gm_willingness_still_allows_bounded_marginal_disagreement(self):
        self.assertTrue(TR.will_accept(-.1,Roll(0),.8))
        self.assertTrue(TR.will_accept(-.1,Roll(0),.8,selling=True))
        self.assertFalse(TR.will_accept(-2,Roll(0),.8))
        self.assertFalse(TR.will_accept(-.4,Roll(0),.8,selling=True))

    def test_retention_shop_joins_targets_without_forcing_a_trade(self):
        a,b=roster('A'),roster('B');L=league(a,b);L.free_agents=[]
        p=next(p for p in a.roster if p.pos=='WR')
        plan=NS(refresh=Mock(),choices=Mock(return_value=[dict(pid=p.pid,decision='shop',trade_floor=4.)]))
        with patch.dict('sys.modules',retention_plan=plan), \
             patch.object(TR,'starter_bar',return_value={}), \
             patch.object(TR,'player_asset',side_effect=lambda L,t,p,*args,**kw:dict(pid=p.pid,obj=p,trade_value=5.)):
            TR._refresh_retention(L,['A'],{})
            assets,_=TR.surplus_and_needs(L,a,{},Roll())
            TR.surplus_and_needs(L,a,{},Roll())  # viewing the same list records nothing
        shop=next(x for x in assets if x['pid']==p.pid)
        self.assertTrue(shop['retention_shop'])
        self.assertEqual(TR._market_floor(shop),4.)
        self.assertEqual(p.pid,shop['pid'])
        self.assertEqual(L.transactions,[])
        plan.refresh.assert_called_once()


if __name__=='__main__': unittest.main()
