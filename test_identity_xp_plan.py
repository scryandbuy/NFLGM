import copy
import unittest
from unittest.mock import patch

import numpy as np
import gameplan as GP
import gameplan_week as GW
import season
import staff
import xp
import personality as PT
import views_gameplan as VG
from session import Session
from cap_engine import Contract
from test_cap_accounting import fixture, player


class IdentityAndPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fresh = Session.new('GB', seed=23)
        cls.saved = cls.fresh.save()

    def test_first_game_and_reload_have_same_actual_staff_bonus(self):
        p = next(p for p in self.fresh.L.teams['GB'].roster if p.pos == 'QB')
        loaded = Session.load(self.saved)
        q = loaded.L.player(p.pid)
        expected = 1000 * PT.xp_mult(p) * staff.xp_mult(self.fresh.L.teams['GB'], p)
        self.assertIs(p._team_ref, self.fresh.L.teams['GB'])
        self.assertIs(q._team_ref, loaded.L.teams['GB'])
        self.assertAlmostEqual(xp.credit(p, 1000, 'test'), expected)
        self.assertAlmostEqual(xp.credit(q, 1000, 'test'), expected)

    def test_identity_changes_refresh_caller_preserve_health_and_weekly_choices(self):
        s = Session.load(self.saved)
        s.stop = ('week', 1)
        s.runner = season.SeasonRunner(s.L, s.rng)
        st = s.runner.states['GB']
        pid = s.L.teams['GB'].roster[0].pid
        st.cond.cond[pid] = 61
        st.jaded[pid] = .25
        st.out.add(pid)
        st.injuries.append({'pid': pid, 'weeks': 2})
        s.plan_act('set_lean', key='tempo', value=st.base_plan.tempo + .1)
        s.plan_act('set_decision', key='protection', value='six')
        wp = copy.deepcopy(s.L.user_week_plan)
        before_rng = copy.deepcopy(s.rng.bit_generator.state)
        result = s.frontoffice_act('set_identity', changes={'def_front': '3-4', 'off_personnel': '11', 'off_blocking': 'gap'})
        self.assertTrue(result['ok'])
        self.assertEqual(st.base_plan.front_pref, ['3-4 one', '3-4 two', 'tite', 'mint'])
        self.assertEqual(st.base_plan.off_personnel, '11')
        self.assertEqual(st.coach_base['off_personnel'], '11')
        self.assertEqual(st.plan.protection, 'six')
        self.assertAlmostEqual(st.plan.tempo, st.base_plan.tempo + .1)
        self.assertEqual(st.scheme, s.L.teams['GB'].scheme)
        self.assertEqual(st.cond.cond[pid], 61)
        self.assertEqual(st.jaded[pid], .25)
        self.assertIn(pid, st.out)
        self.assertEqual(st.injuries, [{'pid': pid, 'weeks': 2}])
        s.runner.refresh('GB'); s.runner._staff_terms('GB')
        self.assertAlmostEqual(st.plan.tempo, st.base_plan.tempo + .1)
        self.assertEqual(s.L.user_week_plan, wp)
        self.assertEqual(s.rng.bit_generator.state, before_rng)
        # Kickoff starts with the new base and applies weekly choices once.
        opp, away = s._opponent(1)
        home, road = (opp, 'GB') if away else ('GB', opp)
        s.runner.open_live(home, road, 1)
        self.assertAlmostEqual(st.plan.tempo, st.base_plan.tempo + .1)
        self.assertEqual(st.plan.protection, 'six')

    def test_identity_is_frozen_during_live_game(self):
        s = Session.load(self.saved)
        s.runner = season.SeasonRunner(s.L, s.rng)
        s.runner.live = {'done': False}
        before = s.L.teams['GB'].gm.def_front
        self.assertFalse(s.frontoffice_act('set_identity', changes={'def_front': '3-4'})['ok'])
        self.assertEqual(s.L.teams['GB'].gm.def_front, before)

    def test_cpu_coach_change_is_seen_on_next_refresh(self):
        s = Session.load(self.saved)
        s.runner = season.SeasonRunner(s.L, s.rng)
        s.L.teams['MIN'].gm.def_front = '3-4'
        s.runner.refresh('MIN')
        self.assertIn('3-4 one', s.runner.states['MIN'].base_plan.front_pref)

    def test_screen_recommendation_survives_copy_adjustment_and_session_reload(self):
        s = Session.load(self.saved)
        s.stop = ('week', 1)
        s.runner = season.SeasonRunner(s.L, s.rng)
        st = s.runner.states['GB']
        GW.apply_changes(st.plan, st.base_plan, {'screen_boost': .03})
        adjusted, applied = GP.apply_change(st.plan, 'tempo', .05, skill=1)
        self.assertTrue(applied)
        self.assertEqual(adjusted.screen_boost, .03)
        st.plan = adjusted
        loaded = Session.load(s.save())
        self.assertEqual(loaded.runner.states['GB'].plan.screen_boost, .03)
        self.assertFalse(loaded.runner.refresh_identity('GB'))
        self.assertEqual(loaded.runner.states['GB'].plan.screen_boost, .03)

    def test_box_shift_reaches_live_snap_resolver(self):
        import game, plays
        s = Session.load(self.saved)
        runner = season.SeasonRunner(s.L, s.rng)
        defense = runner.states['MIN']
        defense.plan.box_bias = .12
        co, cd = season._deps()
        class Captured(Exception): pass
        def call_def(*args, **kwargs):
            result = cd(*args, **kwargs)
            result['box'] = 6
            return result
        def resolve(off, deff, oc, dc, yards, rng):
            self.assertEqual(dc['box'], 7)
            raise Captured()
        with patch.object(GP, 'box_shift', return_value=1) as shift:
            with self.assertRaises(Captured):
                list(game.drive_steps(runner.states['GB'].roster, defense.roster, 75, 900, 1, 0,
                                      s.rng, resolve, co, call_def, plays.rate,
                                      off_state=runner.states['GB'], def_state=defense))
            shift.assert_called_once_with(.12, s.rng)


