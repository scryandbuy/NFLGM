"""QB escape lanes and the extra work of a live scramble, with final accounting."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np
import defensive_rush as D
import events as E
import game as G
import health as H
import plays as P
import schemes as S
from test_designed_qb_runs import offense
from test_defensive_rush import unit, call


class EscapeLanes(unittest.TestCase):
    def lanes(self, grade=70, arrival=2., drop=False):
        defense = unit('4-3', 'nickel')
        for p in defense['dl']:
            if p['pos'] in ('LEDG', 'REDG'):
                p.update(pursuit_rating=grade, speed_rating=grade,
                         accel_rating=grade, play_rec_rating=grade)
        dc = call('4-3', 'nickel')
        if drop:
            dc['dropper_ids'] = [a['player']['pid'] for a in D.assignments(defense)
                                 if a['alignment'] == 'left_edge']
        rush = D.select_rush(defense, dc)
        return E.escape_lane_evidence(defense, rush,
            [(p['pid'], arrival) for p in rush['rushers']], 2.8, P.rate)

    def decisions(self, lanes, mobility=85, **kw):
        qb = offense(mobility)['qb']
        args = dict(separation=.1, pressure=.3, time_available=2.8)
        args.update(kw)
        return (E.pocket_run_chance(qb, [], P.rate, escape_lanes=lanes, **args),
                E.scramble_chance(qb, 1., 1.4, P.rate, escape_lanes=lanes))

    def test_both_strong_edges_reduce_both_escape_paths_without_banning_running(self):
        weak, strong = self.decisions(self.lanes(40)), self.decisions(self.lanes(95))
        for low, high in zip(weak, strong):
            self.assertGreater(low, high)
            self.assertGreater(high, 0.)
        self.assertGreater(self.decisions(self.lanes(95), 94)[0], self.decisions(self.lanes(95), 60)[0])

    def test_one_weak_side_remains_a_viable_escape(self):
        both = self.lanes(95); mixed = copy.deepcopy(both)
        mixed['right'][0]['grade'] = .4
        self.assertGreater(self.decisions(mixed)[0], self.decisions(both)[0])

    def test_late_blocked_edge_cannot_control_lane_like_disengaged_edge(self):
        self.assertGreater(self.decisions(self.lanes(95, arrival=5.))[0],
                           self.decisions(self.lanes(95, arrival=2.))[0])

    def test_dropped_edge_counts_on_his_coverage_side(self):
        lanes = self.lanes(95, arrival=5., drop=True)
        self.assertEqual(lanes['left'][0]['available'], 1.)
        self.assertEqual(lanes['right'][0]['available'], 0.)

    def test_middle_drop_does_not_seal_both_sides_and_inactive_edge_is_ignored(self):
        defense = unit('4-3', 'nickel'); rush = D.select_rush(defense, call('4-3', 'nickel'))
        a = next(a for a in rush['assignments'] if a['alignment'] == 'left_edge')
        rush['assignments'].remove(a)
        rush['coverage']['defensive_assignments'].append(dict(a, alignment='offball_middle'))
        lanes = E.escape_lane_evidence(defense, rush, [], 2.8, P.rate)
        self.assertEqual(lanes['left'], [])
        # Metadata for a defender absent from the live field cannot contribute.
        defense['dl'] = [p for p in defense['dl'] if p['pid'] != a['player']['pid']]
        rush['coverage']['defensive_assignments'][-1]['alignment'] = 'offball_left'
        self.assertEqual(E.escape_lane_evidence(defense, rush, [], 2.8, P.rate)['left'], [])

    def test_open_throw_quick_answer_and_late_clock_remain_restrained(self):
        lanes = self.lanes(40)
        self.assertEqual(self.decisions(lanes, separation=.9, pressure=.1)[0], 0.)
        self.assertEqual(self.decisions(lanes, screen=True)[0], 0.)
        self.assertEqual(self.decisions(lanes, hot=True)[0], 0.)
        self.assertLess(self.decisions(lanes, seconds=10, margin=-3)[0], self.decisions(lanes)[0])
        self.assertLess(self.decisions(lanes, aggression=0)[0], self.decisions(lanes, aggression=1)[0])

    def test_open_or_fully_blocked_lanes_do_not_add_an_automatic_bonus(self):
        self.assertEqual(E.escape_lane_factor(.9, {'left': [], 'right': []}), 1.)
        self.assertEqual(E.escape_lane_factor(.9, self.lanes(50, arrival=5.)), 1.)

    def test_actual_pass_resolver_supplies_same_context_to_decision_and_log(self):
        off, defense = offense(), unit('4-3', 'nickel')
        observed = []
        original = E.pocket_run_chance
        def capture(*args, **kw):
            observed.append(kw['escape_lanes'])
            return original(*args, **kw)
        with patch.object(E, 'pocket_run_chance', side_effect=capture):
            for seed in range(30):
                out = P.resolve_play(off, defense,
                    dict(is_pass=True, personnel='11', depth='medium', concept='dagger'),
                    dict(call('4-3', 'nickel'), box=6, shell='two_high'), 70, np.random.default_rng(seed))
                self.assertIsInstance(out['escape_lanes'], dict)
                if observed:
                    self.assertEqual(observed[-1], out['escape_lanes']); break
        self.assertTrue(observed)


class ScrambleWorkload(unittest.TestCase):
    def drive(self, result='scramble', live=False, backup=False, stamina=70, escape=1., nullified=False):
        off, defense = offense(), unit('4-3', 'nickel')
        for p in off['depth']['QB']: p['stamina_rating'] = stamina
        state, dst = G.TeamState(off), G.TeamState(defense)
        state.road_stamina = 1.1
        if backup: state.out.add('QB')
        observed = []
        def hurt(p, pos, contact, *args, **kw):
            if pos == 'QB': observed.append((p['pid'], contact, state.cond.get(p['pid'])))
        def co(down, distance, margin, ytg, rng, **kw):
            return dict(is_pass=result!='designed', scheme='power', personnel='11',
                        down=down, ydstogo=distance, score_diff=margin)
        lanes = {'left': [dict(pid='edge', grade=.9, available=1)], 'right': []}
        def resolve(o, d, oc, dc, ytg, rng):
            return dict(type='run' if result=='designed' else 'sack' if result=='escape' else result,
                yards=-5. if result=='escape' else 45., touchdown=result!='escape', target='WR0', carrier_pid=o['qb']['pid'],
                qb_run=result=='designed', by='edge', sack_credits=[('edge', .5), ('other', .5)],
                pb_award=[('LT', .5, .2, .1)], rush_pressures=['edge'], escape_lanes=lanes,
                is_pass=result!='designed')
        book = G.StatBook(); G.LAST_KICKOFF.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(S, 'designed_qb_run_chance', return_value=1. if result=='designed' else 0.))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **kw: (oc, None)))
            def penalty(*args, **kw):
                if nullified and kw.get('timing') == 'live':
                    return dict(penalty='Offensive Holding', yards=10., rule_yards=10.,
                                on_offense=True, auto_first=False, nullifies=True)
            stack.enter_context(patch.object(E, 'penalty_check', side_effect=penalty))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            check = stack.enter_context(patch.object(E, 'scramble_chance', return_value=escape))
            stack.enter_context(patch.object(E, 'resolve_scramble', return_value=dict(type='scramble', yards=45., touchdown=True, by='backup' if backup else 'QB')))
            stack.enter_context(patch.object(state, 'hurt', side_effect=hurt))
            stack.enter_context(patch.object(dst, 'hurt', return_value=None))
            args = (off, defense, 45, 1 if nullified or not escape else 700, 3, 0, np.random.default_rng(51), resolve, co,
                    lambda *a, **kw: dict(call('4-3', 'nickel'), front='4-3', box=6), P.rate)
            kw = dict(off_state=state, def_state=dst, book=book)
            if live:
                gen = G.drive_steps(*args, **kw)
                while True:
                    try: next(gen)
                    except StopIteration as done: dr = done.value; break
            else: dr = G.run_drive(*args, **kw)
        self.assertEqual(check.call_args.kwargs['escape_lanes'], lanes)
        return state, dr, book, observed

    def test_voluntary_and_sack_escape_charge_same_running_work_as_designed_keep(self):
        rows = {kind: self.drive(kind) for kind in ('complete', 'scramble', 'escape', 'designed')}
        self.assertLess(rows['scramble'][0].cond.get('QB'), rows['complete'][0].cond.get('QB'))
        for kind in ('scramble', 'escape', 'designed'):
            state, dr, book, hits = rows[kind]
            self.assertAlmostEqual(state.cond.get('QB'), rows['designed'][0].cond.get('QB'))
            self.assertEqual(state.snaps['QB'], 1)
            self.assertEqual(state.cond.snaps['QB'], 1)
            self.assertEqual(state.snap_counts['offense']['players']['QB'], 1)
            self.assertEqual(hits[0], ('QB', 1.6, state.cond.get('QB')))

    def test_stamina_actual_backup_and_live_instant_parity(self):
        a = self.drive('escape', backup=True, stamina=90)
        b = self.drive('escape', backup=True, stamina=90, live=True)
        self.assertEqual(a[1].log, b[1].log); self.assertEqual(a[2].p, b[2].p)
        self.assertNotIn('QB', a[0].cond.snaps)
        self.assertEqual(a[0].cond.snaps['backup'], 1)
        self.assertGreater(a[0].cond.get('backup'), self.drive('escape', backup=True, stamina=50)[0].cond.get('backup'))

    def test_successful_escape_removes_half_sack_credits_preserves_pressure(self):
        _, dr, book, _ = self.drive('escape')
        play = next(p for p in dr.log if p.get('scramble_kind') == 'escape')
        self.assertNotIn('sack_credits', play)
        self.assertEqual(play['rush_pressures'], ['edge'])
        self.assertEqual(play['pb_sack_survival'], 0.)
        self.assertEqual(book.p['QB']['rush_att'], 1)
        self.assertEqual(sum(p.get('sacks', 0) for p in book.p.values()), 0.)

    def test_incremental_work_does_not_add_snap_and_respects_condition_floor(self):
        state = H.Condition(); state.play('QB', 'QB', 90, 1.1)
        state.add_running_work('QB', 90, 1.1)
        expected = H.Condition(); expected.play('QB', 'HB', 90, 1.1)
        self.assertAlmostEqual(state.get('QB'), expected.get('QB'))
        self.assertEqual(state.snaps, expected.snaps)
        state.cond['QB'] = 1.; state.add_running_work('QB')
        self.assertEqual(state.get('QB'), 0.)

    def test_failed_escape_retains_half_sacks_and_does_not_charge_running(self):
        state, dr, book, _ = self.drive('escape', escape=0.)
        sack = next(p for p in dr.log if p.get('type') == 'sack')
        self.assertEqual(sack['sack_credits'], [('edge', .5), ('other', .5)])
        self.assertEqual(book.p['edge']['sacks'], .5)
        self.assertEqual(book.p['other']['sacks'], .5)
        expected = H.Condition(); expected.play('QB', 'QB', effort=1.1)
        self.assertAlmostEqual(state.cond.get('QB'), expected.get('QB'))

    def test_nullified_live_scramble_still_costs_work_but_no_official_carry(self):
        state, dr, book, _ = self.drive('scramble', nullified=True)
        self.assertEqual(state.cond.snaps['QB'], 1)
        expected = H.Condition(); expected.play('QB', 'HB', effort=1.1)
        self.assertAlmostEqual(state.cond.get('QB'), expected.get('QB'))
        self.assertEqual(book.p.get('QB', {}).get('rush_att', 0), 0)

    def test_two_point_live_retries_cost_work_false_start_does_not(self):
        for penalty in (None, 'offense', 'defense'):
            with self.subTest(penalty=penalty):
                off, defense = offense(), unit('4-3', 'nickel')
                state, dst = G.TeamState(off), G.TeamState(defense)
                flag = None if penalty is None else dict(penalty='False Start' if penalty=='offense' else 'Offside',
                    yards=5., on_offense=penalty=='offense', auto_first=False, nullifies=True)
                outcomes = [dict(type='scramble', yards=0.)] if penalty=='defense' else []
                outcomes.append(dict(type='scramble', yards=10.))
                with patch.object(E, 'special_teams_penalty_check', return_value=flag):
                    G.attempt_two_point(off, defense, np.random.default_rng(42),
                        lambda *a, **kw: outcomes.pop(0),
                        lambda *a, **kw: dict(is_pass=True, personnel='11'),
                        lambda *a, **kw: dict(call('4-3', 'nickel'), box=6), P.rate,
                        off_state=state, def_state=dst)
                count = 2 if penalty=='defense' else 1
                expected = H.Condition()
                for _ in range(count): expected.play('QB', 'HB')
                self.assertEqual(state.cond.snaps['QB'], count)
                self.assertAlmostEqual(state.cond.get('QB'), expected.get('QB'))


if __name__ == '__main__': unittest.main()
