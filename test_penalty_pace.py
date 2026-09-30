"""Clock restart cases for the pace regression, including real drive integration."""
import unittest
from unittest.mock import patch
import game as G
import test_game_log_regressions as fixtures


class PenaltyPaceTests(unittest.TestCase):
    def drive(self, clock=3000, quarter=1):
        return G.Drive({}, {}, 50, clock, quarter, 0, None)

    def test_running_presnap_foul_has_new_ready_interval(self):
        dr = self.drive()
        dr.clock_running = True
        dr.runoff_charged = 30  # previous play's interval already consumed
        pen = dict(on_offense=True)
        G._penalty_ready_clock(dr, pen, 1800, before_snap=True, was_running=True)
        self.assertEqual(dr.clock, 2975)
        self.assertEqual(dr.runoff_charged, 25)
        self.assertEqual(dr.play_clock, 25)
        self.assertTrue(dr.clock_running)

    def test_stopped_clock_and_late_fouls_have_no_ready_runoff(self):
        for clock, quarter, wall, before_snap, running, offense in (
            (3000, 1, 1800, True, False, True),
            (1910, 2, 1800, False, True, False),
            (290, 4, None, False, True, True),
            (290, 5, None, False, True, False),
            (700, 4, None, True, True, True),
        ):
            with self.subTest(clock=clock, quarter=quarter, before_snap=before_snap):
                dr = self.drive(clock, quarter)
                G._penalty_ready_clock(dr, dict(on_offense=offense), wall,
                    before_snap=before_snap, was_running=running, result='run')
                self.assertEqual(dr.clock, clock)
                self.assertFalse(dr.clock_running)

    def test_incomplete_pass_and_timeout_stay_stopped(self):
        for result, timeout in (('incomplete', False), ('drop', False), ('run', True)):
            dr = self.drive()
            G._penalty_ready_clock(dr, dict(on_offense=False), 1800,
                                  result=result, timeout=timeout)
            self.assertEqual(dr.clock, 3000)

    def test_ready_interval_clips_at_quarter_and_warning(self):
        for clock, quarter, wall, expected in ((2710, 1, 1800, 2700),
                                               (1930, 2, 1800, 1920)):
            dr = self.drive(clock, quarter)
            # A first-half pre-snap defensive foul can restart before the warning.
            G._penalty_ready_clock(dr, dict(on_offense=False), wall,
                                  before_snap=True, was_running=True)
            self.assertEqual(dr.clock, expected)
            self.assertFalse(dr.clock_running)

    def test_live_play_crossing_quarter_has_no_next_quarter_runoff(self):
        dr = self.drive(2700)
        G._penalty_ready_clock(dr, dict(on_offense=False), 1800,
                              result='complete', live_start=2703)
        self.assertEqual(dr.clock, 2700)
        self.assertFalse(dr.clock_running)

    def test_hurry_and_tempo_still_affect_ready_interval(self):
        clocks = []
        for hurry, tempo in ((False, .5), (True, .5), (False, 1)):
            dr = self.drive()
            G._penalty_ready_clock(dr, dict(on_offense=False), 1800,
                                  result='complete', hurry=hurry, tempo=tempo)
            clocks.append(dr.clock)
        self.assertGreater(clocks[1], clocks[0])
        self.assertGreater(clocks[2], clocks[0])

    def test_live_holding_charges_live_seconds_and_one_ready_interval(self):
        flag = dict(penalty='Offensive Holding', yards=10, rule_yards=10,
                    on_offense=True, auto_first=False, nullifies=False)
        dr = fixtures.GameLogRegressions().snaps(3000, 1,
            [dict(type='complete', yards=8), dict(type='complete', yards=55)],
            penalties=[flag], half_end=1800)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertTrue(snaps[0]['nullified'])
        self.assertEqual(snaps[0]['clock'] - snaps[1]['clock'], 31)
        self.assertEqual(dr.plays, 1)

    def test_presnap_foul_after_run_uses_the_reset_play_clock(self):
        flag = dict(penalty='False Start', yards=5, rule_yards=5,
                    on_offense=True, auto_first=False, nullifies=True)
        dr = fixtures.GameLogRegressions().snaps(1500, 3,
            [dict(type='run', yards=5), dict(type='complete', yards=45)],
            penalties=[None, flag])
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual(snaps[0]['clock'] - snaps[1]['clock'], int(G.play_seconds('run')) + 25)

    def test_late_holding_does_not_spend_timeout_for_stopped_clock(self):
        flag = dict(penalty='Offensive Holding', yards=10, rule_yards=10,
                    on_offense=True, auto_first=False, nullifies=False)
        with patch.object(G, '_timeout_call', return_value=(False, None)) as timeout:
            dr = fixtures.GameLogRegressions().snaps(60, 4,
                [dict(type='complete', yards=8), dict(type='complete', yards=55)],
                penalties=[flag])
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual(snaps[1]['clock'], 54)
        self.assertEqual(timeout.call_count, 1)  # only the subsequent valid snap

    def test_live_action_below_warning_is_not_given_back(self):
        flag = dict(penalty='Offensive Holding', yards=10, rule_yards=10,
                    on_offense=True, auto_first=False, nullifies=False)
        dr = fixtures.GameLogRegressions().snaps(1923, 2,
            [dict(type='complete', yards=8), dict(type='complete', yards=55)],
            penalties=[flag], half_end=1800)
        warning = next(p for p in dr.log if p['type'] == 'two_minute')
        self.assertEqual(warning['clock'], 1917)

    def test_added_dead_ball_foul_uses_late_clock_exception(self):
        flag = dict(penalty='Unnecessary Roughness', yards=15, rule_yards=15,
                    on_offense=False, auto_first=True, nullifies=False)
        dr = fixtures.GameLogRegressions().snaps(250, 4,
            [dict(type='run', yards=5), dict(type='complete', yards=25)],
            penalties=[flag])
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual(snaps[1]['clock'], 244)
        self.assertFalse(snaps[0].get('nullified'))

    def test_added_foul_does_not_erase_live_time_at_warning(self):
        flag = dict(penalty='Unnecessary Roughness', yards=15, rule_yards=15,
                    on_offense=False, auto_first=True, nullifies=False)
        dr = fixtures.GameLogRegressions().snaps(1923, 2,
            [dict(type='run', yards=5), dict(type='complete', yards=25)],
            penalties=[flag], half_end=1800)
        warning = next(p for p in dr.log if p['type'] == 'two_minute')
        self.assertEqual(warning['clock'], 1917)

    def test_special_teams_presnap_uses_same_restart_rules(self):
        for clock, quarter, wall, expected in ((3000, 1, 1800, 2975),
                                               (250, 4, None, 250)):
            dr = self.drive(clock, quarter)
            dr.clock_running = True
            pen = dict(penalty='False Start', phase='pre', yards=5, on_offense=True)
            self.assertTrue(G._kick_presnap_flag(dr, pen, wall))
            self.assertEqual(dr.clock, expected)

    def test_running_play_clock_is_bounded_and_hurry_timeout_unchanged(self):
        for outcome in ('run', 'complete', 'scramble', 'sack'):
            self.assertLessEqual(G.play_seconds(outcome, tempo=0), 46)
            self.assertEqual(G.play_seconds(outcome, timeout=True), 6)
            self.assertAlmostEqual(G.play_seconds(outcome, hurry=True), G.SEC[outcome] * .65)


if __name__ == '__main__':
    unittest.main()
