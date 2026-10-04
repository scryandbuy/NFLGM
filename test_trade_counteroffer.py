import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import ExitStack
import views_personnel as VP, trades as TR, trade_engine as TE, valuation as VAL
class CounterTests(unittest.TestCase):
 def run_case(self, target, values, existing=(), blocked=False, plans=None, swap=None):
  picks=[NS(year=2026,round=i,original='GB',used_on=False) for i in values]
  me=NS(picks=picks,gm=None,cap_space=100,ctx=lambda:{})
  them=NS(picks=[],gm=None,cap_space=100,ctx=lambda:{})
  league=NS(teams={'GB':me,'MIN':them})
  prices={f'2026-{i}-GB':v for i,v in values.items()};prices['target']=target
  def assets(L,abbr,ids,*args,**kwargs): return [dict(value=prices[x]) for x in ids]
  def evaluate(offer,*args,**kwargs):
   gain=sum(x['value'] for x in offer['a_sends'])-sum(x['value'] for x in offer['a_gets'])
   return dict(a_gain=-gain,b_gain=gain,blocked='cap' if blocked else None)
  with ExitStack() as st:
   st.enter_context(patch.object(TR,'seller_pick_counter',return_value=([dict(kind='pick',value=values[i],obj=next(p for p in picks if p.round==i)) for i in swap] if swap else None)))
   st.enter_context(patch.object(TR,'cpu_trade_check',side_effect=plans or [dict(approved=True)]*3))
   for obj,name,fn in [(VP,'_trade_ids',lambda L,a,x:list(x)),(VP,'_rng',lambda *a:None),(VP,'_assets',assets),(VP,'_pick_row',lambda L,p:dict(label=f'Round {p.round}')),(VAL,'pool_from_league',lambda L:None),(TR,'persona',lambda x:{}),(TR,'pick_asset',lambda L,p:dict(value=values[p.round])),(TE,'evaluate',evaluate)]: st.enter_context(patch.object(obj,name,side_effect=fn))
   return VP.act_ask(league,'GB','MIN',list(existing),['target'])
 def test_meaningful_combination_not_late_pick_pile(self):
  r=self.run_case(12,{2:8,3:5,6:.3,7:.1});self.assertTrue(r['ok']);self.assertEqual(set(r['adds']),{'2026-2-GB','2026-3-GB'})
 def test_single_sufficient_pick(self):
  r=self.run_case(4,{1:20,2:9,3:5,7:.1});self.assertEqual(r['adds'],['2026-3-GB'])
 def test_impossible_unchanged(self):
  r=self.run_case(100,{2:8,3:5,6:.3,7:.1});self.assertFalse(r['ok']);self.assertEqual(r['adds'],[])
 def test_cap_blocked(self):
  r=self.run_case(1,{1:20},blocked=True);self.assertFalse(r['ok']);self.assertEqual(r['adds'],[])
 def test_existing_pick_not_duplicated(self):
  r=self.run_case(12,{2:8,3:5,7:.1},existing=['2026-2-GB']);self.assertEqual(r['adds'],['2026-3-GB'])
 def test_actual_value_not_round_number(self):
  r=self.run_case(4,{2:5,3:10,7:.1});self.assertEqual(r['adds'],['2026-2-GB'])
 def test_seller_threshold(self):
  r=self.run_case(4.3,{3:5,7:.3});self.assertEqual(set(r['adds']),{'2026-3-GB','2026-7-GB'})
 def test_ask_does_not_promise_to_fix_roster_loss_with_picks(self):
  r=self.run_case(4,{2:9},plans=[dict(approved=False,why='Would weaken lineup.')])
  self.assertFalse(r['ok']);self.assertEqual(r['adds'],[]);self.assertIn('lineup',r['why'])
 def test_final_pick_package_must_also_pass_funding(self):
  r=self.run_case(4,{2:9},plans=[dict(approved=True),dict(approved=False,why='Cannot fund rookie commitments.')])
  self.assertFalse(r['ok']);self.assertEqual(r['adds'],[])
 def test_optional_swap_returns_removed_picks_without_changing_offer(self):
  existing=['2026-3-GB','2026-4-GB']
  r=self.run_case(8,{1:10,3:3,4:2,5:4},existing=existing,swap=[1])
  self.assertTrue(r['ok']);self.assertEqual(r['adds'],['2026-1-GB'])
  self.assertEqual(r['removes'],existing);self.assertEqual(existing,['2026-3-GB','2026-4-GB'])
 def test_already_acceptable_original_can_be_kept(self):
  r=self.run_case(2,{3:5},existing=['2026-3-GB'])
  self.assertTrue(r['ok']);self.assertEqual(r['adds'],[]);self.assertEqual(r['removes'],[])
 def test_already_acceptable_original_can_receive_optional_swap(self):
  r=self.run_case(8,{1:12,3:6,4:4},existing=['2026-3-GB','2026-4-GB'],swap=[1])
  self.assertTrue(r['ok']);self.assertEqual(r['adds'],['2026-1-GB']);self.assertEqual(len(r['removes']),2)
if __name__ == '__main__':
 unittest.main()
