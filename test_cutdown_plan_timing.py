"""The cutdown claim window must finish before Week 1 planning opens."""
import copy
import json
import unittest
from unittest.mock import patch

import gameplan_week as GW
import session as SS
import views
import views_gameplan as VG


class CutdownPlanTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = SS.Session.new('GB', seed=41).save()

    def fresh(self):
        return SS.Session.load(self.initial)

    def reports(self, s):
        return [m for m in s.L.inbox if m.get('kind') == 'game_plan'
                and m.get('year') == s.L.year and m.get('payload', {}).get('link') == 'gameplan:1']

    def test_new_game_and_waivers_do_not_open_week_one_surfaces_or_actions(self):
        s = self.fresh()
        self.assertEqual(self.reports(s), [])
        for stop in [('cutdown',), ('wire',), ('offseason', 11)]:
            s.stop = stop
            before = copy.deepcopy(getattr(s.L, 'user_week_plan', None))
            with patch.object(GW, 'opponent_report', side_effect=AssertionError('too early')):
                self.assertTrue(s.plan_view('this_week')['off'])
                self.assertTrue(s.plan_view('report')['off'])
                self.assertIsNone(views._matchup(s, s.L, 'GB'))
                for action in ('save', 'reopen', 'reset'):
                    self.assertFalse(s.plan_act(action)['ok'])
                self.assertFalse(s.plan_take_all()['ok'])
            self.assertEqual(getattr(s.L, 'user_week_plan', None), before)
            if stop[0] == 'wire':
                self.assertEqual(s.next_label()['title'], 'Post-Cutdown Waivers')
                self.assertEqual(views.rail(s, s.L, 'GB')['clock']['line'], 'Post-Cutdown Waivers')
            if stop[0] in ('cutdown', 'wire'):
                s.gameday = dict(week=18, scores=[], game=None)
                self.assertTrue(views.gameday(s, s.L, 'GB')['empty'])
                self.assertFalse(views.gameday(s, s.L, 'GB', gd=s.gameday)['empty'])

    def test_successful_clear_posts_report_only_after_entering_week_one(self):
        s = self.fresh(); s.stop = ('wire',)
        real_post = GW.post_report
        def check(league, week):
            self.assertEqual(s.stop, ('week', 1))
            return real_post(league, week)
        with patch.object(s, 'step_clear_wire', return_value=None), patch.object(GW, 'post_report', side_effect=check) as post:
            s._advance()
        post.assert_called_once_with(s.L, 1)
        self.assertEqual(len(self.reports(s)), 1)
        self.assertFalse(s.plan_view('this_week').get('off', False))
        self.assertTrue(s.plan_act('save')['ok'])

    def test_unresolved_roster_problem_blocks_without_opening_game_plan(self):
        s = self.fresh(); s.stop = ('wire',)
        with patch.object(s, 'step_clear_wire', return_value=False), patch.object(GW, 'post_report') as post:
            s._advance()
        post.assert_not_called()
        self.assertEqual(s.stop, ('wire',))
        self.assertTrue(s.plan_view('this_week')['off'])

    def test_new_repair_cuts_carry_into_week_one_without_another_stage(self):
        import waivers as WV
        s = self.fresh(); s.stop = ('wire',)
        old = dict(pid='opening', from_team='MIN', user_notified=True)
        new = dict(pid='fresh-cut', from_team='CHI', user_notified=False)
        s.L.waivers = [old]
        def repair(*_):
            if new not in s.L.waivers: s.L.waivers.append(new)
        def process(league, rng, week, *, entries):
            self.assertEqual(entries, [old])
            league.waivers.remove(old)
        with patch.object(SS.CD, 'finalize', side_effect=repair), \
             patch.object(SS.CD, 'violations', return_value=[]), \
             patch.object(WV, 'process', side_effect=process), \
             patch('veteran_market.review'), \
             patch.object(WV, 'notify_user') as notice, \
             patch.object(SS.PSQ, 'fill_squads'), patch('franchise.clear_undrafted'), \
             patch.object(SS.MO, 'review_captains'), patch.object(GW, 'post_report') as post:
            result = s._advance()
        self.assertEqual(result['done'], 'Post-Cutdown Waivers')
        self.assertEqual(s.stop, ('week', 1))
        self.assertEqual(s.L.waivers, [new])
        notice.assert_called_once_with(s.L, [new], 1, digest=True)
        post.assert_called_once_with(s.L, 1)

    def test_legacy_premature_report_is_replaced_without_deleting_history_or_plan(self):
        s = self.fresh(); s.stop = ('wire',)
        GW.post_report(s.L, 1)
        old = copy.deepcopy(self.reports(s)[0]); old['year'] -= 1; old['id'] += 1000
        s.L.inbox.append(old)
        s.L.user_week_plan = dict(year=s.L.year, week=1, changes={'pass_bias': .05})
        resumed = SS.Session.load(s.save())
        self.assertEqual(self.reports(resumed), [])
        self.assertTrue(any(m['id'] == old['id'] for m in resumed.L.inbox))
        self.assertEqual(resumed.L.user_week_plan['changes'], {'pass_bias': .05})
        with patch.object(resumed, 'step_clear_wire', return_value=None): resumed._advance()
        self.assertEqual(len(self.reports(resumed)), 1)
        loaded = SS.Session.load(resumed.save())
        self.assertEqual(len(self.reports(loaded)), 1)

    def test_each_year_cutdown_defers_report_until_claims_clear(self):
        s = self.fresh(); s.stop = ('offseason', len(s.OFFSEASON)-1)
        with patch.object(s, 'blocking', return_value=[]), patch.object(s, 'step_cutdown'), patch.object(GW, 'post_report') as post:
            s._advance()
        self.assertEqual(s.stop, ('wire',))
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
