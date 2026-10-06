"""Premium expiring acquisitions fund an intention, never an automatic deal."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
from cap_engine import Contract, CAP
from league import Team, Player, DraftPick, League
import gm_engine as GM
import targets as TG
import extensions as EXT
import trade_retention as TRE
import trades as TR
import financial_plan as FP
import retention_plan as RP
from test_draft_planning import fixture, set_grade


def market():
    L,buyer=fixture()
    L.set_phase('regular'); L.week=8; buyer.record=[6,1,0]
    seller=Team('BUF','Continental East','Continental'); seller.league=L; seller.gm=GM.GM()
    seller.phase=buyer.phase; L.teams['BUF']=seller
    p=Player('target','Acquired Receiver','WR',27,{k:90 for k in TG.DEPTH_WEIGHTS['WR']},
             team='BUF',contract=Contract(1,[4.],signed=2026))
    seller.roster=[p]; L.players[p.pid]=p
    buyer.picks=[DraftPick(2027,r,'MIN','MIN',selection=(r-1)*32+16) for r in (1,2,3,6,7)]
    for t in (buyer,seller): t.cap.cap=350.;t.sync_cap()
    return L,buyer,seller,p


class TradeExtensionPlanTests(unittest.TestCase):
    def setUp(self):
        caps=dict(CAP)
        self.addCleanup(lambda:(CAP.clear(),CAP.update(caps)))
        self.L,self.b,self.s,self.p=market()
        self.terms=dict(ask=20.,offer=20.,years=3,discount=.07)
        for ctx in (patch.object(EXT,'terms',return_value=self.terms),
                    patch.object(TR.VAL,'value_player',return_value=dict(apy=25.,years=3))):
            ctx.start();self.addCleanup(ctx.stop)

    def plan(self,picks=None):
        return TRE.purchase_plans(self.L,self.b,self.s,picks or [self.b.picks[0]],[self.p.pid])

    def buy(self):
        self.L.trade(self.b.abbr,self.s.abbr,[self.b.picks[0]],[self.p.pid])
        return self.p.xp_spent[TRE.KEY]

    def test_worthwhile_acquisition_preserves_unsigned_contract_and_full_roster(self):
        before=self.L.save(); rng=np.random.get_state()
        identities=[(id(p),id(p.contract),id(p.xp_spent),id(getattr(p,'_team_ref',None))) for p in self.b.roster]
        result=self.plan()
        self.assertTrue(result['approved'],result)
        self.assertEqual(len(result['plans']),1)
        self.assertEqual(self.L.save(),before)
        self.assertEqual(identities,[(id(p),id(p.contract),id(p.xp_spent),id(getattr(p,'_team_ref',None))) for p in self.b.roster])
        self.assertTrue(np.array_equal(rng[1],np.random.get_state()[1]))
        plan=self.buy()
        self.assertEqual(self.p.contract.years,1)
        self.assertEqual(plan['state'],'pending')
        self.assertTrue(all(self.L.player('WR'+str(i)) in self.b.roster for i in range(5)))

    def test_future_room_not_only_inherited_current_salary(self):
        # Four-dollar salary fits, but future committed cash leaves no room
        # for a twenty-dollar extension and the remaining roster.
        blocker=self.b.by_pos('QB')[0]
        blocker.contract=Contract(4,[1.,295.,295.,295.]); self.b.sync_cap()
        self.L.cap_history.update({2028:350.,2029:350.,2030:350.})
        self.assertGreater(self.b.cap_space,200)
        result=self.plan()
        self.assertFalse(result['approved'])
        self.assertEqual(result['reason'],'no_funded_extension_plan')
        before=self.L.save()
        with self.assertRaisesRegex(ValueError,'extension plan'): self.buy()
        self.assertEqual(self.L.save(),before)

    def test_cheap_coverage_purchase_and_existing_multiyear_control_still_allowed(self):
        self.b.cap.dead_next=330
        cheap=self.plan([self.b.picks[-1]])
        self.assertTrue(cheap['approved']);self.assertEqual(cheap['plans'],[])
        self.p.contract=Contract(3,[4.]*3)
        controlled=self.plan()
        self.assertTrue(controlled['approved']);self.assertEqual(controlled['plans'],[])

    def test_surplus_receiver_and_veteran_successor_are_not_a_retention_plan(self):
        for p in self.b.by_pos('WR'):set_grade(p,96)
        result=self.plan()
        self.assertFalse(result['approved'])
        self.assertEqual(result['assessment']['role_share'],0)

    def test_midseason_deferral_is_respected_and_offseason_attempt_is_prioritized(self):
        with patch.object(EXT,'_ai_refusal',return_value='His agent will not negotiate an extension during the season'):
            intent=self.buy()
            with patch.object(EXT,'negotiate_ai') as talks:
                EXT.in_season_round(self.L,np.random.default_rng(91),8)
                talks.assert_not_called()
            self.assertEqual(intent['state'],'deferred')
        self.L.set_phase('offseason')
        with patch.object(EXT,'negotiate_ai',return_value=dict(result='countered',why='different guarantees')) as talks:
            TRE.pursue(self.L,self.b,np.random.default_rng(91))
        self.assertEqual(talks.call_count,1)
        self.assertEqual(intent['state'],'countered')

    def test_known_firm_refusal_prevents_premium_purchase_but_new_refusal_can_happen(self):
        with patch.object(EXT,'_ai_refusal',return_value='His extension negotiation is closed'):
            self.assertFalse(self.plan()['approved'])
        intent=self.buy()
        with patch.object(EXT,'_ai_refusal',return_value='His extension negotiation is closed'),patch.object(EXT,'negotiate_ai') as talks:
            TRE.pursue(self.L,self.b,np.random.default_rng(22))
            talks.assert_not_called()
        self.assertEqual(intent['state'],'refused')
        self.assertIsNone(TRE.active_plan(self.L,self.b,self.p))
        self.assertEqual(self.p.contract.years,1)

    def test_no_random_team_skip_or_duplicate_attempt_and_actual_contract_checks_apply(self):
        intent=self.buy()
        self.L.set_phase('offseason')
        EXT.in_season_round(self.L,np.random.default_rng(4),8)
        self.assertEqual(intent['state'],'accepted')
        self.assertEqual(self.p.contract.years,4)
        attempts=[e for e in self.L.transactions if e['kind']=='trade_extension_attempt']
        self.assertEqual(len(attempts),1)
        EXT.in_season_round(self.L,np.random.default_rng(4),8)
        self.assertEqual(len([e for e in self.L.transactions if e['kind']=='trade_extension_attempt']),1)

    def test_saved_intention_reserves_space_without_double_counting_accepted_extension(self):
        self.buy()
        booked=FP.snapshot(self.L,self.b)
        old=self.p.xp_spent.pop(TRE.KEY)
        unreserved=FP.snapshot(self.L,self.b)
        self.p.xp_spent[TRE.KEY]=old
        self.assertGreater(unreserved['years'][1]['funded_room'],booked['years'][1]['funded_room'])
        reloaded=League.load(self.L.save());q=reloaded.player(self.p.pid);club=reloaded.teams['MIN']
        self.assertEqual(TRE.active_plan(reloaded,club,q),old)
        self.L.set_phase('offseason');TRE.pursue(self.L,self.b,np.random.default_rng(31))
        with_plan=FP.snapshot(self.L,self.b)
        self.p.xp_spent.pop(TRE.KEY)
        self.assertEqual(FP.snapshot(self.L,self.b),with_plan)

    def test_user_controls_their_own_purchase(self):
        self.L.user_team='MIN';self.b.cap.dead_next=400
        result=self.plan()
        self.assertTrue(result['approved']);self.assertEqual(result['plans'],[])

    def test_two_expiring_arrivals_cannot_spend_same_future_room(self):
        other=copy.deepcopy(self.p);other.pid='second';other.pos='CB'
        other.ratings={k:90 for k in TG.DEPTH_WEIGHTS['CB']}
        self.L.players[other.pid]=other;self.s.roster.append(other);self.s.sync_cap()
        # Choose a concrete funding boundary from the existing financial model,
        # then show either standalone deal fits but their combined plans do not.
        found=False
        for dead in range(190,281,5):
            self.b.cap.dead_next=dead
            one=self.plan()
            two=TRE.purchase_plans(self.L,self.b,self.s,[self.b.picks[0]],[other.pid])
            together=TRE.purchase_plans(self.L,self.b,self.s,[self.b.picks[0]],[self.p.pid,other.pid])
            if one['approved'] and two['approved'] and not together['approved']:
                found=True;break
        self.assertTrue(found,'Expected a funding boundary between one and two serious renewals')

    def test_actual_new_refusal_does_not_undo_trade(self):
        intent=self.buy()
        with patch.object(EXT,'negotiate_ai',return_value=dict(result='refused',why='Going to free agency')):
            TRE.pursue(self.L,self.b,np.random.default_rng(12))
        self.assertEqual(intent['state'],'refused')
        self.assertEqual(self.p.team,'MIN');self.assertEqual(self.p.contract.years,1)

    def test_intent_does_not_follow_player_to_a_different_team(self):
        self.buy();self.p.team='BUF'
        self.assertIsNone(TRE.active_plan(self.L,self.b,self.p))
        self.assertIsNone(TRE.active_plan(self.L,self.s,self.p))

    def test_real_replacement_can_change_intent_but_hidden_ceiling_cannot(self):
        initial=self.plan()
        self.p.potential=99;self.p.longevity=1.5
        self.assertEqual(self.plan(),initial)
        intent=self.buy()
        for p in self.b.by_pos('WR'):
            if p is not self.p:set_grade(p,97)
        TRE.pursue(self.L,self.b,np.random.default_rng(4))
        self.assertEqual(intent['state'],'abandoned')
        self.assertEqual(self.p.contract.years,1)

    def test_gm_youth_preference_can_change_veteran_commitment(self):
        self.p.age=33.5;set_grade(self.p,91)
        # Actual controlled succession alternatives; neither young nor old is
        # banned. A stronger age-adjusted edge supports either GM's agreement.
        for p in self.b.by_pos('WR'):set_grade(p,85)
        self.b.gm.youth=.1
        willing=self.plan()
        self.b.gm.youth=.95
        cautious=self.plan()
        self.assertTrue(willing['approved'],willing)
        self.assertFalse(cautious['approved'],cautious)
        for p in self.b.by_pos('WR'):set_grade(p,65)
        self.assertTrue(self.plan()['approved'])

    def test_intent_survives_contract_rollover_and_next_year_negotiation(self):
        intent=self.buy()
        self.p.contract.advance();self.p.contract=None;self.L.year+=1
        self.L.set_phase('offseason');self.L.season_closed_year=self.L.year-1
        self.b.sync_cap()
        self.assertIs(TRE.active_plan(self.L,self.b,self.p),intent)
        TRE.pursue(self.L,self.b,np.random.default_rng(7))
        self.assertEqual(intent['state'],'accepted')
        self.assertEqual(self.p.contract.years,3)

    def test_cash_and_player_currency_cannot_disguise_an_expensive_purchase(self):
        set_grade(self.L.player('LT0'),91)
        outgoing=self.L.player('LT0')
        self.b.cap.dead_next=350
        denied=TRE.purchase_plans(self.L,self.b,self.s,[outgoing.pid],[self.p.pid])
        self.assertFalse(denied['approved'])
        self.assertEqual(outgoing.team,'MIN')

    def test_later_optional_trade_cannot_spend_reserved_renewal_room(self):
        self.buy()
        self.L.cap_history.update({2028:350.,2029:350.,2030:350.})
        q=self.b.by_pos('QB')[0]
        proposed=Contract(4,[1.,300.,300.,300.])
        blocked=FP.evaluate(self.L,self.b,additions=[(q,proposed)],gain=1000,action='trade')
        self.assertFalse(blocked['approved'])
        self.assertEqual(blocked['reason'],'fund_trade_extension_plan')
        self.p.xp_spent[TRE.KEY]['state']='refused'
        ordinary=FP.evaluate(self.L,self.b,additions=[(q,proposed)],gain=1000,action='trade')
        self.assertTrue(ordinary['approved'])

    def test_buyer_considers_age_at_extension_start_before_paying_picks(self):
        self.p.age=30.9;set_grade(self.p,88)
        for p in self.b.by_pos('WR'):set_grade(p,85)
        self.b.gm.youth=.95
        result=self.plan()
        self.assertFalse(result['approved'])
        self.assertFalse(result['assessment']['veteran_viable'])
        self.assertEqual(self.p.age,30.9)


if __name__=='__main__': unittest.main()
