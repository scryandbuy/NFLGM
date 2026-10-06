import unittest
from unittest.mock import patch
import numpy as np
import targets as TG
import xp as XP
import xp_spend as XS
import views_club as VC
from gm_engine import GM
from session import Session
from test_cap_accounting import fixture,player


class SpendReadinessTests(unittest.TestCase):
    def setUp(self):
        self.L=fixture();self.p=player(self.L);self.p.pos='WR';self.p.age=29
        self.p.ratings={k:88. for k in TG.DEPTH_WEIGHTS['WR']}
        self.p.ratings['injury_rating']=70.
        self.p.potential=93.;self.p.xp_spent={'catch_rating':5,'_bought_season':5}
        self.p.xp=1_000_000;self.t=self.L.teams['GB'];self.t.gm=GM()
        self.s=Session(self.L,np.random.default_rng(1),'GB')

    def row(self):
        with patch.object(VC,'rail',return_value={}):
            return VC.progression(self.s,self.L,'GB')['rows'][0]

    def test_readiness_excludes_cheap_attributes_assistants_never_choose(self):
        for k in TG.DEPTH_WEIGHTS['WR']:self.p.xp_spent[k]=5
        cheap=XP.cost_per_point(self.p,'injury_rating')
        eligible=XS.next_spend_cost(self.p,self.t)
        self.assertGreater(eligible,cheap)
        self.p.xp=(cheap+eligible)/2
        self.assertFalse(self.row()['can_buy']);self.assertFalse(XP.at_ceiling(self.p))
        self.assertEqual(self.row()['cheapest'],round(eligible))
        bank=self.p.xp
        result=VC.act_spend_by_read(self.L,'GB',self.p.pid)
        self.assertEqual(result['spent'],0);self.assertEqual(bank,self.p.xp)
        sheet=VC.development(self.s,self.L,'GB',self.p.pid)
        self.assertFalse(sheet['can_spend'])
        injury=next(r for r in sheet['rows'] if r['key']=='injury_rating')
        self.assertTrue(injury['afford']);self.assertIsNone(injury['blocked'])
        self.assertTrue(VC.act_buy_point(self.L,'GB',self.p.pid,'injury_rating')['ok'])
        self.assertLess(self.p.xp,bank)

    def test_available_point_spends_without_a_false_ceiling_notice(self):
        self.p.xp=XS.next_spend_cost(self.p,self.t)+.01
        self.assertTrue(self.row()['can_buy'])
        result=VC.act_spend_by_read(self.L,'GB',self.p.pid)
        self.assertEqual(result['spent'],1);self.assertLess(self.p.xp,1)
        self.assertFalse(self.s.development_notices()['players'])

    def test_explicit_spend_does_not_wait_for_an_unaffordable_saved_target(self):
        self.p.age=22;self.p.xp_spent['_saving_for']='speed_rating'
        self.p.xp=XS.next_spend_cost(self.p,self.t)+.01
        self.assertTrue(self.row()['can_buy'])
        result=VC.act_spend_by_read(self.L,'GB',self.p.pid)
        self.assertGreater(result['spent'],0);self.assertLess(self.p.xp,1)

    def test_ceiling_and_insufficient_xp_are_distinct(self):
        self.p.potential=TG.position_score(self.p.ratings,self.p.pos)+.001
        self.p.xp=1
        row=self.row();self.assertTrue(XP.at_ceiling(self.p));self.assertFalse(row['can_buy'])
        result=VC.act_spend_by_read(self.L,'GB',self.p.pid)
        self.assertEqual(result['spent'],0)

    def test_every_enabled_manual_spend_uses_xp_even_if_draw_is_too_expensive(self):
        self.p.age=22
        self.p.xp=XS.next_spend_cost(self.p,self.t)+.01
        self.assertTrue(self.row()['can_buy'])
        with patch.object(XS,'choose_attr',return_value='speed_rating'):
            result=VC.act_spend_by_read(self.L,'GB',self.p.pid)
        self.assertGreater(result['spent'],0);self.assertLess(self.p.xp,1)

    def test_weekly_automatic_spending_still_respects_a_saved_target(self):
        self.p.age=22;self.p.xp_spent['_saving_for']='speed_rating'
        self.p.xp=XS.next_spend_cost(self.p,self.t)+.01;bank=self.p.xp
        acts=XS.spend_player(self.p,self.t.gm,self.t,4,np.random.default_rng(1))
        self.assertEqual(acts[0][0],'save');self.assertEqual(self.p.xp,bank)

    def test_enabled_spend_invariant_across_positions_and_random_choices(self):
        for pos in TG.DEPTH_WEIGHTS:
            for age in (22,29):
                for seed in range(4):
                    with self.subTest(pos=pos,age=age,seed=seed):
                        self.p.pos=pos;self.p.age=age;self.p.potential=95
                        self.p.ratings={k:70. for k in TG.DEPTH_WEIGHTS[pos]}
                        self.p.xp_spent={};self.p.xp=XS.next_spend_cost(self.p,self.t)+.01
                        bank=self.p.xp
                        self.assertTrue(self.row()['can_buy'])
                        XS.spend_player(self.p,self.t.gm,self.t,4,np.random.default_rng(seed),spend_now=True)
                        self.assertLess(self.p.xp,bank)


if __name__=='__main__':unittest.main()
