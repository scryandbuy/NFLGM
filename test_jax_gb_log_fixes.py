"""JAX-GB Week 1: long-play timing, consistent spots, and drive tempo."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import game as G
import ticker
import test_game_clock_decisions as clocks


class JaxGbLogFixes(unittest.TestCase):
    def setUp(self):
        self.helper=clocks.ClockDecisions(); self.helper.setUp()
        self.league=NS(player=lambda pid:None)

    def test_eighty_five_yard_score_requires_more_than_six_seconds(self):
        play=dict(type='complete',yards=85,air=10,ttt=2.7)
        for live in (False,True):
            dr,_,_=self.helper.drive([play],start=85,clock=3578,quarter=1,
                wall=1800,diff=0,live=live)
            self.assertEqual(dr.result,'Touchdown')
            self.assertEqual(dr.clock,3578-G.live_play_seconds(play))
            self.assertLess(dr.clock,3572)
            snap=next(p for p in dr.log if p.get('type')=='complete')
            self.assertEqual(snap['yards'],85)
            self.assertGreater(snap['live_seconds'],6)

    def test_short_score_keeps_baseline_and_deep_air_has_route_time(self):
        self.assertEqual(G.live_play_seconds(dict(type='run',yards=5)),6)
        self.assertGreater(G.live_play_seconds(dict(type='run',yards=85)),6)
        self.assertGreater(G.live_play_seconds(dict(type='complete',yards=85,air=85,ttt=2.5)),10)

    def test_long_play_at_halftime_finishes_without_extra_snap_or_timeout(self):
        dr,_,tos=self.helper.drive([dict(type='complete',yards=70,air=10)],
            start=85,clock=1808,quarter=2,wall=1800,diff=0,own=1)
        self.assertEqual(dr.clock,1800); self.assertEqual(dr.plays,1)
        self.assertEqual(dr.result,'End of half'); self.assertEqual(tos.left['home'],1)

    def test_long_touchdown_can_finish_after_period_expires(self):
        dr,_,_=self.helper.drive([dict(type='complete',yards=85,air=10)],
            start=85,clock=1808,quarter=2,wall=1800,diff=0)
        self.assertEqual(dr.clock,1800); self.assertEqual(dr.result,'Touchdown')

    def test_warning_does_not_restore_time_consumed_by_long_play(self):
        play=dict(type='complete',yards=70,air=10)
        with patch.object(G,'end_of_half_plan',return_value=None):
            dr,_,_=self.helper.drive([play,dict(type='interception',yards=0,air=0,ret=0)],
                start=85,clock=125,quarter=4,wall=None,diff=0,own=0,other=0)
        warning=next(p for p in dr.log if p['type']=='two_minute')
        self.assertEqual(warning['clock'],125-G.live_play_seconds(play))
        self.assertLess(warning['clock'],120)

    def test_long_kick_and_defensive_returns_use_travel_time(self):
        self.assertEqual(G.kickoff_clock(3600,dict(touchback=True,ret=95)),3600)
        self.assertLess(G.kickoff_clock(3600,dict(touchback=False,ret=95)),3594)
        self.assertEqual(G.kickoff_clock(1805,dict(touchback=False,ret=95)),1800)
        dr=G.Drive({}, {},85,400,4,0,None)
        G._finish_turnover(dr,dict(type='interception',yards=0,ret=95,end_spot=100,defensive_td=True))
        self.assertLess(dr.clock,388); self.assertEqual(dr.result,'Defensive touchdown')

    def test_hurry_up_drive_does_not_stop_hurrying_at_ninety_seconds(self):
        results=[]
        for live in (False,True):
            dr,_,tos=self.helper.drive([dict(type='complete',yards=5),
                dict(type='complete',yards=14),dict(type='interception',yards=0,air=0,ret=0)],
                start=86,clock=90,quarter=4,wall=None,diff=-23,own=1,live=live)
            snaps=[p['clock'] for p in dr.log if p.get('down')]
            self.assertEqual(snaps,[90,76,62])
            self.assertEqual(tos.left['home'],1)
            results.append(dr.log)
        self.assertEqual(*results)

    def test_long_punt_return_uses_travel_time_and_stops_at_period_end(self):
        punt=dict(type='punt',how='return',ret=85,gross=40,new_yardline=0,touchdown=True)
        for clock,quarter,wall,expected in ((400,4,None,384),(1805,2,1800,1800),(5,5,None,0)):
            with patch.object(G,'fourth_down_decision',return_value='punt'), \
                 patch.object(G,'end_of_half_plan',return_value=None), \
                 patch.object(G,'punt',return_value=copy.deepcopy(punt)):
                dr,_,_=self.helper.drive([],start=85,clock=clock,quarter=quarter,
                    wall=wall,diff=0,down=4,own=0)
            self.assertEqual(dr.clock,expected)
            self.assertEqual(dr.result,'Defensive touchdown')

    def test_new_decided_game_drive_does_not_inherit_previous_chase(self):
        dr,_,_=self.helper.drive([dict(type='complete',yards=5),
            dict(type='interception',yards=0,air=0,ret=0)],
            start=86,clock=76,quarter=4,wall=None,diff=-23)
        snaps=[p['clock'] for p in dr.log if p.get('down')]
        self.assertGreater(snaps[0]-snaps[1],25)

    def test_half_yard_spots_move_by_the_logged_whole_yard_gain(self):
        for start in (54.5,30.5,18.5,11.5,64.1):
            for gain in (-3,0,1,3,5):
                dr=G.Drive({}, {},start,600,4,0,None)
                G._advance(dr,gain)
                self.assertEqual(ticker._field_round(start)-ticker._field_round(dr.yardline),gain)

    def test_field_goal_distance_and_touchdown_origin_use_same_spot(self):
        fg=dict(type='field_goal',yardline=11.5,distance=28.5,down=4,ydstogo=7,clock=500,made=True)
        before=copy.deepcopy(fg)
        line=ticker.play_line(self.league,fg,'JAX','GB')
        self.assertIn('GB 12',line['head']); self.assertIn('29-yard',line['text'])
        self.assertEqual(fg,before)
        td=ticker.play_line(self.league,dict(type='run',yardline=4.5,yards=4.5,touchdown=True), 'JAX','GB')
        self.assertIn('from the 5',td['text'])
        td=ticker.play_line(self.league,dict(type='complete',yardline=4.5,yards=4.5,touchdown=True), 'JAX','GB')
        self.assertIn('for 5 yards',td['text'])


if __name__=='__main__': unittest.main()
