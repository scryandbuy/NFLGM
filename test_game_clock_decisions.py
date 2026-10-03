"""GB–DAL clock regressions; coach fourth-down choices remain untouched."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import events
import game as G
import gameday
import ticker


class ClockDecisions(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                        wr=[dict(pid='wr', pos='WR')], te=[], ol=[], k={}, p={})
        self.deff = dict(db=[dict(pid='cb', pos='CB')], lb=[], dl=[])
        G.LAST_KICKOFF.clear()

    def drive(self, outcomes=(), *, start=36, clock=1820, quarter=2, wall=1800,
              diff=11, own=1, other=0, down=1, live=False, states=None, calls=None):
        outcomes = iter(outcomes)
        tos = G.Timeouts(); tos.left = dict(home=own, away=other)
        book = G.StatBook()
        constructor = G.Drive
        def make_drive(*args):
            dr = constructor(*args); dr.down = down
            return dr
        with ExitStack() as stack:
            stack.enter_context(patch.object(G, 'Drive', side_effect=make_drive))
            stack.enter_context(patch.object(events, 'penalty_check', return_value=None))
            stack.enter_context(patch.object(events, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(events, 'fumble_check', return_value=None))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)))
            if states is None:
                stack.enter_context(patch.object(G, 'field_units', side_effect=lambda ros, *a, **k: (ros, {})))
            args = (self.off, self.deff, start, clock, quarter, diff,
                    np.random.default_rng(11), lambda *a: ((calls.append(dict(a[2])) if calls is not None else None),
                               dict(target='wr', **next(outcomes)))[1],
                    lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                    lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                    lambda *a: .7)
            kw = dict(book=book, timeouts=tos, half_end=wall,
                      off_state=states[0] if states else None, def_state=states[1] if states else None)
            if live:
                stepper = G.drive_steps(*args, **kw)
                while True:
                    try: next(stepper)
                    except StopIteration as end:
                        dr = end.value; break
            else:
                dr = G.run_drive(*args, **kw)
        return dr, book, tos

    def test_own_one_halftime_uses_live_run_not_pass_or_safety_knee(self):
        calls = []
        dr, _, _ = self.drive([dict(type='run', yards=1)], start=99,
                              clock=1804, diff=1, calls=calls)
        self.assertFalse(calls[0]['is_pass'])
        self.assertEqual(calls[0]['scheme'], 'inside_zone')
        self.assertEqual(dr.result, 'End of half')

    def test_trailing_half_timeout_not_spent_to_punt(self):
        dr = NS(down=3, togo=2, yardline=52, score_diff=-1)
        tos = G.Timeouts()
        used, who = G._timeout_call(dr, 'complete', {'yards': 0}, tos,
                                    'home', 1800, 19,
                                    plan={'choice': 'play', 'hurry': True})
        self.assertFalse(used)
        self.assertEqual(tos.left['home'], 3)
        self.assertEqual(dr._half_stall_intent, 'protect')

    def test_reported_halftime_completion_saves_scoring_chance(self):
        # GB at the DAL 36 with 0:20 and one timeout, leading by eleven.
        dr, _, tos = self.drive([dict(type='complete', yards=33),
                                 dict(type='complete', yards=3)])
        snaps = [p for p in dr.log if p.get('down')]
        self.assertEqual((snaps[1]['yardline'], snaps[1]['clock']), (3, 1814))
        self.assertEqual(tos.left['home'], 0)
        self.assertEqual(dr.result, 'Touchdown')
        self.assertTrue(any(p['type'] == 'timeout' and p['clock'] == 1814 for p in dr.log))

    def test_sack_timeout_preview_uses_next_down_and_distance(self):
        plans = []
        original = G.end_of_half_plan
        def plan(dr, *args, **kwargs):
            plans.append((dr.down, dr.togo, dr.yardline, dr.clock))
            return original(dr, *args, **kwargs)
        with patch.object(G, 'end_of_half_plan', side_effect=plan):
            self.drive([dict(type='sack', yards=-8, by='cb'),
                        dict(type='complete', yards=44)])
        self.assertIn((2, 18, 44, 1814), plans)

    def test_timeout_is_not_invented_when_none_left(self):
        dr, _, tos = self.drive([dict(type='complete', yards=33)], own=0)
        self.assertEqual(tos.left['home'], 0)
        self.assertFalse(any(p['type'] == 'timeout' for p in dr.log))

    def test_live_play_can_still_end_half(self):
        with patch.object(G, 'end_of_half_plan', return_value=dict(choice='shot', hurry=False)):
            dr, _, tos = self.drive([dict(type='complete', yards=33)], clock=1805)
        self.assertEqual(dr.clock, 1800)
        self.assertEqual(tos.left['home'], 1)

    def test_bleed_still_runs_clock_when_time_remains(self):
        dr, _, tos = self.drive([dict(type='complete', yards=5),
                                 dict(type='interception', yards=0, air=0, ret=0)],
                                clock=1865, start=75)
        snaps = [p for p in dr.log if p.get('down')]
        self.assertGreater(snaps[0]['clock'] - snaps[1]['clock'], 20)
        self.assertEqual(tos.left['home'], 1)

    def test_score_does_not_spend_timeout(self):
        dr, _, tos = self.drive([dict(type='complete', yards=36)])
        self.assertEqual(dr.result, 'Touchdown')
        self.assertEqual(tos.left['home'], 1)

    def test_fourth_down_failure_stops_clock_without_own_timeout(self):
        with patch.object(G, 'fourth_down_decision', return_value='go'):
            dr, _, tos = self.drive([dict(type='run', yards=1)], down=4)
        self.assertEqual(dr.result, 'Turnover on downs')
        self.assertEqual(dr.clock, 1814)
        self.assertEqual(tos.left['home'], 1)

    def test_three_knees_at_two_minutes_with_stat_and_display_accounting(self):
        dr, book, tos = self.drive(start=18, clock=120, quarter=4, wall=None, diff=12)
        knees = [p for p in dr.log if p['type'] == 'kneel']
        self.assertEqual([p['clock'] for p in knees], [120, 78, 36])
        self.assertEqual([p['down'] for p in knees], [1, 2, 3])
        self.assertEqual((dr.clock, dr.yardline, dr.plays), (0, 21, 3))
        self.assertEqual((book.p['qb']['rush_att'], book.p['qb']['rush_yds']), (3, -3))
        self.assertEqual(tos.left['home'], 1)
        league = NS(player=lambda pid: None, week=8, teams={t: NS(roster=[]) for t in ('GB', 'DAL')})
        result = dict(home=38, away=26, drives=[('home', dr)], overtime=False)
        saved = gameday.capture(league, [('GB', 'DAL', result, book)], 'GB')['game']
        self.assertEqual(saved['team_stats']['GB']['plays'], 3)
        self.assertEqual(saved['team_stats']['GB']['rush_yds'], -3)
        self.assertIn('3 plays, -3 yards', ticker.write_game(league, result, 'GB', 'DAL')[0]['header'])

    def test_defensive_timeout_is_spent_between_knees(self):
        dr, _, tos = self.drive(start=18, clock=80, quarter=4, wall=None, other=1)
        self.assertEqual([p['clock'] for p in dr.log if p['type'] == 'kneel'], [80, 78, 36])
        self.assertEqual(tos.left['away'], 0)
        self.assertEqual(dr.clock, 0)
        self.assertEqual(next(p for p in dr.log if p['type'] == 'timeout')['clock'], 78)

    def test_cannot_kneel_when_timeouts_downs_or_own_goal_prevent_it(self):
        for clock, down, tos, spot in ((120, 1, 1, 18), (32, 4, 0, 18),
                                      (50, 3, 0, 18), (122, 1, 0, 18),
                                      (80, 1, 0, 98), (1, 1, 0, 99)):
            with self.subTest(clock=clock, down=down, tos=tos, spot=spot):
                dr = G.Drive(self.off, self.deff, spot, clock, 4, 12, None); dr.down = down
                self.assertFalse(G._can_kneel_out(dr, clock, tos))

    def test_warning_stops_live_knee_without_spending_timeout(self):
        self.assertEqual(G._kneel_interval(121, 1, 2), (119, False, True))
        self.assertEqual(G._kneel_interval(140, 1, 0), (120, False, True))

    def test_live_and_simmed_drive_have_identical_knees(self):
        kw = dict(start=18, clock=120, quarter=4, wall=None)
        simmed, sb, _ = self.drive(**kw)
        live, lb, _ = self.drive(**kw, live=True)
        self.assertEqual(live.log, simmed.log)
        self.assertEqual(lb.p, sb.p)
        self.assertEqual(live.clock, simmed.clock)

    def test_real_units_count_eleven_players_on_each_kneel(self):
        depth = {pos: [dict(pid=f'{pos}{i}', pos=pos) for i in range(n)]
                 for pos, n in dict(QB=2, HB=2, WR=4, TE=2, LT=1, LG=1, C=1, RG=1, RT=1).items()}
        self.off.update(depth=depth, qb=depth['QB'][0], qbs=depth['QB'])
        self.deff = dict(dl=[dict(pid=f'dl{i}', pos=p) for i, p in enumerate(('LEDG', 'DT', 'DT', 'REDG'))],
                         lb=[dict(pid=f'lb{i}', pos=p) for i, p in enumerate(('MIKE', 'WILL', 'SAM'))],
                         db=[dict(pid=f'db{i}', pos=p) for i, p in enumerate(('CB', 'CB', 'CB', 'FS', 'SS'))])
        os, ds = G.TeamState(self.off), G.TeamState(self.deff)
        os.out.add('QB0')
        dr, book, _ = self.drive(start=18, clock=120, quarter=4, wall=None, states=(os, ds))
        for state, unit in ((os, 'offense'), (ds, 'defense')):
            self.assertEqual(state.snap_counts[unit]['total'], 3)
            self.assertEqual(sum(state.snap_counts[unit]['players'].values()), 33)
        self.assertNotIn('QB0', os.snap_counts['offense']['players'])
        self.assertEqual(book.p['QB1']['rush_att'], 3)

    def test_penalties_and_timeouts_have_clock_labels(self):
        league = NS(player=lambda pid: None)
        for kind in ('penalty', 'timeout'):
            pl = dict(type=kind, clock=1820, penalty='False Start', yards=5,
                      on_offense=True, timing='before_snap', side='home', left=1)
            line = ticker.play_line(league, pl, 'GB', 'DAL')
            self.assertIn('0:20', line['head'])
            if kind == 'penalty': self.assertIn('before the next snap; no play occurred', line['text'])
        line = ticker.play_line(league, dict(type='complete', yards=8, nullified=True), 'GB', 'DAL')
        self.assertIn('Play nullified by penalty', line['text'])


if __name__ == '__main__':
    unittest.main()
