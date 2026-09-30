"""Break gating, reversible plans, per-period capture and replay coverage."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import gameplan as GP
import halftime as HT
from season import SeasonRunner
from session import Session


class BreakFlowTests(unittest.TestCase):
    def runner(self):
        r = SeasonRunner.__new__(SeasonRunner)
        r.rng = np.random.default_rng(71)
        r.L = NS(user_team='GB')
        st = NS(plan=GP.Gameplan(), base_plan=GP.Gameplan())
        st.plan.protection = 'full_slide'
        st.plan.depth_mix = (.85, .1, .05)
        r.states = {'GB':st}
        r.live = dict(home='GB',away='LAC',week=2,drives=[],current=None,pos='away',score=dict(home=0,away=0),
                      halftime_open=False,at='kick',done=False,res=None,actions=[],start={'adjustment_version':2})
        def events():
            yield ('halftime',dict(home=7,away=7))
            yield ('overtime',dict(home=24,away=24))
            self.applied = copy.deepcopy(st.plan.__dict__)
            return dict(home=31,away=24,drives=[],overtime=True)
        r.live['gen'] = events()
        r._close_live = lambda: None
        return r

    def suggestions(self,*a,**kw):
        return [dict(text='Protect',side='offence',why='Pressure',changes={'protection':'six','depth_mix':(.08,0,-.08)})]

    @patch('halftime.recommendations')
    def test_finish_pauses_both_breaks_and_choices_are_reversible(self,mock):
        mock.side_effect=self.suggestions
        r=self.runner();original=copy.deepcopy(r.states['GB'].plan.__dict__)
        r.live_step('finish');self.assertEqual(r.live['at'],'halftime')
        r.half_take(0,True);r.half_take(0,False)
        self.assertEqual(r.states['GB'].plan.__dict__,original)
        r.half_take(0,True)
        halftime_plan=copy.deepcopy(r.states['GB'].plan.__dict__)
        r.live_step('resume');self.assertEqual(r.live['at'],'overtime')
        self.assertTrue(r.live['halftime_open']);self.assertFalse(r.live['done'])
        self.assertEqual(mock.call_args.kwargs['period'],'overtime')
        r.live_step('finish');self.assertFalse(r.live['done'])
        r.half_take(0,True);r.half_take(0,False)
        self.assertEqual(r.states['GB'].plan.__dict__,halftime_plan)
        self.assertTrue(r.live['half_recs'][0]['taken'])
        self.assertFalse(r.live['ot_recs'][0]['taken'])
        r.half_take(0,True);expected=copy.deepcopy(r.states['GB'].plan.__dict__)
        r.live_step('resume');self.assertTrue(r.live['done'])
        self.assertEqual(self.applied,expected)

    @patch('halftime.recommendations')
    def test_ot_journal_replays_same_choices_without_second_application(self,mock):
        mock.side_effect=self.suggestions
        r=self.runner();r.live_step('finish');r.half_take(0,True);r.live_step('resume');r.half_take(0,True)
        actions=copy.deepcopy(r.live['actions'])
        restored=self.runner();restored.replay_live(actions,copy.deepcopy(r.rng.bit_generator.state))
        self.assertEqual(restored.live['at'],'overtime')
        self.assertEqual(restored.states['GB'].plan.__dict__,r.states['GB'].plan.__dict__)
        self.assertEqual(restored.live['half_recs'],r.live['half_recs'])
        self.assertEqual(restored.live['ot_recs'],r.live['ot_recs'])

    @patch('halftime.recommendations')
    def test_finish_helper_handles_both_stops(self,mock):
        mock.side_effect=self.suggestions
        s=Session.__new__(Session);s.runner=self.runner();s._capture_gameday=lambda w:None
        self.assertTrue(s._finish_live());self.assertTrue(s.runner.live['done'])

    def test_recommendation_stats_count_pressure_once_and_scramble_as_pass(self):
        dr=NS(points=0,first_downs=0,log=[dict(type='sack',yards=-5,pressured=True),dict(type='scramble',yards=8,is_pass=True),dict(type='run',yards=4)])
        me,_=HT.first_half([('home',dr)],'home')
        self.assertEqual((me['passes'],me['runs'],me['pass_yds']),(2,1,3))
        self.assertEqual(me['sacks']+me['pressures'],1)


class RealOvertimeTests(unittest.TestCase):
    @patch('halftime.recommendations', side_effect=lambda *a, **kw: [dict(text='Protect for overtime',side='offence',why='Test recommendation',changes={'protection':'six'})])
    def test_save_at_actual_ot_break_and_resume_same_result(self, recommendation):
        baseline = Session.new('GB', seed=71).save()
        # Select a naturally tied game, without changing its score or forcing OT.
        # Every candidate starts from the same untouched league and a fresh caller.
        for seed in range(1, 65):
            s = Session.load(baseline)
            s.rng.bit_generator.state = np.random.default_rng(seed).bit_generator.state
            r = SeasonRunner(s.L, s.rng); s.runner = r; r.week = 2
            s.stop = ('week', 2); s.played = True
            r.open_live('GB','LAC',2)
            r.live_step('finish'); r.live_step('resume'); r.live_step('finish')
            if r.live['at'] == 'overtime': break
        self.assertEqual(r.live['at'],'overtime')
        self.assertTrue(r.live['halftime_open'])
        self.assertTrue(r.live['ot_recs'])
        s.half_take(0,True)
        before = s.gameday_view()
        loaded = Session.load(s.save())
        self.assertEqual(before, loaded.gameday_view())
        self.assertEqual(json.loads(json.dumps(r.states['GB'].plan.__dict__)),
                         json.loads(json.dumps(loaded.runner.states['GB'].plan.__dict__)))
        observed = []
        import game
        original_ot = game.play_overtime
        def overtime(*args, **kwargs):
            observed.append(copy.deepcopy(r.states['GB'].plan.__dict__))
            return original_ot(*args, **kwargs)
        expected = copy.deepcopy(r.states['GB'].plan.__dict__)
        with patch('game.play_overtime', side_effect=overtime): s._finish_live()
        self.assertEqual(observed[0], expected)
        loaded._finish_live()
        self.assertEqual(r.live['score'], loaded.runner.live['score'])
        self.assertEqual(r.live['book'].p, loaded.runner.live['book'].p)
        context = r.live['res']['coaching_review']
        self.assertEqual(len(context['overtime']),1)
        self.assertEqual(context['halftime'],[])
        messages = [m for m in s.L.inbox if (m.get('payload') or {}).get('game_key','').startswith('game-recap-')]
        self.assertEqual(len(messages),1)
        self.assertIn('OVERTIME ADJUSTMENTS', messages[0]['body'])
        self.assertEqual(s.inbox_message(messages[0]['id'])['recap'],messages[0]['payload']['recap'])


if __name__=='__main__': unittest.main()
