"""Reported Week 9 spots, credited plays and one-score clock budgets."""
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import numpy as np
import decisions as D
import events as E
import game as G
import test_game_clock_decisions as clocks


def facemask():
    return dict(penalty='Face Mask', yards=15., rule_yards=15.,
                on_offense=True, auto_first=False, nullifies=False)


class TenGbRules(unittest.TestCase):
    def test_reported_screen_keeps_gain_and_repeats_first_at_gb14(self):
        dr = G.Drive({}, {}, 75, 3200, 1, 0, None)
        dr.togo = 20
        out = dict(type='complete', yards=3, screen=True)
        flag = facemask()
        self.assertEqual(G._resolve_live_penalty(dr, flag, out, {}), 'enforced')
        self.assertEqual((dr.yardline, dr.down, dr.togo, flag['yards']), (86, 1, 31, 14))
        self.assertFalse(out['converted'])
        self.assertFalse(out.get('nullified', False))

    def test_live_foul_tests_first_down_after_walkoff(self):
        for yards, state in ((12, (73, 2, 13)), (30, (55, 1, 10))):
            dr = G.Drive({}, {}, 70, 3000, 1, 0, None)
            dr.down = 2
            out = dict(type='complete', yards=yards)
            self.assertEqual(G._resolve_live_penalty(dr, facemask(), out, {}), 'enforced')
            self.assertEqual((dr.yardline, dr.down, dr.togo), state)
            self.assertEqual(dr.first_downs, int(yards == 30))
            self.assertEqual(out['converted'], yards == 30)

    def test_defense_can_decline_instead_of_giving_back_fourth_down(self):
        dr = G.Drive({}, {}, 70, 3000, 1, 0, None)
        dr.down = 4
        self.assertIsNone(G._resolve_live_penalty(dr, facemask(), dict(type='run', yards=3), {}))
        G._advance(dr, 3)
        self.assertEqual(dr.down, 5)

    def penalty_drive(self, live=False):
        off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                   wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        deff = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        outcomes = iter([dict(type='complete', yards=3, screen=True, target='wr'),
                         dict(type='interception', yards=0, air=0, ret=0)])
        book = G.StatBook()
        with ExitStack() as st:
            st.enter_context(patch.object(E, 'penalty_check', return_value=None))
            st.enter_context(patch.object(E, 'contextual_penalty', side_effect=[facemask(), None]))
            st.enter_context(patch.object(E, 'fumble_check', return_value=None))
            st.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            st.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            args = (off, deff, 75, 3224, 1, 0, np.random.default_rng(11),
                lambda *a: next(outcomes),
                lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                lambda *a, **k: dict(personnel='nickel', front_family='4-3'), lambda *a: .7)
            if live:
                gen = G.drive_steps(*args, book=book, start_state=(1,20))
                while True:
                    try: next(gen)
                    except StopIteration as end:
                        dr = end.value; break
            else:
                dr = G.run_drive(*args, book=book, start_state=(1,20))
        return dr, book

    def test_penalty_retains_completion_stats_and_next_snap_in_live_and_sim(self):
        dr, book = self.penalty_drive()
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual((snaps[1]['yardline'], snaps[1]['down'], snaps[1]['ydstogo']), (86, 1, 31))
        self.assertEqual((dr.plays, book.p['qb']['pass_att'], book.p['qb']['pass_cmp'],
                          book.p['qb']['pass_yds'], book.p['wr']['rec_yds']), (2, 2, 1, 3, 3))
        self.assertIn('epa', snaps[0])
        live, lb = self.penalty_drive(live=True)
        self.assertEqual(dr.log, live.log)
        self.assertEqual(book.p, lb.p)

    def test_missed_kick_distance_spot_and_twenty_floor(self):
        for line, distance, start in ((42,59,51), (13,30,80), (4,21,80), (43,60,50)):
            self.assertEqual(D.field_goal_distance(line), distance)
            self.assertEqual(D.missed_field_goal_start(line), start)
            with patch.object(D, '_flip', return_value=.5) as flip:
                D.fourth_down(0, 1800, line, min(8,line/2), fg_prob=.6)
            self.assertEqual(flip.call_args_list[2].args[2], 100-start)

    def test_overtime_miss_places_next_possession_at_kick_spot(self):
        for line, expected in ((42,51), (4,80)):
            starts = []
            def drive(off, deff, start, clock, quarter, diff, *a, **kw):
                starts.append(start)
                dr = G.Drive(off, deff, line, clock-30 if len(starts)==1 else 0, quarter, diff, None)
                dr.result = 'Missed field goal' if len(starts)==1 else 'Field goal'
                dr.points = 0 if len(starts)==1 else 3
                return dr
            with patch.object(G, 'run_drive', side_effect=drive), \
                 patch.object(G, 'kickoff_for', return_value=dict(new_yardline=65, ret=0)), \
                 patch.object(G, 'kickoff_clock', side_effect=lambda clock, kick: clock):
                G.LAST_KICKOFF.clear()
                G.play_overtime({}, {}, dict(home=0,away=0), np.random.default_rng(1), None,None,None,None)
            self.assertEqual(starts, [65,expected])

    def test_regulation_miss_uses_same_spot(self):
        starts = []
        def drive(off, deff, start, clock, quarter, diff, *a, **kw):
            starts.append(start)
            dr = G.Drive(off, deff, 42, clock-30, quarter, diff, None)
            dr.result = 'Missed field goal'
            if False: yield
            return dr
        with patch.object(G, 'drive_steps', side_effect=drive), \
             patch.object(G, 'kickoff_for', return_value=dict(new_yardline=65, ret=0)), \
             patch.object(G, 'kickoff_clock', side_effect=lambda clock, kick: clock):
            gen = G.game_steps({}, {}, np.random.default_rng(1), None,None,None,None)
            try:
                while len(starts)<2: next(gen)
            finally: gen.close()
        self.assertEqual(starts, [65,51])

    def test_one_score_pace_preserves_reply_and_coach_tempo(self):
        pace = G.comeback_pace(367,-8,4,yardline=73,timeouts=3)
        self.assertGreater(pace, .3)
        self.assertLess(pace, 1)
        self.assertGreater(G.comeback_pace(367,-8,4,yardline=73,timeouts=0), pace)
        slow = G.play_seconds('run', tempo=.2, catchup=pace)
        fast = G.play_seconds('run', tempo=.8, catchup=pace)
        self.assertGreater(slow,fast)
        self.assertLess(slow,G.play_seconds('run',tempo=.2))
        for diff,q,sec,line in ((-8,3,1000,73),(-8,4,700,73),(-2,4,200,15),(3,4,200,73),(0,4,200,73)):
            self.assertEqual(G.comeback_pace(sec,diff,q,yardline=line),0)

    def test_live_drive_uses_one_score_budget(self):
        fixture = clocks.ClockDecisions(); fixture.setUp()
        outcomes = [dict(type='run',yards=4),dict(type='interception',yards=0,air=0,ret=0)]
        dr, _, _ = fixture.drive(outcomes,start=73,clock=367,quarter=4,wall=None,diff=-8,own=3,other=3)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertLess(snaps[0]['clock']-snaps[1]['clock'],32)
        self.assertGreater(snaps[0]['clock']-snaps[1]['clock'],14)


if __name__ == '__main__': unittest.main()
