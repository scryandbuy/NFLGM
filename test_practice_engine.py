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
    team=NS(abbr='A',roster=players[:53],practice_squad=players[53:],depth=depth)
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
        moved=ps[0];l.teams['B']=NS(abbr='B',roster=[moved],practice_squad=[],depth={'QB':[moved]})
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
        self.assertLessEqual(sum(p.xp for p in ps),len(ps)*P.WEEKLY_XP_CEILINGS[0])
        self.assertLessEqual(max(p.xp for p in ps),1000);self.assertEqual(len(v['plan']['focus']),3)
        self.assertNotIn('2023:1',l.practice_state['completed']);self.assertTrue(l.practice_state['auto']['A'])
    def test_new_season_ignores_prior_health_and_snaps(self):
        l,r,ps=setup();p=ps[0]
        l.practice_state={'players':{p.pid:dict(condition=45,jaded=.8,hard_streak=12,last_key='2026:22',last_team='A')}}
        l.year=2027
        self.assertEqual(P._health(l,r,'A',p),(100.,0.,{}))
        stale=P.preview(l,r,'A',1,plan('standard'))
        r.states['A'].last_snaps={p.pid:80}
        self.assertEqual(stale,P.preview(l,r,'A',1,plan('standard')))

    def test_coach_uses_recovered_condition_and_individual_protection(self):
        l,r,ps=setup();st=r.states['A']
        for p in ps:
            st.cond.cond[p.pid]=70
            st.jaded[p.pid]=.04
        q=P.recommend_plan(l,r,'A',4)
        self.assertEqual({v['intensity'] for v in q['units'].values()},{'standard'})
        # One fatigued QB gets restricted work, not a unit-wide light week.
        st.jaded[ps[0].pid]=.5
        q=P.recommend_plan(l,r,'A',4)
        self.assertEqual(q['individual'][ps[0].pid],'limited')
        self.assertEqual(q['units']['offense']['intensity'],'standard')
        for p in ps:
            if P._unit(p)=='offense':st.jaded[p.pid]=.09
        self.assertEqual(P.recommend_plan(l,r,'A',4)['units']['offense']['intensity'],'light')
        for p in ps:
            if P._unit(p)=='offense':st.jaded[p.pid]=.07
        self.assertEqual(P.recommend_plan(l,r,'A',19)['units']['offense']['intensity'],'light')

    def test_coach_schedule_development_and_focus(self):
        l,r,ps=setup()
        l.schedule=[(1,'A','B',None,None),(3,'A','B',None,None)]
        # A fresh young reserve-heavy unit can train harder after a bye.
        q=P.recommend_plan(l,r,'A',3)
        self.assertEqual(q['units']['offense']['intensity'],'hard')
        self.assertEqual(q['units']['offense']['reps'],'development')
        self.assertEqual(len(q['focus']),3)

        l.practice_state={'players':{p.pid:dict(last_key='2026:2',hard_streak=1) for p in ps}}
        self.assertEqual(P.recommend_plan(l,r,'A',3)['units']['offense']['intensity'],'standard')
        l.practice_state={}
        for p in ps:p.age=32
        self.assertEqual(P.recommend_plan(l,r,'A',3)['units']['offense']['intensity'],'standard')
        self.assertEqual({v['intensity'] for v in P.recommend_plan(l,r,'A',3,bye=True)['units'].values()},{'light'})
        for p in ps:p.age=24
        self.assertNotIn('hard',{v['intensity'] for v in P.recommend_plan(l,r,'A',19)['units'].values()})

    def test_focus_includes_young_starters_and_prefers_development(self):
        l,r,ps=setup()
        for p in ps:
            p.age=31;p.entry_year=2017
        for p,dev in zip(ps[:4],('xfactor','superstar','star','normal')):
            p.age=22;p.entry_year=2026;p.dev=dev
        q=P.recommend_plan(l,r,'A',1)
        self.assertEqual(q['focus'],[p.pid for p in ps[:3]])
        ps[0].out_until=4
        q=P.recommend_plan(l,r,'A',1)
        self.assertNotIn(ps[0].pid,q['focus'])
        self.assertEqual(len(q['focus']),3)

    def test_bye_develops_healthy_players_and_rests_tired_or_injured_players(self):
        l,r,ps=setup();st=r.states['A']
        l.user_team='A'
        tired,heavy,injured=ps[:3]
        st.jaded[tired.pid]=.20;st.cond.cond[tired.pid]=72
        st.last_snaps[heavy.pid]=78
        injured.out_until=8
        q=P.recommend_plan(l,r,'A',6,bye=True)
        self.assertEqual({v['intensity'] for v in q['units'].values()},{'light'})
        self.assertEqual({v['reps'] for v in q['units'].values()},{'development'})
        for p in (tired,heavy,injured):
            self.assertEqual(q['individual'][p.pid],'rest')
            self.assertNotIn(p.pid,q['focus'])
        preview=P.preview(l,r,'A',6,bye=True)
        rows={x['pid']:x for x in preview['players']}
        for p in (tired,heavy,injured):
            self.assertEqual((rows[p.pid]['xp'],rows[p.pid]['risk']),(0,0))
        self.assertLess(rows[tired.pid]['jaded'],.20)
        self.assertGreater(rows[tired.pid]['condition'],72)
        self.assertTrue(all(rows[p.pid]['xp']>0 for p in ps[3:]))
        self.assertTrue(all(rows[p.pid]['xp']>0 for p in l.teams['A'].practice_squad))
        result=P.resolve(l,r,'A',6,bye=True)
        self.assertGreater(result['totals']['xp'],0)
        self.assertAlmostEqual(sum(p.xp for p in ps),result['totals']['xp'],places=2)
        self.assertEqual(preview['totals']['xp'],result['totals']['xp'])
        earned=sum(p.xp for p in ps)
        self.assertEqual(P.resolve(l,r,'A',6,bye=True),result)
        self.assertEqual(sum(p.xp for p in ps),earned)

    def test_bye_recovery_remains_available_and_depleted_units_rest(self):
        l,r,ps=setup()
        explicit=P.preview(l,r,'A',6,plan('recovery'),bye=True)
        self.assertEqual(explicit['totals']['xp'],0)
        self.assertEqual(explicit['totals']['expected_injuries'],0)
        for p in ps:
            if P._unit(p)=='offense':r.states['A'].jaded[p.pid]=.2
        v=P.preview(l,r,'A',6,bye=True)
        self.assertEqual(v['plan']['units']['offense']['intensity'],'recovery')
        self.assertEqual(v['plan']['units']['defense']['intensity'],'light')
        self.assertTrue(all(row['xp']==0 for row in v['players'] if row['unit']=='offense'))
        self.assertGreater(v['totals']['xp'],0)

    def test_manual_workloads_have_costs_and_rest_is_protected(self):
        l,r,ps=setup();st=r.states['A']
        for p in ps:st.cond.cond[p.pid]=70;st.jaded[p.pid]=.2
        forecasts={mode:P.preview(l,r,'A',4,plan(mode)) for mode in ('recovery','light','standard','hard')}
        for mode in ('recovery','light','standard'):
            nxt={'recovery':'light','light':'standard','standard':'hard'}[mode]
            self.assertLess(forecasts[mode]['totals']['xp'],forecasts[nxt]['totals']['xp'])
            self.assertLess(forecasts[mode]['totals']['expected_injuries'],forecasts[nxt]['totals']['expected_injuries'])
            self.assertGreater(forecasts[mode]['players'][0]['condition'],forecasts[nxt]['players'][0]['condition'])
        q=plan('hard');q['individual']={ps[0].pid:'rest',ps[1].pid:'limited'}
        rows={x['pid']:x for x in P.preview(l,r,'A',4,q)['players']}
        self.assertEqual(rows[ps[0].pid]['xp'],0);self.assertEqual(rows[ps[0].pid]['risk'],0)
        self.assertLess(rows[ps[1].pid]['risk'],forecasts['hard']['players'][1]['risk'])
        self.assertLess(rows[ps[1].pid]['jaded'],forecasts['hard']['players'][1]['jaded'])
        # A light week slows fatigue growth, but no longer erases weeks of game load.
        self.assertGreater(forecasts['light']['players'][0]['jaded'],.19)

    def test_focus_increases_individual_award_and_does_not_override_rest(self):
        l,r,ps=setup();q=plan('standard')
        baseline=P.preview(l,r,'A',4,q)
        target=ps[0];q['focus']=[target.pid]
        focused=P.preview(l,r,'A',4,q)
        self.assertGreater(focused['players'][0]['xp'],baseline['players'][0]['xp'])
        self.assertEqual(focused['players'][1]['xp'],baseline['players'][1]['xp'])
        self.assertLessEqual(max(x['xp'] for x in focused['players']),1000)
        q['individual']={target.pid:'rest'}
        row=P.preview(l,r,'A',4,q)['players'][0]
        self.assertEqual((row['xp'],row['risk']),(0,0))
    def test_season_workload_comparison(self):
        results={}
        for mode in ('recovery','light','standard','hard','adaptive'):
            samples=[]
            for seed in range(20):
                l,r,ps=setup(seed);injuries=0;xp=0;conditions=[];fatigue=[]
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
                    if week>=15:
                        conditions.append(sum(st.cond.get(p.pid) for p in ps[:22])/22)
                        fatigue.append(sum(st.jaded.get(p.pid,0) for p in ps[:22])/22)
                samples.append((xp,injuries,sum(conditions)/len(conditions),sum(p.xp for p in ps[:22])/22,sum(p.xp for p in ps[22:])/44,sum(fatigue)/len(fatigue)))
            results[mode]=tuple(float(np.mean([v[i] for v in samples])) for i in range(6))
        print('Season workload means (XP, injuries, late starter condition, starter XP, reserve XP, late fatigue):',results)
        self.assertEqual(results['recovery'][0],0)
        self.assertLess(results['standard'][1],2)
        self.assertLess(results['hard'][1],5)
        self.assertGreater(results['standard'][2],85)
        self.assertGreater(results['adaptive'][2],results['hard'][2])
        self.assertGreater(results['recovery'][2],results['standard'][2])
        self.assertGreater(results['light'][2],results['standard'][2])
        self.assertGreater(results['light'][5],0)
        self.assertGreater(results['standard'][5],results['light'][5])
        self.assertGreater(results['hard'][5],results['standard'][5])
        self.assertGreater(results['adaptive'][5],.02)
        self.assertLess(results['adaptive'][5],.35)
        # New individual ceiling applies even across a whole practice season.
        self.assertLess(results['adaptive'][0],66*18*P.WEEKLY_XP_CEILINGS[0])
        self.assertLess(results['hard'][0],results['standard'][0]*1.21)
        self.assertLess(results['standard'][3],18*P.WEEKLY_XP_CEILINGS[0])

if __name__=='__main__':unittest.main()
