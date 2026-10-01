import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import numpy as np
import decisions as D
import game as G
import events as E
import gameday
import ticker


class GameLogRegressions(unittest.TestCase):
    def test_overtime_reply_never_punts_and_tying_field_goal_remains_available(self):
        for draw in (0, .5, .999999):
            rng = NS(random=lambda: draw)
            self.assertEqual(G.fourth_down_decision(66, 1, -7, 130, rng, must_score=True), 'go')
            self.assertEqual(G.fourth_down_decision(23, 4, -3, 200, rng, must_score=True), 'field_goal')
            self.assertEqual(G.fourth_down_decision(80, 24, -3, 200, rng, must_score=True), 'go')

    def test_long_fourth_down_is_not_eight_yards_and_desperation_still_goes(self):
        self.assertLess(D.fourth_conversion(24), .04)
        self.assertGreater(D.fourth_conversion(12), D.fourth_conversion(24))
        for draw in (0, .5, .999999):
            rng = NS(random=lambda: draw)
            self.assertEqual(G.fourth_down_decision(32, 24, -10, 2015, rng), 'field_goal')
            self.assertEqual(G.fourth_down_decision(66, 24, -7, 6, rng), 'go')

    def test_overtime_supplies_shared_timeouts_book_and_reply_context(self):
        calls = []
        book = object()
        def drive(off, deff, start, clock, quarter, diff, rng, *args, **kw):
            calls.append((diff, args, kw))
            dr = G.Drive(off, deff, start, clock, quarter, diff, rng)
            dr.clock = clock - 80
            dr.result = 'Touchdown' if len(calls) == 1 else 'Turnover on downs'
            dr.points = 7 if len(calls) == 1 else 0
            return dr
        with patch.object(G, 'kickoff_booked', return_value=dict(new_yardline=65, touchback=True)), \
             patch.object(G, 'run_drive', side_effect=drive):
            score, drives, result = G.play_overtime({}, {}, dict(home=30, away=30),
                np.random.default_rng(1), None, None, None, None, first='home', book=book)
        self.assertEqual(score, dict(home=37, away=30))
        self.assertFalse(calls[0][2]['must_score'])
        self.assertTrue(calls[1][2]['must_score'])
        self.assertEqual(calls[1][2]['pos'], 'away')
        self.assertIs(calls[0][2]['timeouts'], calls[1][2]['timeouts'])
        self.assertEqual(calls[0][2]['timeouts'].left, dict(home=2, away=2))
        self.assertIs(calls[0][1][5], book)

    def snaps(self, clock, quarter, outcomes, plan=None, penalties=None, half_end=None):
        off = dict(qb={'pid': 'qb'}, rb={'pid': 'rb'}, wr=[{'pid': 'wr'}], ol=[], te=[])
        deff = dict(db=[], lb=[], dl=[])
        flags = iter(penalties or [])
        plays = iter(outcomes)
        def resolve(*args):
            return dict(next(plays))
        def co(*args, **kwargs):
            return dict(is_pass=True, personnel='11', depth='short')
        def cd(*args, **kwargs):
            return dict(personnel='nickel', front_family='4-3')
        G.LAST_KICKOFF.clear()
        with patch.object(E, 'penalty_check', side_effect=lambda *a, **k: next(flags, None)), \
             patch.object(E, 'fumble_check', return_value=None), \
             patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})), \
             patch.object(G, 'end_of_half_plan', side_effect=plan or (lambda *a, **k: None)), \
             patch.object(G, 'attempt_extra_point', return_value=dict(type='extra_point', points=1, made=True)), \
             patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)):
            # A tied game keeps these clock/penalty cases outside victory formation.
            return G.run_drive(off, deff, 45, clock, quarter, 0, np.random.default_rng(2),
                resolve, co, cd, lambda *a: .7, half_end=half_end)

    def test_bleed_does_not_add_another_full_play_clock(self):
        def plan(dr, *args, **kwargs):
            if dr.plays:
                return dict(choice='shot', hurry=False)
            return None
        dr = self.snaps(1887, 2, [dict(type='run', yards=16), dict(type='complete', yards=29)],
                        plan=plan, half_end=1800)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertLessEqual(snaps[0]['clock'] - snaps[1]['clock'], 40)
        self.assertGreater(snaps[1]['clock'] - 1800, 40)

    def test_presnap_foul_on_stopped_clock_does_not_burn_fourteen_seconds(self):
        flag = dict(penalty='False Start', yards=5, rule_yards=5,
                    on_offense=True, auto_first=False, nullifies=True)
        dr = self.snaps(120, 4, [dict(type='complete', yards=50)], penalties=[flag])
        snap = next(p for p in dr.log if p.get('down'))
        self.assertEqual(snap['clock'], 120)
        self.assertEqual(snap['ydstogo'], 15)
        self.assertEqual(dr.log[0]['timing'], 'before_snap')

    def test_cross_quarter_drive_updates_tactics_and_score_period(self):
        seen = []
        def plan(dr, *args, **kwargs):
            seen.append(dr.quarter)
            return None
        dr = self.snaps(2710, 1, [dict(type='run', yards=5), dict(type='complete', yards=40)],
                        plan=plan, half_end=1800)
        self.assertEqual(dr.start_quarter, 1)
        self.assertIn(2, seen)
        self.assertEqual(gameday.scoring_quarter(dr), 2)
        self.assertTrue(any(p.get('type') == 'period' and p['quarter'] == 2 for p in dr.log))

    def test_legacy_scoring_quarter_uses_snap_and_boundary_kick_uses_previous_period(self):
        dr = G.Drive({}, {}, 30, 2750, 1, 0, None)
        dr.log = [dict(type='complete', touchdown=True, clock=2600)]
        dr.clock = 2594
        self.assertEqual(gameday.scoring_quarter(dr), 2)
        dr.log = [dict(type='field_goal', made=True)]; dr.clock = 900
        self.assertEqual(gameday.scoring_quarter(dr), 3)

    def test_try_flags_and_period_breaks_are_explicit(self):
        league = NS(player=lambda pid: None)
        for kind, word in (('extra_point', 'extra-point'), ('two_point', 'two-point')):
            flag = dict(type='penalty', penalty='False Start', on_offense=True,
                        yards=5, try_type=kind)
            self.assertIn(word, ticker.play_line(league, flag, 'GB', 'NYJ')['text'])
        self.assertEqual(ticker.play_line(league, dict(type='period', quarter=5), 'GB', 'NYJ')['text'], 'Overtime begins.')


if __name__ == '__main__':
    unittest.main()
