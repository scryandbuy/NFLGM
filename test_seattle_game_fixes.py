"""Clock, blocked-punt, terminal-event and spot regressions from SEA at GB."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import events as E
import gameday
import ticker
import season


class SeattleGameFixes(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                        wr=[dict(pid='wr', pos='WR')], ol=[], te=[], p=dict(pid='punter'), k=dict(pid='home-k'))
        self.defense = dict(db=[dict(pid='defender', pos='CB')], lb=[], dl=[], k=dict(pid='away-k'))
        self.league = NS(player=lambda pid: None, week=3, teams={a: NS(roster=[]) for a in ('GB', 'SEA')})
        G.LAST_KICKOFF.clear()

    def run_drive(self, outcomes, start=50, clock=300, diff=0, quarter=4, half_end=None, plan=None, punt=None):
        outcomes = iter(outcomes)
        book = G.StatBook()
        with patch.object(E, 'penalty_check', return_value=None), \
             patch.object(E, 'special_teams_penalty_check', return_value=None), \
             patch.object(E, 'fumble_check', return_value=None), \
             patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})), \
             patch.object(G, 'end_of_half_plan', return_value=plan), \
             patch.object(G, 'fourth_down_decision', return_value='punt'), \
             patch.object(G, 'punt', return_value=punt), \
             patch.object(G, 'attempt_extra_point', return_value=dict(type='extra_point', made=True, points=1)), \
             patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)):
            dr = G.run_drive(self.off, self.defense, start, clock, quarter, diff, np.random.default_rng(2),
                    lambda *a: dict(target='wr', **next(outcomes)),
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                    lambda *a: .7, book=book, half_end=half_end)
        return dr, book

    def test_leading_hurry_plan_controls_actual_snap_interval(self):
        plays = [dict(type='complete', yards=5), dict(type='interception', air=10, ret=0)]
        dr, _ = self.run_drive(plays, clock=1853, quarter=2, half_end=1800, diff=7,
                              plan=dict(choice='play', hurry=True))
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual(snaps[0]['clock'] - snaps[1]['clock'], 21)

    def test_exact_two_minute_snap_uses_hurry_clock(self):
        dr, _ = self.run_drive([dict(type='complete', yards=8), dict(type='interception', air=10, ret=0)],
                              clock=120, diff=-7)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual(snaps[0]['clock'] - snaps[1]['clock'], 21)
        self.assertFalse(G.hurry_for_snap(119, 7, dict(choice='play', hurry=False)))
        self.assertFalse(G.hurry_for_snap(119, 0, dict(choice='play', hurry=False)))
        self.assertTrue(G.hurry_for_snap(119, 7, dict(choice='play', hurry=True)))

    def blocked(self, start=50, recovery='receiving', behind=8, advance=7):
        rng = NS(uniform=lambda *a: behind, random=lambda: .1 if recovery == 'receiving' else .9,
                 integers=lambda n: 0, gamma=lambda *a: advance)
        return G._blocked_punt(start, rng, [dict(pid='kicking-player')], [dict(pid='receiving-player')])

    def punt_drive(self, kick, start=50, extra=()):
        return self.run_drive([dict(type='incomplete', yards=0)] * 3 + list(extra), start=start, punt=kick)

    def test_blocked_return_uses_recovery_and_advance_not_original_line(self):
        kick = self.blocked()
        dr, book = self.punt_drive(kick)
        self.assertEqual((kick['recovery_spot'], kick['end_spot']), (58, 65))
        self.assertEqual((dr.result, dr.next_yardline), ('Punt', 35))
        self.assertEqual(book.p['punter']['punts'], 1)
        text = ticker.play_line(self.league, kick, 'GB', 'SEA')['text']
        self.assertIn('Recovered by SEA', text)
        self.assertIn('GB 35', text)
        self.assertIn('SEA takes possession', text)

    def test_kicking_recovery_short_of_line_is_turnover_at_actual_spot(self):
        kick = self.blocked(recovery='kicking', advance=3)
        dr, _ = self.punt_drive(kick)
        self.assertEqual((dr.result, dr.next_yardline), ('Punt', 45))
        self.assertFalse(kick['retained'])

    def test_kicking_recovery_past_line_continues_same_drive(self):
        kick = self.blocked(recovery='kicking', advance=20)
        dr, book = self.punt_drive(kick, extra=[dict(type='complete', yards=100)])
        self.assertTrue(kick['retained'])
        self.assertEqual((dr.result, dr.points), ('Touchdown', 7))
        self.assertEqual(book.p['punter']['punts'], 1)
        self.assertEqual(dr.log[-2]['down'], 1)

    def test_blocked_punt_defensive_touchdown_and_correct_try_kicker(self):
        dr, book = self.punt_drive(self.blocked(start=97, behind=5, advance=0), start=97)
        self.assertEqual((dr.result, dr.points), ('Defensive touchdown', -7))
        self.assertEqual(book.p['away-k']['xp_made'], 1)
        self.assertNotIn('home-k', book.p)
        res = dict(home=0, away=7, drives=[('home', dr)], overtime=False)
        rendered = gameday.capture(self.league, [('GB', 'SEA', res, book)], 'GB')['game']
        self.assertEqual(rendered['drives'][0]['score'], '0–7')
        self.assertEqual(rendered['quarters']['SEA'][3], 7)
        scored = [p for p in rendered['drives'][0]['plays'] if p.get('td') or p['type'] == 'extra_point']
        self.assertEqual([p['scoring_side'] for p in scored], ['defense', 'defense'])

    def test_blocked_kick_own_end_zone_safety_and_escape(self):
        for recovery, behind, advance in [('kicking', 5, 0), ('receiving', 14, 0)]:
            dr, _ = self.punt_drive(self.blocked(start=97, recovery=recovery, behind=behind, advance=advance), start=97)
            self.assertEqual((dr.result, dr.points), ('Safety', -2))
        dr, _ = self.punt_drive(self.blocked(start=97, recovery='kicking', behind=5, advance=8), start=97)
        self.assertEqual((dr.result, dr.next_yardline), ('Punt', 6))

    def test_overtime_block_return_touchdown_ends_game(self):
        kick = self.blocked(start=97, behind=5, advance=0)
        dr, book = self.run_drive([dict(type='incomplete', yards=0)] * 3, start=97,
                                  clock=300, quarter=5, punt=kick)
        self.assertEqual(dr.points, -6)
        self.assertNotIn('away-k', book.p)
        def drive(off, defense, start, clock, q, diff, rng, *a, **kw):
            dr = G.Drive(off, defense, start, clock, q, diff, rng)
            dr.clock, dr.result, dr.points = 400, 'Defensive touchdown', -6
            return dr
        with patch.object(G, 'run_drive', side_effect=drive), \
             patch.object(G, 'kickoff_booked', return_value=dict(new_yardline=70, touchback=True)):
            score, drives, result = G.play_overtime({}, {}, dict(home=17, away=17), np.random.default_rng(3),
                                None, None, None, None, first='home')
        self.assertEqual(score, dict(home=17, away=23))
        self.assertEqual(result, 'defensive_touchdown_walkoff')

    def fake_game(self, remaining, defensive_td=False):
        calls, kicks, yielded = [], [], []
        def drive(off, defense, start, clock, quarter, diff, rng, *a, **kw):
            calls.append(off)
            dr = G.Drive(off, defense, start, clock, quarter, diff, rng)
            if len(calls) == 1:
                dr.clock, dr.result = 1800, 'End of half'
            elif len(calls) == 2:
                dr.clock, dr.result, dr.points = remaining, 'Defensive touchdown' if defensive_td else 'Field goal', -7 if defensive_td else 3
            else:
                dr.clock, dr.result = 0, 'End of half'
            if False: yield None
            return dr
        def kick(*a, **kw):
            kicks.append(1)
            return dict(new_yardline=75, touchback=len(kicks)<3, ret=20, returner='returner')
        with patch.object(G, 'drive_steps', side_effect=drive), patch.object(G, 'kickoff_booked', side_effect=kick), \
             patch.object(G.W, 'draw', return_value=G.W.CLEAR):
            gen = G.game_steps(self.off, self.defense, np.random.default_rng(3), None, None, None, lambda *a: .7)
            try:
                while True: yielded.append(next(gen))
            except StopIteration as done: res = done.value
        return res, calls, kicks

    def test_terminal_kickoff_survives_without_empty_drive_in_both_reports(self):
        res, calls, kicks = self.fake_game(1.6)
        self.assertEqual((len(calls), len(kicks)), (2, 3))
        dr = res['drives'][-1][1]
        self.assertEqual(dr.log[-1]['possession'], 'away')
        self.assertEqual(dr.log[-1]['end_clock'], 0)
        report = gameday.capture(self.league, [('GB', 'SEA', res, G.StatBook())], 'GB')['game']
        line = report['drives'][-1]['plays'][-1]
        self.assertEqual(line['off'], 'SEA')
        self.assertIn('SEA 25', line['text'])
        self.assertIn('Time expires in regulation', line['text'])
        self.assertIn('SEA 25', ticker.write_game(self.league, res, 'GB', 'SEA')[-1]['lines'][-1]['text'])

    def test_no_phantom_kickoff_after_game_clock_expired(self):
        _, calls, kicks = self.fake_game(0)
        self.assertEqual((len(calls), len(kicks)), (2, 2))

    def test_defensive_touchdown_kicks_back_to_original_offense(self):
        res, calls, kicks = self.fake_game(60, defensive_td=True)
        self.assertEqual((res['home'], res['away']), (0, 7))
        self.assertIs(calls[1], self.off)
        self.assertIs(calls[2], self.off)

    def test_terminal_half_and_overtime_return_wording(self):
        for quarter, before, after, word in [(2, 1804, 1800, 'first half'), (5, 4, 0, 'overtime')]:
            dr = G.Drive({}, {}, 30, before, quarter, 0, None)
            G._terminal_kickoff(dr, dict(new_yardline=80, ret=15), before, after, 'away', quarter)
            self.assertIn(word, ticker.play_line(self.league, dr.log[-1], 'SEA', 'GB')['text'])

    def test_field_goal_has_snap_clock_even_without_scrimmage_play(self):
        dr, _ = self.run_drive([], start=30, clock=5, plan=dict(choice='kick', hurry=True))
        kick = next(p for p in dr.log if p.get('type') == 'field_goal')
        self.assertEqual(kick['clock'], 5)
        self.assertIn('0:05', ticker.play_line(self.league, kick, 'GB', 'SEA')['head'])

    def test_spots_match_drive_header_kickoff_and_first_snap(self):
        for start in (81.49, 75.49, 30.51, .4, 50):
            dr = G.Drive(self.off, self.defense, start, 300, 4, 0, None)
            dr.result = 'End of half'
            dr.log = [dict(type='kickoff', new_yardline=start, ret=20),
                      dict(type='incomplete', down=1, ydstogo=10, yardline=start, clock=300)]
            res = dict(home=0, away=0, drives=[('home', dr)], overtime=False)
            report = gameday.capture(self.league, [('GB', 'SEA', res, G.StatBook())], 'GB')['game']['drives'][0]
            expected = ticker._spot(start, 'GB', 'SEA')
            self.assertIn(expected, report['head'])
            self.assertIn(expected, next(p for p in report['plays'] if p['type'] == 'kickoff')['text'])
            self.assertIn(expected, next(p for p in report['plays'] if p['type'] == 'incomplete')['head'])

    def test_live_partial_credits_defensive_points(self):
        runner = season.SeasonRunner.__new__(season.SeasonRunner)
        runner.live = dict(drives=[], score=dict(home=0, away=0), current=NS(points=-7),
                           pos='home', at='snap', res=None, done=False, halftime_open=False)
        self.assertEqual(runner.live_partial()['away'], 7)


if __name__ == '__main__': unittest.main()