class XpOwnershipTests(unittest.TestCase):
    def test_trade_release_squad_and_sign_resolve_current_staff(self):
        import practice_squad as PS
        L = fixture()
        p = player(L, contract=Contract(2, [1, 1]))
        with patch.object(staff, 'xp_mult', side_effect=lambda t, p: 1.1 if t.abbr == 'GB' else .9):
            baseline = 100 * PT.xp_mult(p)
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline * 1.1)
            L.trade('GB', 'MIN', [p.pid], [])
            self.assertIs(p._team_ref, L.teams['MIN'])
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline * .9)
            p._team_ref = L.teams['GB']  # legacy stale cache still resolves by p.team
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline * .9)
            L.release(p.pid)
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline)
            self.assertTrue(PS.sign_to_squad(L, 'GB', p.pid))
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline * 1.1)
            PS.release_from_squad(L, 'GB', p.pid)
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline)
            L.sign(p.pid, 'MIN', Contract(1, [1]))
            self.assertAlmostEqual(xp.credit(p, 100, 'test'), baseline * .9)


class BoxFrequencyTests(unittest.TestCase):
    def test_recommendations_change_frequency_in_both_directions(self):
        for bias in (.12, -.05, .25, -.25, .45):
            rng = np.random.default_rng(91)
            draws = [GP.box_shift(bias, rng) for _ in range(10000)]
            self.assertAlmostEqual(np.mean(draws), bias * 4, delta=.025)
            if bias > 0: self.assertGreater(max(draws), 0)
            else: self.assertLess(min(draws), 0)
        self.assertEqual(VG._lean_word('box_bias', .12), '+0.48 avg')
        self.assertEqual(VG._lean_word('box_bias', -.05), '-0.20 avg')

    def test_neutral_does_not_draw_randomness(self):
        rng = np.random.default_rng(17)
        before = copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(GP.box_shift(0, rng), 0)
        self.assertEqual(before, rng.bit_generator.state)


if __name__ == '__main__':
    unittest.main()
