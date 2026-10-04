import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import financial_plan as FP

class ForecastPolicyTests(unittest.TestCase):
    def assess(self, gain, gap):
        team=NS(abbr='DET',gm=NS(aggression=.5))
        league=NS(user_team='GB')
        def row(room):
            return dict(raw_room=room, funded_room=room, soft_reserve=0.,limit=300.)
        before=dict(years=[row(50),row(0)])
        after=dict(years=[row(47),row(-gap)])
        with patch.object(FP,'snapshot',return_value=after):
            return FP.evaluate(league,team,before=before,action='trade',gain=gain)
    def test_future_negative_cap_is_not_automatic_veto(self):
        self.assertTrue(self.assess(0,10)['approved'])
    def test_meaningful_upgrade_can_outweigh_same_financial_risk(self):
        self.assertFalse(self.assess(0,30)['approved'])
        self.assertTrue(self.assess(20,30)['approved'])
    def test_extreme_shortfalls_keep_increasing_risk(self):
        moderate = self.assess(20,150)
        extreme = self.assess(20,500)
        self.assertFalse(moderate['approved'])
        self.assertFalse(extreme['approved'])
        self.assertGreater(extreme['forecast_risk'], moderate['forecast_risk'])
    def test_concrete_current_roster_costs_outweigh_optional_cushions(self):
        team=NS(abbr='DET',gm=NS(aggression=.5))
        league=NS(user_team='GB')
        def assess(room, reserve):
            before=dict(years=[dict(funded_room=0.,soft_reserve=0.,limit=300.)])
            after=dict(years=[dict(funded_room=room,soft_reserve=reserve,limit=300.)])
            with patch.object(FP,'snapshot',return_value=after):
                return FP.evaluate(league,team,before=before,action='trade',gain=3)
        self.assertFalse(assess(-10,0)['approved'])
        self.assertTrue(assess(0,10)['approved'])
    def test_existing_future_shortfall_is_not_recharged(self):
        self.assertTrue(self.assess(0,0)['approved'])

if __name__=='__main__': unittest.main()

class GatherOfferTests(unittest.TestCase):
    def gather(self, blocked=False, accepts=True):
        from contextlib import ExitStack
        import views_personnel as VP, trades as TR, trade_engine as TE, valuation as VAL
        player=NS(pid='p',team='GB',name='Player')
        pick=NS(year=2029,round=2,original='DET',used_on=False)
        me=NS(gm=None,cap_space=50,ctx=lambda:{},picks=[])
        them=NS(gm=None,cap_space=50,ctx=lambda:{},picks=[pick])
        league=NS(year=2029,teams={'GB':me,'DET':them},player=lambda pid:player)
        with ExitStack() as stack:
            for obj,name,value in [(VP,'_rng',None),(VAL,'pool_from_league',None),
                (TR,'persona',{'aggression':.5}),(VP,'_assets',[{'trade_value':1}]),
                (TR,'surplus_and_needs',([],[])),(TR,'pick_asset',{}),
                (TE,'evaluate',dict(a_gain=2,b_gain=2)),
                (VP,'_evaluate',dict(verdict='blocked' if blocked else 'fair')),
                (TR,'will_accept',accepts),(VP,'_pick_row',dict(label='2029 R2'))]:
                stack.enter_context(patch.object(obj,name,return_value=value))
            return VP.act_gather(league,'GB','p')['offers']
    def test_final_assessment_rejection_is_not_advertised(self):
        self.assertEqual(self.gather(blocked=True),[])
    def test_gm_rejection_is_not_advertised(self):
        self.assertEqual(self.gather(accepts=False),[])
    def test_acceptable_offer_is_advertised(self):
        self.assertEqual(len(self.gather()),1)
