import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import events
import game as G
import plays as P
import fumble_resolution as F
import ticker
import test_defensive_returns as returns


class LooseBallRules(unittest.TestCase):
    def test_boundaries_and_both_end_zones(self):
        self.assertEqual(F.resolve(3, 1, 'offense', out_of_bounds=True)['fumble_dead_spot'], 3)
        self.assertEqual(F.resolve(3, 5, 'offense', out_of_bounds=True)['fumble_dead_spot'], 5)
        r = F.resolve(1, -1, 'offense', out_of_bounds=True)
        self.assertTrue(r['touchback']); self.assertTrue(r['fumble_lost'])
        self.assertEqual(r['end_spot'], 20)
        self.assertTrue(F.resolve(99, 101, 'offense', out_of_bounds=True)['safety'])
        self.assertTrue(F.resolve(101, 99, 'offense', out_of_bounds=True)['safety'])

    def test_teammate_recovery_action_and_restraint(self):
        self.assertTrue(F.resolve(1, -1, 'offense')['touchdown'])
        r = F.resolve(1, -1, 'offense', restricted=True)
        self.assertFalse(r['touchdown']); self.assertEqual(r['fumble_dead_spot'], 1)
        self.assertTrue(F.resolve(1, -1, 'offense', restricted=True, same_player=True)['touchdown'])
        self.assertEqual(F.resolve(1, 3, 'offense', restricted=True)['fumble_dead_spot'], 3)
        self.assertTrue(F.resolve(99, 101, 'offense')['safety'])


