import unittest
from unittest.mock import patch
from test_draft_planning import fixture,set_grade
import trades as TR
import roster_needs as RN

class TradeNeedsLabelsTests(unittest.TestCase):
 def test_fullback_need_does_not_become_halfback(self):
  L,t=fixture();t.gm.off_personnel='21'
  for p in t.active():
   if p.pos=='HB':set_grade(p,87)
   if p.pos=='FB':set_grade(p,60)
  needs=TR.roster_need_labels(t)
  self.assertIn('FB',needs);self.assertNotIn('HB',needs)
 def test_receiving_depth_slots_matter(self):
  L,t=fixture();t.gm.off_personnel='11'
  for i,p in enumerate(t.by_pos('WR')):set_grade(p,95 if i==0 else 60)
  self.assertIn('WR',TR.roster_need_labels(t))
 def test_short_injury_is_not_a_new_vacancy(self):
  L,t=fixture();t.gm.off_personnel='11'
  for p in t.by_pos('QB'):set_grade(p,55)
  p=t.by_pos('QB')[0];set_grade(p,92);p.out_until=10
  self.assertNotIn('QB',TR.roster_need_labels(t,9))
  p.out_until=16
  self.assertIn('QB',TR.roster_need_labels(t,9))
 def test_generic_surplus_excludes_multi_starters(self):
  L,t=fixture();L.week=5;L.set_phase('regular');t.gm.off_personnel='11'
  for i,p in enumerate(t.by_pos('WR')):set_grade(p,95 if i==0 else 80)
  def asset(L,t,p,*a,**kw):return dict(pid=p.pid,trade_value=10,grp=p.pos)
  with patch.object(TR,'player_asset',side_effect=asset),patch.object(TR,'seller_veterans',return_value=[]),patch.object(TR,'_young_core',return_value=False):
   surplus,_=TR.surplus_and_needs(L,t,{},None,n=100)
  report=RN.assess(t);shares={}
  for r in report['package_assignments']:
   if r['player']:shares[r['player'].pid]=shares.get(r['player'].pid,0)+r['weight']
  self.assertTrue(all(shares.get(a['pid'],0)<.15 for a in surplus))

if __name__=='__main__':unittest.main()
