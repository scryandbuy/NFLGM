import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import ticker
import test_game_clock_decisions as clocks

class InjuryClockTests(unittest.TestCase):
    def apply(self, sides=('def',), own=3, other=3, diff=10, kind='complete', **kw):
        d=G.Drive({}, {}, 53, 1886, 2, diff, np.random.default_rng(1))
        d._two_min=True
        t=G.Timeouts();t.left={'home':own,'away':other}
        G._injury_timeout(d,[dict(side=s) for s in sides],dict(type=kind),t,'home',1800,1914,**kw)
        return d,t
    def test_pitre_charges_carolina_and_preserves_live_play_time(self):
        d,t=self.apply()
        self.assertEqual(d.clock,1914)
        self.assertEqual(t.left,dict(home=3,away=2))
        self.assertFalse(d.clock_running)
        self.assertEqual(d.log[0]['reason'],'injury')
    def test_both_teams_and_duplicate_injuries(self):
        d,t=self.apply(sides=('off','off','def'))
        self.assertEqual(t.left,dict(home=2,away=2))
        self.assertEqual(len(d.log),2)
    def test_incomplete_still_charges_timeout(self):
        d,t=self.apply(kind='incomplete')
        self.assertEqual(t.left['away'],2)
    def test_excess_defensive_timeout_has_no_ten_second_runoff(self):
        d,t=self.apply(other=0,diff=-7)
        self.assertEqual(d.clock,1914)
        self.assertTrue(d.log[0]['excess'])
    def test_excess_offense_runoff_when_defense_wants_clock(self):
        d,t=self.apply(sides=('off',),own=0,diff=-7)
        self.assertTrue(any(e['type']=='injury_runoff' for e in d.log))
        self.assertLessEqual(d.clock,1904)
    def test_both_excess_have_no_runoff_or_penalty(self):
        d,t=self.apply(sides=('off','def'),own=0,other=0,diff=-7)
        self.assertEqual(d.clock,1914)
        self.assertEqual([e['type'] for e in d.log],['timeout','timeout'])
    def test_touchdown_and_pre_warning_exempt(self):
        for result,warning in [('Touchdown',True),(None,False)]:
            d=G.Drive({}, {}, 0, 1914, 2, 0, None);d.result=result;d._two_min=warning
            t=G.Timeouts()
            self.assertFalse(G._injury_timeout(d,[dict(side='def')],dict(type='complete'),t,'home',1800,1914))
            self.assertEqual(t.left['away'],3)
    def test_second_excess_timeout_penalty_preserves_down(self):
        d,t=self.apply(sides=('off',),own=0,diff=-7)
        G._injury_timeout(d,[dict(side='off')],dict(type='complete'),t,'home',1800,1860)
        self.assertEqual((d.yardline,d.togo,d.down),(58,15,1))
        self.assertEqual(len([e for e in d.log if e['type']=='penalty']),1)
    def test_runoff_can_end_half(self):
        d=G.Drive({}, {}, 53, 1808, 2, -7, None);d._two_min=True
        t=G.Timeouts();t.left['home']=0
        G._injury_timeout(d,[dict(side='off')],dict(type='complete'),t,'home',1800,1808)
        self.assertEqual(d.clock,1800)
    def test_foul_prevents_excess_injury_runoff(self):
        d,t=self.apply(sides=('off',),own=0,diff=-7,foul=True)
        self.assertEqual(d.clock,1914)
        self.assertFalse(any(e['type']=='injury_runoff' for e in d.log))
    def test_live_and_batch_next_snap_at_injury_whistle(self):
        for live in (False,True):
            h=clocks.ClockDecisions();h.setUp()
            states=(G.TeamState(h.off),G.TeamState(h.deff))
            hit=[False]
            def hurt(*a,**kw):
                if hit[0]: return None
                hit[0]=True
                return dict(kind='ankle',weeks_out=1)
            with patch.object(states[0],'hurt',return_value=None), patch.object(states[1],'hurt',side_effect=hurt), patch.object(G,'field_units',side_effect=lambda ros,*a,**kw:(ros,{})):
                dr,_,tos=h.drive([dict(type='complete',yards=8),dict(type='interception',yards=0,air=0,ret=0)],start=61,clock=1920,diff=10,own=3,other=3,states=states,live=live)
            snaps=[p for p in dr.log if p.get('down')]
            self.assertEqual(snaps[1]['clock'],1914)
            self.assertEqual(tos.left['away'],2)
            self.assertEqual(tos.left['home'],3)

class SpotDisplayTests(unittest.TestCase):
    def test_possession_reversal_keeps_same_label(self):
        for y in (40.5,40.6,41.,59.5,59.6,93.5):
            self.assertEqual(ticker._spot(y,'CAR','GB'),ticker._spot(100-y,'GB','CAR'))
    def test_touchdown_drive_length_matches_start_label(self):
        self.assertEqual(ticker._spot(93.5,'GB','CAR'),'GB 7')
        self.assertEqual(ticker.display_drive_yards(93.5,0),93)
        self.assertEqual(ticker._spot(60.5,'CAR','GB'),'CAR 40')
        self.assertEqual(ticker.display_drive_yards(60.5,0),60)
