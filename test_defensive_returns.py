"""Turnover returns, scoring ownership, enforcement and deterministic replay."""
import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import advanced_stats as AS
import events as E
import game as G
import plays as P


class DefensiveReturns(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb',pos='QB'), rb=dict(pid='rb',pos='HB'),
                        wr=[dict(pid='wr1',pos='WR'),dict(pid='wr2',pos='WR')], te=[],ol=[],k=dict(pid='ok'))
        self.defense = dict(db=[dict(pid='cb',pos='CB')],lb=[],dl=[dict(pid='edge',pos='LEDG')], k=dict(pid='dk'))
        G.LAST_KICKOFF.clear()

    def drive(self, plays, start=70, quarter=4, flag=None, fumble=None, return_end=None, clock=300):
        outcomes = iter(copy.deepcopy(plays))
        book = G.StatBook()
        def forced_return(spot, kind, returner, *a, **k):
            end = return_end if return_end is not None else spot
            d = dict(return_start=spot,end_spot=end,returner=returner['pid'],return_kind=kind,
                     ret=max(0,end-max(spot,0)),touchback=False,defensive_td=end>=100)
            if end>=100: d.update(touchdown=True,scoring_side='defense')
            return d
        with ExitStack() as stack:
            stack.enter_context(patch.object(E,'penalty_check',side_effect=[flag]+[None]*30))
            stack.enter_context(patch.object(E,'fumble_check',return_value=fumble))
            stack.enter_context(patch.object(E,'scramble_chance',return_value=0))
            stack.enter_context(patch.object(G,'field_units',side_effect=lambda ros,*a,**k:(ros,{})))
            stack.enter_context(patch.object(G,'end_of_half_plan',return_value=None))
            stack.enter_context(patch.object(G,'two_point_decision',return_value=False))
            xp = stack.enter_context(patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',made=True,points=1)))
            stack.enter_context(patch('playcall.audible',side_effect=lambda oc,*a,**k:(oc,None)))
            if return_end is not None: stack.enter_context(patch.object(P,'defensive_return',side_effect=forced_return))
            dr=G.run_drive(self.off,self.defense,start,clock,quarter,0,np.random.default_rng(14),
                          lambda *a:next(outcomes),lambda *a,**k:dict(is_pass=True,personnel='11',depth='short'),
                          lambda *a,**k:dict(personnel='nickel',front_family='4-3'),lambda *a:.7,book=book)
        return dr,book,xp

    def pick(self, ret=40, air=10):
        return dict(type='interception',yards=0,air=air,ret=ret,by='cb',target='wr2')

    def flag(self, offense, name='Unnecessary Roughness'):
        return dict(penalty=name,on_offense=offense,yards=15,rule_yards=15,auto_first=not offense,nullifies=False)

    def test_interception_scores_for_defense_and_preserves_offensive_stats(self):
        dr,b,xp=self.drive([self.pick()])
        self.assertEqual((dr.result,dr.points,dr.yardline),('Defensive touchdown',-7,100))
        self.assertEqual(b.p['cb']['int_ret_td'],1)
        self.assertEqual(b.p['cb']['int_ret_yds'],40)
        self.assertEqual(b.p['cb']['def_td'],1)
        self.assertEqual((b.p['qb']['ints'],b.p['qb']['pass_td'],b.p['qb']['pass_yds']),(1,0,0))
        self.assertEqual(xp.call_args.args[0]['pid'],'dk')
        self.assertLess(b.p['qb']['pass_epa'],-6.95)
        self.assertEqual(dr.log[0]['scoring_side'],'defense')

    def test_non_scoring_return_and_touchback_spots(self):
        dr,b,_=self.drive([self.pick(ret=12,air=20)])
        self.assertEqual((dr.result,dr.yardline),('Turnover',62))
        self.assertEqual(b.p['cb']['int_ret_yds'],12)
        dr,b,_=self.drive([self.pick(ret=0,air=25)],start=20)
        self.assertTrue(dr.log[0]['touchback'])
        self.assertEqual((dr.yardline,b.p['cb']['int_ret_yds']),(20,0))

    def test_model_end_zone_exit_counts_only_field_return_yards(self):
        rng=NS(random=lambda: .99,exponential=lambda scale:8)
        r=P.defensive_return(-3,'int',dict(pid='cb'),[],rng)
        self.assertEqual((r['end_spot'],r['ret'],r['touchback']),(5,5,False))
        rng=NS(random=lambda:0,exponential=lambda scale:8)
        r=P.defensive_return(-3,'int',dict(pid='cb'),[],rng)
        self.assertEqual((r['end_spot'],r['ret'],r['touchback']),(20,0,True))

    def test_model_td_depends_on_distance_not_fixed_td_draw(self):
        rng=NS(random=lambda:.99,exponential=lambda scale:30)
        for start,scored,end in ((10,False,40),(80,True,100)):
            r=P.defensive_return(start,'int',dict(pid='cb'),[],rng)
            self.assertEqual((r['defensive_td'],r['end_spot']),(scored,end))
            self.assertEqual(r['ret'],end-start)
        r=P.defensive_return(100,'fumble',dict(pid='edge'),[],rng)
        self.assertTrue(r['defensive_td']);self.assertEqual(r['ret'],0)

    def test_fumble_actual_receiver_and_returner_receive_separate_stats(self):
        out=dict(type='complete',yards=8,target='wr2',tackler='cb')
        dr,b,_=self.drive([out],fumble=dict(lost=True,forced=True),return_end=100)
        p=dr.log[0];pid=p['recoverer']
        self.assertEqual((dr.result,dr.points),('Defensive touchdown',-7))
        self.assertEqual(p['return_start'],62)
        self.assertEqual(b.p[pid]['fum_ret_yds'],38)
        self.assertEqual((b.p[pid]['fum_rec'],b.p[pid]['fum_ret_td']),(1,1))
        self.assertEqual((b.p['wr2']['fumbles_lost'],b.p['wr2']['rec_yds'],b.p['wr2']['rec_td']),(1,8,0))
        self.assertNotIn('wr1',b.p)
        self.assertEqual(b.p['cb']['ff'],1)
        self.assertEqual((b.p['qb']['pass_yds'],b.p['qb']['pass_td']),(8,0))
        self.assertLess(b.p['qb']['pass_epa'],-6.95)

    def test_sack_fumble_recovery_in_end_zone_is_defensive_td(self):
        dr,b,_=self.drive([dict(type='sack',yards=-5,by='edge')],start=98,
                         fumble=dict(lost=True,forced=True),return_end=100)
        self.assertEqual((dr.result,dr.points),('Defensive touchdown',-7))
        self.assertEqual(dr.log[0]['ret'],0)
        self.assertEqual((b.p['qb']['sacked'],b.p['qb']['fumbles_lost']),(1,1))
        self.assertEqual(b.p['edge']['ff'],1)

    def test_live_defensive_foul_nullifies_pick_six_and_stats(self):
        dr,b,_=self.drive([self.pick(),self.pick(ret=0,air=0)],flag=self.flag(False,'Roughing the Passer'))
        self.assertTrue(dr.log[0]['nullified'])
        self.assertEqual((dr.result,dr.points),('Turnover',0))
        self.assertEqual((b.p['qb']['ints'],b.p['cb']['int_def'],b.p['cb']['def_td']),(1,1,0))

    def test_offensive_live_foul_declined_to_keep_return_touchdown(self):
        dr,b,_=self.drive([self.pick()],flag=self.flag(True,'Offensive Holding'))
        self.assertEqual(dr.points,-7)
        self.assertFalse(dr.log[0].get('nullified'))

    def test_post_score_penalty_changes_defending_try_not_touchdown(self):
        for offender,distance in ((True,25.5),(False,48)):
            dr,b,xp=self.drive([self.pick()],flag=self.flag(offender))
            self.assertEqual(dr.points,-7)
            self.assertEqual(xp.call_args.kwargs['distance'],distance)
            self.assertEqual(b.p['cb']['int_ret_yds'],40)
            self.assertTrue(next(p for p in dr.log if p['type']=='penalty')['on_try'])

    def test_post_return_penalty_changes_possession_spot_not_return_stat(self):
        dr,b,_=self.drive([self.pick(ret=12,air=20)],flag=self.flag(True))
        self.assertEqual(dr.yardline,77)
        self.assertEqual(b.p['cb']['int_ret_yds'],12)
        self.assertEqual(next(p for p in dr.log if p['type']=='penalty')['yards'],15)

    def test_post_fumble_return_penalty_uses_return_endpoint(self):
        dr,b,_=self.drive([dict(type='run',yards=8,tackler='cb')],
                         flag=self.flag(False),fumble=dict(lost=True,forced=False),return_end=82)
        self.assertEqual((dr.result,dr.yardline),('Turnover',67))
        p=dr.log[0]
        self.assertEqual(b.p[p['recoverer']]['fum_ret_yds'],20)
        self.assertEqual((b.p['rb']['rush_yds'],b.p['rb']['fumbles_lost'],b.p['cb']['ff']),(8,1,0))

    def test_live_defensive_foul_cancels_fumble_return_and_recovery_stats(self):
        dr,b,_=self.drive([dict(type='complete',yards=8,target='wr2',tackler='cb'),self.pick(ret=0,air=0)],
                         flag=self.flag(False,'Roughing the Passer'),
                         fumble=dict(lost=True,forced=True),return_end=100)
        self.assertTrue(dr.log[0]['nullified'])
        self.assertEqual(dr.points,0)
        self.assertEqual(sum(s['fum_rec'] for s in b.p.values()),0)
        self.assertEqual(sum(s['fumbles_lost'] for s in b.p.values()),0)

    def test_legacy_overlong_interception_return_is_capped_at_goal(self):
        dr,b,_=self.drive([self.pick(ret=140,air=0)],start=90)
        self.assertEqual((dr.yardline,b.p['cb']['int_ret_yds']),(100,10))

    def test_overtime_return_touchdown_has_no_try(self):
        dr,b,xp=self.drive([self.pick()],quarter=5)
        self.assertEqual(dr.points,-6);xp.assert_not_called()
        with patch.object(G,'run_drive',return_value=dr),patch.object(G,'kickoff_booked',return_value=dict(new_yardline=70,touchback=True)):
            score,drives,reason=G.play_overtime(self.off,self.defense,dict(home=17,away=17),
                                      np.random.default_rng(2),None,None,None,lambda *a:.7,first='home')
        self.assertEqual((score,reason),(dict(home=17,away=23),'defensive_touchdown_walkoff'))

    def test_same_seed_and_restored_rng_reproduce_return(self):
        rng=np.random.default_rng(123)
        state=copy.deepcopy(rng.bit_generator.state)
        a=[P.defensive_return(70,'fumble',dict(pid='cb'),[],rng) for _ in range(100)]
        resumed=np.random.default_rng();resumed.bit_generator.state=state
        b=[P.defensive_return(70,'fumble',dict(pid='cb'),[],resumed) for _ in range(100)]
        self.assertEqual(a,b)
        self.assertEqual(rng.bit_generator.state,resumed.bit_generator.state)

    def test_defensive_td_epa_precedes_offensive_touchdown_flag(self):
        out=dict(type='complete',touchdown=True,defensive_td=True,fumble_lost=True)
        self.assertEqual(AS.epa(out,1,10,70,1,10,100),-AS.TD_VALUE-AS.ep(1,10,70))


if __name__=='__main__':unittest.main()
