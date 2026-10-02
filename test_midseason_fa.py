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
  team=NS(gm=None); L=NS(year=2026,teams={'TST':team})
  t=dict(id=1,team='TST',kind='fa_inseason',ask=10,years=1,patience=3,log=[])
  assessment=dict(acceptable=False,reference_package=dict(apy=10,years=1,bonus=2,front_load=.5))
  with patch.object(NG,'_say'),patch.object(NG,'_post'),patch.object(NG,'_assessment',return_value=assessment):
   result=NG._answer(L,t,NS(name='Test',pos='QB'),dict(apy=9,years=1),9.6)
  self.assertEqual(result,'countered');self.assertEqual(t['counter']['years'],1)
 def test_one_year_accepted(self):
  L=NS(year=2026,teams={'TST':NS(gm=None)})
  t=dict(team='TST',kind='fa_inseason',ask=10,years=1)
  with patch.object(NG,'_assessment',return_value=dict(acceptable=True)),\
       patch.object(NG,'_accept',return_value=dict(ok=True,how='agreed')) as accept:
   self.assertEqual(NG._answer(L,t,NS(pos='QB'),dict(apy=10,years=1),9.6),'agreed')
   self.assertEqual(accept.call_args.args[2]['years'],1)
 def test_bonus_proration_capped_at_five_years(self):
  r=self.setup_terms(0,'free_agency',years=7)
  self.assertAlmostEqual(r['cap_hits'][0]-r['base'][0],.4,places=3)
  self.assertAlmostEqual(r['cap_hits'][5],r['base'][5],places=3)
 def test_bonus_cannot_exceed_total(self):
  with self.assertRaises(ValueError):
   MK.signing_terms(NS(year=2026,week=10,phase='regular'),NS(pos='QB'),NS(gm=None),1,1,300,bonus=2)
 def test_paid_ledger_drives_fraction(self):
  with patch('contract_structure.structure',return_value=dict(base=[8],signing_bonus=2)):
   r=MK.signing_terms(NS(year=2026,week=10,phase='regular'),NS(pos='QB'),NS(gm=None,cap=NS(paid_week=10)),10,1,300)
  self.assertAlmostEqual(r['base'][0],3.556,places=3)
 def test_pre_roll_preview_starts_next_year(self):
  with patch('contract_structure.structure',return_value=dict(base=[8],signing_bonus=2)):
   r=MK.signing_terms(NS(year=2026,week=22,phase='offseason',season_closed_year=2026),NS(pos='QB'),NS(gm=None),10,1,300)
  self.assertEqual(r['start_year'],2027)
  self.assertEqual(r['cap_hits'],[10])
if __name__ == '__main__':
 unittest.main()
