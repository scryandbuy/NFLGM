"""Interactive offers carry the CPU's future roster cost into its decision."""
import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import inbox as IB
import trades as TR
import trade_engine as TE
import views_personnel as VP
from test_trade_integrity import roster, league, pk


class PortfolioEntryTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=roster('GB'),roster('DEN')
        self.L=league(self.a,self.b);self.L.user_team='GB'
        self.L.trade=Mock();self.L.log=Mock()
        for p in self.a.roster+self.b.roster:p.name=p.pid
        self.pid=self.a.roster[0].pid;self.other=self.b.roster[0].pid
        self.plan=dict(approved=True,portfolio_costs={'DEN':2.4,'GB':999},required_gain=0)

    def proposal(self, raw=2., cost=2.4, aggression=.5):
        self.plan['portfolio_costs']['DEN']=cost
        with patch.object(VP,'_evaluate',return_value=dict(verdict='fair',read='Fair.')), \
             patch('valuation.pool_from_league',return_value=[]),patch.object(VP,'_assets',return_value=[]), \
             patch.object(VP,'_rng',return_value=NS(random=lambda:.45)), \
             patch.object(TR,'persona',return_value={'aggression':aggression}), \
             patch.object(TE,'evaluate',return_value=dict(a_gain=5,b_gain=raw,accepted=True)), \
             patch.object(TR,'cpu_trade_check',return_value=self.plan),patch.object(IB,'post'):
            return VP.act_propose(self.L,'GB','DEN',[self.pid],[self.other])

    def test_proposal_uses_narrow_seller_window_after_cost_and_rejects_atomically(self):
        before=([p.pid for p in self.a.roster],[p.pid for p in self.b.roster],list(self.L.transactions))
        self.assertFalse(self.proposal()['done'])  # 2 - 2.4 is below the seller's -.3 window.
        self.L.trade.assert_not_called();self.L.log.assert_not_called()
        self.assertEqual(before,([p.pid for p in self.a.roster],[p.pid for p in self.b.roster],self.L.transactions))

    def test_worthwhile_offer_still_accepted_and_user_cost_is_not_imposed(self):
        self.assertTrue(self.proposal(raw=2,cost=.5)['done'])
        self.L.trade.assert_called_once()

    def test_same_marginal_effective_gain_preserves_gm_disagreement(self):
        self.assertFalse(self.proposal(raw=1,cost=1,aggression=0)['done'])
        self.assertTrue(self.proposal(raw=1,cost=1,aggression=1)['done'])
        self.L.trade.assert_called_once()

    def test_preview_does_not_claim_acceptance_from_unadjusted_quote(self):
        for t in (self.a,self.b):t.phase='season'
        with patch('valuation.pool_from_league',return_value=[]),patch.object(VP,'_assets',return_value=[]), \
             patch.object(TR,'cpu_trade_check',return_value=self.plan), \
             patch.object(TE,'evaluate',return_value=dict(a_gain=5,b_gain=2,b_in=10,b_out=8,accepted=True)), \
             patch('cap_accounting.trade_projection',return_value=NS(space=lambda phase:100)):
            view=VP._evaluate(self.L,'GB','DEN',[self.pid],[self.other])
        self.assertFalse(view['would_accept']);self.assertEqual(view['verdict'],'short')
        self.assertNotIn('portfolio_cost',view)
        self.assertIn('like your side',view['my_read'])

    def test_gather_does_not_advertise_offer_propose_would_decline(self):
        self.b.picks=[pk(48,'DEN',2028)]
        def preview(*args,**kwargs):
            kwargs['decision_out'].update(self.plan)
            return dict(verdict='short')
        with patch('valuation.pool_from_league',return_value=[]), \
             patch.object(VP,'_assets',return_value=[dict(kind='player',trade_value=1)]), \
             patch.object(TR,'surplus_and_needs',return_value=([],[])), \
             patch.object(TR,'pick_asset',return_value=dict(kind='pick')), \
             patch.object(VP,'_evaluate',side_effect=preview), \
             patch.object(TE,'evaluate',return_value=dict(a_gain=5,b_gain=2,accepted=True)):
            result=VP.act_gather(self.L,'GB',self.pid)
        self.assertEqual(result['offers'],[])

    def offer(self):
        self.b.picks=[pk(48,'DEN',2028),pk(80,'DEN',2028)]
        self.L.inbox=[dict(id=1,kind='trade_offer',status='open',payload=dict(
            buyer='DEN',user_team='GB',sends=[dict(year=2028,round=2,original='DEN')],gets=[self.pid]))]

    def test_old_inbox_offer_rechecks_changed_inventory_without_roll_or_mutation(self):
        self.offer();observed=[]
        def check(*args,**kwargs):
            observed.append(len(self.b.picks))
            return dict(approved=True,portfolio_costs={'DEN':3},
                        portfolio_gains={'DEN':0 if len(self.b.picks)>1 else -2})
        with patch.object(IB,'reconcile'),patch.object(TR,'cpu_trade_check',side_effect=check), \
             patch.object(TR,'will_accept',side_effect=AssertionError('mail cannot reroll')):
            check()  # The proposal was affordable before another pick left.
            self.b.picks.pop()
            before=copy.deepcopy(self.L.inbox)
            with self.assertRaisesRegex(ValueError,'future roster options'):
                IB.accept(self.L,1,'GB')
        self.assertEqual(observed,[2,1]);self.assertEqual(self.L.inbox,before)
        self.L.trade.assert_not_called();self.L.log.assert_not_called()
        self.assertEqual(self.b.picks[0].owner,'DEN')

    def test_valid_marginal_inbox_offer_keeps_existing_willingness(self):
        self.offer()
        with patch.object(IB,'reconcile'),patch.object(TR,'cpu_trade_check',return_value=dict(
                approved=True,portfolio_costs={'DEN':1},portfolio_gains={'DEN':-.5})), \
             patch.object(TR,'will_accept',side_effect=AssertionError('mail cannot reroll')):
            IB.accept(self.L,1,'GB')
        self.L.trade.assert_called_once();self.assertEqual(self.L.inbox[0]['status'],'accepted')


