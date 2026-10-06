"""Regression checks for personnel, unique players, and the live call path."""
import unittest
from collections import Counter
from types import SimpleNamespace
import numpy as np
import offense_roles as OR
import game
import schemes
import formations
from unittest.mock import patch


def roster():
    depth = {}
    for pos, n in dict(QB=2, HB=3, FB=2, WR=6, TE=4,
                       LT=2, LG=2, C=2, RG=2, RT=2).items():
        depth[pos] = [dict(pid=f'{pos}{i}', pos=pos, stamina_rating=90) for i in range(n)]
    return dict(depth=depth, qb=depth['QB'][0], rb=depth['HB'][0],
                backs=depth['HB'], fullbacks=depth['FB'],
                ol=[depth[p][0] for p in OR.OL],
                wr=depth['WR']+depth['TE']+depth['HB'][:1],
                extra_blockers=depth['TE'][1:3])


class State:
    def __init__(self, out=()):
        self.out = set(out)
        self.cond = SimpleNamespace(needs_rest=lambda *a: False)
        self.recorded = []

    def snap(self, p, pos, on_field):
        self.recorded.append((p['pid'], on_field))

    def state(self, p, pos):
        return dict(p)


def on_field(unit):
    return [p for p in [unit['qb'], unit.get('rb')] + unit['ol'] + unit['wr'] if p]


