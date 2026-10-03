"""Individual practice ceilings, saved awards and practice-only growth samples."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import health as H
import practice as P
import xp as XP
import xp_spend as XS
import targets as TG
from league import Player, League
from test_cap_accounting import fixture, player
from test_practice_engine import setup, plan


def full_plan(pid, intensity='standard'):
    q=plan(intensity)
    for unit in q['units'].values(): unit['reps']='development'
    q['focus']=[pid]
    return q


class PracticeXPTests(unittest.TestCase):
    def test_ideal_ceiling_at_each_experience_and_hard_cannot_replace_other_factors(self):
        l,r,ps=setup(); p=ps[-1];p.dev='xfactor';p.entry_year=l.year
        with patch('staff.xp_mult',return_value=P.MAX_COACH_XP_MULT):
            for experience, ceiling in enumerate(P.WEEKLY_XP_CEILINGS):
                p.entry_year=l.year-experience
                for intensity in ('standard','hard'):
                    row=P.preview(l,r,'A',1,full_plan(p.pid,intensity))['players'][-1]
                    self.assertAlmostEqual(row['xp'],ceiling)
                    self.assertEqual(row['xp_ceiling'],ceiling)
                    self.assertTrue(all(0<=v<=1 for v in row['xp_factors'].values()))
            p.entry_year=l.year
            p.dev='normal'
            self.assertLess(P.preview(l,r,'A',1,full_plan(p.pid,'hard'))['players'][-1]['xp'],1000)
            p.dev='xfactor'
            q=full_plan(p.pid,'hard');q['focus']=[]
            self.assertLess(P.preview(l,r,'A',1,q)['players'][-1]['xp'],1000)
        with patch('staff.xp_mult',return_value=1.):
            self.assertLess(P.preview(l,r,'A',1,full_plan(p.pid,'hard'))['players'][-1]['xp'],1000)

    def test_elapsed_ps_seasons_and_legacy_anchor(self):
        l,r,ps=setup();p=ps[-1];p.accrued=0;p.entry_year=2023;p.draft_year=2022
        self.assertIn(p,l.teams['A'].practice_squad)
        row=P.preview(l,r,'A',1)['players'][-1]
        self.assertEqual((row['xp_experience'],row['xp_ceiling']),(3,550))
        p.entry_year=None
        self.assertEqual(P.preview(l,r,'A',1)['players'][-1]['xp_ceiling'],425)
        p.draft_year=None
        before=copy.deepcopy(p.xp_spent)
        P.preview(l,r,'A',1)
        self.assertEqual(p.xp_spent,before)
        P.resolve(l,r,'A',1,plan('recovery'))
        self.assertEqual(p.xp_spent['_practice_entry_year'],2026)
        l.year=2027
        self.assertEqual(P.preview(l,r,'A',1)['players'][-1]['xp_ceiling'],850)
        self.assertEqual(p.accrued,0)
        l.year=2066
        self.assertEqual(P.preview(l,r,'A',1)['players'][-1]['xp_ceiling'],150)

    def test_real_credit_modifiers_applied_once_with_save_reload_and_user_cpu_parity(self):
        l=fixture();p=player(l);p.entry_year=l.year;p.dev='xfactor';p.accrued=0
        p.traits={'work_ethic':0}
        l.user_team='GB'
        # Real staff functions, with an actual top Teacher coordinator.
        l.teams['GB'].staff={'oc':NS(effective=lambda:99,staff_traits=['teacher'])}
        r=NS(states={'GB':NS(cond=H.Condition(),jaded={},last_snaps={},snaps={},out=set())},
             desks={},rng=np.random.default_rng(14))
        q=plan('standard');q['units']['offense']['reps']='starters';q['focus']=[p.pid]
        with patch('practice.BASE_INJURY_RISK',0):
            forecast=P.preview(l,r,'GB',1,q)
            self.assertAlmostEqual(forecast['players'][0]['xp'],800)
            result=P.resolve(l,r,'GB',1,q)
        self.assertAlmostEqual(p.xp,800)  # Low work ethic applies once, before the ceiling.
        self.assertLessEqual(p.xp,1000)
        self.assertAlmostEqual(p.xp_spent['_earned']['practice'],800)
        self.assertLessEqual(p.xp_spent['_earned']['practice'],1000)
        self.assertEqual(result['players'][0]['xp_ceiling'],1000)
        self.assertIn('Rookie',result['players'][0]['xp_explanation'])
        l.teams['GB'].staff={}  # Serializable fixture; award and plan stay intact.
        loaded=League.load(l.save());loaded.user_team='GB'
        before=copy.deepcopy(r.rng.bit_generator.state)
        self.assertEqual(P.resolve(loaded,r,'GB',1,q),result)
        self.assertEqual(r.rng.bit_generator.state,before)
        self.assertAlmostEqual(loaded.player(p.pid).xp,800)
        loaded.year+=1
        self.assertEqual(P.preview(loaded,r,'GB',1,q)['players'][0]['xp_ceiling'],850)
        # Same roster/plan/modifiers yields identical CPU and user payouts.
        for user_team in ('A',None):
            ll,rr,pp=setup();ll.user_team=user_team
            with patch('practice.BASE_INJURY_RISK',0):
                P.resolve(ll,rr,'A',1,plan('standard'))
            if user_team: expected=[x.xp for x in pp]
            else: self.assertEqual([x.xp for x in pp],expected)

    def test_zero_participation_and_limited_work_never_gain_from_focus(self):
        l,r,ps=setup();p=ps[-1];q=full_plan(p.pid)
        baseline=P.preview(l,r,'A',1,q)['players'][-1]['xp']
        q['individual']={p.pid:'limited'}
        self.assertAlmostEqual(P.preview(l,r,'A',1,q)['players'][-1]['xp'],baseline*.35)
        for condition in ('rest','rehab','duplicate'):
            q=full_plan(p.pid,'hard');p.out_until=None;l.practice_state={}
            if condition=='rest': q['individual']={p.pid:'rest'}
            if condition=='rehab': p.out_until=4
            if condition=='duplicate': l.practice_state={'participants':{'2026:1':{p.pid:'B'}}}
            row=P.preview(l,r,'A',1,q)['players'][-1]
            self.assertEqual((row['xp'],row['risk']),(0,0))

    def test_practice_only_sample_growth_uses_real_upgrade_costs(self):
        results=[]
        for pos in ('QB','WR','LT','REDG','CB','K'):
            for label,experience,dev,coach,focused,reps in (
                ('ideal rookie',0,'xfactor',P.MAX_COACH_XP_MULT,True,1.25),
                ('ordinary rookie',0,'normal',1.,False,1.),
                ('year 10',9,'normal',1.,False,1.)):
                p=Player(f'{pos}-{label}',label,pos,22+experience,
                         {k:70. for k in TG.DEPTH_WEIGHTS[pos]},dev=dev,potential=90,
                         entry_year=2026-experience)
                l=NS(year=2026);team=NS(record=(0,0,0));gm=NS(dev_belief=.5,patience=.5)
                before=p.ovr;earned=0.;rng=np.random.default_rng(200)
                with patch('staff.xp_mult',return_value=coach):
                    for week in range(1,19):
                        award=P._xp_award(l,team,p,reps,1.,focused,0)['xp']
                        p.xp+=award;earned+=award
                        XS.spend_player(p,gm,team,week,rng,year=2026)
                self.assertLessEqual(earned,18*P.WEEKLY_XP_CEILINGS[experience])
                self.assertGreaterEqual(p.ovr,before)
                self.assertLessEqual(p.ovr,p.potential+.01)
                results.append((pos,label,round(earned),round(p.ovr-before,2),XP.points_bought(p)))
        print('Practice-only 18-week samples (position, profile, XP, OVR gain, attribute points):',results)


if __name__=='__main__':unittest.main()
