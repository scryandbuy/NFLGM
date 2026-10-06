import unittest
from types import SimpleNamespace as NS
import fa_demand as FD

class DemandTests(unittest.TestCase):
    def setUp(self):
        self.L = NS(phase='regular', year=2030, week=9, transactions=[])
        self.p = NS(pid='p', team=None, fa_class='UFA', xp_spent={}, accrued=5)
    def test_weekly_compounding_and_no_read_mutation(self):
        self.assertAlmostEqual(FD.factor(self.L,self.p), .95**8)
        self.assertEqual(FD.asking(self.L,self.p,20), FD.asking(self.L,self.p,20))
        self.L.week=10
        self.assertAlmostEqual(FD.factor(self.L,self.p), .95**9)
    def test_recent_release_and_new_stint(self):
        self.L.transactions=[dict(pid='p',kind='release',year=2030,phase='regular',week=8)]
        self.assertAlmostEqual(FD.factor(self.L,self.p), .95)
        self.p.xp_spent['_fa_demand_start']=[2030,9]
        self.assertEqual(FD.factor(self.L,self.p),1)
    def test_rostered_restricted_and_offseason_excluded(self):
        self.p.team='GB';self.assertEqual(FD.factor(self.L,self.p),1)
        self.p.team=None;self.p.fa_class='RFA';self.assertEqual(FD.factor(self.L,self.p),1)
        self.p.fa_class='UFA';self.L.phase='offseason';self.assertEqual(FD.factor(self.L,self.p),1)
    def test_minimum_and_year_reset(self):
        self.assertGreater(FD.asking(self.L,self.p,.01),.01)
        self.L.year=2031;self.L.week=1
        self.assertEqual(FD.factor(self.L,self.p),1)
    def test_existing_negotiation_updates_once_per_week(self):
        import negotiations as NG
        self.L.player=lambda pid:self.p
        self.L.negotiations=[dict(id=1,pid='p',kind='fa_inseason',state='open',ask=20.,unsigned_factor=.95**8)]
        self.L.week=10
        t=NG._threads(self.L)[0]
        self.assertEqual(t['ask'],19.)
        self.assertEqual(NG._threads(self.L)[0]['ask'],19.)

class BudgetTests(unittest.TestCase):
    def decision(self,gain,aggression,room=3.):
        from unittest.mock import patch
        import financial_plan as FP
        L=NS(user_team='GB');t=NS(abbr='MIN')
        before={'years':[dict(raw_room=15.,funded_room=15.,soft_reserve=10.,limit=300.)]}
        after={'years':[dict(raw_room=room,funded_room=room,soft_reserve=10.,limit=300.)]}
        with patch.object(FP,'snapshot',return_value=after), patch.object(FP,'_trait',side_effect=lambda t,k:aggression if k=='aggression' else .5):
            return FP.evaluate(L,t,gain=gain,action='veteran_market',before=before)
    def test_upgrade_can_spend_cushion_marginal_move_cannot(self):
        self.assertTrue(self.decision(8,.5)['approved'])
        self.assertFalse(self.decision(1,.5)['approved'])
    def test_gms_disagree(self):
        self.assertFalse(self.decision(3,0)['approved'])
        self.assertTrue(self.decision(3,1)['approved'])
    def test_current_cap_remains_hard(self):
        self.assertFalse(self.decision(100,1,-1)['approved'])