class OffensivePersonnelTests(unittest.TestCase):
    def test_every_package_fields_exact_composition_and_one_snap_each(self):
        for package, spec in OR.PACKAGES.items():
            for seed in range(15):
                with self.subTest(package=package, seed=seed):
                    state = State()
                    unit, positions = game.field_units(roster(), state, np.random.default_rng(seed), True, package)
                    men = on_field(unit)
                    self.assertEqual(len(men), 11)
                    self.assertEqual(len({p['pid'] for p in men}), 11)
                    self.assertEqual(len(positions), 11)
                    expected = Counter(dict(spec, QB=1, **{pos:1 for pos in OR.OL}))
                    self.assertEqual(Counter(p['pos'] for p in men), +expected)
                    self.assertEqual(Counter(pid for pid, active in state.recorded if active),
                                     Counter({p['pid']: 1 for p in men}))

    def test_two_backs_without_fb_uses_different_hbs(self):
        team = roster(); team['depth']['FB'] = []; team['fullbacks'] = []
        unit = OR.field(team, '21')
        self.assertEqual(unit['rb']['pid'], 'HB0')
        self.assertIn('HB1', [p['pid'] for p in unit['wr']])
        self.assertEqual(len({p['pid'] for p in on_field(unit)}), 11)

    def test_blocking_te_can_fill_fullback_role(self):
        team = roster(); team['depth']['FB'] = []; team['fullbacks'] = []
        team['depth']['HB'][1].update(run_block_rating=40, lead_block_rating=40,
                                     impact_block_rating=40, carry_rating=75)
        team['depth']['TE'][0].update(run_block_rating=55, lead_block_rating=50,
                                     impact_block_rating=50, carry_rating=50)
        team['depth']['TE'][1].update(run_block_rating=90, lead_block_rating=90,
                                     impact_block_rating=90, carry_rating=60)
        rows = OR.field(team, '21')['offensive_assignments']
        self.assertEqual(next(p['pid'] for role, p in rows if role == 'FB'), 'TE1')
        self.assertEqual(next(p['pid'] for role, p in rows if role == 'TE'), 'TE0')

    def test_injuries_and_missing_tight_ends_use_healthy_unique_replacements(self):
        team = roster(); team['depth']['TE'] = []; team['extra_blockers'] = []
        team['wr'] = team['depth']['WR']
        state = State(['HB0','QB0','LT0','WR0'])
        unit, positions = game.field_units(team, state, np.random.default_rng(5), True, '13')
        self.assertEqual(len(positions), 11)
        self.assertFalse(state.out.intersection(positions))
        self.assertEqual(unit['qb']['pid'], 'QB1')

    def test_stateless_call_still_fields_package(self):
        unit, positions = game.field_units(roster(), None, np.random.default_rng(2), True, '00')
        self.assertIsNone(unit['rb'])
        self.assertEqual(len(unit['wr']), 5)
        self.assertEqual(len(positions), 11)

    def test_coach_mix_changes_calls(self):
        totals = []
        for mix in ({'11': .95, '12': .05}, {'11': .05, '12': .95}):
            rng = np.random.default_rng(802)
            calls = [schemes.call_offense(1,10,0,50,rng,lean={'personnel_mix':mix}) for _ in range(300)]
            totals.append(sum(c['personnel']=='12' for c in calls))
            for call in calls:
                self.assertIn(call['personnel'], formations.FORMATIONS[call['formation']]['packages'])
        self.assertGreater(totals[1]-totals[0], 200)

    def test_sneak_formation_matches_changed_package(self):
        rng = np.random.default_rng(144)
        calls = [schemes.call_offense(3,1,0,30,rng,lean={'personnel_mix':{'11':1}}) for _ in range(150)]
        self.assertTrue(any(c.get('sneak') for c in calls))
        for call in calls:
            self.assertIn(call['personnel'], formations.FORMATIONS[call['formation']]['packages'])

    def test_depth_chart_highlights_same_unique_starters_as_engine(self):
        import views_club as VC
        import rosters as RO
        team = roster()
        objects = {pos: [SimpleNamespace(pid=p['pid'],pos=pos,ratings=p,
                                        out_until=None,team='TST') for p in men]
                   for pos, men in team['depth'].items()}
        objects['HB'][0].out_until = 99
        pins = {'WR':['WR3','WR2','WR0','WR1']}
        t = SimpleNamespace(depth=objects,scheme=None,depth_pins=pins,
                            roster=[p for men in objects.values() for p in men],
                            gm=SimpleNamespace(def_front='4-3',off_personnel='11'))
        t.active = lambda: t.roster
        league = SimpleNamespace(teams={'TST':t},week=1)
        session = SimpleNamespace(runner=None, user_team='TST')
        healthy = [dict(p.ratings) for p in t.roster if p.out_until is None]
        healthy.append(dict(healthy[0], pid='CB0', pos='CB'))
        assembled = RO.build_roster_rows(healthy,pins=pins)
        with patch.object(VC,'rail',return_value={}), patch.object(VC,'user_player_grade',return_value=dict(ovr=70,fit=0)), \
             patch.object(VC,'player_plate',side_effect=lambda p:{'pid':p.pid}):
            for package in OR.PACKAGES:
                t.gm.off_personnel = package
                view = VC.depth(session,league,'TST')
                chart = {p['pid'] for col in view['sides']['offense'] for p in col['slots'] if p['start']}
                actual = OR.empty_package(assembled['depth'], t.gm) if package in ('00', '01') else package
                engine = {p['pid'] for role,p in OR.field(assembled,actual)['offensive_assignments']}
                self.assertEqual(chart,engine,package)
                self.assertEqual(len(chart),11)
                t.gm.off_personnel = '11'
                selected = VC.depth(session,league,'TST',offense_package=package)
                self.assertEqual(selected['offense_package'],actual)
                self.assertEqual([p for p in selected['offense_packages'] if p in ('00', '01')], ['00'])
                selected_starters = {p['pid'] for col in selected['sides']['offense'] for p in col['slots'] if p['start']}
                self.assertEqual(selected_starters,engine)
                self.assertEqual(t.gm.off_personnel,'11')

    def test_single_empty_preview_adapts_for_gap_and_available_players(self):
        import views_club as VC
        for te_grade, wr_grade, injured_receivers, expected in (
                (80, 70, False, '01'), (75, 82, False, '01'),
                (60, 85, False, '00'), (60, 85, True, '01')):
            with self.subTest(te=te_grade, wr=wr_grade, injured=injured_receivers):
                objects = {pos: [SimpleNamespace(pid=p['pid'], pos=pos,
                    ovr=te_grade if pos == 'TE' else wr_grade,
                    ratings=dict(p, ovr=te_grade if pos == 'TE' else wr_grade),
                    out_until=99 if injured_receivers and pos == 'WR' and i >= 4 else None,
                    team='TST') for i, p in enumerate(men)]
                    for pos, men in roster()['depth'].items()}
                t = SimpleNamespace(depth=objects, scheme=None, depth_pins={},
                    roster=[p for men in objects.values() for p in men],
                    gm=SimpleNamespace(def_front='4-3', off_personnel='11', aggression=.5))
                t.active = lambda: t.roster
                session = SimpleNamespace(runner=None, user_team='TST')
                league = SimpleNamespace(teams={'TST':t}, week=1)
                with patch.object(VC,'rail',return_value={}), \
                     patch.object(VC,'user_player_grade',return_value=dict(ovr=70,fit=0)), \
                     patch.object(VC,'player_plate',side_effect=lambda p:{'pid':p.pid}):
                    # Either previously selected variant migrates to the same
                    # adaptive preview, including after player availability changes.
                    for old_selection in ('00', '01'):
                        view = VC.depth(session, league, 'TST', offense_package=old_selection)
                        self.assertEqual(view['offense_package'], expected)
                        self.assertEqual([p for p in view['offense_packages'] if p in ('00','01')], ['00'])
                        starters = [(c['pos'], p['pid']) for c in view['sides']['offense']
                                    for p in c['slots'] if p['start']]
                        count = Counter(pos for pos, pid in starters)
                        self.assertEqual((count['WR'], count['TE']), (5, 0) if expected == '00' else (4, 1))
                        self.assertEqual(len({pid for pos, pid in starters}), 11)
                        self.assertFalse({p.pid for p in t.roster if p.out_until is not None}
                                         .intersection(pid for pos, pid in starters))


if __name__ == '__main__':
    unittest.main()
