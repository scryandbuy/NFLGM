"""Fourth-down choices must compare the outcomes that the engine will play."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import game
import decisions
import plays
import numpy as np


class FourthDownValueTests(unittest.TestCase):
    def setUp(self):
        self.kicker = dict(kick_power_rating=95,kick_acc_rating=80,awareness_rating=80)
        self.decline_go = SimpleNamespace(random=lambda: .999999)

    def test_model_receives_actual_kicker_and_weather_probability(self):
        with patch.object(game.ENV,'kick_mult',.8), \
             patch.object(decisions,'fourth_down',wraps=decisions.fourth_down) as decision:
            game.fourth_down_decision(38,8,0,1800,self.decline_go,
                                     kicker=self.kicker,rate_fn=plays.rate)
        self.assertAlmostEqual(decision.call_args.kwargs['fg_prob'],
                               game.fg_probability(55,self.kicker,plays.rate)*.8)

    def test_model_miss_spot_matches_engine_turnover_spot(self):
        with patch.object(decisions,'_flip',return_value=.5) as flip:
            decisions.fourth_down(0,1800,43,8,fg_prob=.6)
        # _flip converts the old offense's coordinates to the new offense.
        self.assertEqual(flip.call_args_list[2].args[2],50)

    def test_reachable_kick_does_not_override_a_better_punt(self):
        for fg_value, expected in ((.4,'punt'),(.6,'field_goal')):
            with patch.object(decisions,'fourth_down',return_value={
                    'go_boost':-.2,'wp_fg':fg_value,'wp_punt':.5}):
                actual=game.fourth_down_decision(38,8,0,1800,self.decline_go,
                                               kicker=self.kicker,rate_fn=plays.rate)
            self.assertEqual(actual,expected)

    def test_last_play_tying_or_winning_kick_is_not_forced_into_conversion(self):
        for score in (-3,-2,-1,0):
            for draw in (0.0,.999):
                actual=game.fourth_down_decision(43,8,score,1,
                    SimpleNamespace(random=lambda:draw),kicker=self.kicker,rate_fn=plays.rate)
                self.assertEqual(actual,'field_goal')

    def test_late_reachable_kick_can_be_taken_without_desperation_override(self):
        self.assertEqual(game.fourth_down_decision(43,8,-3,60,self.decline_go,
            kicker=self.kicker,rate_fn=plays.rate),'field_goal')

    def test_late_tying_kick_outweighs_generic_comeback_go_floor(self):
        # GB at CHI: down three, fourth-and-seven at the 18 with one minute.
        # A good kicker should get the tying attempt almost every time, while
        # preserving a small chance for a coach to prefer the conversion.
        calls = [game.fourth_down_decision(18,7,-3,60,
                 SimpleNamespace(random=lambda draw=draw: draw),
                 kicker=self.kicker,rate_fn=plays.rate,timeout_edge=1)
                 for draw in (i / 1000 for i in range(1000))]
        self.assertGreater(calls.count('field_goal'), 940)
        self.assertGreater(calls.count('go'), 0)

    def test_tying_kick_can_be_rejected_when_kicker_is_unreliable(self):
        with patch.object(game,'fg_probability',return_value=.35):
            self.assertEqual(game.fourth_down_decision(18,7,-3,60,
                SimpleNamespace(random=lambda:.2),kicker=self.kicker,
                rate_fn=plays.rate,timeout_edge=1),'go')

    def test_short_yardage_and_touchdown_need_retain_aggressive_choices(self):
        self.assertEqual(game.fourth_down_decision(18,1,-3,60,
            SimpleNamespace(random=lambda:.15),aggression=.9,
            kicker=self.kicker,rate_fn=plays.rate,timeout_edge=1),'go')
        self.assertEqual(game.fourth_down_decision(18,7,-4,60,
            SimpleNamespace(random=lambda:.5),kicker=self.kicker,
            rate_fn=plays.rate,timeout_edge=1),'go')

    def test_meaningless_or_unreachable_late_kick_does_not_replace_needed_score(self):
        for yardline,score in ((43,-7),(75,-3)):
            self.assertEqual(game.fourth_down_decision(yardline,8,score,1,self.decline_go,
                kicker=self.kicker,rate_fn=plays.rate),'go')

    def test_one_score_touchdown_need_does_not_become_onside_dependency(self):
        # LA at GB: 17-9, fourth-and-20 at GB31, 28 seconds, no timeouts.
        # Even a great kicker cannot remove the touchdown still required.
        for deficit in (-7, -8):
            for stops in (0, 3):
                for aggression in (.1, .9):
                    for draw in (0., .999999):
                        self.assertEqual(game.fourth_down_decision(31,20,deficit,28,
                            SimpleNamespace(random=lambda:draw), aggression=aggression,
                            kicker=self.kicker,rate_fn=plays.rate,offense_timeouts=stops), 'go')

    def test_timeouts_can_preserve_a_kick_and_defensive_stop_route(self):
        # Same timeout edge, different absolute counts. Three clock stops
        # leave a second possession possible; zero cannot buy that time.
        for stops, expected in ((0, 'go'), (3, 'field_goal')):
            self.assertEqual(game.fourth_down_decision(31,20,-8,120,self.decline_go,
                kicker=self.kicker,rate_fn=plays.rate,timeout_edge=0,
                offense_timeouts=stops), expected)
        self.assertEqual(game.fourth_down_decision(31,20,-8,270,self.decline_go,
            kicker=self.kicker,rate_fn=plays.rate,offense_timeouts=0), 'field_goal')

    def test_required_first_score_and_tying_kicks_remain_available(self):
        # Down ten/eleven, either route already requires two possessions.
        for deficit in (-3, -10, -11):
            self.assertEqual(game.fourth_down_decision(31,20,deficit,28,self.decline_go,
                kicker=self.kicker,rate_fn=plays.rate,offense_timeouts=0), 'field_goal')

    def test_clock_feasible_bridge_kick_retains_coaching_discretion(self):
        # No mandatory kick just because another possession is feasible.
        self.assertEqual(game.fourth_down_decision(31,2,-8,270,
            SimpleNamespace(random=lambda:0),aggression=.9,
            kicker=self.kicker,rate_fn=plays.rate,offense_timeouts=3), 'go')

    def test_live_drive_supplies_own_timeouts_and_runs_the_needed_play(self):
        import events
        import rosters
        import schemes
        teams = rosters.load_league()
        for own, other, seconds in ((0, 2, 28), (3, 3, 120)):
            timeouts = game.Timeouts()
            timeouts.left.update(away=own, home=other)
            with patch.object(events, 'penalty_check', return_value=None), \
                 patch.object(events, 'contextual_penalty', return_value=None), \
                 patch.object(game, 'end_of_half_plan', return_value=None), \
                 patch.object(game, 'fourth_down_decision', wraps=game.fourth_down_decision) as choice:
                dr = game.run_drive(teams['LA'],teams['GB'],31,seconds,4,-8,
                    np.random.default_rng(14),
                    lambda *a:dict(type='incomplete',yards=0),
                    lambda d,di,sd,ytg,r,**kw:schemes.call_offense(d,di,sd,ytg,r,**kw),
                    lambda oc,d,di,r,ytg=50,**kw:schemes.call_defense(oc,d,di,r,yards_to_endzone=ytg,**kw),
                    plays.rate,timeouts=timeouts,pos='away',start_state=(4,20))
            self.assertEqual(choice.call_args.kwargs['offense_timeouts'], own)
            self.assertEqual(choice.call_args.kwargs['timeout_edge'], own-other)
            if seconds == 28:
                self.assertEqual(dr.result, 'Turnover on downs')
                self.assertFalse(any(p.get('type')=='field_goal' for p in dr.log))


if __name__=='__main__':unittest.main()
