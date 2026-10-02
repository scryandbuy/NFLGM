"""CPU recruitment follows actual jobs, resources and negotiable agreements."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import extensions as EXT
import financial_plan as FP
import market as MK
import retention_plan as RP
import roster_needs as RN
from cap_engine import Contract
from league import League
from test_draft_planning import fixture, set_grade
import test_roster_cap_recovery as recovery


class RetentionRecruitmentTests(unittest.TestCase):
    def setUp(self):
        self.L,self.t=fixture()
        self.t.picks=[]; self.t.cap.cap=500.; self.t.sync_cap()
        self.rng=np.random.default_rng(313)
        self.quote=dict(ask=10.,offer=10.,years=3,discount=.07)

    def expiring(self,pid):
        p=self.L.player(pid);p.contract=Contract(1,[1.],signed=2026)
        self.t.sync_cap();return p

    def arrival(self,pos,grade,pid='arrival',accrued=3):
        p=copy.deepcopy(self.t.by_pos(pos)[0]);p.pid=pid;p.name=pid
        p.team=None;p.contract=None;p.fa_class='UFA';p.tender_team=None
        p.accrued=accrued;set_grade(p,grade)
        self.L.players[pid]=p;self.L.free_agents.append(pid)
        return p

    def test_real_package_candidates_include_wr3_nickel_and_second_te(self):
        for i,p in enumerate(self.t.by_pos('CB')):set_grade(p,86-i*2)
        for base,pid in (('11','WR2'),('11','CB2'),('12','TE1')):
            with self.subTest(base=base,pid=pid):
                self.t.gm.off_personnel=base
                p=self.expiring(pid)
                rows={q.pid:role for q,role in RP.candidates(self.L,self.t)}
                self.assertIn(pid,rows)
                self.assertGreaterEqual(rows[pid]['role_share'],.15)
                self.assertTrue(rows[pid]['roles'])
                p.contract=Contract(4,[1.]*4)

    def test_candidate_order_uses_positional_scale_not_raw_specialist_overall(self):
        tackle=self.expiring('LT0');kicker=self.expiring('K0')
        set_grade(tackle,86);set_grade(kicker,95)
        # Equal job importance isolates the position-scale part of ranking.
        with patch.object(RN,'departure_loss',return_value=5.), \
             patch.object(RP.DFT,'common_scale',side_effect=lambda o,p,s:90 if p=='LT' else 75):
            ids=[p.pid for p,_ in RP.candidates(self.L,self.t)]
        self.assertLess(ids.index(tackle.pid),ids.index(kicker.pid))

    def test_assessment_is_deterministic_and_does_not_change_saved_state(self):
        p=self.expiring('WR2');before=self.L.save()
        with patch.object(EXT,'terms',return_value=self.quote):
            a=RP.assess(self.L,self.t,p);b=RP.assess(self.L,self.t,p)
        self.assertEqual(a,b);json.dumps(a)
        self.assertEqual(self.L.save(),before)
        self.assertEqual(a['decision'],'retain');self.assertTrue(a['affordable'])
        self.assertGreater(a['extension_probability'],.35)

    def test_retention_forecast_keeps_real_negotiation_uncertainty(self):
        p=self.expiring('WR2')
        def quote(L,who,rng,pool=None):
            return dict(self.quote,ask=30.,offer=5.) if rng is not None else self.quote
        old=copy.deepcopy(vars(p.contract))
        with patch.object(EXT,'terms',side_effect=quote):
            self.assertEqual(RP.assess(self.L,self.t,p)['decision'],'retain')
            result=EXT._pursue_retention(self.L,self.t,p,self.rng)
        self.assertNotEqual(result['result'],'accepted')
        self.assertEqual(vars(p.contract),old)

    def test_unlikely_extension_can_be_shopped_without_forcing_a_trade(self):
        p=self.expiring('WR0');self.L.set_phase('regular');self.L.week=8
        before=list(self.t.roster)
        with patch.object(EXT,'terms',return_value=self.quote), \
             patch.object(EXT,'_ai_refusal',return_value='His agent will not negotiate an extension during the season'), \
             patch.object(RP.TE,'window',return_value='rebuilding'):
            row=RP.assess(self.L,self.t,p)
        self.assertEqual(row['decision'],'shop')
        self.assertIn('agent_defers',row['reasons']);self.assertGreater(row['trade_floor'],0)
        self.assertEqual(self.t.roster,before);self.assertEqual(self.L.transactions,[])

    def test_contender_can_keep_a_rental_after_agent_defers(self):
        p=self.expiring('WR0');self.L.set_phase('regular');self.L.week=8
        with patch.object(EXT,'terms',return_value=self.quote), \
             patch.object(EXT,'_ai_refusal',return_value='His agent will not negotiate an extension during the season'), \
             patch.object(RP.TE,'window',return_value='contending'):
            row=RP.assess(self.L,self.t,p)
        self.assertEqual(row['decision'],'retain')
        self.assertIn('keep_for_current_run',row['reasons'])

    def test_expired_unaffordable_player_can_walk_instead_of_breaking_budget(self):
        self.L.set_phase('offseason');p=self.L.player('WR2');p.contract=None
        with patch.object(EXT,'terms',return_value=self.quote), \
             patch.object(FP,'evaluate',return_value=dict(approved=False,reason='preserve_flexibility')):
            row=RP.assess(self.L,self.t,p)
        self.assertEqual(row['decision'],'let_walk');self.assertFalse(row['affordable'])
        self.assertEqual(row['trade_floor'],0)
        self.assertIn('preserve_flexibility',row['reasons'])

    def test_weekly_route_tries_another_candidate_after_refusal(self):
        first=self.expiring('QB0');second=self.expiring('WR2')
        self.L.set_phase('regular');self.L.week=5
        with patch.object(EXT,'terms',return_value=self.quote), \
             patch.object(RP,'candidates',return_value=[(first,{}),(second,{})]), \
             patch.object(EXT,'_ai_refusal',side_effect=lambda L,p: 'closed' if p is first else None):
            result=EXT.in_season_round(self.L,SimpleNamespace(random=lambda:0.),5)
        self.assertEqual([r[1] for r in result],[second.name])
        self.assertEqual(first.contract.years,1)
        self.assertEqual(second.contract.years,4)

    def test_offseason_route_reaches_third_receiver(self):
        p=self.expiring('WR2')
        with patch.object(EXT,'terms',return_value=self.quote):
            result=EXT.ai_round(self.L,self.rng)
        self.assertIn(p.name,[r[1] for r in result])
        self.assertEqual(p.contract.years,4)

    def test_immediate_expiries_are_not_capped_at_six_reviews(self):
        self.L.set_phase('offseason')
        ids=['QB0','LT0','LG0','C0','RG0','RT0','WR2']
        for pid in ids:self.L.player(pid).contract=None
        # Even a highly valuable early renewal waits behind current expiries.
        early=self.expiring('TE0');set_grade(early,95)
        quote=dict(ask=2.,offer=2.,years=2,discount=.07)
        with patch.object(EXT,'terms',return_value=quote):
            ordered=[p.pid for p,_ in RP.candidates(self.L,self.t)]
            self.assertGreater(ordered.index(early.pid),max(ordered.index(pid) for pid in ids))
            signed=EXT.ai_round(self.L,self.rng)
        self.assertEqual(len(signed),7)
        self.assertTrue(all(self.L.player(pid).contract.years==2 for pid in ids))
        self.assertEqual(early.contract.years,1)

    def test_seventh_expiry_still_cannot_bypass_budget(self):
        self.L.set_phase('offseason')
        ids=['QB0','LT0','LG0','C0','RG0','RT0','WR2']
        for pid in ids:self.L.player(pid).contract=None
        original=EXT._retention_budget
        def budget(L,t,p,c,*a,**kw):
            if p.pid=='WR2':return dict(approved=False,reason='preserve_flexibility')
            return original(L,t,p,c,*a,**kw)
        with patch.object(EXT,'terms',return_value=dict(ask=2.,offer=2.,years=2,discount=.07)), \
             patch.object(EXT,'_retention_budget',side_effect=budget):
            signed=EXT.ai_round(self.L,self.rng)
        self.assertEqual(len(signed),6)
        self.assertIsNone(self.L.player('WR2').contract)
        self.assertIn('preserve_flexibility',next(r for r in RP.choices(self.L,self.t) if r['pid']=='WR2')['reasons'])

    def test_user_contracts_and_decisions_remain_user_controlled(self):
        p=self.expiring('WR2');self.L.user_team=self.t.abbr
        self.assertEqual(RP.refresh(self.L,self.t),[])
        self.assertEqual(EXT.ai_round(self.L,self.rng),[])
        self.L.set_phase('regular');self.L.week=8
        self.assertEqual(EXT.in_season_round(self.L,SimpleNamespace(random=lambda:0.),8),[])
        self.assertEqual(p.contract.years,1);self.assertEqual(self.L.transactions,[])

    def test_saved_decision_dedup_and_contract_ownership_invalidation(self):
        p=self.expiring('WR2')
        with patch.object(EXT,'terms',return_value=self.quote):row=RP.assess(self.L,self.t,p)
        self.assertTrue(RP.record(self.L,row));self.assertFalse(RP.record(self.L,row))
        outcome=dict(row,extension_result='countered')
        self.assertTrue(RP.record(self.L,outcome));self.assertFalse(RP.record(self.L,row))
        self.assertFalse(RP.record(self.L,outcome))
        loaded=League.load(self.L.save());lt=loaded.teams[self.t.abbr]
        self.assertEqual(RP.choices(loaded,lt)[0]['extension_result'],'countered')
        loaded.player(p.pid).contract=Contract(4,[2.]*4,signed=2027)
        self.assertEqual(RP.choices(loaded,lt),[])
        p.team='DEN';self.t.roster.remove(p)
        self.assertEqual(RP.choices(self.L,self.t),[])

    def test_refresh_reassesses_changed_budget_but_does_not_repeat_same_reason(self):
        self.expiring('WR2')
        with patch.object(EXT,'terms',return_value=self.quote), \
             patch.object(RP,'assess',wraps=RP.assess) as evaluate:
            RP.refresh(self.L,self.t);n=evaluate.call_count
            RP.refresh(self.L,self.t);self.assertEqual(evaluate.call_count,n)
            events=len(self.L.transactions)
            self.L.week+=1;RP.refresh(self.L,self.t)
            self.assertGreater(evaluate.call_count,n);self.assertEqual(len(self.L.transactions),events)
            self.t.cap.dead=1000.;RP.refresh(self.L,self.t)
            row=RP.choices(self.L,self.t)[0]
        self.assertFalse(row['affordable'])
        self.assertIn('legal_cap_failure',row['reasons'])

    def test_late_market_can_fill_secondary_jobs_behind_elite_starter(self):
        for pos,base in (('WR','11'),('CB','11'),('TE','12')):
            with self.subTest(pos=pos):
                self.setUp();self.t.gm.off_personnel=base
                for i,p in enumerate(self.t.by_pos(pos)):set_grade(p,95 if i==0 else 55)
                p=self.arrival(pos,82);before=RN.assess(self.t)['score']
                with patch.object(MK.VAL,'value_player',return_value=dict(apy=10.,years=2)):
                    signed=MK.sign_the_leftovers(self.L,[p],self.rng)
                self.assertEqual(len(signed),1)
                self.assertEqual(p.team,self.t.abbr);self.assertEqual(p.contract.years,1)
                self.assertGreater(RN.assess(self.t)['score'],before)
                self.assertGreaterEqual(self.t.cap_space,0)

    def test_late_market_preserves_financial_and_user_guards(self):
        for user in (True,False):
            with self.subTest(user=user):
                self.setUp();p=self.arrival('WR',95)
                if user:self.L.user_team=self.t.abbr
                with patch.object(MK.VAL,'value_player',return_value=dict(apy=10.,years=2)), \
                     patch.object(FP,'evaluate',return_value=dict(approved=False,reason='reserve')):
                    self.assertEqual(MK.sign_the_leftovers(self.L,[p],self.rng),[])
                self.assertIsNone(p.team)

    def test_late_market_snapshot_refreshes_after_each_successful_signing(self):
        for i,p in enumerate(self.t.by_pos('WR')):set_grade(p,95 if i==0 else 55)
        pool=[self.arrival('WR',85,'first'),self.arrival('WR',82,'second')]
        original=RN.move_gain;observed=[]
        def gain(team,p,departure=None,baseline=None):
            # Compare the reused snapshot to the actual current roster, not
            # to another cached result. The second bid must see the first deal.
            self.assertIsNotNone(baseline)
            self.assertEqual({q.pid for q in baseline['players']},{q.pid for q in team.active()})
            self.assertAlmostEqual(baseline['score'],RN.assess(team)['score'])
            observed.append((p.pid,{q.pid for q in baseline['players']}))
            return original(team,p,departure,baseline)
        with patch.object(RN,'move_gain',side_effect=gain), \
             patch.object(MK.VAL,'value_player',return_value=dict(apy=10.,years=2)):
            signed=MK.sign_the_leftovers(self.L,pool,self.rng)
        self.assertEqual(len(signed),2)
        self.assertTrue(any(pid=='second' and 'first' in roster for pid,roster in observed))

    def test_fill_skips_unaffordable_veteran_and_signs_cheaper_rookie(self):
        self.L,self.t=recovery.RecoveryTests().roster()
        old=self.t.by_pos('WR')[-1];self.t.roster.remove(old)
        self.t.sync_cap();self.t.cap.cap=self.t.cap.charges(self.t.phase)+1.15
        veteran=self.arrival('WR',74,'veteran',10);rookie=self.arrival('WR',70,'rookie',0)
        signed=MK.fill_out_rosters(self.L,[veteran,rookie],self.rng)
        self.assertEqual(signed,1);self.assertIsNone(veteran.team)
        self.assertEqual(rookie.team,self.t.abbr);self.assertEqual(len(self.t.active()),53)
        self.assertGreaterEqual(self.t.cap_space,0.)

    def test_premium_small_upgrade_fails_but_discounted_useful_player_passes(self):
        p=self.arrival('WR',83)
        premium=MK.Offer(self.t.abbr,p.pid,12.,3)
        cheap=MK.Offer(self.t.abbr,p.pid,1.2,1)
        a=MK.acquisition_read(self.L,self.t,p,premium,2.,reference_apy=12.)
        b=MK.acquisition_read(self.L,self.t,p,cheap,2.,reference_apy=12.)
        self.assertFalse(a['approved']);self.assertTrue(b['approved'])
        self.assertEqual(a['cash_commitment'],36.)
        self.assertFalse(MK.acquisition_read(self.L,self.t,p,cheap,0.)['approved'])

    def test_redundant_specialist_cost_includes_displaced_guarantees(self):
        incumbent=self.t.by_pos('K')[0];incumbent.contract=Contract(2,[1.,1.],signing_bonus=6.)
        p=self.arrival('K',83);offer=MK.Offer(self.t.abbr,p.pid,3.,2)
        read=MK.acquisition_read(self.L,self.t,p,offer,2.,reference_apy=3.)
        self.assertEqual(read['displaced_guarantees'],6.)
        self.assertEqual(read['annual_economic_cost'],6.)
        self.assertFalse(read['approved'])

    def test_near_equivalent_cheaper_alternative_gets_first_look_not_a_veto(self):
        expensive=self.arrival('WR',90,'premium');cheap=self.arrival('WR',89,'value')
        other=self.arrival('CB',90,'corner')
        c=[(1.,expensive,20.,5),(1.,other,15.,4),(.95,cheap,10.,2)]
        ordered=MK._prefer_affordable_alternatives(c,{expensive.pid:10,cheap.pid:9.5,other.pid:10})
        self.assertIs(ordered[0][1],cheap)
        self.assertIn(c[0],ordered);self.assertIn(c[1],ordered)

    def test_pending_specialist_bid_cannot_claim_the_same_upgrade_twice(self):
        set_grade(self.t.by_pos('K')[0],60)
        a=self.arrival('K',88,'first');b=self.arrival('K',87,'second')
        with patch.object(MK.VAL,'value_player',return_value=dict(apy=2.,years=2)):
            bids=MK.ai_bids(self.L,[a,b],1,self.rng)
        self.assertEqual(sum(len(v) for v in bids.values()),1)
        self.assertIsNone(a.team);self.assertIsNone(b.team)


if __name__=='__main__':unittest.main()
