"""Punter capability, coach preference, and safe fourth-down state handling."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import plays as P
import decisions as D
import punt_strategy as S


class PuntStrategyTests(unittest.TestCase):
    def test_estimate_matches_actual_unblocked_punts(self):
        # Fixed seeds check the estimate against real punt outcomes, not a
        # duplicate implementation of its arithmetic.
        for power, accuracy in ((60, 60), (90, 60), (60, 95), (90, 95)):
            punter = dict(kick_power_rating=power, kick_acc_rating=accuracy)
            for spot in (40, 50, 60, 80):
                with self.subTest(power=power, accuracy=accuracy, spot=spot):
                    rng = np.random.default_rng(755)
                    kicks = [G.punt(spot, punter, {}, rng, P.rate) for _ in range(2000)]
                    starts = [100-k['new_yardline'] for k in kicks if not k['blocked']]
                    estimate = S.estimate(spot, punter, {}, P.rate, G.PUNT)
                    self.assertLess(abs(estimate['receiving_start'] - np.mean(starts)), 1.8)
                    if spot <= 50:
                        self.assertGreater(estimate['receiving_start'], 10)
                        self.assertGreater(sum(y <= 5 for y in starts), 0)
                        self.assertLess(estimate['inside10'], .5)

    def test_power_accuracy_weather_and_returner_have_distinct_effects(self):
        def est(spot=80, power=70, accuracy=70, weather=1., ret=70):
            return S.estimate(spot, dict(kick_power_rating=power, kick_acc_rating=accuracy),
                dict(kick_ret_rating=ret, speed_rating=ret, juke_move_rating=ret), P.rate, G.PUNT, weather)
        self.assertLess(est(power=95)['receiving_start'], est(power=55)['receiving_start'])
        self.assertLess(est(40, accuracy=95)['receiving_start'], est(40, accuracy=55)['receiving_start'])
        self.assertGreater(est(weather=.85)['receiving_start'], est()['receiving_start'])
        self.assertGreater(est(ret=95)['receiving_start'], est(ret=55)['receiving_start'])

    def test_punt_value_changes_decision_model_and_has_safe_fallback(self):
        args = (0, 2400, 45, 3)
        pin = D.fourth_down(*args, punt_start=5)
        realistic = D.fourth_down(*args, punt_start=17)
        self.assertGreater(pin['wp_punt'], realistic['wp_punt'])
        self.assertGreater(realistic['go_boost'], pin['go_boost'])
        fallback = D.fourth_down(*args)
        self.assertEqual(fallback['wp_punt'], D.fourth_down(*args, punt_start=16)['wp_punt'])

    def test_confidence_requires_repeated_stops_not_one_lucky_drive(self):
        state = NS()
        def drive(result='Punt', yards=1., n=3):
            return NS(result=result, log=[dict(type='run', yards=yards) for _ in range(n)])
        S.record_defense(state, drive())
        self.assertEqual(S.confidence(state), 0)
        for _ in range(3): S.record_defense(state, drive())
        self.assertGreater(S.confidence(state), .4)
        before = list(state._fourth_defense)
        S.record_defense(state, drive('End of half', n=20))
        S.record_defense(state, drive('Turnover', n=1))
        self.assertEqual(state._fourth_defense, before)
        bad = NS()
        for _ in range(5): S.record_defense(bad, drive('Touchdown', 10, 6))
        self.assertEqual(S.confidence(bad), 0)

    def test_same_strong_defense_supports_opposite_coach_choices(self):
        self.assertGreater(S.flow_adjustment(.9, .8, .7), 0)
        self.assertLess(S.flow_adjustment(.1, .8, .7), 0)
        self.assertEqual(S.flow_adjustment(.5, .8, .7), 0)
        self.assertEqual(S.flow_adjustment(.1, .8, 0), 0)
        # Verify the effect reaches the live decision, not just the helper.
        def threshold(aggression, confidence, secs=2400, spot=50, distance=2):
            lo, hi = 0., 1.
            for _ in range(16):
                mid = (lo+hi)/2
                choice = G.fourth_down_decision(spot, distance, 0, secs, NS(random=lambda: mid),
                    aggression=aggression, defensive_confidence=confidence, punter={}, rate_fn=P.rate)
                if choice == 'go': lo = mid
                else: hi = mid
            return (lo+hi)/2
        self.assertGreater(threshold(.9,.8), threshold(.9,0))
        self.assertLess(threshold(.1,.8), threshold(.1,0))
        for kwargs in (dict(secs=100), dict(spot=85), dict(distance=12)):
            self.assertEqual(threshold(.9,.8,**kwargs), threshold(.9,0,**kwargs))

    def test_must_score_and_halftime_rules_take_priority(self):
        for confidence in (0, 1):
            for aggression in (.1, .9):
                kw = dict(aggression=aggression, defensive_confidence=confidence, punter={}, rate_fn=P.rate)
                self.assertEqual(G.fourth_down_decision(50, 2, -7, 100, NS(random=lambda:1), must_score=True, **kw), 'go')
                self.assertEqual(G.fourth_down_decision(65, 2, 0, 1810, NS(random=lambda:0), half_seconds_left=10, **kw), 'punt')

    def test_live_caller_supplies_punter_and_resets_previous_game_form(self):
        # Real game entry resets the previous game's observations before
        # any kickoff or play can be run.
        state = NS(_fourth_defense=[dict(plays=30,yards=0,stopped=True)], abbr='GB')
        with patch.object(G.W, 'draw', side_effect=RuntimeError('stop after reset')):
            gen = G.game_steps({}, {}, np.random.default_rng(1), None,None,None,P.rate, home_state=state)
            with self.assertRaisesRegex(RuntimeError, 'stop after reset'): next(gen)
        self.assertEqual(state._fourth_defense, [])
        from test_game_clock_decisions import ClockDecisions
        fixture = ClockDecisions(); fixture.setUp()
        fixture.off['p'] = dict(pid='punter',kick_power_rating=91,kick_acc_rating=87)
        original = G.fourth_down_decision
        with patch.object(G, 'fourth_down_decision', wraps=original) as choice:
            fixture.drive(start=65,clock=2400,quarter=2,wall=None,diff=0,down=4)
        self.assertEqual(choice.call_args.kwargs['punter']['pid'], 'punter')


if __name__ == '__main__': unittest.main()
