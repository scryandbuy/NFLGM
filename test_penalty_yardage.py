"""Boundary cases for penalty enforcement, turnovers and scoring yardage."""
import unittest
from unittest.mock import patch

import numpy as np

import events
import game
import ticker


class PenaltyYardageTests(unittest.TestCase):
    def drive(self, spot=70, down=2, togo=10):
        dr = game.Drive({}, {}, spot, 1800, 2, 0, np.random.default_rng(1))
        dr.down, dr.togo = down, togo
        return dr

    def flag(self, offense, name='Unnecessary Roughness', yards=15):
        return dict(penalty=name, yards=float(yards), rule_yards=float(yards),
                    on_offense=offense, auto_first=not offense, nullifies=False)

    def test_goal_to_go_survives_penalty_beyond_twenty(self):
        self.assertEqual(ticker._down(3, 22, 22), '3rd & Goal')
        self.assertEqual(ticker._down(3, 12, 22), '3rd & 12')

    def test_illegal_formation_is_live_and_erases_touchdown(self):
        self.assertEqual(events.PEN_INFO['Illegal Formation']['phase'], 'any')
        dr = self.drive(9, down=3, togo=9)
        flag = self.flag(True, 'Illegal Formation', 5)
        result = game._resolve_live_penalty(dr, flag, {'type': 'complete', 'yards': 9}, {})
        self.assertEqual(result, 'replaced')
        self.assertEqual((dr.down, dr.yardline, dr.togo), (3, 14, 14))
        self.assertIsNone(dr.result)

    def test_roughing_keeps_completion_and_adds_yards(self):
        dr = self.drive(47, down=2, togo=13)
        flag = self.flag(False, 'Roughing the Passer', 15)
        self.assertEqual(game._resolve_live_penalty(dr, flag, {'type':'complete','yards':8}, {}), 'added')
        game._advance(dr, 8)
        self.assertEqual((dr.yardline, dr.down, dr.togo), (24, 1, 10))

    def test_roughing_on_interception_replaces_play(self):
        dr = self.drive(47)
        flag = self.flag(False, 'Roughing the Passer', 15)
        self.assertEqual(game._resolve_live_penalty(dr, flag, {'type':'interception','yards':0,'air':8,'ret':0}, {}), 'replaced')
        self.assertEqual(dr.yardline, 32)

    def test_week16_roughing_keeps_ten_yard_catch(self):
        dr = self.drive(43, down=1, togo=10)
        flag = self.flag(False, 'Roughing the Passer', 15)
        out = {'type':'complete', 'yards':10}
        self.assertEqual(game._resolve_live_penalty(dr, flag, out, {}), 'added')
        game._advance(dr, out['yards'])
        self.assertEqual((dr.yardline, dr.down, dr.togo), (18, 1, 10))
        self.assertFalse(out.get('nullified', False))

    def test_roughing_after_catch_uses_half_distance_and_keeps_touchdown(self):
        dr = self.drive(8)
        flag = self.flag(False, 'Roughing the Passer', 15)
        self.assertEqual(game._resolve_live_penalty(dr, flag, {'type':'complete','yards':4}, {}), 'added')
        game._advance(dr, 4)
        self.assertEqual(dr.yardline, 2)
        dr = self.drive(8)
        flag = self.flag(False, 'Roughing the Passer', 15)
        self.assertEqual(game._resolve_live_penalty(dr, flag, {'type':'complete','yards':8,'touchdown':True}, {}), 'added')
        game._advance(dr, 8)
        self.assertEqual(dr.result, 'Touchdown')
        self.assertEqual(dr.try_penalty, 15)

    def test_dead_ball_offensive_foul_follows_first_down(self):
        dr = self.drive()
        p = self.flag(True)
        self.assertEqual(game._resolve_live_penalty(dr, p, {'type': 'run', 'yards': 20}, {}), 'added')
        self.assertFalse(game._advance(dr, 20))
        self.assertEqual((dr.yardline, dr.down, dr.togo, dr.first_downs), (65, 1, 10, 1))

    def test_touchdown_stands_and_foul_moves_try(self):
        dr = self.drive(4)
        p = self.flag(True)
        self.assertEqual(game._resolve_live_penalty(dr, p, {'type': 'run', 'yards': 5}, {}), 'added')
        self.assertTrue(p['on_try'])
        self.assertTrue(game._advance(dr, 5))
        self.assertEqual((dr.result, dr.points, dr.try_penalty), ('Touchdown', 6, -15))

    def test_score_from_inside_one_does_not_round_back_to_zero(self):
        dr = self.drive(.5, togo=.5)
        flag = self.flag(True)
        self.assertEqual(game._resolve_live_penalty(dr, flag, {'type': 'run', 'yards': .5}, {}), 'added')
        self.assertTrue(flag['on_try'])
        self.assertTrue(game._advance(dr, .5))
        self.assertEqual((dr.yardline, dr.result), (0, 'Touchdown'))

    def test_score_stats_use_actual_distance_to_goal(self):
        dr = self.drive(4)
        out = {'type': 'complete', 'yards': 11.2, 'target': 'WR'}
        game._prepare_scoring_play(dr, out)
        book = game.StatBook()
        off = {'qb': {'pid': 'QB'}, 'wr': [{'pid': 'WR'}]}
        book.record(out, off, {'db': [], 'lb': [], 'dl': []}, np.random.default_rng(1))
        self.assertEqual((out['yards'], book.p['QB']['pass_yds'], book.p['WR']['rec_yds']), (4, 4, 4))
        self.assertEqual((book.p['QB']['pass_td'], book.p['WR']['rec_td']), (1, 1))

    def test_defensive_post_foul_uses_half_distance_at_goal(self):
        dr = self.drive(1.5, togo=1.5)
        p = self.flag(False)
        self.assertEqual(game._resolve_live_penalty(dr, p, {'type': 'run', 'yards': 1}, {}), 'added')
        self.assertAlmostEqual(p['yards'], .25)
        self.assertFalse(game._advance(dr, 1))
        self.assertAlmostEqual(dr.yardline, .25)
        self.assertEqual(dr.down, 1)

    def test_end_zone_interference_inside_two_uses_half_distance(self):
        dr = self.drive(1.5, down=2, togo=1.5)
        p = self.flag(False, 'Defensive Pass Interference', 15)
        self.assertEqual(game._resolve_live_penalty(dr, p,
                         {'type': 'incomplete', 'yards': 0, 'air': 10}, {}), 'replaced')
        self.assertAlmostEqual(dr.yardline, .75)
        self.assertAlmostEqual(p['spot'], .75)

    def test_goal_line_kick_foul_never_places_ball_in_end_zone(self):
        dr = self.drive(99, down=4, togo=3)
        p = self.flag(True, 'False Start', 5)
        p['phase'] = 'pre'
        self.assertTrue(game._kick_presnap_flag(dr, p))
        self.assertEqual((dr.yardline, dr.togo, p['yards']), (99.5, 3.5, .5))
        self.assertEqual(ticker._spot(dr.yardline, 'GB', 'MIN'), 'GB 1')

    def test_interception_catch_return_and_turnover_foul(self):
        dr = self.drive(70)
        dr.yardline = game._interception_spot(dr.yardline, {'air': 20, 'ret': 12})
        self.assertEqual(dr.yardline, 62)
        p = self.flag(True)
        game._enforce_turnover_penalty(dr, p)
        self.assertEqual(dr.yardline, 77)
        self.assertEqual(game._interception_spot(12, {'air': 20, 'ret': 0}), 20)

    def test_defensive_hands_is_five_and_grounding_requires_throwaway(self):
        class Draw:
            calls = 0
            def random(self):
                self.calls += 1
                return 0 if self.calls == 1 else .9
            def choice(self, items, p=None):
                return events._names.index('Illegal Use of Hands')
        p = events.penalty_check(Draw())
        self.assertEqual((p['yards'], p['rule_yards'], p['on_offense']), (5, 5, False))
        dr = self.drive()
        grounding = self.flag(True, 'Intentional Grounding', 10)
        self.assertIsNone(game._resolve_live_penalty(dr, grounding,
                            {'type': 'incomplete', 'yards': 0, 'pressured': True, 'throwaway': False}, {}))
        roughing = self.flag(False, 'Roughing the Passer')
        self.assertIsNone(game._resolve_live_penalty(dr, roughing,
                            {'type': 'sack', 'yards': -5}, {}))

    def test_grounding_from_own_end_zone_is_safety(self):
        dr = self.drive(99, down=2, togo=10)
        p = self.flag(True, 'Intentional Grounding', 10)
        taken = game._resolve_live_penalty(dr, p,
                    {'type': 'incomplete', 'yards': 0, 'pressured': True,
                     'throwaway': True, 'throwback': 3}, {})
        self.assertEqual(taken, 'replaced')
        self.assertEqual((dr.result, dr.points, p['safety']), ('Safety', -2, True))

    def test_roughing_kicker_replays_as_first_down(self):
        dr = self.drive(30, down=4, togo=7)
        kick = {'type': 'field_goal', 'made': False}
        p = self.flag(False, 'Roughing the Kicker')
        p['phase'] = 'kick'
        self.assertTrue(game._kick_roughing(dr, p, kick))
        self.assertEqual((dr.yardline, dr.down, dr.togo), (15, 1, 10))
        self.assertTrue(kick['nullified'])

    def test_made_field_goal_declines_defensive_offside(self):
        dr = self.drive(30, down=4, togo=7)
        p = self.flag(False, 'Defensive Offside', 5)
        p['phase'] = 'kick_offside'
        self.assertFalse(game._kick_offside(dr, p, {'type': 'field_goal', 'made': True}))
        self.assertEqual((dr.yardline, dr.down, dr.togo), (30, 4, 7))
        self.assertTrue(game._kick_offside(dr, p, {'type': 'field_goal', 'made': False}))
        self.assertEqual((dr.yardline, dr.down, dr.togo), (25, 4, 2))

    def test_kickoff_return_foul_moves_receiving_team_back(self):
        p = self.flag(True, 'Illegal Block in Back', 10)
        p['phase'] = 'return'
        with patch.object(game, 'kickoff', return_value={'type': 'kickoff', 'touchback': False,
                                                         'ret': 25, 'new_yardline': 70}), \
             patch.object(events, 'special_teams_penalty_check', return_value=p):
            kick = game.kickoff_booked({'pid': 'KR'}, np.random.default_rng(1), lambda *_: .7, None)
        self.assertEqual(kick['new_yardline'], 80)
        self.assertEqual(kick['penalty']['yards'], 10)
        self.assertTrue(kick['penalty']['on_offense'])

    def test_extra_point_foul_changes_kick_distance(self):
        p = self.flag(True, 'False Start', 5)
        p['phase'] = 'pre'
        with patch.object(events, 'special_teams_penalty_check', return_value=p):
            result = game.attempt_extra_point({}, np.random.default_rng(2), lambda *_: .7)
        self.assertEqual((result['distance'], result['penalty']['yards']), (38, 5))

    def test_defensive_offside_replays_failed_extra_point(self):
        p = self.flag(False, 'Defensive Offside', 5)
        p['phase'] = 'kick_offside'
        class Draw:
            values = iter((.9, .1))
            def random(self): return next(self.values)
        with patch.object(events, 'special_teams_penalty_check', return_value=p), \
             patch.object(game, 'fg_probability', return_value=.5), \
             patch.object(game, 'snap_quality', return_value=0):
            result = game.attempt_extra_point({}, Draw(), lambda *_: .7)
        self.assertTrue(result['made'])
        self.assertEqual((result['distance'], result['penalty']['yards']), (28, 5))

    def test_defensive_offside_replays_failed_two_point_try(self):
        p = self.flag(False, 'Defensive Offside', 5)
        p['phase'] = 'kick_offside'
        plays = iter(({'type': 'incomplete', 'yards': 0}, {'type': 'run', 'yards': 1}))
        with patch.object(events, 'special_teams_penalty_check', return_value=p), \
             patch.object(game, 'field_units', return_value=({}, {})):
            result = game.attempt_two_point({}, {}, np.random.default_rng(1),
                     lambda *_: next(plays), lambda *_a, **_k: {'personnel': '11', 'is_pass': True},
                     lambda *_a, **_k: {'personnel': 'nickel', 'front_family': '4-3'},
                     lambda *_: .7)
        self.assertEqual((result['points'], result['from_yardline'], result['penalty']['yards']), (2, 1, 1))


if __name__ == '__main__':
    unittest.main()
