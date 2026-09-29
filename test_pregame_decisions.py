"""Regressions for the six pregame wiring findings."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game
import gameplan as GP
import gameplan_week as GW
import season
import rosters
import plays
import practice_squad as PS
import position_change as PC
import morale as MO
from session import Session
from test_cap_accounting import fixture, player
from test_defensive_assignment import depth


class PregameTacticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = Session.new('GB', seed=23).save()

    def test_conversion_uses_plan_at_both_callers_and_resolver(self):
        s = Session.load(self.saved)
        r = season.SeasonRunner(s.L, s.rng)
        off, deff = r.states['GB'], r.states['MIN']
        off.plan.pass_bias = .08
        off.plan.protection = 'six'; off.plan.protection_locked = True
        off.plan.personnel_mix = {'12': 1.0}; off.plan.off_personnel = '12'
        off.plan.run_scheme_mix = {'gap': 1.0}
        deff.plan.front_pref = ['3-4 two']
        deff.plan.man_rate = .8; deff.plan.box_bias = .25
        target = off.roster['depth']['WR'][0]['pid']
        deff.plan.bracket = target; deff.plan.travel = True
        deff.plan.travel_target = target; deff.plan.zone_aggression = .7
        co, cd = season._deps()
        seen = {}
        def call_off(*args, **kw):
            seen['off'] = kw
            oc = co(*args, **kw)
            oc['is_pass'] = True
            return oc
        def call_def(*args, **kw):
            seen['def'] = kw
            dc = cd(*args, **kw); seen['box'] = dc['box']
            return dc
        def resolve(o, d, oc, dc, yards, rng):
            self.assertIs(oc['plan'], off.plan)
            self.assertEqual(dc['bracket'], target)
            self.assertEqual(dc['travel_target'], target)
            self.assertTrue(dc['travel'])
            self.assertEqual(dc['zone_aggression'], .7)
            self.assertEqual(dc['box'], min(10, seen['box'] + 1))
            # The same engine package selection still fields legal units.
            op = [o['qb']] + o['ol'] + o['wr'] + ([o['rb']] if o['rb'] else [])
            dp = d['dl'] + d['lb'] + d['db']
            self.assertEqual(len({p['pid'] for p in op}), 11)
            self.assertEqual(len({p['pid'] for p in dp}), 11)
            return {'type':'complete', 'yards':2}
        result = game.attempt_two_point(off.roster, deff.roster, s.rng, resolve,
                                       call_off, call_def, plays.rate, off, deff)
        self.assertTrue(result['made'])
        self.assertEqual(seen['off']['lean']['pass_bias'], .08)
        self.assertEqual(seen['off']['lean']['protection'], 'six')
        self.assertEqual(seen['off']['lean']['personnel_mix'], {'12':1.0})
        self.assertEqual(seen['off']['lean']['run_scheme_mix'], {'gap':1.0})
        self.assertEqual(seen['def']['lean']['front_pref'], ['3-4 two'])

    def test_identity_box_refresh_and_weekly_override_survive_reload(self):
        s = Session.load(self.saved); s.stop = ('week',1)
        s.runner = season.SeasonRunner(s.L, s.rng)
        self.assertTrue(s.frontoffice_act('set_identity', changes={'box':.9})['ok'])
        st = s.runner.states['GB']
        self.assertAlmostEqual(st.base_plan.box_bias, .2)
        self.assertTrue(s.plan_act('set_lean', key='box_bias', value=.3)['ok'])
        st.plan = st.base_plan.copy(); GW.user_plan(s.L, st, 1)
        self.assertAlmostEqual(st.plan.box_bias, .3)
        loaded = Session.load(s.save())
        self.assertAlmostEqual(loaded.runner.states['GB'].base_plan.box_bias, .2)
        self.assertAlmostEqual(loaded.runner.states['GB'].plan.box_bias, .3)
        self.assertTrue(loaded.frontoffice_act('set_identity', changes={'box':.1})['ok'])
        self.assertAlmostEqual(loaded.runner.states['GB'].base_plan.box_bias, -.2)
        self.assertAlmostEqual(loaded.runner.states['GB'].plan.box_bias, -.1)

    def test_skip_survives_reload_excludes_accept_all_and_can_restore(self):
        s = Session.load(self.saved)
        self.assertTrue(s.plan_act('skip', i=0)['ok'])
        view = s.plan_view('this_week')
        self.assertTrue(view['suggestions'][0]['skipped'])
        loaded = Session.load(s.save())
        self.assertTrue(loaded.plan_view('this_week')['suggestions'][0]['skipped'])
        loaded.plan_take_all()
        self.assertFalse(loaded.plan_view('this_week')['suggestions'][0]['taken'])
        loaded.plan_act('skip', i=0, skip=False)
        loaded.plan_take_all()
        self.assertTrue(loaded.plan_view('this_week')['suggestions'][0]['taken'])

    def test_full_game_supplies_a_snapper_to_each_kick_and_punt(self):
        s = Session.load(self.saved); r = season.SeasonRunner(s.L,s.rng)
        seen = set()
        def inspect(name, fn):
            def wrapped(*args, **kw):
                snapper = kw.get('snapper')
                self.assertIsNotNone(snapper)
                self.assertIn(snapper['pos'], ('LS','C'))
                seen.add(name)
                return fn(*args, **kw)
            return wrapped
        with patch.object(game, 'attempt_field_goal', side_effect=inspect('fg',game.attempt_field_goal)), \
             patch.object(game, 'attempt_extra_point', side_effect=inspect('xp',game.attempt_extra_point)), \
             patch.object(game, 'punt', side_effect=inspect('punt',game.punt)):
            result = r.play('GB','MIN',1)
        self.assertIn('home',result)
        self.assertEqual(seen, {'fg','xp','punt'})


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.t = self.L.teams['GB']
        self.p = player(self.L); self.p.pos = 'WR'
        self.t.roster.remove(self.p); PS.squad(self.t).append(self.p)
        self.s = Session.__new__(Session)
        self.s.L = self.L; self.s.user_team = 'GB'; self.s.stop = ('week', 6)

    def test_injured_player_cannot_be_elevated_or_dressed_from_stale_elevation(self):
        self.p.out_until = 10
        self.assertFalse(self.s.club_act('elevate', pids=[self.p.pid])['ok'])
        self.assertEqual(self.p.xp_spent.get('_elevations',0), 0)
        self.t._elevated = [self.p]
        r = season.SeasonRunner.__new__(season.SeasonRunner)
        r.L = self.L; r.week = 6; r.desks = {}
        with patch.object(r, '_apply_field_fit'), patch.object(rosters, 'build_roster_rows', return_value={}) as build:
            r._units('GB')
            self.assertEqual(build.call_args.args[0], [])

    def test_elevation_uses_position_and_morale_effective_ratings_once(self):
        self.t._elevated = [self.p, self.p]
        r = season.SeasonRunner.__new__(season.SeasonRunner)
        r.L = self.L; r.week = 6; r.desks = {}
        with patch.object(PC, 'effective_ratings', return_value={'speed_rating':62}) as position, \
             patch.object(MO, 'effective_ratings_from', return_value={'speed_rating':57}) as morale, \
             patch.object(r, '_apply_field_fit'), \
             patch.object(rosters, 'build_roster_rows', return_value={}) as build:
            r._units('GB')
        position.assert_called_once_with(self.p)
        morale.assert_called_once_with({'speed_rating':62}, self.p)
        self.assertEqual(build.call_args.args[0], [{'speed_rating':57,'pid':self.p.pid,'pos':'WR'}])

    def test_playoff_elevation_remains_temporary_after_three_regular_elevations(self):
        self.p.xp_spent['_elevations'] = 3
        self.s.stop = ('playoffs',2)
        with patch.object(PS, 'call_up') as call_up, patch.object(PS, 'elevate', wraps=PS.elevate) as elevate:
            result = self.s.club_act('elevate', pids=[self.p.pid])
        self.assertTrue(result['ok']); call_up.assert_not_called()
        self.assertEqual(elevate.call_args.args[3], 21)
        self.assertTrue(elevate.call_args.kwargs['playoffs'])
        self.assertIn(self.p, PS.squad(self.t)); self.assertNotIn(self.p, self.t.roster)
        self.assertEqual(self.p.xp_spent['_elevations'], 3)

    def test_regular_fourth_elevation_still_requires_call_up(self):
        self.p.xp_spent['_elevations'] = 3
        with patch.object(PS, 'call_up', return_value=False) as call_up:
            self.assertFalse(self.s.club_act('elevate', pids=[self.p.pid])['ok'])
        call_up.assert_called_once_with(self.L,'GB',self.p.pid)

    def test_automatic_playoff_elevations_use_same_exemption(self):
        self.p.xp_spent['_elevations'] = 3
        for phase, week, flags in [('regular',18,{'playoffs':True}), ('playoffs',19,{})]:
            self.L.set_phase(phase); PS.clear_elevations(self.t)
            with patch.object(PS, 'keep_groups_whole', return_value=[]), \
                 patch.object(PS, 'roster_review', return_value=[]), \
                 patch.object(PS, 'call_up') as call_up:
                PS.weekly(self.L, np.random.default_rng(5), week, user_team='GB', **flags)
            call_up.assert_not_called()
            self.assertIn(self.p, self.t._elevated)
            self.assertEqual(self.p.xp_spent['_elevations'],3)

    def test_duplicates_and_game_limit_cannot_add_extra_players(self):
        PS.elevate(self.L,'GB',[self.p.pid,self.p.pid],6)
        self.assertEqual(len(self.t._elevated),1)
        self.assertEqual(self.p.xp_spent['_elevations'],1)
        q = player(self.L,'q'); self.t.roster.remove(q); PS.squad(self.t).append(q)
        PS.elevate(self.L,'GB',[q.pid],6,playoffs=True)
        z = player(self.L,'z'); self.t.roster.remove(z); PS.squad(self.t).append(z)
        self.assertEqual(PS.elevate(self.L,'GB',[z.pid],6,playoffs=True),[])


class LongSnapperTests(unittest.TestCase):
    def test_chart_order_and_availability_choose_actual_snapper(self):
        rows = [p for group in depth().values() for p in group]
        rows += [dict(pid='low',pos='LS',awareness_rating=40),dict(pid='high',pos='LS',awareness_rating=95)]
        roster = rosters.build_roster_rows(rows, pins={'LS':['low','high']})
        self.assertEqual(game.snapper_for(roster)['pid'],'low')
        self.assertEqual(game.snapper_for(roster,NS(out={'low'}))['pid'],'high')
        roster = rosters.build_roster_rows(rows, pins={'LS':['high','low']})
        self.assertEqual(game.snapper_for(roster)['pid'],'high')

    def test_snapper_changes_field_goal_and_extra_point_outcome(self):
        k = dict(kick_power_rating=80,kick_acc_rating=80,awareness_rating=80)
        weak = dict(awareness_rating=40); strong = dict(awareness_rating=95)
        for kind in ('fg','xp'):
            distance = 47 if kind=='fg' else 33
            threshold = game.fg_probability(distance,k,plays.rate)
            rng = NS(random=lambda:threshold)
            if kind=='fg':
                with patch.object(game.ENV, 'kick_mult',1.0):
                    a=game.attempt_field_goal(30,k,rng,plays.rate,snapper=weak)
                    b=game.attempt_field_goal(30,k,rng,plays.rate,snapper=strong)
            else:
                a=game.attempt_extra_point(k,rng,plays.rate,snapper=weak)
                b=game.attempt_extra_point(k,rng,plays.rate,snapper=strong)
            self.assertFalse(a['made']); self.assertTrue(b['made'])

    def test_snapper_changes_punt_block_risk_and_neutral_preserves_results(self):
        p = dict(kick_power_rating=80,kick_acc_rating=80,awareness_rating=80)
        class Rng:
            def __init__(self): self.rng=np.random.default_rng(8); self.first=True
            def random(self):
                if self.first: self.first=False; return game.PUNT['blocked']
                return self.rng.random()
            def __getattr__(self,key): return getattr(self.rng,key)
        weak=game.punt(75,p,p,Rng(),plays.rate,snapper={'awareness_rating':40})
        strong=game.punt(75,p,p,Rng(),plays.rate,snapper={'awareness_rating':95})
        self.assertTrue(weak['blocked']); self.assertFalse(strong.get('blocked',False))
        for seed in range(30):
            a=game.punt(75,p,p,np.random.default_rng(seed),plays.rate)
            b=game.punt(75,p,p,np.random.default_rng(seed),plays.rate,snapper={'awareness_rating':70})
            self.assertEqual(a,b)


if __name__ == '__main__': unittest.main()
