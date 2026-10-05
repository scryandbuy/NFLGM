import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import game_substitutions as S
import plays as P
import rosters
import schemes


class PressureTiming(unittest.TestCase):
    def test_timing_matches_report_across_routes_and_protections(self):
        teams = rosters.load_league()
        seen = set()
        try:
            for depth in ('short', 'medium', 'deep'):
                for protection in ('five', 'six_bob', 'seven'):
                    for seed in range(60):
                        rng = np.random.default_rng(seed)
                        off, _ = G.field_units(teams['GB'], None, rng, True, '11')
                        defense, _ = G.field_units(teams['DEN'], None, rng, False, 'nickel', '3-4')
                        oc = dict(is_pass=True, personnel='11', depth=depth, concept='dagger',
                                  down=2, ydstogo=8, play_action=False, shotgun=True)
                        dc = schemes.call_defense(oc, 2, 8, rng)
                        P.PASS_TRACE = []
                        with patch.object(schemes, 'choose_protection', return_value=protection):
                            out = P._pass_play(off, defense, oc, dc, 50, rng)
                        tr = next((x for x in reversed(P.PASS_TRACE) if x['path'] in ('man', 'zone')), None)
                        if tr is None: continue
                        seen.add(tr['path'])
                        # Hot calls retain their separate hurried-throw cost.
                        clock = next(x for x in P.PASS_TRACE if x['path'] == 'clock')
                        self.assertAlmostEqual(tr['pressure'], min(1., out['pressure_severity'] + (.2 if clock['hot'] else 0.)))
                        self.assertEqual(out['pressured'], out['pressure_severity'] > 0.)
                        if out.get('read') == 'checkdown' and depth == 'deep' and not clock['hot']:
                            self.assertGreater(out['pressure_release'], P.BASE_TTT)
            self.assertEqual(seen, {'man', 'zone'})
        finally: P.PASS_TRACE = None


