"""Interactive trade entry points must enforce the same CPU plan at execution."""
import unittest
from unittest.mock import Mock, patch

import inbox
import trades as TR
import views_personnel as VP
from test_trade_integrity import roster, league


class TradeEntryGuardTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=roster('GB'),roster('DEN')
        self.L=league(self.a,self.b);self.L.user_team='GB'
        self.L.trade=Mock();self.L.log=Mock()
        self.pid=self.a.roster[0].pid

    def test_manual_proposal_cannot_bypass_cpu_plan_with_favorable_price(self):
        with patch.object(VP,'_evaluate',return_value=dict(verdict='fair',read='Fair.')), \
             patch('valuation.pool_from_league',return_value=[]), \
             patch.object(VP,'_assets',return_value=[]), \
             patch('trade_engine.evaluate',return_value=dict(a_gain=10,b_gain=10,accepted=True)), \
             patch.object(TR,'will_accept',return_value=True), \
             patch.object(TR,'cpu_trade_check',return_value=dict(approved=False,why='Essential coverage.')) as check:
            result=VP.act_propose(self.L,'GB','DEN',[self.pid],[self.b.roster[0].pid])
        self.assertFalse(result['done']);self.assertEqual(result['why'],'Essential coverage.')
        self.L.trade.assert_not_called();check.assert_called_once()

    def offer(self):
        self.L.inbox=[dict(id=1,kind='trade_offer',status='open',payload=dict(
            buyer='DEN',user_team='GB',sends=[self.b.roster[0].pid],gets=[self.pid]))]

    def test_inbox_revalidates_before_any_assets_or_mail_status_change(self):
        self.offer()
        with patch.object(inbox,'reconcile'), patch.object(TR,'cpu_trade_check',return_value=dict(
                approved=False,why='No longer funded.')) as check:
            with self.assertRaisesRegex(ValueError,'No longer funded'):
                inbox.accept(self.L,1,'GB')
        self.L.trade.assert_not_called()
        self.assertEqual(self.L.inbox[0]['status'],'open')
        self.assertEqual(check.call_args.kwargs['buyer'],'DEN')

    def test_still_valid_inbox_offer_executes_once(self):
        self.offer()
        with patch.object(inbox,'reconcile'), patch.object(TR,'cpu_trade_check',return_value=dict(approved=True)):
            inbox.accept(self.L,1,'GB')
            with self.assertRaisesRegex(ValueError,'no open offer'):
                inbox.accept(self.L,1,'GB')
        self.L.trade.assert_called_once()
        self.assertEqual(self.L.inbox[0]['status'],'accepted')

    def test_stale_buyer_upgrade_is_rejected_without_new_willingness_roll(self):
        # This fixture tests the CPU decision after the separate cap-legality gate.
        with patch('cap_accounting.require_trade_room') as legality, \
             patch.object(TR,'package_football',return_value=dict(approved=True,gains={'DEN':0.})), \
             patch.object(TR,'_financial_trade') as funding, patch.object(TR,'will_accept') as roll:
            result=TR.cpu_trade_check(self.L,self.b,self.a,[],[self.pid],buyer='DEN')
        self.assertFalse(result['approved']);self.assertIn('upgrade',result['why'])
        legality.assert_called_once_with(self.L,'DEN','GB',[],[self.pid])
        roll.assert_not_called();funding.assert_not_called()

    def test_manual_cpu_future_funding_failure_is_rejected(self):
        with patch('cap_accounting.require_trade_room') as legality, \
             patch.object(TR,'package_football',return_value=dict(approved=True,gains={})), \
             patch.object(TR,'_financial_trade',return_value=False) as funding:
            result=TR.cpu_trade_check(self.L,self.a,self.b,[],[])
        self.assertFalse(result['approved'])
        self.assertEqual(result['why'],"The roster benefit doesn't justify the financial risk for us.")
        funding.assert_called_once()
        legality.assert_called_once_with(self.L,'GB','DEN',[],[])

    def test_user_can_choose_to_empty_own_position(self):
        outgoing=[p.pid for p in self.a.roster if p.pos=='WR']
        result=TR.package_football(self.L,self.a,self.b,outgoing,[])
        self.assertTrue(result['approved'])
        self.L.user_team=None
        cpu=TR.package_football(self.L,self.a,self.b,outgoing,[])
        self.assertTrue(cpu['approved'])
        self.assertGreater(cpu['reserves']['GB'],0)


if __name__=='__main__': unittest.main()
