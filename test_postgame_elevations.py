"""Roster choices after the whistle must survive until the intended game."""
import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as N
from unittest.mock import patch

import game_availability as GA
import practice_squad as PS
from session import Session


class PostgameElevations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Session.new('GB', seed=23)

    def setUp(self):
        self.s = copy.deepcopy(self.base)
        self.s.L.set_phase('regular')
        self.s.L.week = 5
        self.s.stop = ('week', 5)
        self.s.played = True
        self.s.runner = None
        self.L = self.s.L
        self.t = self.L.teams['GB']
        self.ps = list(self.t.roster[-3:])
        for p in self.ps:
            self.t.roster.remove(p)
            self.t.practice_squad.append(p)
            p.xp_spent['_ps'] = True
            p.out_until = None
        self.L.schedule = [(5, 'GB', 'CHI', 20, 10),
                           (6, 'CHI', 'GB', None, None),
                           (7, 'GB', 'DET', None, None)]

    def weekly(self, week):
        # Keep the actual elevation rollover; isolate unrelated league transactions.
        with ExitStack() as stack:
            for module, name in [(PS, 'keep_groups_whole'), (PS, 'roster_review'),
                                 (PS, 'replenish_squads'), (PS, 'elevate_for_coverage')]:
                stack.enter_context(patch.object(module, name, return_value=[]))
            stack.enter_context(patch('veteran_market.review', return_value=[]))
            PS.weekly(self.L, self.s.rng, week, user_team='GB', playoffs=week >= 18)

    def elevate(self, *players):
        return self.s.club_act('elevate', pids=[p.pid for p in players])

    def test_postgame_elevation_survives_advance_save_and_next_game(self):
        p = self.ps[0]
        stats = copy.deepcopy(self.L.stats)
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 6)
        self.assertEqual(self.s.club_roster()['elevation_label'], 'Week 6')
        self.assertEqual(p.xp_spent['_elevations'], 1)
        self.assertNotIn(p, GA.dressed(self.t, None, 5))
        self.assertIn(p, GA.dressed(self.t, None, 6))
        self.s.runner = N(live=None, desks={}, roll_week=self.weekly)
        with patch.object(self.s, 'blocking', return_value=[]), \
             patch.object(self.s, '_finish_live'), \
             patch('game_availability.settle_roster'), \
             patch('staff.resolve_references'):
            self.s.advance()
        self.assertEqual(self.s.stop, ('week', 6))
        self.assertIn(p, self.t._elevated)
        self.assertEqual(p.xp_spent['_elevations'], 1)
        self.s.runner = None
        loaded = Session.load(self.s.save())
        lp = loaded.L.player(p.pid)
        self.assertIn(lp, loaded.L.teams['GB']._elevated)
        self.assertEqual(lp.xp_spent['_elevation_week'], 6)
        self.assertEqual(self.L.stats, stats)
        self.weekly(6)
        self.assertNotIn(p, self.t._elevated)
        self.assertNotIn('_elevation_week', p.xp_spent)

    def test_pregame_choice_reverts_after_its_game(self):
        self.s.played = False
        self.L.schedule[0] = (5, 'GB', 'CHI', None, None)
        p = self.ps[0]
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 5)
        self.weekly(5)
        self.assertNotIn(p, self.t._elevated)

    def test_old_slots_reopen_but_next_game_limit_still_applies(self):
        PS.elevate(self.L, 'GB', [p.pid for p in self.ps[:2]], 5)
        view = self.s.club_roster()
        self.assertEqual(view['elevations_used'], 0)
        self.assertTrue(self.elevate(*self.ps[:2])['ok'])
        self.assertEqual(self.ps[0].xp_spent['_elevations'], 2)
        self.assertFalse(self.elevate(self.ps[2])['ok'])
        self.weekly(5)
        self.assertEqual(len(self.t._elevated), 2)

    def test_bye_does_not_consume_next_game_choice(self):
        self.L.schedule = [g for g in self.L.schedule if g[0] != 6]
        self.L.schedule.append((6, 'CHI', 'DET', None, None))
        self.assertEqual(self.s._elevation_context('CHI')['week'], 6)
        p = self.ps[0]
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 7)
        self.weekly(5)
        self.weekly(6)
        self.assertIn(p, self.t._elevated)
        self.assertNotIn(p, GA.dressed(self.t, None, 6))
        self.assertEqual(p.xp_spent['_elevations'], 1)

    def test_in_progress_game_rejects_elevation_without_consuming_one(self):
        self.s.runner = N(live={'done': False})
        self.assertFalse(self.elevate(self.ps[0])['ok'])
        self.assertNotIn('_elevations', self.ps[0].xp_spent)

    def test_playoffs_and_regular_season_boundary(self):
        p = self.ps[0]
        p.xp_spent['_elevations'] = 3
        self.s.stop = ('week', 18)
        self.L.schedule = [(18, 'GB', 'CHI', 20, 10)]
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 19)
        self.assertEqual(p.xp_spent['_elevations'], 3)
        self.weekly(18)
        self.assertIn(p, self.t._elevated)
        self.s.stop = ('playoffs', 0)
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 20)
        self.weekly(19)
        self.assertIn(p, self.t._elevated)
        self.s.stop = ('playoffs', 3)
        self.assertFalse(self.elevate(self.ps[1])['ok'])

    def test_legacy_unstamped_elevation_still_expires(self):
        p = self.ps[0]
        self.t._elevated = [p]
        p.xp_spent['_elevations'] = 1
        self.weekly(5)
        self.assertNotIn(p, self.t._elevated)
        self.assertEqual(p.xp_spent['_elevations'], 1)

    def test_playoff_bye_targets_divisional_game(self):
        self.s.stop = ('playoffs', 0)
        self.s.played = False
        self.s.post_live = N(seeds={'NFC': ['GB', 'CHI']}, exit_round={})
        p = self.ps[0]
        self.assertTrue(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevation_week'], 20)
        self.weekly(19)
        self.assertIn(p, self.t._elevated)

    def test_health_and_season_limit_still_apply(self):
        p = self.ps[0]
        p.out_until = 9
        self.assertFalse(self.elevate(p)['ok'])
        self.assertNotIn('_elevations', p.xp_spent)
        p.out_until = None
        p.xp_spent['_elevations'] = 3
        with patch.object(PS, 'call_up', return_value=False):
            self.assertFalse(self.elevate(p)['ok'])
        self.assertEqual(p.xp_spent['_elevations'], 3)
        self.assertNotIn('_elevation_week', p.xp_spent)

    def test_permanent_callup_stays_active_across_roll(self):
        p = self.ps[0]
        with patch.object(PS, '_active_move', return_value=(True, None)):
            self.assertTrue(self.s.club_act('call_up', pid=p.pid)['ok'])
        self.weekly(5)
        self.assertIn(p, self.t.roster)
        self.assertNotIn(p, self.t.practice_squad)
        self.assertNotIn('_elevation_week', p.xp_spent)


if __name__ == '__main__':
    unittest.main()
