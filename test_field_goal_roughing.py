import unittest
from unittest.mock import patch
import numpy as np
import game


class FieldGoalRoughingTests(unittest.TestCase):
    def drive(self, clock=2067, quarter=2, diff=-24, spot=18):
        dr = game.Drive({}, {}, spot, clock, quarter, diff, np.random.default_rng(1))
        dr.down, dr.togo = 4, 8
        return dr

    def flag(self):
        return dict(penalty='Roughing the Kicker', phase='kick', yards=15,
                    rule_yards=15, auto_first=True, on_offense=False, offender_pid='rusher')

    def test_atlanta_takes_first_and_goal_and_nullifies_kick(self):
        dr = self.drive(); book = game.StatBook(); kick = dict(type='field_goal', made=True, points=3)
        self.assertTrue(game._kick_roughing(dr, self.flag(), kick, book, half_end=1800))
        self.assertEqual((dr.yardline, dr.down, dr.togo), (9, 1, 9))
        self.assertTrue(kick['nullified'])
        self.assertEqual(dr.points, 0)
        self.assertEqual(book.p['rusher']['penalty_yards'], 9)
        self.assertEqual(book.p['rusher']['penalties_accepted'], 1)

    def test_ordinary_first_down_is_not_a_coach_aggression_gate(self):
        for aggression in (0, .5, 1):
            dr = self.drive(500, 4, 7, 40)
            self.assertTrue(game._kick_roughing(dr, self.flag(), dict(made=True), aggression=aggression))
            self.assertEqual(dr.yardline, 25)

    def test_late_winning_kick_keeps_points_and_accepts_enforcement(self):
        dr = self.drive(3, 4, -2); book = game.StatBook(); kick = dict(made=True)
        self.assertFalse(game._kick_roughing(dr, self.flag(), kick, book))
        self.assertEqual(dr.kickoff_penalty, 15)
        self.assertTrue(kick['kickoff_penalty']['accepted'])
        self.assertNotIn('declined_penalty', kick)
        self.assertEqual(book.p['rusher']['penalty_yards'], 15)
        self.assertEqual(book.p['rusher']['penalties_committed'], 1)

    def test_tie_at_expiration_keeps_points_but_need_touchdown_takes_down(self):
        for diff, take in ((-3, False), (-4, True), (-7, True)):
            dr = self.drive(3, 4, diff)
            self.assertEqual(game._kick_roughing(dr, self.flag(), dict(made=True)), take)
            if take:
                self.assertTrue(dr.untimed)
                self.assertEqual(dr.untimed_at, len(dr.log))

    def test_half_expiring_keeps_points(self):
        dr = self.drive(1803, 2, -24)
        self.assertFalse(game._kick_roughing(dr, self.flag(), dict(made=True), half_end=1800))

    def test_overtime_winning_score_stands(self):
        dr = self.drive(100, 5, 0)
        dr.field_goal_wins = True
        self.assertFalse(game._kick_roughing(dr, self.flag(), dict(made=True)))

    def test_opening_overtime_kick_is_not_a_winner(self):
        dr = self.drive(100, 5, 0)
        self.assertTrue(game._kick_roughing(dr, self.flag(), dict(made=True)))

    def test_accepted_kickoff_moves_to_fifty_and_touchback_to_twenty(self):
        with patch.dict(game.KICKOFF, touchback=.98):
            out = game.kickoff_for({}, {}, None, None, np.random.default_rng(1), lambda *a: .7, None, penalty_yards=15)
        self.assertTrue(out['touchback'])
        self.assertEqual((out['kickoff_line'], out['new_yardline']), (50, 80))

    def test_kick_from_twenty_changes_return_landing(self):
        import kick_returns
        with patch.dict(game.KICKOFF, touchback=.02), patch.object(kick_returns, 'resolve', return_value=dict(new_yardline=55)) as resolve:
            game.kickoff({}, np.random.default_rng(1), lambda *a: .7, kick_offset=-15)
        self.assertEqual(resolve.call_args.args[0], 80)

    def test_next_kick_consumes_penalty_once_and_handles_other_kicking_team(self):
        for kicker, expected in (('away', 15), ('home', -15)):
            pending = ['away']
            self.assertEqual(game._kickoff_adjustment(pending, kicker), expected)
            self.assertEqual(game._kickoff_adjustment(pending, kicker), 0)

    def test_actual_game_carries_enforcement_across_halftime(self):
        starts = []; kicks = []
        def kick(*a, **kw):
            kicks.append(kw.get('from_50'))
            return dict(touchback=True, new_yardline=80 if kw.get('from_50') else 65)
        def drive(off, deff, start, clock, q, sd, rng, *a, **kw):
            starts.append(start)
            dr = self.drive(1800 if len(starts) == 1 else 0)
            dr.result = 'Field goal' if len(starts) == 1 else 'End of half'
            dr.points = 3 if len(starts) == 1 else 0
            if len(starts) == 1: dr.kickoff_penalty = 15
            if False: yield None
            return dr
        with patch.object(game, 'kickoff_booked', side_effect=kick), patch.object(game, 'drive_steps', side_effect=drive), patch.object(game.W, 'draw', return_value=game.W.CLEAR):
            result = game.play_game({}, {}, np.random.default_rng(2), None, None, None, None)
        self.assertEqual(kicks, [False, True])
        self.assertEqual(starts, [65, 80])
        self.assertEqual(result['away'], 3)


if __name__ == '__main__': unittest.main()
