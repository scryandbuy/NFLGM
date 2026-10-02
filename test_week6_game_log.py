import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import numpy as np
import game as G
import ticker
from test_game_clock_decisions import ClockDecisions

class WeekSixTests(unittest.TestCase):
    def test_rolling_touchback_gross_reaches_goal_line(self):
        rng=NS(random=lambda: .5,normal=iter([55,2,7]).__next__)
        values=iter([55,2,7]); rng.normal=lambda *a: next(values)
        # Aim 4? Force exact landing two yards short regardless of configured aim.
        values=iter([55,G.PUNT['aim']-2,7])
        with patch.object(G.ENV,'punt_mult',1):
            kick=G.punt(44,{}, {},rng,lambda *a:.7)
        self.assertTrue(kick['touchback'])
        self.assertEqual((kick['gross'],kick['net'],kick['new_yardline']),(44,24,80))
        old=dict(kick,gross=42)
        self.assertIn('Punt, 44 yards, touchback',ticker.play_line(NS(player=lambda p:None),old,'CHI','GB')['text'])
        self.assertEqual(old['gross'],42)

    def test_warning_after_return_in_each_half_and_drive_mode(self):
        for q,wall in ((2,1800),(4,0)):
            for live in (False,True):
                h=ClockDecisions();h.setUp()
                G.LAST_KICKOFF['r']=dict(new_yardline=20,clock=wall+123,touchback=False,ret=17)
                dr,_,_=h.drive([dict(type='complete',yards=20)],start=20,clock=wall+117,quarter=q,wall=wall if q==2 else None,diff=0,live=live)
                warnings=[p for p in dr.log if p['type']=='two_minute']
                self.assertEqual(len(warnings),1)
                self.assertEqual(warnings[0]['clock'],wall+117)
                self.assertEqual([p['type'] for p in dr.log[:2]],['kickoff','two_minute'])

    def test_game_loop_passes_point_deficit_to_onside_policy(self):
        n=0
        def drive(off,deff,start,clock,quarter,diff,rng,*a,**kw):
            nonlocal n
            n+=1; dr=G.Drive(off,deff,start,clock,quarter,diff,rng)
            dr.result='Touchdown'; dr.points=37 if n==1 else 22
            dr.clock=1800 if n==1 else 123
            if False:yield
            return dr
        with patch.object(G,'drive_steps',side_effect=drive),patch.object(G,'kickoff_booked',return_value=dict(touchback=True,new_yardline=65)),patch.object(G.W,'draw',return_value=G.W.CLEAR),patch.object(G,'_onside_call',wraps=G._onside_call) as policy:
            gen=G.game_steps({}, {},np.random.default_rng(1),None,None,None,None)
            next(gen);next(gen);next(gen);next(gen)
            self.assertEqual(policy.call_args.args[:3],(123,15,3))
            gen.close()

    def test_actual_two_score_case_still_allows_deep_with_three_timeouts(self):
        self.assertFalse(G._onside_call(123,15,3,None,np.random.default_rng(1)))
        self.assertTrue(G._onside_call(134,23,3,None,np.random.default_rng(1)))

if __name__=='__main__':unittest.main()
