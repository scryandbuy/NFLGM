"""Reproduce the six defects reported in the LAC–GB Week 2 game log."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import events
import game
import gameday
import ticker


class ReportedGameFixes(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='starter', pos='QB'),
                        qbs=[dict(pid='starter', pos='QB'), dict(pid='backup', pos='QB')],
                        rb=dict(pid='back', pos='HB'), wr=[dict(pid='receiver', pos='WR')], ol=[], te=[])
        self.defense = dict(db=[], lb=[], dl=[])
        self.league = NS(player=lambda pid: None, week=2,
                         teams={t: NS(roster=[]) for t in ('GB', 'LAC')})

    def drive(self, outcome=None, start=48, clock=2, quarter=4, diff=0, state=None, half_end=None):
        calls = []
        def resolve(off, defense, oc, dc, *args):
            calls.append(dict(oc))
            return dict(outcome or dict(type='incomplete', yards=0))
        game.LAST_KICKOFF.clear()
        with patch.object(events, 'penalty_check', return_value=None), \
             patch.object(events, 'fumble_check', return_value=None), \
             patch.object(game, 'field_units', side_effect=lambda roster, *a, **k: (roster, {})), \
             patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)):
            dr = game.run_drive(self.off, self.defense, start, clock, quarter, diff,
                    np.random.default_rng(2), resolve,
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                    lambda *a: .7, off_state=state, half_end=half_end)
        return dr, calls

    def test_injured_qb_cannot_take_halftime_kneel(self):
        state = NS(out={'starter'}, coach={}, new_series=lambda: None, adjust=lambda *a: None)
        dr, calls = self.drive(start=70, clock=1801, quarter=2, state=state, half_end=1800)
        self.assertFalse(calls)
        self.assertEqual(dr.log[-1]['type'], 'kneel')
        self.assertEqual(dr.log[-1]['passer'], 'backup')
        self.assertEqual(dr.clock, 1800)

    def test_all_qbs_out_uses_healthy_emergency_player(self):
        state = NS(out={'starter', 'backup'}, coach={}, new_series=lambda: None, adjust=lambda *a: None)
        dr, _ = self.drive(start=70, clock=1801, quarter=2, state=state, half_end=1800)
        self.assertEqual(dr.log[-1]['passer'], 'back')

    def test_final_two_seconds_allow_a_snap_and_downfield_attempt(self):
        dr, calls = self.drive()
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]['is_pass'], calls[0]['depth'], calls[0]['concept']),
                         (True, 'deep', 'four_verts'))
        self.assertFalse(any(p.get('type') == 'kneel' for p in dr.log))
        self.assertLessEqual(dr.clock, 0)

    def test_final_choices_preserve_kick_range_safe_kneel_and_no_snap_at_zero(self):
        for spot, diff, expected in ((20, 0, 'kick'), (70, 0, 'kneel'), (48, -7, 'shot'), (70, -7, 'shot')):
            dr = game.Drive(self.off, self.defense, spot, 1, 4, diff, None)
            plan = game.end_of_half_plan(dr, self.off, self.defense, lambda *a: .7,
                                        None, 'home', None, 1)
            self.assertEqual(plan['choice'], expected)
        dr, calls = self.drive(diff=7)
        self.assertFalse(calls)
        self.assertEqual(dr.log[-1]['type'], 'kneel')
        dr, calls = self.drive(clock=0)
        self.assertFalse(calls)

    def test_end_zone_interception_return_uses_actual_spot(self):
        dr, _ = self.drive(dict(type='interception', yards=0, air=47, ret=4),
                           start=45, clock=120, diff=0)
        play = next(p for p in dr.log if p.get('type') == 'interception')
        self.assertEqual(dr.yardline, 2)  # new possession starts on its own 2
        self.assertFalse(play['touchback'])
        self.assertEqual(play['ret'], 4)
        self.assertIn('returned 4 yards', ticker.play_line(self.league, play, 'LAC', 'GB')['text'])

    def test_return_still_inside_end_zone_is_touchback_with_no_return_credit(self):
        dr, _ = self.drive(dict(type='interception', yards=0, air=50, ret=4),
                           start=45, clock=120, diff=0)
        play = next(p for p in dr.log if p.get('type') == 'interception')
        self.assertEqual(dr.yardline, 20)
        self.assertEqual((play['touchback'], play['ret']), (True, 0))
        text = ticker.play_line(self.league, play, 'LAC', 'GB')['text']
        self.assertIn('touchback', text)
        self.assertNotIn('returned', text)
        untouched = dict(type='interception', air=50, ret=4)
        game._interception_spot(45, untouched)
        self.assertEqual(untouched['ret'], 4)  # expected-points preview is read-only

    def test_short_dpi_is_a_spot_foul_but_real_half_distance_stays(self):
        dr = game.Drive({}, {}, 72, 1000, 3, 0, None)
        flag = dict(penalty='Defensive Pass Interference', on_offense=False,
                    yards=15, rule_yards=15, auto_first=True, nullifies=True)
        self.assertEqual(game._resolve_live_penalty(dr, flag,
                         dict(type='incomplete', yards=0, air=4), {}), 'replaced')
        self.assertEqual(dr.yardline, 68)
        text = ticker.play_line(self.league, dict(flag, type='penalty'), 'LAC', 'GB')['text']
        self.assertIn('4 yards', text)
        self.assertNotIn('half the distance', text)
        flag.update(penalty='Defensive Holding', rule_yards=5, yards=2)
        self.assertIn('half the distance', ticker.play_line(self.league, dict(flag, type='penalty'), 'LAC', 'GB')['text'])

    def test_fractional_goal_line_spot_does_not_imply_a_missing_touchdown(self):
        for kind in ('run', 'complete', 'scramble'):
            dr = game.Drive({}, {}, 3.4, 1000, 3, 0, None)
            play = dict(type=kind, yards=3, yardline=3.4, down=2, ydstogo=3.4, clock=1000)
            game._prepare_scoring_play(dr, play)
            self.assertFalse(game._advance(dr, 3))
            text = ticker.play_line(self.league, play, 'LAC', 'GB')['text']
            self.assertIn('just short of the goal line', text)
            self.assertNotIn('TOUCHDOWN', text)
            self.assertEqual(ticker._spot(dr.yardline, 'LAC', 'GB'), 'inside the GB 1')
        td = ticker.play_line(self.league, dict(type='run', yardline=.4, yards=.4,
                                             touchdown=True), 'LAC', 'GB')['text']
        self.assertIn('inside the 1. TOUCHDOWN', td)

    def test_regulation_and_overtime_end_labels_in_both_game_reports(self):
        for quarters, overtime, expected in (([2, 4, 5], True, ['End of half', 'End of regulation', 'End of game']),
                                              ([4], False, ['End of game'])):
            drives = []
            for q in quarters:
                dr = game.Drive(self.off, self.defense, 70, 1801 if q == 2 else 1, q, 0, None)
                dr.result, dr.clock = 'End of half', 1800 if q == 2 else 0
                drives.append(('home', dr))
            res = dict(home=0, away=0, overtime=overtime, drives=drives)
            report = gameday.capture(self.league, [('GB', 'LAC', res, game.StatBook())], 'GB')['game']
            self.assertEqual([d['result'] for d in report['drives']], expected)
            self.assertEqual([d['result'] for d in ticker.write_game(self.league, res, 'GB', 'LAC')], expected)


if __name__ == '__main__':
    unittest.main()
