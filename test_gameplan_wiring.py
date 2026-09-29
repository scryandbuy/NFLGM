import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from session import Session
import views_gameplan as VG, gameplan as GP, gameplan_week as GW
import game,schemes,coverage

class GameplanWiringTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.session=Session.new('GB',seed=23)
 def setUp(self):
  self.s=self.session; self.s.stop=('cutdown',); self.s.played=False; self.s.runner=None
  self.s.L.user_week_plan=None
 def test_save_reload(self):
  self.s.plan_act('set_lean',key='pass_bias',value=.08)
  self.s.plan_take_all()
  saved=Session.load(self.s.save())
  self.assertEqual(json.loads(json.dumps(self.s.L.user_week_plan)),saved.L.user_week_plan)
 def test_camp_accept_all_and_undo_manual(self):
  v=self.s.plan_view('this_week'); self.assertTrue(v['suggestions'])
  self.assertTrue(self.s.plan_take_all()['ok'])
  target=v['their_wrs'][1]['pid']; self.s.plan_act('set_decision',key='bracket',value=target)
  self.s.plan_act('untake',i=0)
  self.assertEqual(target,self.s.L.user_week_plan['changes']['bracket'])
 def test_overlapping_suggestions(self):
  suggestions=[dict(text='A',changes={'pass_bias':.04}),dict(text='B',changes={'pass_bias':.03})]
  with patch.object(GW,'opponent_report',return_value={'suggestions':suggestions}):
   self.s.plan_act('take',i=0); self.s.plan_act('take',i=1); self.s.plan_act('untake',i=0)
  self.assertAlmostEqual(.03,self.s.L.user_week_plan['changes']['pass_bias'])
 def test_manual_lean_survives_undo(self):
  with patch.object(GW,'opponent_report',return_value={'suggestions':[dict(text='A',changes={'pass_bias':.04})]}):
   self.s.plan_act('take',i=0); self.s.plan_act('set_lean',key='pass_bias',value=.07); before=self.s.L.user_week_plan['changes']['pass_bias']; self.s.plan_act('untake',i=0)
  self.assertEqual(before,self.s.L.user_week_plan['changes']['pass_bias'])
 def test_explicit_none_and_reset(self):
  self.s.plan_act('set_decision',key='bracket',value=''); self.s.plan_act('set_decision',key='travel',value=False)
  base=GP.Gameplan(); st=SimpleNamespace(plan=base.copy(),base_plan=base)
  GW.user_plan(self.s.L,st,1)
  self.assertTrue(st.plan.bracket_locked); self.assertTrue(st.plan.travel_locked); self.assertIsNone(st.plan.bracket)
  self.s.plan_act('reset'); self.assertEqual({},self.s.L.user_week_plan['changes'])
 def test_invalid_depth_is_rejected(self):
  for values in [(0,0,0),(-1,50,51),(float('nan'),1,2),(float('inf'),1,2)]:
   self.assertFalse(self.s.plan_act('set_depth',short=values[0],medium=values[1],deep=values[2])['ok'])
  self.assertIsNone(self.s.L.user_week_plan)
 def test_playoff_and_bye(self):
  old=list(self.s.L.schedule)
  try:
   self.s.stop=('playoffs',0); self.s.L.schedule.append((19,'GB','MIN',None,None))
   self.assertEqual(19,self.s.plan_view('this_week')['week']); self.assertTrue(self.s.plan_take_all()['ok'])
   self.s.stop=('playoffs',1); self.assertTrue(self.s.plan_view('this_week')['off']); self.assertFalse(self.s.plan_take_all()['ok'])
  finally:self.s.L.schedule=old
 def test_protection(self):
  for key,expected in [('half_slide','half_slide'),('full_slide','six_slide'),('six','six_bob'),('empty','five')]:
   self.assertEqual(expected,schemes.choose_protection('11',4,'medium',np.random.default_rng(1),preference=key))
  self.assertEqual('five',schemes.choose_protection('00',4,'deep',np.random.default_rng(1),preference='six'))
 def test_tempo_and_clock_overrides(self):
  self.assertLess(game.play_seconds('run',tempo=.65),game.play_seconds('run',tempo=.35))
  for flags in [dict(hurry=True),dict(timeout=True),dict(clock_stopped=True)]:
   self.assertEqual(game.play_seconds('run',tempo=.2,**flags),game.play_seconds('run',tempo=.8,**flags))
 def test_named_shadow_works_in_slot(self):
  wrs=[dict(pid='best',pos='WR'),dict(pid='chosen',pos='WR')]
  cbs=[dict(pid='cb1',pos='CB'),dict(pid='cb2',pos='CB'),dict(pid='cb3',pos='CB')]
  aligned=[dict(player=wrs[0],spot='X',side='L'),dict(player=wrs[1],spot='slot',side='R')]
  pairs,_=coverage.assign_coverage(aligned,dict(db=cbs,lb=[]),dict(under='man',travel_target='chosen'),np.random.default_rng(1),lambda p,w:90 if p.get('pid')=='best' else 80,travel=True,sides={'L':cbs[0],'R':cbs[1]})
  chosen=next(p for p in pairs if p['receiver']['pid']=='chosen')
  self.assertEqual('cb1',chosen['defender']['pid']); self.assertTrue(chosen['travelled'])
  self.assertNotEqual(pairs[0]['defender']['pid'],chosen['defender']['pid'])

if __name__=='__main__': unittest.main()