class PortfolioCounters(unittest.TestCase):
    def test_counter_search_prices_cpu_remaining_options_once_for_each_package(self):
        picks=[pk(48,'GB',2028),pk(80,'GB',2028)]
        target=pk(16,'DEN',2028)
        a=NS(picks=picks,gm=None,cap_space=100,ctx=lambda:{})
        b=NS(picks=[target],gm=None,cap_space=100,ctx=lambda:{})
        L=NS(teams={'GB':a,'DEN':b})
        values={'2028-2-GB':8.,'2028-3-GB':5.,'2028-1-DEN':4.}
        def evaluate(offer,*args,**kw):
            gain=sum(x['value'] for x in offer['a_sends'])-sum(x['value'] for x in offer['a_gets'])
            return dict(a_gain=-gain,b_gain=gain,blocked=None)
        checked=[]; caches=[]
        def plan(L,ta,tb,sent,received,**kw):
            checked.append(tuple(p.round for p in sent))
            caches.append((kw['football_cache'],kw['financial_cache']))
            return dict(approved=True,portfolio_costs={'DEN':2,'GB':999})
        with ExitStack() as stack:
            for obj,name,fn in [
                (VP,'_trade_ids',lambda L,a,x:list(x)),(VP,'_rng',lambda *a:None),
                (VP,'_assets',lambda L,a,ids,*args,**kw:[dict(value=values[x]) for x in ids]),
                (VP,'_pick_row',lambda L,p:dict(label=f'Round {p.round}')),
                (TR,'persona',lambda gm:{}),(TR,'pick_asset',lambda L,p:dict(value=values[f'{p.year}-{p.round}-{p.original}'])),
                (TR,'cpu_trade_check',plan),(TE,'evaluate',evaluate)]:
                stack.enter_context(patch.object(obj,name,side_effect=fn))
            stack.enter_context(patch('valuation.pool_from_league',return_value=[]))
            stack.enter_context(patch.object(TR,'seller_pick_counter',return_value=None))
            result=VP.act_ask(L,'GB','DEN',[],['2028-1-DEN'])
        self.assertTrue(result['ok']);self.assertEqual(result['adds'],['2028-2-GB'])
        self.assertIn((3,),checked);self.assertIn((2,),checked)
        self.assertTrue(all(a is caches[0][0] and b is caches[0][1] for a,b in caches))
        self.assertEqual(a.picks,picks);self.assertEqual(b.picks,[target])


if __name__=='__main__':unittest.main()
