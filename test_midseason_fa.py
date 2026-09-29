import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import market as MK, negotiations as NG
class MidseasonTests(unittest.TestCase):
 def setup_terms(self,week=10,phase='regular',years=1):
  L=NS(year=2026,week=week,phase=phase); p=NS(pos='QB'); t=NS(gm=None)
  with patch('contract_structure.structure',return_value=dict(base=[8]*years,signing_bonus=2,front_load=.5)):
   return MK.signing_terms(L,p,t,10,years,300,bonus=2)
 def test_remainder_cash_and_cap(self):
  r=self.setup_terms(); self.assertEqual(r['base'],[4]);self.assertEqual(r['cash_this_season'],6);self.assertEqual(r['cap_hits'],[6])
 def test_multiyear_preserved(self):
  r=self.setup_terms(years=2);self.assertEqual(r['base'],[4.5,9]);self.assertEqual(r['cap_hits'],[5.5,10]);self.assertEqual(r['total'],15.5)
 def test_offseason_full_cost(self):
  r=self.setup_terms(0,'free_agency');self.assertEqual(r['total'],10)
 def test_week18(self):
  r=self.setup_terms(18);self.assertAlmostEqual(r['cash_this_season'],2.444,places=3)
 def test_counter_one_year(self):
  t=dict(id=1,kind='fa_inseason',ask=10,years=4,patience=3,log=[])
  with patch.object(NG,'_say'),patch.object(NG,'_post'):
   result=NG._answer(NS(),t,NS(name='Test'),dict(apy=9),9.6)
  self.assertEqual(result,'countered');self.assertEqual(t['counter']['years'],1)
 def test_one_year_accepted(self):
  t=dict(kind='fa_inseason',ask=10,years=1)
  with patch.object(NG,'_accept',return_value=dict(ok=True,how='agreed')) as accept:
   self.assertEqual(NG._answer(NS(),t,NS(),dict(apy=10,years=1),9.6),'agreed')
   self.assertEqual(accept.call_args.args[2]['years'],1)
unittest.main()
