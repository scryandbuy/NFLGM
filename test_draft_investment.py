"""Draft restraint preserves upgrades, succession, GM differences and waiting."""
import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import draft as D
import draft_plan as DP
from draft_day import Draft
from league import DraftPick
from test_draft_planning import fixture, set_grade
from test_draft_redundancy import room, add_pick

class DraftInvestmentTests(unittest.TestCase):
    def test_recent_low_rated_picks_use_development_slots(self):
        L,t=fixture();t.gm.off_personnel='11'
        room(L,t,'WR',[(92,29,1),(87,27,2),(81,26,1)])
        prospect=L.player('rookie-WR0')
        costs=[]
        for i in range(5):
            costs.append(DP.redundancy_penalty(DP.assess(L,'MIN'),prospect,grade=72))
            p=add_pick(L,t,'WR',69,selection=160+i)
            p.contract.signed=L.year
        self.assertEqual(costs[0],0)
        self.assertGreater(costs[-1], costs[-2])
        self.assertGreater(costs[-2],0)
        self.assertEqual(DP.redundancy_penalty(DP.assess(L,'MIN'),prospect,grade=96,gain=8),0)

    def test_campbell_darrisaw_controlled_young_starter_is_not_displaced_for_small_gain(self):
        L,t=fixture();p=L.player('LT0');p.name='Will Campbell';set_grade(p,88)
        veteran=L.player('rookie-LT0');veteran.name='Christian Darrisaw';veteran.age=32
        plan=DP.assess(L,'MIN');saved=copy.deepcopy(L.save())
        marginal=DP.commitment_penalty(plan,veteran,89)
        self.assertGreater(marginal,0)
        self.assertEqual(DP.commitment_penalty(plan,veteran,96),0)
        veteran.name='Different player'
        self.assertEqual(DP.commitment_penalty(plan,veteran,89),marginal)
        veteran.name='Christian Darrisaw'
        self.assertEqual(L.save(),saved)
        set_grade(p,65)
        self.assertEqual(DP.commitment_penalty(DP.assess(L,'MIN'),veteran,89),0)

    def test_commitment_is_less_binding_for_best_available_gm(self):
        L,t=fixture();p=L.player('rookie-LT0');plan=DP.assess(L,'MIN')
        t.gm.board_trust=0.;need_first=DP.commitment_penalty(plan,p,77)
        t.gm.board_trust=1.;self.assertLess(DP.commitment_penalty(plan,p,77),need_first)

    def test_retention_accounts_for_money_performance_and_loyalty(self):
        L,t=fixture();p=L.player('QB0');p.contract.years=1;set_grade(p,85)
        good=dict(pass_att=500,pass_yds=4000,pass_td=30,ints=8)
        poor=dict(pass_att=500,pass_yds=3200,pass_td=12,ints=20)
        self.assertGreater(DP.return_chance(p,t.gm,0,good),DP.return_chance(p,t.gm,0,poor))
        self.assertGreater(DP.return_chance(p,t.gm,0,good),DP.return_chance(p,t.gm,1,good))
        t.gm.loyalty=0.;low=DP.return_chance(p,t.gm)
        t.gm.loyalty=1.;self.assertGreater(DP.return_chance(p,t.gm),low)
        p.age=37;self.assertLess(DP.return_chance(p,t.gm),low)

    def test_qb_expiry_urgency_has_no_new_threshold_cliff(self):
        L,t=fixture();p=L.player('QB0');p.contract.years=1;set_grade(p,85)
        scores=[]
        for chance in (.49,.50,.51):
            with patch.object(DP,'return_chance',return_value=chance),patch.object(D,'slot_value',side_effect=lambda slot:-slot):
                scores.append(dict((p.pid,v) for v,p in D.board(L,'MIN',10,{},set()))['rookie-QB0'])
        self.assertLess(max(scores)-min(scores),3)

    def target_setup(self):
        L,t=fixture();d=Draft(L,np.random.default_rng(3),2026)
        pk=DraftPick(2026,1,'GB','GB',selection=10)
        p,q=L.draft_pool[:2]
        L.consensus[p.pid]['rank']=5;L.consensus[q.pid]['rank']=35
        return L,t,d,pk,p,q

    def test_trade_up_values_preference_and_gm_not_fixed_bonus(self):
        L,t,d,pk,p,q=self.target_setup()
        with patch.object(d,'_pick_asset',return_value={}),patch.object(d,'board_for',return_value=[(100,p),(99,q)]),patch.object(D,'scouted_grade',return_value=80):
            t.gm.aggression=0.;cautious=d._target_asset('MIN',pk,p)['draft_target_premium']
            t.gm.aggression=1.;aggressive=d._target_asset('MIN',pk,p)['draft_target_premium']
        self.assertGreater(aggressive,cautious)
        self.assertLess(aggressive,1.2)
        with patch.object(d,'_pick_asset',return_value={}),patch.object(d,'board_for',return_value=[(100,p),(60,q)]),patch.object(D,'scouted_grade',side_effect=lambda l,a,x:90 if x is p else 80):
            strong=d._target_asset('MIN',pk,p)['draft_target_premium']
        self.assertGreater(strong,1.2)

    def test_same_trade_is_declined_for_flat_board_and_accepted_for_clear_preference(self):
        import trade_engine as TE
        L,t,d,pk,p,q=self.target_setup();t.gm.aggression=1.
        with patch.object(d,'_pick_asset',return_value={'kind':'pick','pick':10,'years_out':0}),patch.object(d,'board_for',return_value=[(100,p),(99,q)]),patch.object(D,'scouted_grade',return_value=80):
            flat=d._target_asset('MIN',pk,p)
        with patch.object(d,'_pick_asset',return_value={'kind':'pick','pick':10,'years_out':0}),patch.object(d,'board_for',return_value=[(100,p),(60,q)]),patch.object(D,'scouted_grade',side_effect=lambda l,a,x:90 if x is p else 80):
            standout=d._target_asset('MIN',pk,p)
        package=[dict(kind='pick',pick=n,years_out=0) for n in (11,45)]
        context=dict(win_pct=.5,avg_age=27)
        def decision(target):
            return TE.evaluate(dict(a_sends=package,a_gets=[target]),context,context,80,80)
        self.assertFalse(decision(flat)['accepted'])
        self.assertTrue(decision(standout)['accepted'])
        # The seller's assessment is not changed by the buyer's enthusiasm.
        self.assertEqual(decision(flat)['b_gain'],decision(standout)['b_gain'])

    def test_likely_available_target_reduces_trade_up_willingness(self):
        L,t,d,pk,p,q=self.target_setup()
        with patch.object(d,'_pick_asset',return_value={}),patch.object(d,'board_for',return_value=[(100,p),(90,q)]),patch.object(D,'scouted_grade',return_value=80):
            early=d._target_asset('MIN',pk,p)['draft_target_premium']
            L.consensus[p.pid]['rank']=80
            self.assertLess(d._target_asset('MIN',pk,p)['draft_target_premium'],early)

if __name__=='__main__':unittest.main()
