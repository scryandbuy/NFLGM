"""Targeted clock, offending-unit discipline, and goal-line valuation regressions."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import decisions as D
import events as E
import game as G


class PenaltyProbe:
    def __init__(self, draw=0): self.draw = draw; self.weights = {}
    def random(self): return self.draw
    def choice(self, options, p):
        self.weights = {E._names[i]: weight for i, weight in zip(options, p)}
        return options[0]


def rates(**kwargs):
    probe = PenaltyProbe()
    E.penalty_check(probe, **kwargs)
    lo, hi = 0., 1.
    for _ in range(32):
        mid = (lo + hi) / 2
        if E.penalty_check(PenaltyProbe(mid), **kwargs) is None: hi = mid
        else: lo = mid
    return {name: (lo + hi) / 2 * weight for name, weight in probe.weights.items()}


class PenaltyOwnership(unittest.TestCase):
    def test_offensive_rates_do_not_depend_on_defensive_discipline(self):
        a = rates(offense_discipline=.7, defense_discipline=.5)
        b = rates(offense_discipline=.7, defense_discipline=.9)
        for name in ('False Start', 'Delay of Game', 'Offensive Holding'):
            self.assertAlmostEqual(a[name], b[name], places=9)
        self.assertGreater(a['Defensive Holding'], b['Defensive Holding'])

    def test_defensive_rates_do_not_depend_on_offensive_discipline(self):
        a = rates(offense_discipline=.5, defense_discipline=.7)
        b = rates(offense_discipline=.9, defense_discipline=.7)
        for name in ('Defensive Holding', 'Defensive Offside', 'Defensive Pass Interference'):
            self.assertAlmostEqual(a[name], b[name], places=9)
        self.assertGreater(a['Delay of Game'], b['Delay of Game'])

    def test_staff_and_crowd_have_separate_effects(self):
        base = rates()
        staff = rates(offense_multiplier=.5)
        crowd = rates(noise=1.3)
        self.assertAlmostEqual(staff['Offensive Holding'], base['Offensive Holding'] * .5, places=9)
        self.assertAlmostEqual(staff['Defensive Holding'], base['Defensive Holding'], places=9)
        self.assertAlmostEqual(crowd['Delay of Game'], base['Delay of Game'] * 1.3, places=9)
        self.assertAlmostEqual(crowd['Offensive Holding'], base['Offensive Holding'], places=9)
        self.assertEqual(rates(hurry=True)['Delay of Game'], 0)

    def test_neutral_rates_keep_existing_calibration(self):
        observed = rates()
        for name in ('Delay of Game', 'False Start', 'Unnecessary Roughness'):
            expected = E._rates[E._names.index(name)] / E.SCRIMMAGE_PLAYS_PER_GAME
            self.assertAlmostEqual(observed[name], expected, places=9)

    def test_either_side_flags_follow_side_specific_weight(self):
        class Both(PenaltyProbe):
            def choice(self, options, p): return E._names.index('Unnecessary Roughness')
        self.assertFalse(E.penalty_check(Both(), offense_multiplier=0)['on_offense'])
        self.assertTrue(E.penalty_check(Both(), defense_multiplier=0)['on_offense'])


class GoalLineValuation(unittest.TestCase):
    def test_conversion_is_touchdown_and_opponent_possession(self):
        with patch.object(D, 'two_point', return_value={'call': 'kick'}):
            result = D.fourth_down(7, 108, 2, 2, conv_prob=1., fg_prob=1., is_home=0, timeout_edge=2)
        def after(lead):
            return 1 - D.win_prob(-lead, 102, 65, is_home=1, timeout_edge=-2)
        expected = D.XP_RATE * after(14) + (1 - D.XP_RATE) * after(13)
        self.assertAlmostEqual(result['wp_go'], expected, places=4)
        self.assertAlmostEqual(result['wp_fg'], after(10), places=4)

    def test_non_goal_conversion_still_retains_possession(self):
        result = D.fourth_down(7, 108, 3, 2, conv_prob=1., is_home=0, timeout_edge=2)
        expected = D.win_prob(7, 102, 1, 1, 1, is_home=0, timeout_edge=2)
        self.assertAlmostEqual(result['wp_go'], expected, places=4)

    def test_expiring_clock_still_prices_required_conversion_attempt(self):
        result = D.fourth_down(-8, 6, 2, 2, conv_prob=1.)
        self.assertAlmostEqual(result['wp_go'], .5 * D.TWO_RATE, places=4)
        result = D.fourth_down(-6, 6, 2, 2, conv_prob=1.)
        self.assertAlmostEqual(result['wp_go'], D.XP_RATE + (1 - D.XP_RATE) * .5, places=4)

    def test_fractional_goal_line_and_kickoff_override(self):
        with patch.object(D, 'two_point', return_value={'call': 'kick'}):
            a = D.fourth_down(0, 300, 1.4, 1.4, conv_prob=1.)
            b = D.fourth_down(0, 300, 2, 2, conv_prob=1.)
        self.assertEqual(a['wp_go'], b['wp_go'])
        result = D.fourth_down(3, 300, 20, 5, fg_prob=1., kickoff_yardline=70)
        self.assertAlmostEqual(result['wp_fg'], 1-D.win_prob(-6,294,70,is_home=0),places=4)


class HalfIntent(unittest.TestCase):
    def test_hurry_can_use_timeout_and_protect_does_not_reverse_on_fourth(self):
        for plan, expected in [(None, False), ({'choice':'shot','hurry':False}, False),
                               ({'choice':'play','hurry':True}, True)]:
            dr = G.Drive({}, {}, 58, 1845, 2, 3, None); dr.down=3; dr.togo=16
            tos = G.Timeouts(); tos.left={'home':1,'away':0}
            used, _ = G._timeout_call(dr,'complete',{'yards':12},tos,'home',1800,45,plan=plan)
            self.assertEqual(used, expected)
            if not expected:
                for draw in (0., .5, .999):
                    self.assertEqual(G.fourth_down_decision(46,4,3,1811,NS(random=lambda:draw),
                        half_seconds_left=11,half_intent=dr._half_stall_intent), 'punt')
            else:
                self.assertEqual(dr._half_stall_intent, 'attack')

    def test_protect_intent_does_not_restrict_trailing_or_second_half_club(self):
        self.assertEqual(G.fourth_down_decision(46,4,-7,11,NS(random=lambda:0),
            half_intent='protect'), 'go')
        self.assertEqual(G.fourth_down_decision(46,4,-7,1811,NS(random=lambda:0),
            half_seconds_left=11,half_intent='protect'), 'go')

    def test_real_drive_carries_intent_to_fourth_down(self):
        for hurry, own in ((False, 1), (True, 1), (True, 0)):
            off=dict(qb={'pid':'qb'}, rb={'pid':'rb'}, ol=[],wr=[{'pid':'wr'}],te=[],p={})
            deff=dict(dl=[],lb=[],db=[])
            ctor=G.Drive; tos=G.Timeouts(); tos.left={'home':own,'away':0}
            def construct(*args):
                dr=ctor(*args);dr.down=3;dr.togo=16;return dr
            calls=[]
            def fourth(*args, **kw):
                calls.append(kw); return 'punt'
            with patch.object(G,'Drive',side_effect=construct), \
                 patch.object(G,'end_of_half_plan',return_value={'choice':'play','hurry':hurry}), \
                 patch.object(G,'fourth_down_decision',side_effect=fourth), \
                 patch.object(G,'field_units',side_effect=lambda r,*a,**k:(r,{})), \
                 patch.object(E,'penalty_check',return_value=None), \
                 patch.object(E,'special_teams_penalty_check',return_value=None), \
                 patch.object(E,'fumble_check',return_value=None), \
                 patch('playcall.audible',side_effect=lambda oc,*a,**k:(oc,None)):
                G.LAST_KICKOFF.clear()
                dr=G.run_drive(off,deff,58,1845,2,3,np.random.default_rng(3),
                    lambda *a:dict(type='complete',yards=12,target='wr'),
                    lambda *a,**k:dict(is_pass=True,personnel='11',depth='short'),
                    lambda *a,**k:dict(personnel='nickel',front_family='4-3'),
                    lambda *a:.7,timeouts=tos,half_end=1800)
            self.assertEqual(calls[0]['half_intent'],'attack' if hurry else 'protect')
            self.assertEqual(tos.left['home'],0 if hurry else 1)
            self.assertGreater(calls[0]['half_seconds_left'],30 if hurry and own else 20 if hurry else 0)


if __name__ == '__main__': unittest.main()
