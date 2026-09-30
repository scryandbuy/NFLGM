import unittest, copy, json
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import health as H
import practice as P
from league import Player


def setup(seed=1):
    positions=['QB','HB','FB','WR','TE','LT','LG','C','RG','RT','LEDG','REDG','DT','MIKE','WILL','SAM','CB','FS','SS','K','P','LS']
    players=[Player(str(i),f'Player {i}',positions[i%22],24,{'injury_rating':80,'tough_rating':80},team='A') for i in range(66)]
    depth={pos:[p for p in players[:53] if p.pos==pos] for pos in positions}
    team=NS(roster=players[:53],practice_squad=players[53:],depth=depth)
    league=NS(year=2026,teams={'A':team})
    state=NS(cond=H.Condition(),jaded={},last_snaps={},snaps={},out=set())
    runner=NS(states={'A':state},desks={},rng=np.random.default_rng(seed))
    return league,runner,players


def plan(intensity):
    return {'units':{u:{'intensity':intensity,'reps':'balanced'} for u in P.UNITS}}


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.patches=[patch('staff.xp_mult',return_value=1.),patch('personality.xp_mult',return_value=1.)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
    def test_preview_pure_idempotent_reload_and_transfer(self):
        l,r,ps=setup(); before=copy.deepcopy(r.rng.bit_generator.state)
        P.preview(l,r,'A',1); P.preview(l,None,'A',1)
        self.assertFalse(hasattr(l,'practice_state')); self.assertEqual(before,r.rng.bit_generator.state)
        first=P.resolve(l,r,'A',1); paid=sum(p.xp for p in ps)
        l.practice_state=json.loads(json.dumps(l.practice_state))
        rng=copy.deepcopy(r.rng.bit_generator.state)
        self.assertEqual(first,P.resolve(l,r,'A',1));self.assertEqual(rng,r.rng.bit_generator.state)
        moved=ps[0];l.teams['B']=NS(roster=[moved],practice_squad=[],depth={'QB':[moved]})
        r.states['B']=NS(cond=H.Condition(),jaded={},last_snaps={},snaps={},out=set())
        P.resolve(l,r,'B',1)
        self.assertEqual(paid,sum(p.xp for p in ps))
        self.assertEqual(r.states['A'].cond.get(moved.pid),r.states['B'].cond.get(moved.pid))
    def test_rest_rehab_legacy_and_bye(self):
        l,r,ps=setup();q=plan('hard');q['individual']={p.pid:'rest' for p in ps}
        r.states['A'].cond.cond[ps[0].pid]=70
        v=P.resolve(l,r,'A',1,q,recovery_done=True)
        self.assertEqual(v['totals']['xp'],0);self.assertFalse(v['injuries']);self.assertEqual(r.states['A'].cond.get(ps[0].pid),70)
        l,r,ps=setup();r.desks['A']=NS(playing_hurt={ps[0].pid:{}})
        v=P.preview(l,r,'A',1,plan('hard'))
        row=v['players'][0];self.assertEqual(row['risk'],0);self.assertEqual(row['xp'],0)
        r.states['A'].jaded[ps[1].pid]=.4;r.states['A'].last_snaps={ps[1].pid:60}
        P.resolve(l,r,'A',1,plan('standard'),bye=True)
        self.assertAlmostEqual(r.states['A'].jaded[ps[1].pid],.28);self.assertFalse(r.states['A'].last_snaps)
    def test_caps_focus_and_ledger_pruning(self):
        l,r,ps=setup();q=plan('hard');q['focus']=[p.pid for p in ps[:10]]
        l.practice_state={'auto':{'A':True},'completed':{'2023:1':{}},'participants':{'2023:1':{}}}
        v=P.resolve(l,r,'A',1,q)
        self.assertLessEqual(sum(p.xp for p in ps),len(ps)*12*1.2+.01)
        self.assertLessEqual(max(p.xp for p in ps),24);self.assertEqual(len(v['plan']['focus']),3)
        self.assertNotIn('2023:1',l.practice_state['completed']);self.assertTrue(l.practice_state['auto']['A'])
    def test_new_season_ignores_prior_health_and_snaps(self):
        l,r,ps=setup();p=ps[0]
        l.practice_state={'players':{p.pid:dict(condition=45,jaded=.8,hard_streak=12,last_key='2026:22',last_team='A')}}
        l.year=2027
        self.assertEqual(P._health(l,r,'A',p),(100.,0.,{}))
        stale=P.preview(l,r,'A',1,plan('standard'))
        r.states['A'].last_snaps={p.pid:80}
        self.assertEqual(stale,P.preview(l,r,'A',1,plan('standard')))
    def test_season_workload_comparison(self):
        results={}
        for mode in ('recovery','standard','hard','adaptive'):
            samples=[]
            for seed in range(20):
                l,r,ps=setup(seed);injuries=0;xp=0;conditions=[]
                for week in range(1,19):
                    st=r.states['A']
                    for i,p in enumerate(ps):
                        if p.out_until is not None and p.out_until<=week:p.out_until=None
                        snaps=60 if i<22 else 8
                        st.last_snaps[p.pid]=snaps
                        st.cond.cond[p.pid]=max(45,st.cond.get(p.pid)-(28 if i<22 else 5))
                        st.jaded[p.pid]=H.update_jadedness(st.jaded.get(p.pid,0),snaps,80)
                    v=P.resolve(l,r,'A',week,None if mode=='adaptive' else plan(mode),bye=week==10)
                    injuries+=len(v['injuries']);xp+=v['totals']['xp']
                    if week>=15:conditions.append(sum(st.cond.get(p.pid) for p in ps[:22])/22)
                samples.append((xp,injuries,sum(conditions)/len(conditions),sum(p.xp for p in ps[:22])/22,sum(p.xp for p in ps[22:])/44))
            results[mode]=tuple(float(np.mean([v[i] for v in samples])) for i in range(5))
        print('Season workload means (XP, injuries, late starter condition, starter XP, reserve XP):',results)
        self.assertEqual(results['recovery'][0],0)
        self.assertLess(results['standard'][1],2)
        self.assertLess(results['hard'][1],5)
        self.assertGreater(results['standard'][2],85)
        self.assertGreater(results['adaptive'][2],results['hard'][2])
        self.assertGreater(results['recovery'][2],results['standard'][2])
        self.assertLess(results['hard'][0],results['standard'][0]*1.21)
        self.assertLess(results['standard'][3],17*(75+3*60)*.05)
        self.assertGreater(results['standard'][4],results['standard'][3]*2)

if __name__=='__main__':unittest.main()
