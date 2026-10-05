import unittest
from unittest.mock import patch
import numpy as np
import events as E
import plays as P
import game as G
import test_defensive_returns as DR
from test_scramble_goal_contact import Draws
from test_designed_qb_runs import offense
from test_defensive_rush import unit, call


class ExactScramblePlane(unittest.TestCase):
    def test_fractional_untouched_crossing_has_no_contact_draws(self):
        for goal, gain in ((3.5,3.7), (16.1,16.859), (.4,.6)):
            rng = Draws(distance=gain)
            out = E.resolve_scramble(dict(pid='qb'), [dict(pid='edge')], goal, rng, lambda *a:.7)
            self.assertTrue(out['touchdown'])
            self.assertEqual(out['yards'],goal)
            self.assertEqual(rng.calls,0)
            self.assertNotIn('scramble_contact',out)
            self.assertNotIn('broken_tackles',out)

    def test_real_contact_before_fractional_plane_retained(self):
        out = E.resolve_scramble(dict(pid='qb'), [dict(pid='edge')], 3.5,
                                 Draws(distance=3.2,burst=1),lambda *a:.7)
        self.assertTrue(out['touchdown'])
        self.assertEqual(out['pre_goal_contact_yards'],3.2)
        self.assertEqual(out['broken_tackles'],1)

    def test_voluntary_pass_path_uses_exact_plane_with_legacy_fallback(self):
        for exact in (3.5,None):
            oc=dict(is_pass=True,personnel='11',depth='short',concept='stick')
            if exact is not None: oc['scramble_goal_distance']=exact
            with patch.object(E,'pocket_run_chance',return_value=1.), \
                 patch.object(E,'resolve_scramble',return_value=dict(type='scramble',yards=4.,touchdown=True)) as resolver:
                for seed in range(30):
                    P.resolve_play(offense(),unit('4-3','nickel'),oc,
                        dict(call('4-3','nickel'),box=6,shell='two_high'),4,np.random.default_rng(seed))
                    if resolver.called: break
            self.assertTrue(resolver.called)
            self.assertEqual(resolver.call_args.args[2],exact if exact is not None else 4)

    def test_sack_escape_drive_hands_off_exact_plane_and_keeps_score(self):
        fixture=DR.DefensiveReturns(); fixture.setUp()
        original=E.resolve_scramble
        def resolve(qb,defenders,goal,*args):
            return original(qb,defenders,goal,Draws(distance=3.7),lambda *a:.7)
        with patch.object(E,'scramble_chance',return_value=1.), \
             patch.object(E,'resolve_scramble',side_effect=resolve) as resolver, \
             patch.object(E,'penalty_check',return_value=None), \
             patch.object(E,'fumble_check',return_value=dict(lost=True,forced=True)), \
             patch.object(G,'field_units',side_effect=lambda ros,*a,**k:(ros,{})), \
             patch.object(G,'end_of_half_plan',return_value=None), \
             patch.object(G,'two_point_decision',return_value=False), \
             patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',made=True,points=1)), \
             patch('playcall.audible',side_effect=lambda oc,*a,**k:(oc,None)):
            book=G.StatBook()
            def sack(off,deff,oc,*args):
                self.assertEqual(oc['scramble_goal_distance'],3.5)
                return dict(type='sack',yards=-4,by='edge')
            dr=G.run_drive(fixture.off,fixture.defense,3.5,300,4,0,np.random.default_rng(14),
                sack,lambda *a,**k:dict(is_pass=True,personnel='11',depth='short'),
                lambda *a,**k:dict(personnel='nickel',front_family='4-3'),lambda *a:.7,book=book)
        self.assertEqual(resolver.call_args.args[2],3.5)
        self.assertEqual((dr.result,dr.points),('Touchdown',7))
        self.assertEqual(book.p['qb']['rush_td'],1)
        self.assertEqual(book.p['qb']['fumbles'],0)
        self.assertNotIn('scramble_contact',dr.log[0])


if __name__=='__main__': unittest.main()
