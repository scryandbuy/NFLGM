import copy
import unittest
from unittest.mock import patch
import numpy as np
import plays as P
import game as G
import defensive_rush as D
import rush_matchup as M
import blocking_evaluation as B
import gameplan_week as W
from test_defensive_rush import unit, call
from test_protection_pressure import blocker
from matchups import PASS_RUSH


class RushBalanceTests(unittest.TestCase):
    def setUp(self):
        self.front = D.select_rush(unit('4-3', 'nickel'), call('4-3', 'nickel'))
        self.line = [blocker(pos, 78) for pos in ('LT', 'LG', 'C', 'RG', 'RT')]

    def test_help_can_fail_and_quality_matters(self):
        weak, strong = blocker('HB', 40), blocker('HB', 90)
        self.assertEqual(M.help_effect(strong, .9, .95, 'right_edge', .999), 0)
        self.assertGreater(M.help_effect(strong, .9, .95, 'right_edge', 0), 0)
        draws=np.linspace(0, 1, 1000, endpoint=False)
        self.assertGreater(sum(M.help_effect(strong,.9,.95,'right_edge',u) for u in draws),
                           sum(M.help_effect(weak,.4,.95,'right_edge',u) for u in draws))

    def test_another_rusher_and_inside_emergency_take_priority(self):
        aa=self.front['assignments']; men=self.line+[blocker('HB')]
        pairs=D.protection_pairs(men, aa)
        threats=[.25 if a['alignment']=='left_edge' else .15 if a['alignment']=='right_edge' else 0 for a in aa]
        def assigned(th):
            helpers=D.protection_helpers(men,aa,pairs,th,'six_bob')
            return next(a['alignment'] for a,hs in zip(aa,helpers) if any(h['pid']=='HB' for h in hs))
        self.assertEqual(assigned(threats),'left_edge')
        threats=[.6 if a['alignment']=='left_interior' else t for a,t in zip(aa,threats)]
        self.assertEqual(assigned(threats),'left_interior')
        missing=list(pairs);missing[0]=None
        help_=D.protection_helpers(men,aa,missing,threats)
        # The back/tackle must address the reachable free edge first. The
        # center cannot get there and can still assist an interior block.
        self.assertFalse(any(h['pid'] in ('HB','RT') for hs in help_ for h in hs))
        self.assertTrue(all(a['alignment'] in D.INTERIOR for a,hs in zip(aa,help_) if hs))

    def test_elite_upgrade_survives_extra_help_and_improves_front(self):
        rows=[]
        for rating in (80,95):
            front=copy.deepcopy(self.front)
            target=next(a['player'] for a in front['assignments'] if a['alignment']=='right_edge')
            keys=set().union(*(set(v) for v in PASS_RUSH['rusher'].values()))
            target.update({key:rating for key in keys})
            # select_rush binds assignments and rusher objects to the same men.
            samples=[P.resolve_protection(self.line+[blocker('HB',65)],front['rushers'],
                        np.random.default_rng(seed), assignments=front['assignments'],
                        protection='six_bob',_defer_award=True) for seed in range(1600)]
            rows.append((sum(dict(r['pr_reps'])[target['pid']] for r in samples),
                         sum(r['sack'] for r in samples)))
        self.assertGreater(rows[1][0],rows[0][0])
        self.assertGreater(rows[1][1],rows[0][1])

    def test_finishing_uses_rusher_attributes_without_forcing_sacks(self):
        low=dict(pursuit_rating=45,tackle_rating=45,speed_rating=45)
        high=dict(pursuit_rating=95,tackle_rating=95,speed_rating=95)
        self.assertLess(M.finish_scale(low),1)
        self.assertGreater(M.finish_scale(high),1)
        front=copy.deepcopy(self.front)
        for p in front['rushers']:p.update(high)
        r=P.resolve_protection(self.line,front['rushers'],np.random.default_rng(5),
                               assignments=front['assignments'],_defer_award=True)
        self.assertTrue(all(x>1 for x in r['pb_model']['finish_scales']))

    def test_chip_attempt_can_miss_contact(self):
        class Fixed:
            def __init__(self,u):
                self.u=u
                self.ties=np.random.default_rng(44)
            def random(self):return self.u
            def lognormal(self,*args):return 1.
            # Fix chip contact, while allowing the production race to break ties.
            def integers(self,*args,**kwargs):return self.ties.integers(*args,**kwargs)
        rush=self.front['rushers'];aa=self.front['assignments']
        idx=next(i for i,a in enumerate(aa) if a['alignment']=='right_edge')
        base=P.resolve_protection(self.line,rush,Fixed(.999),assignments=aa,_defer_award=True)
        missed=P.resolve_protection(self.line,rush,Fixed(.999),assignments=aa,
                                    chip=(blocker('TE',90),idx),_defer_award=True)
        self.assertEqual(base['pb_model']['means'],missed['pb_model']['means'])
        hit=P.resolve_protection(self.line,rush,Fixed(0),assignments=aa,
                                 chip=(blocker('TE',90),idx),_defer_award=True)
        clean=P.resolve_protection(self.line,rush,Fixed(0),assignments=aa,_defer_award=True)
        self.assertGreater(sum(hit['pb_model']['means']),sum(clean['pb_model']['means']))

    def test_blocking_evidence_matches_new_finish_and_pressure_rules(self):
        model=dict(means=[3.4,3.6],free=[],evaluations=[('LT',0,3.5,True)],
                   qb_scale=1.,finish_scales=[1.3,.8])
        row=B.protection_evidence(model,2.5,time_scale=1.05,hold=.08,
                                  sack_k=P.SACK_K,pressure_window=2.8)[0]
        draws=np.random.default_rng(640).lognormal(0,.26,(300000,2))*[3.5,3.6]
        winner=draws.argmin(axis=1);time=np.round(draws.min(axis=1),2)*1.05
        sack=np.clip(P.SACK_K*np.exp(-2.4*(time-.08))*np.array([1.3,.8])[winner],0,.85)
        pressure=np.where(time<=2.8,1.,sack)
        self.assertAlmostEqual(row[1],float((draws[:,0]>=2.5).mean()),delta=.002)
        self.assertAlmostEqual(row[2],float(((draws[:,0]<2.5)*pressure).mean()),delta=.002)
        self.assertAlmostEqual(row[3],float(((winner==0)*sack).mean()),delta=.002)

    def test_coaches_disagree_and_evidence_can_change_their_minds(self):
        rec=dict(value='six'); clean=dict(dropbacks=100,sacks=2,matchups=[dict(gap=10)])
        bad=dict(clean,sacks=15)
        def choices(coach,read):
            return [W.cpu_protection_choice(coach,rec,read,np.random.default_rng(i),.8) for i in range(500)]
        stubborn=dict(adjust_willingness=.1,adjust_skill=.5)
        adaptive=dict(adjust_willingness=.9,adjust_skill=.8)
        low=choices(stubborn,clean);high=choices(adaptive,bad)
        self.assertGreater(high.count(('six',True)),low.count(('six',True)))
        self.assertGreater(low.count(('empty',True)),high.count(('empty',True)))
        self.assertGreater(choices(stubborn,bad).count(('six',True)),low.count(('six',True)))
        self.assertIn(('half_slide',False),low)

    def test_quick_throw_and_late_sack_have_distinct_pressure_evidence(self):
        early=dict(type='incomplete',depth='short',rush_arrivals=[('edge',2.6)],pr_reps=[('edge',True)])
        late=dict(type='sack',depth='deep',by='edge',rush_arrivals=[('edge',3.8)],pr_reps=[('edge',False)])
        for raw,expected in ((early,0),(late,1)):
            with patch.object(P,'_resolve_pass_play',return_value=copy.deepcopy(raw)):
                out=P._pass_play({}, {}, {}, {},50,np.random.default_rng(1))
            book=G.StatBook();book.record(out,dict(qb=dict(pid='qb')),{},np.random.default_rng(1))
            self.assertEqual(book.p['edge']['pressures'],expected)
            self.assertEqual(book.p['edge']['pr_wins'],int(raw['pr_reps'][0][1]))
            out['nullified']=True;empty=G.StatBook();empty.record(out,{}, {},np.random.default_rng(1))
            self.assertEqual(empty.p,{})


if __name__=='__main__': unittest.main()