class GoalLineIntegration(unittest.TestCase):
    def setUp(self):
        self.fixture = returns.DefensiveReturns(); self.fixture.setUp()
        self.off, self.deff = self.fixture.off, self.fixture.defense

    def prepare(self, out, spot=3, recovery=(-1, True), lost=False, **state):
        dr = NS(yardline=spot, down=state.get('down', 1), quarter=state.get('quarter', 1),
                clock=state.get('clock', 900), is_try=state.get('is_try', False))
        with patch.object(events, 'fumble_check', return_value=dict(lost=lost, forced=True)), \
             patch.object(F, 'near_goal_recovery', return_value=recovery):
            G._prepare_scoring_play(dr, out)
            G._prepare_fumble(dr, out, self.off, self.deff, np.random.default_rng(state.get('seed', 3)), lambda *a:.7)
            G._prepare_scoring_play(dr, out)
        return out

    def test_scoring_candidate_can_lose_ball_before_plane(self):
        out = self.prepare(dict(type='run', yards=3, carrier_pid='rb',
                                pre_goal_contact_yards=2, pre_goal_contact_by='edge'))
        self.assertFalse(out['touchdown']); self.assertTrue(out['touchback'])
        self.assertEqual((out['fumble_spot'], out['carrier_yards']), (1, 2))
        self.assertEqual(out['fumble_forced_by'], 'edge')

    def test_end_zone_catch_and_untouched_crossing_stay_dead(self):
        for kind in ('run', 'complete', 'scramble'):
            out = self.prepare(dict(type=kind, yards=3, target='wr1'))
            self.assertTrue(out['touchdown']); self.assertNotIn('fumble', out)

    def test_full_drive_touchback_no_phantom_rush_td_or_returner(self):
        with patch.object(F, 'near_goal_recovery', return_value=(-1, True)):
            dr, book, _ = self.fixture.drive([dict(type='run', yards=3, carrier_pid='rb',
                pre_goal_contact_yards=2, pre_goal_contact_by='edge')], start=3,
                fumble=dict(lost=False, forced=True))
        self.assertEqual((dr.result, dr.points, dr.yardline), ('Turnover', 0, 20))
        self.assertEqual((book.p['rb']['rush_yds'], book.p['rb']['rush_td'], book.p['rb']['fumbles_lost']), (2, 0, 1))
        self.assertEqual(book.p['edge']['ff'], 1)
        self.assertEqual(book.p['edge']['tackles'], 1)
        self.assertFalse(any(s.get('fum_rec', 0) for s in book.p.values()))

    def test_boundary_strip_sack_has_no_recovery_credit(self):
        with patch.object(F, 'near_goal_recovery', return_value=(-1, True)):
            dr, book, _ = self.fixture.drive([dict(type='sack', yards=-1, by='edge')],
                start=1, fumble=dict(lost=True, forced=True))
        self.assertEqual((dr.result, dr.yardline), ('Turnover', 20))
        self.assertEqual(book.p['edge'].get('fum_rec', 0), 0)

    def test_own_recovery_keeps_receiving_yards_and_td(self):
        out = self.prepare(dict(type='complete', yards=2, target='wr1', tackler='cb'),
                           recovery=(-1, False), seed=14)
        self.assertEqual(out['fumble_recovered_by'], 'wr1')
        self.assertFalse(out['offensive_fumble_td'])
        book = G.StatBook(); book.record(out, self.off, self.deff, np.random.default_rng(1)); book.record_fumble(out)
        self.assertEqual((book.p['wr1']['rec_yds'], book.p['wr1']['rec_td']), (3, 1))
        self.assertEqual(book.p['qb']['pass_td'], 1)
        self.assertEqual(book.p['wr1'].get('off_fum_rec_td', 0), 0)

    def test_offensive_recovery_td_has_separate_credit(self):
        with patch.object(F, 'near_goal_recovery', return_value=(-1, False)), \
             patch.object(G, '_offensive_fumble_recoverer', return_value=self.off['qb']):
            dr, book, _ = self.fixture.drive([dict(type='complete', yards=2, target='wr1', tackler='cb')],
                start=3, quarter=1, fumble=dict(lost=False, forced=True))
        p = next(p for p in dr.log if p.get('fumble'))
        self.assertEqual(dr.result, 'Touchdown')
        self.assertEqual(book.p['wr1']['rec_yds'], 2)
        self.assertEqual(book.p['wr1']['rec_td'], 0)
        self.assertEqual(book.p['qb']['pass_td'], 0)
        self.assertEqual(book.p[p['fumble_recovered_by']]['off_fum_rec_td'], 1)
        league = NS(player=lambda pid: NS(name=pid) if pid else None)
        line = ticker.play_line(league, p, 'GB', 'NY')
        self.assertEqual(line['text'].count('TOUCHDOWN'), 1)
        self.assertLess(line['text'].index('FUMBLE'), line['text'].index('TOUCHDOWN'))

    def test_backward_recovery_reduces_receiving_credit(self):
        for lost in (False, True):
            out = self.prepare(dict(type='complete', yards=2, target='wr1', tackler='cb'),
                               recovery=(4., False), lost=lost)
            self.assertEqual(out['carrier_yards'], -1.)

    def test_fourth_down_and_late_half_teammate_no_forward_gain(self):
        for state in (dict(down=4), dict(quarter=2, clock=1850), dict(quarter=4, clock=50), dict(is_try=True)):
            # Seed 3 chooses an offensive teammate, not wr1.
            out = self.prepare(dict(type='complete', yards=2, target='wr1', tackler='cb'),
                               recovery=(-1, False), **state)
            self.assertNotEqual(out['fumble_recovered_by'], 'wr1')
            self.assertFalse(out['touchdown']); self.assertEqual(out['yards'], 2)
            self.assertTrue(out['fumble_advancement_restricted'])

    def test_fractional_spot_is_not_rounded_into_td(self):
        out = self.prepare(dict(type='run', yards=3, carrier_pid='rb',
                               pre_goal_contact_yards=2.8, pre_goal_contact_by='edge'),
                           recovery=(.2, True))
        self.assertFalse(out['touchdown'])
        dr = NS(yardline=3., togo=3., down=1, best=3., result=None)
        self.assertFalse(G._advance(dr, out['yards'], exact=True))
        self.assertAlmostEqual(dr.yardline, .2)

    def test_full_drive_fractional_recovery_keeps_running_clock(self):
        with patch.object(F, 'near_goal_recovery', return_value=(.2, False)):
            dr, _, _ = self.fixture.drive([
                dict(type='run', yards=3, carrier_pid='rb', pre_goal_contact_yards=2.8, pre_goal_contact_by='edge'),
                dict(type='interception', air=0, yards=0, by='cb', ret=0)],
                start=3, clock=600, fumble=dict(lost=False, forced=True))
        snaps = [p for p in dr.log if p.get('down')]
        self.assertAlmostEqual(snaps[1]['yardline'], .2)
        self.assertGreater(snaps[0]['clock'] - snaps[1]['clock'], 12)

    def test_fumble_boundary_late_half_restarts_on_ready(self):
        with patch.object(F, 'near_goal_recovery', return_value=(2., True)):
            dr, _, _ = self.fixture.drive([
                dict(type='run', yards=1, carrier_pid='rb'),
                dict(type='interception', air=0, yards=0, by='cb', ret=0)],
                start=3, clock=110, quarter=4, fumble=dict(lost=False, forced=True))
        snaps = [p for p in dr.log if p.get('down')]
        self.assertGreater(snaps[0]['clock'] - snaps[1]['clock'], 10)

    def test_safety_yards_capped_before_book(self):
        dr, book, _ = self.fixture.drive([dict(type='sack', yards=-4.7, by='edge')], start=98)
        p = next(p for p in dr.log if p.get('type') == 'sack')
        self.assertEqual((p['yards'], dr.result), (-2, 'Safety'))
        self.assertEqual(book.p['qb']['sacked'], 1)
        raw = dict(type='sack', yards=-4.7)
        G._prepare_scoring_play(NS(yardline=98), raw)
        self.assertEqual(raw['yards'], -2)

    def test_try_teammate_recovery_cannot_complete_conversion(self):
        with patch.object(G, 'field_units', side_effect=lambda ros,*a,**k:(ros,{})), \
             patch.object(events, 'special_teams_penalty_check', return_value=None), \
             patch.object(events, 'fumble_check', return_value=dict(lost=False, forced=True)), \
             patch.object(F, 'near_goal_recovery', return_value=(-1., False)), \
             patch.object(G, '_offensive_fumble_recoverer', return_value=self.off['qb']):
            out = G.attempt_two_point(self.off, self.deff, np.random.default_rng(1),
                lambda *a: dict(type='complete', yards=1, target='wr1', tackler='cb'),
                lambda *a,**k:dict(is_pass=True, personnel='11'),
                lambda *a,**k:dict(personnel='nickel', front_family='4-3'), lambda *a:.7)
        self.assertFalse(out['made']); self.assertEqual(out['points'], 0)

    def test_try_defensive_return_is_two_points_not_six(self):
        with patch.object(G, 'field_units', side_effect=lambda ros,*a,**k:(ros,{})), \
             patch.object(events, 'special_teams_penalty_check', return_value=None), \
             patch.object(events, 'fumble_check', return_value=dict(lost=True, forced=True)), \
             patch.object(F, 'near_goal_recovery', return_value=(1., False)), \
             patch.object(P, 'defensive_return', return_value=dict(defensive_td=True, touchdown=True, end_spot=100., ret=99., returner='cb')):
            out = G.attempt_two_point(self.off, self.deff, np.random.default_rng(1),
                lambda *a: dict(type='complete', yards=1, target='wr1', tackler='cb'),
                lambda *a,**k:dict(is_pass=True, personnel='11'),
                lambda *a,**k:dict(personnel='nickel', front_family='4-3'), lambda *a:.7)
        self.assertEqual(out['points'], -2)
        import gameday
        league = NS(player=lambda pid: NS(name=pid) if pid else None)
        shown = gameday.write_play(league, out, 'qb', 'GB', 'NY')
        self.assertFalse(shown['td']); self.assertEqual(shown['try_points'], -2)

    def test_pursuit_keeps_pre_plane_contact_without_changing_rng(self):
        runner, defender = dict(pid='rb'), dict(pid='cb')
        with patch.object(P, 'rate', return_value=.7):
            out = P.resolve_yards_after(runner, [defender], .5, np.random.default_rng(3))
        self.assertEqual(out['pre_goal_contact_by'], 'cb')
        self.assertLess(out['pre_goal_contact_yards'], .5)
        with patch.object(P, 'rate', return_value=.7):
            free = P.resolve_yards_after(runner, [], .5, np.random.default_rng(3), track_tackler=True)
        self.assertNotIn('pre_goal_contact_yards', free)


if __name__ == '__main__': unittest.main()
