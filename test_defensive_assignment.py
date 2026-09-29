"""Defensive packages must use the called front and healthy, unique players."""
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import defense_roles as DR
import game
import rosters
import season
from session import Session
import views_club as VC


def depth():
    counts = dict(QB=2, HB=3, WR=6, TE=4, LT=2, LG=2, C=2, RG=2, RT=2,
                  LEDG=2, DT=5, REDG=2, MIKE=2, WILL=2, SAM=2, CB=6, FS=2, SS=2)
    return {pos: [dict(pid=f'{pos}{i}', pos=pos, stamina_rating=90)
                  for i in range(n)] for pos, n in counts.items()}


class NoRotation:
    def random(self): return .999
    def shuffle(self, values): pass


class State:
    def __init__(self, out=()):
        self.out = set(out)
        self.cond = SimpleNamespace(needs_rest=lambda *args: False)
        self.snaps = Counter()
    available = game.TeamState.available
    def snap(self, p, pos, on_field):
        if on_field: self.snaps[p['pid']] += 1
    def state(self, p, pos): return dict(p)


class DefensiveAssignmentTests(unittest.TestCase):
    def test_injuries_replace_starters_in_every_package_and_front(self):
        for front in ('4-3', '3-4'):
            roster = rosters._assemble(depth(), front=front)
            for package in ('base', 'nickel', 'dime', 'heavy'):
                for hurt in (('CB0',), ('DT0',), ('FS0',), ('LEDG0',),
                             ('SAM0','SAM1'), ('CB0','DT0','FS0','LEDG0')):
                    for seed in range(10):
                        with self.subTest(front=front,package=package,hurt=hurt,seed=seed):
                            state=State(hurt)
                            unit, positions=game.field_units(roster,state,np.random.default_rng(seed),False,package,front)
                            self.assertEqual(len(positions),11)
                            self.assertFalse(set(hurt)&positions.keys())
                            self.assertEqual(sum(len(unit[k]) for k in ('dl','lb','db')),11)
                            self.assertEqual(state.snaps,Counter({pid:1 for pid in positions}))

    def test_multiple_front_reassigns_edges_for_actual_four_three_call(self):
        roster=rosters._assemble(depth(),front='multiple',box=.8)
        for package in ('base','nickel','dime','heavy'):
            with self.subTest(package=package):
                unit,positions=game.field_units(roster,State(),NoRotation(),False,package,'4-3')
                expected=Counter(LEDG=1,REDG=1,DT=3 if package=='heavy' else 2)
                self.assertEqual(Counter(p['pos'] for p in unit['dl']),expected)
                self.assertEqual(len(positions),11)
        unit,positions=game.field_units(roster,State(),NoRotation(),False,'base','3-4')
        self.assertEqual(Counter(p['pos'] for p in unit['dl']),Counter(DT=3))
        self.assertEqual({p['pid'] for p in unit['lb']},{'LEDG0','REDG0','MIKE0','WILL0'})

    def test_healthy_four_three_keeps_nickel_and_linebacker_policies(self):
        chart=depth()
        chart['SAM'][0].update(zone_cover_rating=99,man_cover_rating=99,speed_rating=99,
                               play_rec_rating=99,pursuit_rating=99,accel_rating=99)
        roster=rosters._assemble(chart,front='4-3')
        selected=game.package_units(roster,State(),NoRotation(),False,'nickel','4-3')
        self.assertEqual({p['pid'] for p in selected['lb']},{'MIKE0','SAM0'})
        self.assertEqual(sum(p['pos']=='CB' for p in selected['db']),3)
        # A zero random draw enters the existing three-safety big nickel.
        class Rotate(NoRotation):
            def random(self): return 0
        selected=game.package_units(roster,State(),Rotate(),False,'nickel','4-3')
        self.assertEqual(sum(p['pos']=='CB' for p in selected['db']),2)
        self.assertEqual(sum(p['pos'] in ('FS','SS') for p in selected['db']),3)


class DefensiveChartAvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline=Session.new('GB',seed=23).save()

    def test_hurt_player_stays_visible_but_backup_is_highlighted(self):
        for front in ('4-3','3-4'):
            s=Session.load(self.baseline); t=s.L.teams['GB']; t.gm.def_front=front
            s.runner=season.SeasonRunner(s.L,s.rng)
            first=VC.depth(s,s.L,'GB')
            pid=next(p['pid'] for col in first['sides']['defense'] if col['pos']=='CB'
                     for p in col['slots'] if p['start'])
            hurt=s.L.player(pid);hurt.out_until=5
            view=VC.depth(s,s.L,'GB')
            entries=[p for col in view['sides']['defense'] for p in col['slots']]
            self.assertTrue(any(p['pid']==pid and p['flag']=='out' for p in entries))
            starters={p['pid'] for p in entries if p['start']}
            self.assertNotIn(pid,starters)
            self.assertEqual(len(starters),11)
            roster=s.runner._units('GB')
            units,_=game.field_units(roster,State(),NoRotation(),False,'base',front)
            self.assertEqual({p['pid'] for p in units['db']},
                {p['pid'] for col in view['sides']['defense'] if col['group']=='Secondary'
                 for p in col['slots'] if p['start']})

    def test_approved_playing_hurt_player_remains_available(self):
        s=Session.load(self.baseline);t=s.L.teams['GB']
        s.runner=season.SeasonRunner(s.L,s.rng)
        pid=next(p['pid'] for col in VC.depth(s,s.L,'GB')['sides']['defense'] if col['pos']=='CB'
                 for p in col['slots'] if p['start'])
        s.L.player(pid).out_until=2
        s.runner.desks['GB'].playing_hurt[pid]={'kind':'ankle','weeks':1}
        with patch('injury_status.hurt_words',return_value='Cleared to play'):
            view=VC.depth(s,s.L,'GB')
        self.assertIn(pid,{p['pid'] for col in view['sides']['defense'] for p in col['slots'] if p['start']})
        s.runner.states['GB'].out.add(pid)
        view=VC.depth(s,s.L,'GB')
        self.assertNotIn(pid,{p['pid'] for col in view['sides']['defense'] for p in col['slots'] if p['start']})

    def test_full_game_keeps_eleven_when_eligible_healthy_depth_exists(self):
        s=Session.load(self.baseline)
        s.runner=season.SeasonRunner(s.L,s.rng)
        original=game.field_units
        checked=[]
        def inspect(roster,state,rng,is_offense,package=None,front_family=None):
            unit,positions=original(roster,state,rng,is_offense,package,front_family)
            if not is_offense and package:
                healthy=DR.available_depth(roster['depth'],state.out)
                assignments=DR.assign(healthy,front_family or roster['front_family'],package)
                if all(row['player'] is not None for row in assignments):
                    self.assertEqual(len(positions),11)
                    self.assertFalse(state.out & positions.keys())
                    checked.append(package)
            return unit,positions
        with patch.object(game,'field_units',side_effect=inspect):
            result=s.runner.play('GB','MIN',1)
        self.assertIn('home',result)
        self.assertGreater(len(checked),80)


if __name__=='__main__': unittest.main()
