import unittest
from types import SimpleNamespace as N
from gameplan_week import pressure_advice

class AdviceTests(unittest.TestCase):
 def call(self,rate=.4,gap=8,sample=100,short=.6,pa=.3,screens=0,fit=True):
  return pressure_advice(dict(pressure_version=2,pressure_dropbacks=sample,pressured_dropbacks=rate*sample,blitz_dropbacks=40,blitz_disruptions=20),dict(matchups=[dict(gap=gap)],recommend=False),N(depth_mix=(short,.25,.15),play_action_rate=pa,screen_boost=screens),fit)
 def test_frequency_alone_and_legacy_unknown_do_not_trigger(self):
  self.assertIsNone(self.call(rate=.15));self.assertIsNone(self.call(sample=0))
 def test_strong_line_can_keep_attacking(self):
  self.assertIsNone(self.call(gap=-5))
 def test_real_threat_receives_targeted_changes(self):
  self.assertIn('depth_mix',self.call()['changes'])
  self.assertIn('screen_boost',self.call()['changes'])
  self.assertNotIn('screen_boost',self.call(fit=False)['changes'])
 def test_already_addressed_no_repeat(self):
  self.assertIsNone(self.call(short=.72,pa=.10,screens=.04))
 def test_limited_evidence_not_firm_advice(self):
  self.assertIsNone(self.call(sample=20))
 def test_tape_counts_unique_dropbacks_and_ignores_nullified_plays(self):
  from gameplan_week import record_game
  L=N(year=2030,tendencies={})
  plays=[dict(type='sack',is_pass=True,pressured=True,blitz=True),
         dict(type='complete',is_pass=True,pressured=False,blitz=True),
         dict(type='complete',is_pass=True,pressured=True,nullified=True),
         dict(type='run',is_pass=False,pressured=True)]
  record_game(L,'GB','DAL',{'drives':[('home',N(log=plays,result='Punt'))]})
  c=L.tendencies[2030]['DAL']
  self.assertEqual(c['pressure_dropbacks'],2)
  self.assertEqual(c['pressured_dropbacks'],1)
  self.assertEqual(c['blitz_disruptions'],1)
