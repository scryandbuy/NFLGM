import unittest
from unittest.mock import patch
import numpy as np
import game as G, plays as P, schemes as S, events as E, rosters as R

class ModifierOrderTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.rosters=R.load_league()
 def drive(self,outcomes,off_state=None,field=None,audible=None):
  off=self.rosters['GB'];deff=self.rosters['DEN']; plays=iter(outcomes)
  co=lambda *a,**k:dict(is_pass=True,personnel='11',concept='levels',depth='short')
  cd=lambda *a,**k:dict(personnel='nickel',front_family='3-4',box=6)
  with patch.object(E,'penalty_check',return_value=None),patch.object(E,'fumble_check',return_value=None),patch.object(G,'field_units',side_effect=field or (lambda ros,*a,**k:(ros,{}))),patch.object(G,'end_of_half_plan',return_value=None),patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',points=1,made=True)),patch('playcall.audible',side_effect=audible or (lambda oc,*a,**k:(oc,None))):
   return G.run_drive(off,deff,50,3000,1,0,np.random.default_rng(2),lambda *a:dict(next(plays)),co,cd,P.rate,off_state=off_state)
 def test_scramble_reads_on_field_qb_not_roster_starter(self):
  qb=dict(self.rosters['GB']['qb'],pid='backup',speed_rating=31)
  def field(ros,*a,**k):return (dict(ros,qb=qb) if ros is self.rosters['GB'] else ros),{}
  with patch.object(E,'scramble_chance',return_value=1) as chance,patch.object(E,'resolve_scramble',return_value=dict(type='scramble',yards=50,touchdown=True)) as scramble:
   self.drive([dict(type='sack',yards=-6)],field=field)
  self.assertIs(chance.call_args.args[0],qb);self.assertIs(scramble.call_args.args[0],qb)
 def test_box_plan_applied_once_before_audible(self):
  seen=[]
  def plan(call,*a):call['box']=8
  def audible(oc,dc,*a,**k):seen.append(dc['box']);return oc,None
  with patch.object(G,'apply_defensive_plan',side_effect=plan) as apply:
   self.drive([dict(type='complete',yards=50,air=50,yac=0,target='WR')],audible=audible)
  self.assertEqual(seen,[8]);self.assertEqual(apply.call_count,1)
 def test_script_does_not_rescale_finished_play_or_sack(self):
  state=G.TeamState(self.rosters['GB'])
  with patch.object(state.script,'performance_modifier',return_value=1.06),patch.object(E,'scramble_chance',return_value=0):
   dr=self.drive([dict(type='sack',yards=-6),dict(type='complete',yards=20,air=12,yac=8,target='WR'),dict(type='complete',yards=50,air=50,yac=0,target='WR')],off_state=state)
  plays=[p for p in dr.log if p.get('type') in ('sack','complete')]
  self.assertEqual(plays[0]['yards'],-6)
  self.assertEqual(plays[1]['yards'],plays[1]['air']+plays[1]['yac'])
 def units(self):
  rng=np.random.default_rng(5)
  o,_=G.field_units(self.rosters['GB'],None,rng,True,'11');d,_=G.field_units(self.rosters['DEN'],None,rng,False,'nickel',front_family='3-4');return o,d
 def test_hot_route_can_still_be_sacked_after_relief(self):
  o,d=self.units();original=S.protection_math;trace=[]
  with patch.object(S,'protection_math',side_effect=lambda *a,**k:dict(original(*a,**k),hot=True)),patch.object(P,'resolve_protection',return_value=dict(time=.2,pressure=.9,sack=True,beaten_by=d['dl'][0]['pid'],beaten=o['ol'][0]['pid'],pb_reps=[],pr_reps=[])),patch.object(P,'PASS_TRACE',trace):
   outcomes=[P._pass_play(o,d,dict(is_pass=True,personnel='11',concept='levels',depth='medium',down=1,ydstogo=10),dict(rushers=4,coverage='cover_3',shell='cover_3',box=6,front_family='3-4',personnel='nickel'),50,np.random.default_rng(seed)) for seed in range(60)]
  rolls=sum(t['sack'] for t in trace if t['path']=='clock');self.assertGreater(rolls,0);self.assertLess(rolls,60)
  self.assertEqual(sum(p['type']=='sack' for p in outcomes),rolls)
 def test_run_script_never_makes_same_negative_run_worse(self):
  o,d=self.units();call=dict(scheme='inside_zone');dc=dict(box=7,front='3-4 one',front_family='3-4',personnel='nickel')
  count=0;improved=0
  for seed in range(100):
   a=P._run_play(o,d,dict(call,execution_mod=.94),dc,50,np.random.default_rng(seed));b=P._run_play(o,d,dict(call,execution_mod=1.06),dc,50,np.random.default_rng(seed))
   if a['yards']<0:
    count+=1;self.assertGreaterEqual(b['yards'],a['yards']);improved+=b['yards']>a['yards']
  self.assertGreater(count,0)
  self.assertGreater(improved,0)
 def test_script_reaches_yac_before_outcome_and_preserves_air_accounting(self):
  o,d=self.units();dc=dict(rushers=4,coverage='cover_3',shell='cover_3',box=6,front_family='3-4',personnel='nickel')
  oc=dict(is_pass=True,personnel='11',concept='levels',depth='short',down=1,ydstogo=10)
  original=P.resolve_yards_after
  checked=False
  for seed in range(40):
   with patch.object(P,'resolve_yards_after',wraps=original) as before:
    a=P._pass_play(o,d,dict(oc,execution_mod=1),dc,90,np.random.default_rng(seed))
   with patch.object(P,'resolve_yards_after',wraps=original) as after:
    b=P._pass_play(o,d,dict(oc,execution_mod=1.06),dc,90,np.random.default_rng(seed))
   if before.called and after.called:
    self.assertAlmostEqual(after.call_args.kwargs['gain_scale'],before.call_args.kwargs['gain_scale']*1.06)
    self.assertEqual(a['air'],b['air'])
    self.assertAlmostEqual(b['yards'],b['air']+b['yac'],delta=.11)
    checked=True;break
  self.assertTrue(checked)

if __name__=='__main__':unittest.main()
