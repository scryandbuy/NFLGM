"""Reported DEN–GB clock, enforcement, possession and decision regressions."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import events as E
import game as G
import gameday
import ticker


class DenverGameFixes(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                        wr=[dict(pid='wr', pos='WR')], te=[], ol=[], p={}, k={})
        self.defense = dict(db=[dict(pid='db', pos='CB')], lb=[dict(pid='lb', pos='MIKE')], dl=[])
        G.LAST_KICKOFF.clear()

    def drive(self, outcomes, start=75, clock=300, quarter=4, half_end=None,
              diff=5, tos=0, flag=None, fourth='punt'):
        outcomes = iter(outcomes)
        timeouts = G.Timeouts()
        timeouts.left = dict(home=0, away=tos)
        book = G.StatBook()
        with ExitStack() as stack:
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=[flag] + [None] * 30))
            stack.enter_context(patch.object(E, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=None))
            decision = stack.enter_context(patch.object(G, 'fourth_down_decision', return_value=fourth))
            stack.enter_context(patch.object(G, 'punt', return_value=dict(type='punt', gross=40, net=40, ret=0, touchback=False, new_yardline=65)))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            dr = G.run_drive(self.off, self.defense, start, clock, quarter, diff,
                            np.random.default_rng(2), lambda *a: dict(target='wr', **next(outcomes)),
                            lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                            lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                            lambda *a: .7, book=book, timeouts=timeouts, half_end=half_end)
        return dr, book, decision

    def test_halftime_own_end_punt_keeps_game_end_desperation_separate(self):
        for diff in (-14, 1, 7):
            self.assertEqual(G.fourth_down_decision(75, 2, diff, 1814,
                             np.random.default_rng(1), half_seconds_left=14), 'punt')
        self.assertEqual(G.fourth_down_decision(75, 2, -5, 14,
                         np.random.default_rng(1)), 'go')
        self.assertEqual(G.fourth_down_decision(20, 2, -3, 5,
                         np.random.default_rng(1)), 'field_goal')

    def test_drive_passes_half_clock_without_replacing_game_clock(self):
        dr, _, decision = self.drive([dict(type='incomplete', yards=0)] * 3,
                                    clock=1850, quarter=2, half_end=1800)
        args, kw = decision.call_args
        self.assertGreater(args[3], 1800)
        self.assertAlmostEqual(kw['half_seconds_left'], args[3] - 1800)

    def test_live_facemask_retains_run_and_enforces_from_end(self):
        flag = dict(penalty='Face Mask', on_offense=False, yards=15, rule_yards=15,
                    auto_first=True, nullifies=False)
        dr, book, _ = self.drive([dict(type='run', yards=8),
                                 dict(type='interception', yards=0, air=0, ret=0)], start=39, flag=flag)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual((snaps[1]['yardline'], snaps[1]['down'], snaps[1]['ydstogo']), (16, 1, 10))
        self.assertFalse(snaps[0].get('nullified'))
        self.assertEqual(book.p['rb']['rush_yds'], 8)
        self.assertEqual(dr.plays, 2)

    def test_facemask_half_distance_uses_end_of_run(self):
        dr = G.Drive({}, {}, 20, 300, 4, 0, None)
        flag = dict(penalty='Face Mask', on_offense=False, yards=15, auto_first=True)
        self.assertEqual(G._resolve_live_penalty(dr, flag, dict(type='run', yards=8), {}), 'added')
        G._advance(dr, 8)
        self.assertEqual((dr.yardline, dr.down, flag['yards']), (6, 1, 6))

    def test_warning_removes_huddle_but_preserves_live_play(self):
        for wall, quarter in ((0, 4), (1800, 2)):
            for secs, expected in ((124, 118), (152, 120), (121, 115)):
                with self.subTest(wall=wall, secs=secs):
                    dr, _, _ = self.drive([dict(type='run', yards=1),
                                           dict(type='interception', air=0, ret=0)],
                                          clock=wall + secs, quarter=quarter, half_end=wall or None)
                    warning = [p for p in dr.log if p['type'] == 'two_minute']
                    self.assertEqual(len(warning), 1)
                    self.assertEqual(warning[0]['clock'], wall + expected)
                    self.assertEqual(next(p for p in dr.log if p['type'] == 'interception')['clock'], wall + expected)

    def test_interception_drive_yards_exclude_catch_and_return(self):
        for air, ret in ((36, 20), (90, 0), (0, 20)):
            dr, book, _ = self.drive([dict(type='complete', yards=10),
                                     dict(type='interception', yards=0, air=air, ret=ret)], start=77)
            endpoint = dr.yardline
            league = NS(player=lambda pid: None, week=5, teams={a: NS(roster=[]) for a in ('GB', 'DEN')})
            res = dict(home=0, away=0, drives=[('home', dr)], overtime=False)
            rendered = gameday.capture(league, [('GB', 'DEN', res, book)], 'GB')['game']
            self.assertEqual(rendered['drives'][0]['yards'], 10)
            self.assertEqual(rendered['drives'][0]['end'], 33)
            self.assertEqual(dr.yardline, endpoint)
            self.assertEqual(rendered['team_stats']['GB']['turnovers'], 1)
            self.assertEqual(rendered['team_stats']['GB']['red_zone'], '0/0')
            self.assertEqual(ticker.write_game(league, res, 'GB', 'DEN')[0]['end'], 33)

    def test_final_32_seconds_no_timeout_takes_victory_kneel(self):
        dr, _, _ = self.drive([], start=89, clock=32)
        self.assertEqual([p['type'] for p in dr.log], ['kneel'])
        self.assertEqual(dr.clock, 0)
        for kwargs in (dict(tos=1), dict(diff=-5), dict(start=99.5),
                       dict(clock=1832, quarter=2, half_end=1800)):
            dr, _, _ = self.drive([dict(type='interception', yards=0, air=0, ret=0)],
                                 **dict(dict(start=89, clock=32), **kwargs))
            self.assertFalse(any(p['type'] == 'kneel' for p in dr.log))

    def test_fourth_down_cannot_kneel_away_32_seconds(self):
        dr, _, decision = self.drive([dict(type='incomplete', yards=0)] * 4, clock=66,
                                    fourth='go')
        self.assertTrue(decision.called)
        self.assertEqual(dr.result, 'Turnover on downs')
        self.assertFalse(any(p['type'] == 'kneel' for p in dr.log))


if __name__ == '__main__':
    unittest.main()
