import unittest
from unittest.mock import patch
import numpy as np
import game as G
import schemes as S
import plays as P
import test_game_clock_decisions as clocks

class ConversionAndPace(unittest.TestCase):
    def test_fourth_six_rare_runs_with_coach_variation(self):
        rates=[1-S.pass_rate(4,6,score,34,pers,bias,480) for score in (-10,0,7) for pers in ('11','12','21') for bias in (-.25,0,.25)]
        self.assertTrue(all(0 < r < .03 for r in rates),rates)
        self.assertGreater(max(rates),min(rates))
        self.assertGreater(1-S.pass_rate(4,1,0,40,'11'),.3)
        self.assertGreater(1-S.pass_rate(1,6,0,40,'11'),.3)

    def test_actual_calls_weather_and_extreme_run_lean_still_rare(self):
        for wet in (0,.18):
            rng=np.random.default_rng(203003)
            with patch.object(P.ENV,'run_lean',wet):
                n=sum(not S.call_offense(4,6,-10,34,rng,secs_left=480,lean={'pass_bias':-.25})['is_pass'] for _ in range(2500))
            print('Fourth-and-six designed runs, weather',wet,':',n,'/2500')
            self.assertTrue(0<n<125,n)
        self.assertLess(1-S.pass_rate(4,6,7,34,'21',-3.5,180),.03)

    def test_field_position_timeouts_and_tempo_change_pace(self):
        pace=G.comeback_pace(165,-3,4,yardline=79,timeouts=3)
        self.assertGreater(pace,0)
        self.assertGreater(G.comeback_pace(165,-3,4,yardline=79,timeouts=0),pace)
        self.assertLess(G.play_seconds('complete',catchup=pace),26)
        for margin in (-1,-2,-3):
            self.assertEqual(G.comeback_pace(165,margin,4,yardline=20),0)
        for margin in (0,3):
            self.assertEqual(G.comeback_pace(165,margin,4,yardline=79),0)
        self.assertEqual(G.comeback_pace(700,-3,4,yardline=79),0)
        self.assertEqual(G.comeback_pace(165,-3,2,yardline=79),0)

    def test_real_drive_accelerates_before_two_minute_warning(self):
        fixture=clocks.ClockDecisions();fixture.setUp()
        outcomes=[dict(type='complete',yards=5),dict(type='interception',yards=0,air=0,ret=0)]
        dr,_,_=fixture.drive(outcomes,start=79,clock=165,quarter=4,wall=None,diff=-3,own=3,other=3)
        snaps=[p for p in dr.log if p.get('down')]
        self.assertLess(snaps[0]['clock']-snaps[1]['clock'],26)

if __name__=='__main__':unittest.main()

