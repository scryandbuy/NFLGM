"""FA resolution and seller protection after package-weighted recruitment."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np
import market
import roster_needs as RN
import trades
from test_personnel_package_decisions import offense_fixture, prospect
from test_draft_planning import fixture, set_grade


class TransactionPackageAuditTests(unittest.TestCase):
    def resolve(self,L,pool,offers):
        with ExitStack() as stack:
            stack.enter_context(patch.object(market.VAL,'pool_from_league',return_value={}))
            stack.enter_context(patch.object(market.VAL,'value_player',return_value={'apy':1,'years':1}))
            stack.enter_context(patch.object(market,'profile_for',return_value={}))
            stack.enter_context(patch.object(market,'utility_of',side_effect=lambda L,p,o,*args:o.apy))
            stack.enter_context(patch.object(market,'power',side_effect=lambda L,t,*args:t.cap_space))
            return market.resolve_phase(L,pool,offers,3,np.random.default_rng(31))

    def offer(self,p,apy=10):
        return market.Offer('MIN',p.pid,apy,1,phase=3)

    def test_resolution_rechecks_filled_package_need(self):
        for package,pos in [('10','WR'),('11','WR'),('12','TE')]:
            L,t,wr,te,qb=offense_fixture(package)
            chosen=wr if pos=='WR' else te
            for i,p in enumerate(t.by_pos(pos)):
                set_grade(p,90 if i < (3 if pos=='WR' else 2) else 55)
            duplicate=prospect(L,pos,'alternative')
            L.free_agents=[chosen.pid,duplicate.pid]
            signed,waiting,_=self.resolve(L,[chosen,duplicate],{p.pid:[self.offer(p)] for p in (chosen,duplicate)})
            self.assertEqual([p.pid for _,p,_ in signed],[chosen.pid],package)
            self.assertEqual([p.pid for p in waiting],[duplicate.pid])
            self.assertIsNone(duplicate.team)
            self.assertGreaterEqual(t.cap_space,0)

    def test_resolution_rechecks_cap_after_each_different_position_signing(self):
        L,t,wr,te,qb=offense_fixture('12')
        for p in t.by_pos('WR')[1:]:set_grade(p,55)
        t.sync_cap();t.cap.cap=t.cap.charges(t.phase)+25;t.cap.rollover=0
        pool=[te,wr];L.free_agents=[p.pid for p in pool]
        self.assertTrue(all(RN.move_gain(t,p)>1 for p in pool))
        signed,waiting,_=self.resolve(L,pool,{p.pid:[self.offer(p,20)] for p in pool})
        self.assertEqual(len(signed),1)
        self.assertEqual(len(waiting),1)
        self.assertGreaterEqual(t.cap_space,0)
        self.assertEqual(len([x for x in L.transactions if x['kind']=='sign']),1)

    def test_bid_budget_and_user_exclusion_full_and_sparse_rosters(self):
        for package in ('10','11','12'):
            for sparse in (False,True):
                L,t,wr,te,qb=offense_fixture(package)
                if sparse:t.roster=[p for p in t.roster if p.pos not in ('WR','TE')]
                pool=[wr,te,qb]
                with patch.object(market.VAL,'pool_from_league',return_value={}), \
                     patch.object(market.VAL,'value_player',return_value={'apy':10,'years':1}), \
                     patch.object(market,'power',return_value=20):
                    bids=market.ai_bids(L,pool,1,np.random.default_rng(4))
                    self.assertLessEqual(sum(o.apy for row in bids.values() for o in row),16.001)
                    self.assertFalse(market.ai_bids(L,pool,1,np.random.default_rng(4),skip_teams=('MIN',)))

    def test_surplus_never_discards_more_than_six_points_of_package_value(self):
        for package in ('10','11','12'):
            L,t=fixture();t.gm.off_personnel=package;t.gm.def_front='multiple'
            for pos in ('WR','TE','DT','CB'):
                men=t.by_pos(pos)
                set_grade(men[0],94)
                for p in men[1:]:set_grade(p,79)
            baseline=RN.assess(t)['score']
            with patch.object(trades.VAL,'value_player',return_value={'apy':10}):
                surplus,_=trades.surplus_and_needs(L,t,{},np.random.default_rng(13),n=100)
            for asset in surplus:
                remaining=[p for p in t.active() if p.pid!=asset['pid']]
                self.assertLessEqual(baseline-RN.assess(t,remaining)['score'],6.00001,(package,asset['pid']))

    def test_trade_does_not_spend_picks_for_help_available_on_the_street(self):
        from league import Team
        from gm_engine import GM
        from cap_engine import Contract
        L,t,wr,te,qb=offense_fixture('10')
        seller=Team('DEN','Continental West','Continental');seller.league=L;seller.gm=GM();L.teams['DEN']=seller
        wr.team='DEN';wr.contract=Contract(1,[1]);seller.roster=[wr]
        street=prospect(L,'WR','street-equivalent');L.free_agents=[street.pid]
        self.assertAlmostEqual(RN.move_gain(t,wr),RN.move_gain(t,street),places=4)
        target=dict(pid=wr.pid,obj=wr,kind='player',grp='WR',seen_ovr=80,trade_value=5)
        spare=dict(pid='QB1',obj=L.player('QB1'),kind='player',grp='QB',seen_ovr=90,trade_value=5)
        with patch.object(trades.VAL,'value_player',return_value={'apy':1,'years':1}), \
             patch.object(trades.VAL,'pool_from_league',return_value={}), \
             patch.object(trades,'surplus_and_needs',side_effect=lambda L,team,*args:([spare] if team.abbr=='MIN' else [target],{})), \
             patch.object(trades,'through_buyer_eyes',side_effect=lambda asset,*args:dict(asset)), \
             patch.object(trades,'stars_at',return_value=[]), \
             patch.object(trades,'_negotiate',return_value=(None,None)) as negotiate:
            trades.run(L,np.random.default_rng(8),rounds=1,offers_to_user=False)
        pursued=[call for call in negotiate.call_args_list if call.args[1].abbr=='MIN']
        self.assertFalse(pursued)

    def test_street_guard_preserves_affordability_contract_and_distinct_role_choices(self):
        from cap_engine import Contract
        L,t,wr,te,qb=offense_fixture('10');wr.contract=Contract(1,[1]);wr.team='DEN'
        street=prospect(L,'WR','available-WR');L.free_agents=[street.pid]
        report=RN.assess(t)
        target=dict(obj=wr,package_gain=RN.move_gain(t,wr,baseline=report),inherit=1)
        with patch.object(trades.VAL,'value_player',return_value={'apy':1,'years':1}):
            self.assertTrue(trades.street_alternative(L,t,target,report,{},{}))
            with patch.object(market,'power',return_value=0):
                self.assertFalse(trades.street_alternative(L,t,target,report,{},{}))
        for quote in ({'apy':2,'years':1},{'apy':1,'years':2}):
            with patch.object(trades.VAL,'value_player',return_value=quote):
                self.assertFalse(trades.street_alternative(L,t,target,report,{},{}))
        # Two weak receiving roles remain: one FA does not fill both.
        set_grade(L.player('WR2'),55);report=RN.assess(t)
        target['package_gain']=RN.move_gain(t,wr,baseline=report)
        with patch.object(trades.VAL,'value_player',return_value={'apy':1,'years':1}):
            self.assertFalse(trades.street_alternative(L,t,target,report,{},{}))

    def test_expensive_leaders_cannot_hide_an_affordable_seventh_option(self):
        from cap_engine import Contract
        L,t,wr,te,qb=offense_fixture('10');wr.contract=Contract(1,[1]);wr.team='DEN'
        expensive=[prospect(L,'WR',f'expensive-{i}') for i in range(6)]
        for p in expensive:set_grade(p,88)
        affordable=prospect(L,'WR','affordable-seventh')
        L.free_agents=[p.pid for p in expensive]+[affordable.pid]
        baseline=RN.assess(t)
        target=dict(obj=wr,package_gain=RN.move_gain(t,wr,baseline=baseline),inherit=1)
        cache={}
        with patch.object(trades.VAL,'value_player',side_effect=lambda L,p,**kwargs:
                          {'apy':1 if p.pid==affordable.pid else 30,'years':1}) as quote:
            self.assertTrue(trades.street_alternative(L,t,target,baseline,cache,{}))
            self.assertTrue(trades.street_alternative(L,t,target,baseline,cache,{}))
        self.assertEqual(quote.call_count,7)
        self.assertEqual([key for key in cache if key[0]=='report'],[('report',affordable.pid)])

    def test_sign_boundary_rejects_stale_contract_but_accepts_a_live_tender(self):
        from cap_engine import CAP
        L,t,wr,te,qb=offense_fixture('12');L.free_agents=[te.pid]
        market.sign(L,te,self.offer(te),CAP.get(L.year,301.2))
        snapshot=copy.deepcopy(L.save())
        with self.assertRaises(ValueError):market.sign(L,te,self.offer(te),CAP.get(L.year,301.2))
        self.assertEqual(L.save(),snapshot)
        te.fa_class='tendered';te.tender_team='MIN'
        self.assertTrue(market.available_for_signing(te))
        market.sign(L,te,self.offer(te),CAP.get(L.year,301.2))
        self.assertEqual(te.team,'MIN')
        self.assertEqual(sum(p.pid==te.pid for p in t.roster),1)
        self.assertEqual(te.fa_class,'signed')

    def test_stale_rival_offer_cannot_take_a_player_already_signed_elsewhere(self):
        from league import Team
        from gm_engine import GM
        L,t,wr,te,qb=offense_fixture('12');L.free_agents=[te.pid]
        rival=Team('DEN','Continental West','Continental');rival.league=L;rival.gm=GM();L.teams['DEN']=rival
        self.resolve(L,[te],{te.pid:[self.offer(te)]})
        self.assertEqual(te.team,'MIN')
        before=copy.deepcopy(L.save())
        stale={te.pid:[market.Offer('DEN',te.pid,10,1,phase=3)]}
        signed,_,_=self.resolve(L,[te],stale)
        self.assertFalse(signed)
        self.assertEqual(L.save(),before)

    def test_resolving_stale_offer_pool_cannot_resign_a_signed_player(self):
        L,t,wr,te,qb=offense_fixture('12');L.free_agents=[te.pid]
        offers={te.pid:[self.offer(te)]}
        signed,_,_=self.resolve(L,[te],offers)
        self.assertEqual(len(signed),1)
        before=copy.deepcopy(L.save())
        signed,_,_=self.resolve(L,[te],offers)
        self.assertFalse(signed)
        self.assertEqual(L.save(),before)


if __name__=='__main__':unittest.main()
