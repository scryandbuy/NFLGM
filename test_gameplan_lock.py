import copy
import json
import unittest
from unittest.mock import patch

from session import Session
import gameplan_week as GW


class GameplanLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session.new('GB', seed=23)

    def setUp(self):
        self.s = self.session
        self.s.stop = ('week', 1)
        self.s.played = False
        self.s.runner = None
        self.s.L.user_week_plan = None

    def test_save_none_and_block_all_edit_paths(self):
        self.assertTrue(self.s.plan_act('save')['ok'])
        before = copy.deepcopy(self.s.L.user_week_plan)
        self.assertEqual({}, before['changes'])
        for action, kw in [('take', {'i': 0}), ('untake', {'i': 0}), ('skip', {'i': 0}),
                           ('set_lean', {'key': 'pass_bias', 'value': .1}),
                           ('set_depth', {'short': 50, 'medium': 30, 'deep': 20}),
                           ('set_decision', {'key': 'protection', 'value': 'six'}), ('reset', {})]:
            with self.subTest(action=action):
                self.assertFalse(self.s.plan_act(action, **kw)['ok'])
        self.assertFalse(self.s.plan_take_all()['ok'])
        self.assertEqual(before, self.s.L.user_week_plan)
        self.assertTrue(self.s.plan_view('this_week')['plan_state']['locked'])
        self.assertTrue(self.s.plan_view('report')['plan_state']['locked'])

    def test_partial_choices_and_manual_settings_survive_repeated_cycles(self):
        suggestions = [dict(text='A', changes={'pass_bias': .04}),
                       dict(text='B', changes={'blitz_rate': .03})]
        with patch.object(GW, 'opponent_report', return_value={'suggestions': suggestions}):
            self.s.plan_act('take', i=0)
            self.s.plan_act('skip', i=1)
            self.s.plan_act('set_decision', key='protection', value='six')
            self.s.plan_act('set_decision', key='travel', value=False)
            for _ in range(3):
                self.assertTrue(self.s.plan_act('save')['ok'])
                saved = copy.deepcopy(self.s.L.user_week_plan)
                self.assertTrue(self.s.plan_act('reopen')['ok'])
                current = self.s.L.user_week_plan
                for key in ('changes', 'manual', 'suggestions', 'taken', 'skipped'):
                    self.assertEqual(saved[key], current[key])
                self.assertFalse(current['dirty'])
                self.assertFalse(current['locked'])
                self.s.plan_act('set_decision', key='protection', value='six')
                self.assertTrue(current is not self.s.L.user_week_plan)
                self.assertTrue(self.s.L.user_week_plan['dirty'])
            self.assertEqual(['B'], self.s.L.user_week_plan['skipped'])

    def test_accept_all_and_save_reload(self):
        self.s.plan_take_all()
        self.assertTrue(self.s.plan_view('status')['dirty'])
        self.s.plan_act('save')
        loaded = Session.load(self.s.save())
        self.assertEqual(json.loads(json.dumps(self.s.L.user_week_plan)), loaded.L.user_week_plan)
        self.assertTrue(loaded.plan_view('status')['locked'])
        self.assertFalse(loaded.plan_view('status')['dirty'])
        self.assertTrue(loaded.plan_act('reopen')['ok'])
        loaded.plan_act('set_decision', key='protection', value='empty')
        resumed = Session.load(loaded.save())
        self.assertTrue(resumed.plan_view('status')['dirty'])
        self.assertFalse(resumed.plan_view('status')['locked'])

    def test_save_failure_keeps_changes_and_unlocks(self):
        self.s.plan_act('set_decision', key='protection', value='six')
        self.s.plan_act('save')
        self.s.plan_act('save_failed')
        self.assertEqual('six', self.s.L.user_week_plan['changes']['protection'])
        self.assertTrue(self.s.plan_view('status')['dirty'])
        self.assertFalse(self.s.plan_view('status')['locked'])
        self.assertTrue(self.s.plan_act('save')['ok'])

    def test_lock_does_not_carry_to_another_week_year_or_playoff_round(self):
        self.s.plan_act('save')
        self.s.stop = ('week', 2)
        self.assertFalse(self.s.plan_view('status')['locked'])
        self.assertFalse(self.s.plan_view('status')['dirty'])
        self.s.stop = ('cutdown',)
        self.s.L.user_week_plan['year'] -= 1
        self.assertFalse(self.s.plan_view('status')['locked'])
        self.s.stop = ('playoffs', 0)
        with patch.object(self.s, '_opponent', return_value=('MIN', False)):
            self.assertTrue(self.s.plan_act('save')['ok'])
            self.assertEqual(19, self.s.L.user_week_plan['week'])
            self.s.stop = ('playoffs', 1)
            self.assertFalse(self.s.plan_view('status')['locked'])

    def test_cannot_reopen_after_kickoff(self):
        self.s.plan_act('save')
        self.s.played = True
        self.assertFalse(self.s.plan_act('reopen')['ok'])


if __name__ == '__main__':
    unittest.main()
