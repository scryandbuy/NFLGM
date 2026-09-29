import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import ExitStack
import views_personnel as VP, trades as TR, trade_engine as TE, valuation as VAL
class CounterTests(unittest.TestCase):
 def run_case(self, target, values, existing=(), blocked=False):
  picks=[NS(year=2026,round=i,original='GB',used_on=False) for i in values]
  me=NS(picks=picks,gm=None,cap_space=100,ctx=lambda:{})
  them=NS(gm=None,cap_space=100,ctx=lambda:{})
  league=NS(teams={'GB':me,'MIN':them})
  prices={f'2026-{i}-GB':v for i,v in values.items()};prices['target']=target
  def assets(L,abbr,ids,*args,**kwargs): return [dict(value=prices[x]) for x in ids]
  def evaluate(offer,*args):
   gain=sum(x['value'] for x in offer['a_sends'])-sum(x['value'] for x in offer['a_gets'])
   return dict(a_gain=-gain,b_gain=gain,blocked='cap' if blocked else None)
  with ExitStack() as st:
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
unittest.main()
