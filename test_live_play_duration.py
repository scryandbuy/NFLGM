import unittest
from unittest.mock import patch
import game as G
import test_game_clock_decisions as clocks

class LiveDurationTests(unittest.TestCase):
    def test_dead_ball_tempo_does_not_change_game_clock(self):
        for kind in ('incomplete','drop'):
            for hurry in (False,True):
                for tempo in (0.,1.):
                    self.assertEqual(G.play_seconds(kind,hurry=hurry,tempo=tempo),6)
    def test_extended_pass_and_scramble_can_take_ten_seconds(self):
        self.assertEqual(G.live_play_seconds(dict(type='incomplete',ttt=9,intended_air=30)),11)
        self.assertEqual(G.live_play_seconds(dict(type='incomplete',ttt=9,throwaway=True)),10)
        self.assertEqual(G.live_play_seconds(dict(type='scramble',ttt=5,yards=40)),11)
        self.assertEqual(G.live_play_seconds(dict(type='incomplete',ttt=2,intended_air=5)),6)
    def test_air_and_yac_contribute_without_double_counting_routes(self):
        self.assertGreater(G.live_play_seconds(dict(type='complete',ttt=3,air=10,yards=70)),
                           G.live_play_seconds(dict(type='complete',ttt=3,air=10,yards=10)))
    def test_quarter_has_three_seconds_after_quick_incompletion(self):
        for live in (False,True):
            h=clocks.ClockDecisions();h.setUp()
            dr,_,_=h.drive([dict(type='incomplete',yards=0,ttt=2,intended_air=5),dict(type='interception',yards=0,air=0,ret=0)],
                           start=64,clock=909,quarter=3,wall=0,diff=-14,own=3,other=3,live=live)
            snaps=[p for p in dr.log if p.get('down')]
            self.assertEqual(snaps[1]['clock'],903)
    def test_long_incompletion_can_legitimately_end_quarter(self):
        for live in (False,True):
            h=clocks.ClockDecisions();h.setUp()
            dr,_,_=h.drive([dict(type='incomplete',yards=0,ttt=9,intended_air=30),dict(type='interception',yards=0,air=0,ret=0)],
                           start=64,clock=909,quarter=3,wall=0,diff=-14,own=3,other=3,live=live)
            snaps=[p for p in dr.log if p.get('down')]
            self.assertEqual(snaps[0]['live_seconds'],11)
            self.assertEqual(snaps[1]['clock'],900)
    def test_long_incompletion_ends_half_without_another_snap(self):
        h=clocks.ClockDecisions();h.setUp()
        with patch.object(G,'end_of_half_plan',return_value=dict(choice='shot',hurry=True)):
            dr,_,_=h.drive([dict(type='incomplete',yards=0,ttt=9,intended_air=30)],clock=1809,diff=-7)
        self.assertEqual(dr.clock,1800)
        self.assertEqual(dr.result,'End of half')

    def test_sack_escape_keeps_pocket_time_in_live_and_batch(self):
        import events
        for live in (False, True):
            h=clocks.ClockDecisions();h.setUp()
            with patch.object(events, 'scramble_chance', return_value=1.), patch.object(events, 'resolve_scramble', return_value=dict(type='scramble', yards=40, carrier='qb')):
                dr,_,_=h.drive([dict(type='sack',yards=-5,ttt=5),dict(type='interception',yards=0,air=0,ret=0)],start=80,clock=2200,diff=-7,live=live)
            first=next(p for p in dr.log if p.get('type')=='scramble')
            self.assertEqual(first['ttt'],5)
            self.assertEqual(first['live_seconds'],11)
