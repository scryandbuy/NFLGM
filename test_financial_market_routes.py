"""Full contract schedules must survive CPU bidding, refresh and settlement."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import financial_plan as FP
import market as MK
import roster_needs as RN
from cap_engine import CAP, Contract
from league import Team
from test_draft_planning import fixture, set_grade


class FinancialMarketRouteTests(unittest.TestCase):
    def setUp(self):
        self.L,self.t=fixture(); self.L.set_phase('free_agency'); self.t.picks=[]
        self.addCleanup(patch.stopall)
        patch.dict(CAP,{self.L.year:324.}).start()
        self.t.cap.cap=324.
        self.rng=np.random.default_rng(308)
        # This valuable expiring incumbent used to force unrelated bids down
        # to one year even when the full future books could fund both players.
        keeper=self.t.by_pos('QB')[0]; set_grade(keeper,99)
        keeper.contract=Contract(1,[1])

    def room(self, amount):
        self.t.sync_cap()
        self.t.cap.dead += self.t.cap.limit-self.t.cap.charges(self.t.phase)-amount

    def candidate(self,pid='backloaded-target'):
        p=copy.deepcopy(self.t.by_pos('WR')[0]);p.pid=pid;p.name=pid
        p.team=None;p.contract=None;p.fa_class='UFA';p.tender_team=None
        set_grade(p,95);self.L.players[p.pid]=p;self.L.free_agents.append(p.pid)
        return p

    def market_inputs(self, pool):
        """Fix valuation/need uncertainty; retain actual structures and budgets."""
        stack=ExitStack()
        stack.enter_context(patch.object(MK.VAL,'pool_from_league',return_value=None))
        stack.enter_context(patch.object(MK.VAL,'value_player',return_value=dict(apy=10.,years=5)))
        stack.enter_context(patch.object(RN,'candidate_gains',return_value={p.pid:25. for p in pool}))
        stack.enter_context(patch.object(RN,'move_gain',return_value=25.))
        stack.enter_context(patch('gm_engine.scheme_fit',return_value=0.))
        stack.enter_context(patch('contract_structure.choose_shape',return_value=.05))
        return stack

    def test_bid_keeps_affordable_backloaded_salary_and_five_year_term(self):
        self.room(12.);p=self.candidate()
        old_apy_ceiling=MK.power(self.L,self.t,CAP[self.L.year])*.65
        self.assertIsNotNone(self.t.worst_keeper())
        with self.market_inputs([p]):
            bids=MK.ai_bids(self.L,[p],1,self.rng)
            self.assertIn(p.pid,bids)
            offer=bids[p.pid][0]
            self.assertGreater(offer.apy,old_apy_ceiling)
            self.assertEqual(offer.years,5)
            proposed=MK.offer_contract(self.L,p,offer)
            self.assertLess(proposed.cap_hit(0),offer.apy)
            decision=FP.evaluate(self.L,self.t,additions=[(p,proposed)],gain=25)
            self.assertTrue(decision['approved'],decision['reason'])
        self.assertIsNone(p.team)

    def test_refresh_and_resolve_keep_approved_terms_above_current_apy_room(self):
        self.room(12.);p=self.candidate()
        room=MK.power(self.L,self.t,CAP[self.L.year])
        with self.market_inputs([p]), patch.object(MK,'profile_for',return_value={}), \
             patch.object(MK,'utility_of',return_value=1.), \
             patch('contract_offer.assess',return_value={'acceptable':True}):
            bids=MK.ai_bids(self.L,[p],1,self.rng)
            offer=bids[p.pid][0];self.assertGreater(offer.apy,room)
            revised=MK.reconsider_bid(self.L,p,offer)
            self.assertIsNotNone(revised)
            self.assertEqual(revised.apy,offer.apy)
            self.assertEqual(revised.years,offer.years)
            expected=MK.offer_contract(self.L,p,revised)
            signed,waiting,messages=MK.resolve_phase(self.L,[p],bids,1,self.rng)
        self.assertEqual(len(signed),1);self.assertEqual(waiting,[]);self.assertEqual(messages,[])
        self.assertEqual(p.team,self.t.abbr)
        self.assertEqual(signed[0][2].apy,offer.apy)
        self.assertEqual(p.contract.base,expected.base)
        self.assertEqual(p.contract.bonus_schedule,expected.bonus_schedule)
        self.assertGreaterEqual(self.t.cap_space,0.)

    def test_joint_bids_still_reserve_each_accepted_contract(self):
        self.room(12.);pool=[self.candidate('first'),self.candidate('second')]
        with self.market_inputs(pool):
            bids=MK.ai_bids(self.L,pool,1,self.rng)
        self.assertEqual(sum(len(v) for v in bids.values()),1)
        self.assertTrue(all(p.team is None for p in pool))

    def test_resolution_does_not_reintroduce_annual_salary_filter(self):
        self.room(12.);p=self.candidate()
        offer=MK.Offer(self.t.abbr,p.pid,12.2,5,front_load=.05,planning_gain=25.)
        self.assertGreater(offer.apy,MK.power(self.L,self.t,CAP[self.L.year]))
        with self.market_inputs([p]), patch.object(MK,'profile_for',return_value={}), \
             patch.object(MK,'utility_of',return_value=1.), \
             patch('contract_offer.assess',return_value={'acceptable':True}):
            signed,waiting,_=MK.resolve_phase(self.L,[p],{p.pid:[offer]},1,self.rng)
        self.assertEqual(len(signed),1);self.assertEqual(waiting,[])
        self.assertEqual(signed[0][2].apy,12.2)
        self.assertEqual(p.team,self.t.abbr)

    def test_reconsider_rejects_future_cap_failure_despite_current_room(self):
        self.room(100.);p=self.candidate()
        future=FP._cap(self.L,self.t,self.L.year+1)
        future_players=[q for q in self.t.roster if q.contract.years>1]
        for q in future_players: q.contract.base[1]=(future-1.)/len(future_players)
        offer=MK.Offer(self.t.abbr,p.pid,12.2,5,front_load=.05,planning_gain=25.)
        with self.market_inputs([p]):
            self.assertIsNone(MK.reconsider_bid(self.L,p,offer))
        self.assertIsNone(p.team)

    def test_cpu_matches_high_apy_tender_renewal_using_incremental_cap(self):
        p=self.t.by_pos('WR')[0];set_grade(p,95)
        p.contract=Contract(1,[20.]);p.fa_class='tendered';p.tender_team=self.t.abbr
        self.L.free_agents.append(p.pid)
        self.room(3.)
        suitor=Team('DEN','Continental West','Continental');suitor.league=self.L
        suitor.gm=copy.deepcopy(self.t.gm)
        self.L.teams['DEN']=suitor
        msg=dict(pid=p.pid,team=self.t.abbr,suitor='DEN',offer=24.,years=3,
                 bonus=0.,front_load=.05,status='open')
        # The old APY gate rejected this despite a lower current-year charge.
        self.assertLess(MK.power(self.L,self.t,CAP[self.L.year])+p.apy,24.*1.02)
        with patch.object(MK.VAL,'value_player',return_value=dict(apy=24.,years=3)):
            result=MK._settle_offer_sheet(self.L,msg,self.rng)
        self.assertEqual(result['outcome'],'matched')
        self.assertEqual(p.team,self.t.abbr)
        self.assertEqual(p.contract.years,3)
        self.assertLess(p.contract.cap_hit(0),20.)
        self.assertGreater(self.t.cap_space,3.)
        self.assertNotIn(p,suitor.roster)


if __name__=='__main__': unittest.main()