class BlowoutRest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base = rosters.load_league()['GB']

    def setup(self, young=False, caution=.5):
        r = copy.deepcopy(self.base)
        for men in r['depth'].values():
            for p in men: p['age'] = 23 if young else 30
        st = G.TeamState(r, coach={'starter_protection': caution})
        return r, st

    def test_close_early_and_overtime_do_not_rest(self):
        r, st = self.setup()
        for seconds, margin in ((1500, 35), (600, 16), (900, 24), (0, 35)):
            self.assertIs(S.for_possession(r, st, seconds, margin, np.random.default_rng(1)), r)
            self.assertFalse(st.resting_starters)

    def test_backup_selected_for_call_and_snap_and_real_workload(self):
        r, st = self.setup()
        st.rest_draws = {p['pid']: 0. for men in r['depth'].values() for p in men}
        v = S.for_possession(r, st, 300, 32, np.random.default_rng(1))
        starter, backup = r['depth']['QB'][:2]
        self.assertEqual(v['qb']['pid'], backup['pid'])
        out, positions = G.field_units(v, st, np.random.default_rng(4), True, '11')
        self.assertEqual(out['qb']['pid'], backup['pid'])
        self.assertEqual(st.snaps[backup['pid']], 1)
        self.assertNotIn(starter['pid'], st.snaps)
        self.assertEqual(len(positions), 11)
        self.assertEqual(r['qb']['pid'], starter['pid'])
        self.assertFalse(st.out)
        self.assertIs(S.for_possession(r, st, 200, 16, np.random.default_rng(1)), r)
        self.assertFalse(st.resting_starters)

    def test_injured_or_exhausted_reserve_does_not_displace_qb(self):
        for injured in (True, False):
            r, st = self.setup()
            qb = r['depth']['QB'][0]
            st.rest_draws = {qb['pid']: 0.}
            for reserve in r['depth']['QB'][1:]:
                if injured: st.out.add(reserve['pid'])
                else: st.cond.cond[reserve['pid']] = 40
            v = S.for_possession(r, st, 100, 40, np.random.default_rng(2))
            self.assertEqual(v['qb']['pid'], qb['pid'])

    def test_young_starters_coaches_quality_and_health_change_judgment(self):
        r, st = self.setup()
        a, b = r['depth']['QB'][:2]
        base = S.rest_probability(a, b, 'QB', st, 1.)
        self.assertLess(S.rest_probability(dict(a, age=23), b, 'QB', st, 1.), base)
        st.coach['starter_protection'] = 1
        self.assertGreater(S.rest_probability(a, b, 'QB', st, 1.), base)
        st.coach['starter_protection'] = .5
        st.cond.cond[a['pid']] = 65
        self.assertGreater(S.rest_probability(a, b, 'QB', st, 1.), base)
        st.cond.cond[a['pid']] = 100
        weak = {k: (30 if k.endswith('_rating') else v) for k,v in b.items()}
        self.assertLess(S.rest_probability(a, weak, 'QB', st, 1.), base)

    def test_defense_stays_unique_with_starters_rested(self):
        r, st = self.setup()
        st.rest_draws = {p['pid']: 0. for men in r['depth'].values() for p in men}
        v = S.for_possession(r, st, 200, -38, np.random.default_rng(3))
        for package in ('base', 'nickel', 'dime'):
            out, positions = G.field_units(v, st, np.random.default_rng(4), False, package, '3-4')
            self.assertEqual(len(positions), 11)
            self.assertFalse(set(positions) & st.out)

    def test_choices_stable_and_repeatable(self):
        r, st = self.setup(); other = copy.deepcopy(st)
        a = S.for_possession(r, st, 300, 32, np.random.default_rng(11))
        b = S.for_possession(r, other, 300, 32, np.random.default_rng(11))
        self.assertEqual(st.resting_starters, other.resting_starters)
        choices = set(st.resting_starters)
        S.for_possession(r, st, 300, 32, np.random.default_rng(99))
        self.assertEqual(choices, st.resting_starters)

    def test_real_drive_uses_backup_for_calls_passes_and_book(self):
        from season import _deps
        r, st = self.setup()
        defense = rosters.load_league()['DEN']; dst = G.TeamState(defense)
        st.rest_draws = {p['pid']: 0. for men in r['depth'].values() for p in men}
        view = S.for_possession(r, st, 300, 32, np.random.default_rng(1))
        backup = view['qb']['pid']; observed = []
        co, cd = _deps()
        def call(*args, **kwargs):
            observed.append(kwargs['offense']['qb']['pid'])
            result = co(*args, **kwargs)
            result.update(is_pass=True, depth='short', concept='mesh')
            return result
        book = G.StatBook(); G.LAST_KICKOFF.clear()
        dr = G.run_drive(view, defense, 75, 300, 4, 32, np.random.default_rng(19),
                         P.resolve_play, call, cd, P.rate, .5, book, st, dst)
        self.assertTrue(observed)
        self.assertEqual(set(observed), {backup})
        passes = [p for p in dr.log if p.get('passer')]
        self.assertTrue(passes)
        self.assertEqual({p['passer'] for p in passes}, {backup})
        self.assertIn(backup, st.snaps)
        self.assertIn(backup, book.p)

    def test_game_loop_rechecks_both_sides_between_possessions(self):
        from season import _deps
        r, st = self.setup(); defense = rosters.load_league()['DEN']
        dst = G.TeamState(defense); co, cd = _deps()
        def drive(off, deff, start, clock, quarter, diff, rng, *args, **kwargs):
            if False: yield None
            dr = G.Drive(off, deff, start, clock, quarter, diff, rng)
            dr.clock = max(0, clock - 600); dr.result = 'Touchdown'; dr.points = 7
            dr.plays = 1
            return dr
        with patch.object(G, 'drive_steps', side_effect=drive), patch.object(S, 'for_possession', wraps=S.for_possession) as select:
            G.play_game(r, defense, np.random.default_rng(8), P.resolve_play, co, cd,
                        P.rate, home_state=st, away_state=dst)
        self.assertGreaterEqual(select.call_count, 8)
        states = {id(c.args[1]) for c in select.call_args_list}
        self.assertEqual(states, {id(st), id(dst)})

    def test_actual_live_replay_after_blowout_rest_matches_finish(self):
        from season import SeasonRunner, _deps
        def runner():
            r = SeasonRunner.__new__(SeasonRunner)
            r.rng = np.random.default_rng(3)
            h, a = copy.deepcopy(self.base), rosters.load_league()['DEN']
            hs, ast = G.TeamState(h, coach={'starter_protection':.7}), G.TeamState(a, coach={'starter_protection':.7})
            r.states = {'GB': hs, 'DEN': ast}; co, cd = _deps(); book = G.StatBook()
            r.live = dict(gen=G.game_steps(h, a, r.rng, P.resolve_play, co, cd, P.rate,
                           home_state=hs, away_state=ast, book=book), book=book,
                          done=False, halftime_open=False, adjustment_period=None,
                          drives=[], current=None, pos='away', score={'home':0,'away':0},
                          at='kick', res=None, actions=[])
            r._close_live = lambda: None
            r._halftime_read = lambda lv: None
            return r
        r = runner()
        for _ in range(500):
            r.live_step('resume' if r.live['halftime_open'] else 'play')
            if any(st.resting_starters for st in r.states.values()): break
            if r.live['done']: break
        self.assertFalse(r.live['done'])
        self.assertTrue(any(st.resting_starters for st in r.states.values()))
        replay = runner()
        replay.replay_live(copy.deepcopy(r.live['actions']), copy.deepcopy(r.rng.bit_generator.state))
        for side in r.states:
            self.assertEqual(r.states[side].resting_starters, replay.states[side].resting_starters)
            self.assertEqual(r.states[side].snaps, replay.states[side].snaps)
        for x in (r, replay):
            while not x.live['done']:
                x.live_step('resume' if x.live['halftime_open'] else 'finish')
        self.assertFalse(any(st.resting_starters for st in r.states.values()))
        self.assertEqual(r.live['score'], replay.live['score'])
        self.assertEqual(r.live['book'].p, replay.live['book'].p)
        self.assertEqual(r.rng.bit_generator.state, replay.rng.bit_generator.state)

    def test_legacy_in_progress_game_does_not_gain_substitutions(self):
        r, st = self.setup(); st.engine_version = 1
        self.assertIs(S.for_possession(r, st, 100, 40, np.random.default_rng(1)), r)


if __name__ == '__main__': unittest.main()
