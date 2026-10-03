"""Recovery is a calendar event, not a practice or kickoff bonus."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import health as H
import practice as PR
import practice_integration as PI
from test_practice_engine import setup, plan
import test_practice_integration as integration_tests
from session import Session
from season import SeasonRunner


class WeeklyRecoveryTests(unittest.TestCase):
    def fixture(self):
        league, runner, players = setup()
        runner.L = league
        league.schedule = [(12, 'A', 'B', 14, 21)]
        league.user_team = 'A'
        # Same player attributes/condition on the user and CPU clubs.
        other = copy.deepcopy(league.teams['A'])
        other.abbr = 'B'
        for p in other.roster + other.practice_squad:
            p.pid = 'cpu' + p.pid
            p.team = 'B'
        league.teams['B'] = other
        runner.states['B'] = copy.deepcopy(runner.states['A'])
        for abbr, team in league.teams.items():
            for p in team.roster + team.practice_squad:
                runner.states[abbr].cond.cond[p.pid] = 0.
                runner.states[abbr].jaded[p.pid] = .2
        return league, runner, players

    def test_all_clubs_and_squad_recover_once_without_resetting_to_full(self):
        league, runner, players = self.fixture()
        rng = copy.deepcopy(runner.rng.bit_generator.state)
        PI.recover_week(runner, 13)
        expected = H.recover_between_games(0, 80, 7, .2)
        self.assertAlmostEqual(expected, 81.84)
        for abbr, team in league.teams.items():
            for p in team.roster + team.practice_squad:
                self.assertAlmostEqual(runner.states[abbr].cond.get(p.pid), expected)
        before = copy.deepcopy(league.practice_state)
        PI.recover_week(runner, 13)
        self.assertEqual(before, league.practice_state)
        self.assertEqual(rng, runner.rng.bit_generator.state)
        # Practice removes only its workload, with no second weekly recovery.
        for abbr in league.teams:
            preview = PR.preview(league, runner, abbr, 13, plan('standard'))
            self.assertAlmostEqual(preview['players'][0]['condition'], expected - 1)
            result = PR.resolve(league, runner, abbr, 13, plan('standard'))
            self.assertEqual(preview['players'][0]['condition'], runner.states[abbr].cond.get(preview['players'][0]['pid']))

    def test_practice_and_opening_preview_never_recover_even_without_marker(self):
        league, runner, players = self.fixture()
        before = copy.deepcopy(runner.states['A'].cond.cond)
        preview = PR.preview(league, runner, 'A', 13)
        self.assertTrue(all(p['condition'] == 0 for p in preview['players']))
        self.assertEqual(before, runner.states['A'].cond.cond)
        PR.resolve(league, runner, 'A', 13)
        self.assertEqual(before, runner.states['A'].cond.cond)

    def test_bye_relief_applies_after_bye_not_before(self):
        league, runner, players = self.fixture()
        league.schedule = [(11, 'A', 'B', 14, 21), (13, 'A', 'B', None, None)]
        PI.recover_week(runner, 12)
        st = runner.states['A']
        p = players[0]
        self.assertEqual(st.jaded[p.pid], .2)
        PR.resolve(league, runner, 'A', 12, plan('standard'), bye=True)
        self.assertEqual(st.jaded[p.pid], .2)
        before = st.cond.get(p.pid)
        PI.recover_week(runner, 13)
        self.assertAlmostEqual(st.jaded[p.pid], .08)
        self.assertAlmostEqual(st.cond.get(p.pid), H.recover_between_games(before, 80, 7, .08))

    def test_postseason_bye_and_round_recovery(self):
        league, runner, players = self.fixture()
        league.schedule = [(18, 'A', 'B', 14, 21)]
        league._post_ref = NS(champion=None, alive_now=lambda: {'A', 'B'})
        PI.recover_week(runner, 19)
        league.schedule.append((19, 'B', 'X', 14, 21))
        PI.recover_week(runner, 20)
        self.assertAlmostEqual(runner.states['A'].jaded[players[0].pid], .08)
        self.assertAlmostEqual(runner.states['B'].jaded['cpu' + players[0].pid], .2)

    def test_transfer_after_recovery_cannot_gain_second_week_of_rest(self):
        league, runner, players = self.fixture()
        PI.recover_week(runner, 13)
        p = players[0]
        c = runner.states['A'].cond.get(p.pid)
        league.teams['A'].roster.remove(p)
        league.teams['B'].roster.append(p)
        p.team = 'B'
        PI.restore_transfers(runner, 'B')
        PI.recover_week(runner, 13)
        self.assertEqual(runner.states['B'].cond.get(p.pid), c)

    def session_fixture(self):
        s = integration_tests.PracticeIntegrationTests().fixture()
        s.runner = SeasonRunner(s.L, s.rng)
        s.stop = ('week', 13)
        s.L.week = 13
        s.L.schedule = [(12, 'MIN', 'GB', 14, 21), (13, 'MIN', 'GB', None, None)]
        for abbr, st in s.runner.states.items():
            for p in s.L.teams[abbr].roster:
                st.cond.cond[p.pid] = 0
                st.jaded[p.pid] = .2
        return s

    def test_old_save_mixed_practice_migrates_only_unrecovered_club(self):
        s = self.session_fixture()
        user = s.L.teams['GB'].roster[0]
        cpu = s.L.teams['MIN'].roster[0]
        s.runner.states['GB'].cond.cond[user.pid] = 96
        s.L.practice_state = {'completed': {'2026:13': {'GB': {'players': []}}}}
        loaded = Session.load(s.save())
        self.assertEqual(loaded.runner.states['GB'].cond.get(user.pid), 96)
        self.assertAlmostEqual(loaded.runner.states['MIN'].cond.get(cpu.pid), 81.84)
        again = Session.load(loaded.save())
        self.assertAlmostEqual(again.runner.states['MIN'].cond.get(cpu.pid), 81.84)

    def test_played_save_keeps_game_condition_until_advance(self):
        s = self.session_fixture()
        s.played = True
        s.L.schedule[-1] = (13, 'MIN', 'GB', 14, 21)
        s.L.practice_state = {'version': 1}
        loaded = Session.load(s.save())
        p = loaded.L.teams['MIN'].roster[0]
        self.assertEqual(loaded.runner.states['MIN'].cond.get(p.pid), 0)
        PI.recover_week(loaded.runner, 14)
        self.assertAlmostEqual(loaded.runner.states['MIN'].cond.get(p.pid), 81.84)

    def test_new_save_reload_and_practice_do_not_recover_again(self):
        s = self.session_fixture()
        PI.recover_week(s.runner, 13)
        loaded = Session.load(s.save())
        p = loaded.L.teams['GB'].roster[0]
        self.assertAlmostEqual(loaded.runner.states['GB'].cond.get(p.pid), 81.84)
        plan_json = __import__('json').dumps(plan('standard'))
        self.assertTrue(loaded.practice_act('save', plan_json)['ok'])
        self.assertTrue(loaded.practice_act('run')['ok'])
        self.assertEqual(loaded.runner.states['GB'].cond.get(p.pid), 80.84)
        again = Session.load(loaded.save())
        self.assertEqual(again.runner.states['GB'].cond.get(p.pid), 80.84)

    def test_real_session_advance_recovers_all_32_clubs_before_next_decisions(self):
        import league as LG
        import numpy as np
        rng = np.random.default_rng(231)
        league = LG.build_league(rng=rng)
        s = Session(league, rng, 'GB')
        league.set_phase('regular')
        s.stop = ('week', 12)
        s.played = True
        league.week = 12
        league.schedule = [(w, a, h, 14 if w == 12 else ap, 21 if w == 12 else hp)
                           for w, a, h, ap, hp in league.schedule]
        s.runner = SeasonRunner(league, rng)
        s.runner.last_played = [(h, a, hp, ap) for w, a, h, ap, hp in league.schedule if w == 12]
        tracked = {}
        for abbr, st in s.runner.states.items():
            p = league.teams[abbr].roster[0]
            st.cond.cond[p.pid] = 0.
            st.jaded[p.pid] = .2
            bye = not any(w == 12 and abbr in (a, h) for w, a, h, ap, hp in league.schedule)
            tracked[abbr] = (p.pid, H.recover_between_games(0, PR._fitness(p), 7, .08 if bye else .2))
        observed = []
        def report(*args, **kwargs):
            observed.append({a: s.runner.states[a].cond.get(pid) for a, (pid, _) in tracked.items()})
        with patch('gameplan_week.post_report', side_effect=report):
            result = s._advance()
        self.assertEqual(s.stop, ('week', 13))
        self.assertEqual(result['done'], 'Week 12')
        self.assertTrue(observed)
        for abbr, (pid, expected) in tracked.items():
            self.assertAlmostEqual(s.runner.states[abbr].cond.get(pid), expected)
            self.assertAlmostEqual(observed[0][abbr], expected)
        self.assertIsNone(PI.result(league, 'GB', 13))


if __name__ == '__main__':
    unittest.main()
