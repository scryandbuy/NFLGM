import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

import gameplan as GP
import gameplan_week as GW
import game_recap as GR
from session import Session
from test_pregame_protection import team


class ProtectionDefaults(unittest.TestCase):
    def test_moderate_matchups_choose_help_without_recommendation_card(self):
        me, opp = team('GB'), team('KC')
        league = N(year=2029, teams={'GB': me, 'KC': opp}, tendencies={})
        for matchups, expected in [
            ([dict(role='LT', gap=7, rusher='Edge', blocker='Tackle')], 'six'),
            ([dict(role='LG', gap=5), dict(role='RG', gap=5)], 'full_slide'),
            ([dict(role='LT', gap=0)], 'half_slide'),
        ]:
            with self.subTest(expected=expected), patch.object(GW, 'protection_suggestion', return_value=None):
                choice = GW.protection_choice(league, me, opp, 1, read={'matchups': matchups})
                self.assertEqual(choice['value'], expected)
                self.assertTrue(choice['why'])

    def test_supported_empty_advice_is_default_too(self):
        me, opp = team('GB'), team('KC')
        league = N(year=2029, teams={'GB': me, 'KC': opp}, tendencies={})
        with patch.object(GW, 'protection_suggestion', return_value=dict(changes={'protection':'empty'}, why='Favorable line and receiver matchups')):
            self.assertEqual(GW.protection_choice(league, me, opp, 3, read={'why':''})['value'], 'empty')

    def test_legacy_shadow_target_is_recovered_without_overwriting_manual(self):
        league = N(year=2029, user_week_plan=dict(year=2029, week=3,
            changes={'travel':True,'bracket':'star'},
            suggestions={'Take away Star': {'travel':True,'bracket':'star'}}))
        original = copy.deepcopy(league.user_week_plan)
        self.assertEqual(GW.saved_changes(league, 3)['travel_target'], 'star')
        self.assertEqual(league.user_week_plan, original)
        league.user_week_plan['changes']['travel_target'] = 'other'
        self.assertEqual(GW.saved_changes(league, 3)['travel_target'], 'other')
        league.user_week_plan['changes'].update(travel=False, travel_target=None)
        self.assertIsNone(GW.saved_changes(league, 3)['travel_target'])
        self.assertEqual(GW.saved_changes(league, 4), {})


class WeeklyPlanIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Session.new('GB', seed=23)

    def setUp(self):
        self.s.stop = ('week', 1)
        self.s.played = False
        self.s.runner = None
        self.s.L.user_week_plan = None

    def test_shadow_advice_names_same_receiver_in_controls_engine_and_review(self):
        opp = self.s._opponent(1)[0]
        wrs = [p for p in self.s.L.teams[opp].depth['WR'] if p.out_until is None]
        old = [dict(p.ratings) for p in wrs]
        try:
            for p in wrs: p.ratings = {k:75 for k in p.ratings}
            wrs[0].ratings = {k:97 for k in wrs[0].ratings}
            view = self.s.plan_view('this_week')
            recommendation = next(r for r in view['suggestions'] if r['changes'].get('travel'))
            self.s.plan_act('set_decision', key='travel', value=False)
            self.assertTrue(self.s.plan_act('take', i=recommendation['i'])['ok'])
            target = wrs[0].pid
            view = self.s.plan_view('this_week')
            self.assertTrue(view['travel'])
            self.assertEqual(view['travel_target']['pid'], target)
            self.assertEqual(view['bracket']['pid'], target)
            state = N(plan=GP.Gameplan(), base_plan=GP.Gameplan())
            GW.user_plan(self.s.L, state, 1)
            self.assertEqual(state.plan.travel_target, target)
            self.assertTrue(state.plan.travel_locked)
            captured = GR.capture(self.s.L, state, 1)
            self.assertEqual(captured['changes']['travel_target'], target)
            self.assertEqual(captured['installed']['travel_target'], target)
            loaded = Session.load(self.s.save())
            self.assertEqual(loaded.plan_view('this_week')['travel_target']['pid'], target)
            self.s.plan_act('set_decision', key='travel', value=False)
            off = self.s.plan_view('this_week')
            self.assertFalse(off['travel'])
            self.assertIsNone(off['travel_target'])
        finally:
            for p, value in zip(wrs, old): p.ratings = value

    def test_default_without_acceptance_manual_override_and_next_week(self):
        with patch.object(GW, 'protection_choice', return_value=dict(value='full_slide', why='Interior matchups')):
            view = self.s.plan_view('this_week')
            self.assertEqual(view['protection']['value'], 'full_slide')
            self.assertEqual(view['protection']['recommended'], 'full_slide')
            self.assertIsNone(self.s.L.user_week_plan)
            state = N(plan=GP.Gameplan(), base_plan=GP.Gameplan())
            GW.user_plan(self.s.L, state, 1)
            self.assertEqual(state.plan.protection, 'full_slide')
            self.assertTrue(state.plan.protection_locked)
            # CPU default applies even when the coordinator accepts no cards.
            cpu = N(plan=GP.Gameplan(), base_plan=GP.Gameplan(), coach={})
            GW.ai_plan(self.s.L, cpu, 'GB', self.s._opponent(1)[0], 1, N(random=lambda: 1.0))
            self.assertEqual(cpu.plan.protection, 'full_slide')
            self.s.plan_act('save')
            with patch.object(GW, 'protection_choice', return_value=dict(value='six', why='Changed matchup')):
                self.assertEqual(self.s.plan_view('this_week')['protection']['value'], 'full_slide')
                GW.user_plan(self.s.L, state, 1)
                self.assertEqual(state.plan.protection, 'full_slide')
            self.s.plan_act('reopen')
            self.s.plan_act('set_decision', key='protection', value='empty')
            self.assertEqual(self.s.plan_view('this_week')['protection']['value'], 'empty')
            GW.user_plan(self.s.L, state, 1)
            self.assertEqual(state.plan.protection, 'empty')
            loaded = Session.load(self.s.save())
            self.assertEqual(loaded.plan_view('this_week')['protection']['value'], 'empty')
        self.s.stop = ('week', 2)
        with patch.object(GW, 'protection_choice', return_value=dict(value='six', why='Edge matchup')):
            self.assertEqual(self.s.plan_view('this_week')['protection']['value'], 'six')
            state = N(plan=GP.Gameplan(), base_plan=GP.Gameplan())
            GW.user_plan(self.s.L, state, 2)
            self.assertEqual(state.plan.protection, 'six')


if __name__ == '__main__':
    unittest.main()
