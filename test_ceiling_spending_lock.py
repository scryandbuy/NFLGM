"""Manual and automatic spending share the ceiling's all-attribute lock."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
import targets as TG
import xp as XP
import xp_spend as XS
import views_club as VC
from league import League
from session import Session
from gm_engine import GM
from test_cap_accounting import fixture, player


class CeilingSpendingLockTests(unittest.TestCase):
    def setUp(self):
        self.L=fixture(); self.p=player(self.L)
        self.p.age=23
        self.p.ratings={k:70. for k in TG.DEPTH_WEIGHTS['QB']}
        self.p.ratings.update(injury_rating=70., kick_power_rating=70.)
        self.p.potential=self.p.ovr+.001
        self.p.xp=1_000_000
        self.team=self.L.teams['GB']; self.team.gm=GM()
        self.rng=np.random.default_rng(4)

    def test_all_attributes_blocked_including_zero_overall_gain(self):
        self.assertTrue(XP.at_ceiling(self.p))
        before=copy.deepcopy(self.L.save())
        for attr in self.p.ratings:
            with self.subTest(attr=attr):
                self.assertTrue(XP.at_ceiling(self.p,attr))
                self.assertIsNone(XP.buy(self.p,attr))
        self.assertEqual(self.L.save(),before)

    def test_manual_action_and_sheet_agree_with_ceiling_notice(self):
        s=Session(self.L,self.rng,'GB')
        self.assertTrue(s.development_notices()['players'])
        result=VC.act_buy_point(self.L,'GB',self.p.pid,'injury_rating')
        self.assertFalse(result['ok']); self.assertIn('unlock',result['why'])
        rows=VC.development(s,self.L,'GB',self.p.pid)['rows']
        self.assertTrue(rows)
        self.assertTrue(all(row['blocked']=='at his ceiling' for row in rows))

    def test_unlock_restores_spending_and_costs_are_recorded(self):
        old_xp=self.p.xp; old_pot=self.p.potential
        unlock=XP.unlock(self.p)
        self.assertIsNotNone(unlock); self.assertFalse(XP.at_ceiling(self.p))
        bought=XP.buy(self.p,'injury_rating')
        self.assertIsNotNone(bought)
        self.assertAlmostEqual(self.p.potential,old_pot+1)
        self.assertAlmostEqual(self.p.xp,old_xp-unlock-bought)
        self.assertEqual([p['kind'] for p in self.p.xp_spent['_purchases']],['unlock','buy'])

    def test_lock_survives_save_reload_without_new_save_fields(self):
        loaded=League.load(self.L.save()).player(self.p.pid)
        before=copy.deepcopy(loaded.xp_spent); bank=loaded.xp
        self.assertIsNone(XP.buy(loaded,'injury_rating'))
        self.assertEqual(loaded.xp,bank); self.assertEqual(loaded.xp_spent,before)

    def test_ceiling_does_not_stop_earning_xp(self):
        bank=self.p.xp
        self.p.xp += XP.credit(self.p,1000,'test')
        self.assertGreater(self.p.xp,bank)
        self.assertIsNone(XP.buy(self.p,'injury_rating'))

    def test_ai_queued_purchase_cannot_bypass_unlock(self):
        self.p.xp_spent['_saving_for']='injury_rating'
        with patch.object(XS,'choose_attr',return_value=None):
            actions=XS.spend_player(self.p,self.team.gm,self.team,1,self.rng)
        self.assertEqual([a[0] for a in actions],['unlock','buy'])
        self.assertEqual(actions[1][1],'injury_rating')
        self.assertNotIn('_saving_for',self.p.xp_spent)

    def test_unaffordable_unlock_preserves_bank_and_pending_target(self):
        self.p.xp_spent['_saving_for']='injury_rating'
        self.p.xp=XP.unlock_cost(self.p)-1
        before=copy.deepcopy(self.p.ratings); bank=self.p.xp
        with patch.object(XS,'choose_attr',side_effect=AssertionError('cannot choose attributes while capped')):
            actions=XS.spend_player(self.p,self.team.gm,self.team,1,self.rng)
        self.assertFalse(any(a[0]=='buy' for a in actions))
        self.assertEqual(self.p.ratings,before); self.assertEqual(self.p.xp,bank)
        self.assertEqual(self.p.xp_spent['_saving_for'],'injury_rating')

    def test_cpu_and_user_auto_spend_both_unlock_before_buying(self):
        cpu=player(self.L,'cpu','MIN'); cpu.ratings=dict(self.p.ratings)
        cpu.potential=self.p.potential; cpu.xp=self.p.xp; cpu.age=23
        self.L.teams['MIN'].gm=GM()
        for p in (self.p,cpu): p.xp_spent['_saving_for']='injury_rating'
        self.p.xp_spent['_auto']=True
        with patch.object(XS,'choose_attr',return_value=None):
            actions=XS.spend_week(self.L,3,self.rng,user_team='GB')
        for p in (self.p,cpu):
            self.assertEqual([a[0] for a in actions[p.pid]],['unlock','buy'])

    def test_maximum_ceiling_has_no_attribute_escape(self):
        self.p.ratings.update({k:99. for k in TG.DEPTH_WEIGHTS['QB']})
        self.p.potential=99
        self.assertTrue(XP.at_ceiling(self.p)); self.assertIsNone(XP.unlock(self.p))
        self.assertIsNone(XP.buy(self.p,'kick_power_rating'))
        result=VC.act_buy_point(self.L,'GB',self.p.pid,'kick_power_rating')
        self.assertIn('maximum ceiling',result['why'])


if __name__=='__main__': unittest.main()
