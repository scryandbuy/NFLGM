"""Regression checks for saving an in-progress game and season health."""
import json
import unittest
from types import SimpleNamespace

import game
import numpy as np
import season
import session


class SaveResumeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = session.Session.new('GB', seed=17).save()

    def fresh_session(self):
        return session.Session.load(self.baseline)

    def test_live_game_replays_to_same_finish(self):
        original = self.fresh_session()
        runner = season.SeasonRunner(original.L, original.rng)
        week, away, home, *_ = next(g for g in original.L.schedule
                                    if g[0] == 1 and original.user_team in g[1:3])
        runner.week = week
        runner.open_live(home, away, week)
        original.runner = runner
        original.stop = ('week', week)
        original.played = True
        for _ in range(4): original.live_step('play')
        original.live_step('half')
        if runner.live['halftime_open'] and runner.live.get('half_recs'):
            original.half_take(0, True)
        before = original.gameday_view()
        resumed = session.Session.load(original.save())
        self.assertEqual(before, resumed.gameday_view())
        self.assertEqual(json.loads(json.dumps(runner.live['actions'])),
                         resumed.runner.live['actions'])
        original._finish_live()
        resumed._finish_live()
        self.assertEqual(runner.live['score'], resumed.runner.live['score'])
        self.assertEqual(runner.live['book'].p, resumed.runner.live['book'].p)

    def test_live_journal_appends_to_existing_saved_actions(self):
        original = self.fresh_session()
        runner = season.SeasonRunner(original.L, original.rng)
        week, away, home, *_ = next(g for g in original.L.schedule
                                    if g[0] == 1 and original.user_team in g[1:3])
        runner.week = week
        runner.open_live(home, away, week)
        original.runner = runner
        original.stop = ('week', week)
        original.played = True
        for _ in range(2): original.live_step('play')
        base = original.save()
        for _ in range(2): original.live_step('play')
        journal = json.loads(json.dumps(original.live_journal()))
        resumed = session.Session.load(base)
        self.assertTrue(resumed.apply_live_journal(journal))
        self.assertEqual(original.gameday_view(), resumed.gameday_view())
        self.assertEqual(len(resumed.runner.live['actions']), 4)

    def test_season_health_and_injury_decisions_survive_load(self):
        original = self.fresh_session()
        original.runner = season.SeasonRunner(original.L, original.rng)
        state = original.runner.states['GB']
        state.cond.cond['player-check'] = 73.5
        state.jaded['player-check'] = 0.27
        state.last_snaps = {'player-check': 42}
        original.runner.desks['GB'].pending['player-check'] = 'questionable'
        original.runner._listed_week = 5
        original.L.week_book = {'player-check': {'snaps': 42}}
        resumed = session.Session.load(original.save())
        other = resumed.runner.states['GB']
        self.assertEqual(other.cond.cond['player-check'], 73.5)
        self.assertEqual(other.jaded['player-check'], 0.27)
        self.assertEqual(other.last_snaps['player-check'], 42)
        self.assertEqual(resumed.runner.desks['GB'].pending['player-check'], 'questionable')
        self.assertEqual(resumed.runner._listed_week, 5)
        self.assertEqual(resumed.L.week_book['player-check']['snaps'], 42)

    def test_script_opens_again_next_game(self):
        state = game.TeamState({}, coach={'script_length': 15})
        state.script.used = 15
        state.script.active = False
        state.end_game(np.random.default_rng(1), bye=True)
        self.assertEqual(state.script.used, 0)
        self.assertTrue(state.script.active)

    def test_live_journal_replays_actions_after_full_save(self):
        original = self.fresh_session()
        runner = season.SeasonRunner(original.L, original.rng)
        week, away, home, *_ = next(g for g in original.L.schedule
                                    if g[0] == 1 and original.user_team in g[1:3])
        runner.week = week
        runner.open_live(home, away, week)
        original.runner = runner
        original.stop = ('week', week)
        original.played = True
        base = original.save()
        for _ in range(4): original.live_step('play')
        journal = json.loads(json.dumps(original.live_journal()))
        self.assertLess(len(json.dumps(journal)), len(base) // 100)
        resumed = session.Session.load(base)
        self.assertTrue(resumed.apply_live_journal(journal))
        self.assertEqual(original.gameday_view(), resumed.gameday_view())
        original._finish_live()
        resumed._finish_live()
        self.assertEqual(runner.live['score'], resumed.runner.live['score'])
        self.assertEqual(runner.live['book'].p, resumed.runner.live['book'].p)

    def test_retry_includes_games_completed_before_interruption(self):
        runner = season.SeasonRunner.__new__(season.SeasonRunner)
        runner.L = SimpleNamespace(schedule=[(1, 'A', 'B', None, None),
                                             (1, 'C', 'D', None, None)], week=1,
                                   week_book={'first-game': {'snaps': 1}})
        runner.week = 1
        runner.desks = {}
        runner.states = {}
        runner._listed_week = 1
        runner.last_games = []
        runner._after_games = lambda _week, _played: None
        calls = 0
        def interrupted(_home, _away, _week):
            nonlocal calls
            calls += 1
            if calls == 2: raise RuntimeError('interrupted')
            runner.L.week_book['first-game'] = {'snaps': 1}
            runner._book = game.StatBook()
            return {'home': 17, 'away': 10}
        runner.play = interrupted
        with self.assertRaises(RuntimeError): runner.play_games(1)
        runner.play = lambda _home, _away, _week: {'home': 21, 'away': 14}
        runner._book = game.StatBook()
        played = runner.play_games(1)
        self.assertEqual(played, [('B', 'A', 17, 10), ('D', 'C', 21, 14)])
        self.assertEqual(len(runner.last_games), 2)
        self.assertIn('first-game', runner.L.week_book)


if __name__ == '__main__':
    unittest.main()
