import unittest
from types import SimpleNamespace as NS
import numpy as np
import game as G
import gameplan as GP
import targets as T
import plays as P
from test_target_grade_scale import pairs, order

class ReceiverOpportunities(unittest.TestCase):
    def test_gap_increases_preference_but_crowded_room_tempers_it(self):
        small=pairs([('WR',85),('WR',80),('WR',75),('TE',70),('HB',70)])
        lone=pairs([('WR',99),('WR',80),('WR',75),('TE',70),('HB',70)])
        crowded=pairs([('WR',99),('WR',97),('WR',94),('TE',90),('HB',90)])
        self.assertGreater(order(lone)[1][0],order(small)[1][0])
        self.assertGreater(order(lone)[1][0],order(crowded)[1][0])
        for plan in (NS(target_priority={},feature_receivers=0),NS(target_priority={},feature_receivers=1)):
            w=order(lone,plan=plan)[1]
            self.assertGreater(w[0],w[1]); self.assertLess(w[0],.6)
    def test_bracket_and_protection_can_redirect_featured_reads(self):
        rows=pairs([('WR',99),('WR',90),('WR',85),('TE',80)])
        original=order(rows)[1][0]
        rows[0]['bracket']=True
        self.assertLess(order(rows)[1][0],original)
        rows[0]['late']=True
        self.assertNotEqual(order(rows)[0],'0')
    def test_coach_preference_preserved_by_copy_and_old_save_default(self):
        rows=pairs([('WR',99),('WR',80),('WR',75),('TE',70)])
        spread=GP.base_plan({'feature_receivers':0})
        feature=GP.base_plan({'feature_receivers':1})
        self.assertGreater(order(rows,plan=feature)[1][0],order(rows,plan=spread)[1][0])
        self.assertEqual(feature.copy().feature_receivers,1)
        self.assertEqual(GP.Gameplan(**{'tempo':.5}).feature_receivers,.5)
    def test_useful_open_short_catch_earns_attention(self):
        self.assertTrue(G.receiver_won_read(dict(type='complete',yards=6,separation=.7)))
        self.assertFalse(G.receiver_won_read(dict(type='complete',yards=6,separation=.3)))
        self.assertFalse(G.receiver_won_read(dict(type='complete',yards=1,separation=.9)))
        self.assertFalse(G.receiver_won_read(dict(type='incomplete',yards=0,separation=.9)))
        self.assertTrue(G.receiver_won_read(dict(type='complete',yards=18,separation=.3)))
        self.assertFalse(G.receiver_won_read(dict(type='complete',yards=4,separation=.9,down=3,ydstogo=15)))
        self.assertTrue(G.receiver_won_read(dict(type='complete',yards=3,separation=.9,down=3,ydstogo=2)))
    def test_all_options_still_receive_targets(self):
        rows=pairs([('WR',99),('WR',80),('WR',75),('TE',70),('HB',70)])
        T.assign_concept_roles(rows,'dagger','medium')
        rng=np.random.default_rng(921); counts={str(i):0 for i in range(5)}
        for _ in range(1500):
            r,*_=T.select_target(rows,{},'dagger',rng,P.rate)
            counts[r['pid']]+=1
        self.assertTrue(all(c>50 for c in counts.values()))
        self.assertLess(counts['0'],750)

    def test_short_open_catch_updates_live_coaching_priority(self):
        from unittest.mock import patch
        import test_game_clock_decisions as clocks
        for live in (False, True):
            h=clocks.ClockDecisions();h.setUp()
            states=(G.TeamState(h.off),G.TeamState(h.deff))
            with patch.object(states[0],'hurt',return_value=None), patch.object(states[1],'hurt',return_value=None), patch.object(G,'field_units',side_effect=lambda ros,*a,**kw:(ros,{})):
                h.drive([dict(type='complete',yards=6,separation=.7),dict(type='interception',yards=0,air=0,ret=0)],start=70,clock=2100,diff=0,own=3,other=3,states=states,live=live)
            self.assertAlmostEqual(states[0].plan.target_priority['wr'],.065)
