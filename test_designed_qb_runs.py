"""Designed QB carries are football calls, ordinary rushes, and real workload."""
import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import events as E
import game as G
import offense_roles as O
import plays as P
import schemes as S
import ticker
from test_defensive_rush import unit, call


def offense(mobility=94):
    depth = {p: [dict(pid=p, pos=p)] for p in ('QB', 'HB', 'FB', 'LT', 'LG', 'C', 'RG', 'RT')}
    depth['QB'][0].update(speed_rating=mobility, agility_rating=mobility, accel_rating=mobility)
    depth['QB'].append(dict(pid='backup', pos='QB', speed_rating=60, agility_rating=60, accel_rating=60))
    depth['TE'] = [dict(pid='TE'+str(i), pos='TE') for i in range(3)]
    depth['WR'] = [dict(pid='WR'+str(i), pos='WR') for i in range(5)]
    return dict(O.field(dict(depth=depth), '11'), depth=depth, k={}, p={})


class DesignedRunChoices(unittest.TestCase):
    def chance(self, mobility=94, condition=100, backups=1, defense=None, box=6, **kw):
        oc = dict(is_pass=False, scheme='power', down=2, ydstogo=6,
                  seconds=500, score_diff=0, qb_run_aggression=.5)
        oc.update(kw)
        return S.designed_qb_run_chance(offense(mobility), defense or unit(), oc,
            dict(call(), box=box), P.rate, condition=condition, healthy_backups=backups)

    def test_mobile_action_pocket_restraint_and_not_every_handoff(self):
        self.assertEqual(self.chance(mobility=60), 0)
        self.assertGreater(self.chance(), self.chance(mobility=82))
        self.assertGreater(self.chance(), .1)
        self.assertLessEqual(self.chance(qb_run_aggression=1), .32)
        draws = np.random.default_rng(488).random(2000)
        self.assertGreater(sum(draws < self.chance()), 100)
        self.assertGreater(sum(draws >= self.chance()), 1000)

    def test_coaches_front_pursuit_and_ball_security_can_disagree(self):
        self.assertGreater(self.chance(qb_run_aggression=.9), self.chance(qb_run_aggression=.1))
        self.assertLess(self.chance(box=8), self.chance(box=6))
        strong = unit()
        for p in strong['lb'] + strong['dl']:
            p.update(pursuit_rating=99, play_rec_rating=99, speed_rating=99)
        self.assertLess(self.chance(defense=strong), self.chance())
        low, high = offense(), offense()
        low['qb']['carry_rating'] = 30; high['qb']['carry_rating'] = 95
        args = (unit(), dict(is_pass=False), dict(call(), box=6), P.rate)
        self.assertGreater(S.designed_qb_run_chance(high, *args), S.designed_qb_run_chance(low, *args))

    def test_clock_distance_health_and_protecting_qb_restraint(self):
        normal = self.chance()
        for kw in ({'is_pass': True}, {'sneak': True}, {'protect_ball': True},
                   {'seconds': 20, 'score_diff': -3}, {'seconds': 20, 'score_diff': 3},
                   {'down': 4, 'ydstogo': 10}, {'condition': 60}):
            self.assertEqual(self.chance(**kw), 0, kw)
        for kw in ({'seconds': 95, 'score_diff': -3}, {'seconds': 180, 'score_diff': 3},
                   {'score_diff': 24}, {'condition': 72}, {'backups': 0}):
            self.assertLess(self.chance(**kw), normal, kw)
        self.assertGreater(self.chance(ydstogo=2), normal)


class DesignedRunResolution(unittest.TestCase):
    def resolve(self, off=None, deff=None, seed=3, **kw):
        oc = dict(is_pass=False, qb_run=True, scheme='power'); oc.update(kw)
        return P.resolve_play(off or offense(), deff or unit(), oc,
            dict(call(), front='3-4 one', box=6), 60, np.random.default_rng(seed))

    def test_runner_blockers_statbook_and_ticker_use_quarterback(self):
        off, defense = offense(), unit()
        out = self.resolve(off, defense)
        self.assertEqual((out['type'], out['carrier'], out['carrier_pid']), ('run', 'QB', 'QB'))
        self.assertTrue(out['qb_run'])
        reps = [p for p, won in out['rb_reps']]
        self.assertIn('HB', reps); self.assertNotIn('QB', reps)
        self.assertEqual(len(reps), len(set(reps)))
        support = out['run_support']
        self.assertEqual(len(support), len({p['defender'] for p in support}))
        book = G.StatBook(); book.record(out, off, defense, np.random.default_rng(1))
        self.assertEqual(book.p['QB']['rush_att'], 1)
        self.assertEqual(book.p['QB']['pass_plays'], 0)
        self.assertEqual(book.p.get('HB', {}).get('rush_att', 0), 0)
        line = ticker.play_line(NS(player=lambda pid: NS(name=pid)), out, 'H', 'A')
        self.assertIn('keeps', line['text'])

    def test_halfback_lead_block_ability_matters_without_runner_self_block(self):
        low, high = offense(), offense()
        for off, rating in ((low, 20), (high, 99)):
            off['rb'].update(lead_block_rating=rating, impact_block_rating=rating, run_block_rating=rating)
        for seed in range(25):
            self.assertGreater(self.resolve(high, seed=seed)['ybc'], self.resolve(low, seed=seed)['ybc'])
        handoff = self.resolve(high, qb_run=False)
        self.assertEqual(handoff['carrier_pid'], 'HB')
        self.assertNotIn('HB', {p for p, won in handoff['rb_reps']})

    def test_negative_runs_and_strong_edge_containment_are_not_sacks(self):
        weak, strong = unit(), unit()
        for defense, rating in ((weak, 30), (strong, 99)):
            for p in defense['lb']:
                if p['pos'] in ('LEDG', 'REDG'):
                    p.update(block_shed_rating=rating, strength_rating=rating,
                             pursuit_rating=rating, tackle_rating=rating)
        self.assertLess(self.resolve(deff=strong)['ybc'], self.resolve(deff=weak)['ybc'])
        losses = [self.resolve(seed=s) for s in range(100)]
        self.assertTrue(any(p['yards'] < 0 for p in losses))
        self.assertTrue(all(p['type'] == 'run' and not p.get('is_pass') for p in losses))

    def test_fumble_uses_qb_security_and_is_attributed_to_qb(self):
        off, defense = offense(), unit()
        out = dict(type='run', yards=3, qb_run=True, carrier='QB', carrier_pid='QB')
        with patch.object(E, 'fumble_check', return_value=dict(lost=False)) as check:
            G._prepare_fumble(NS(yardline=60), out, off, defense, np.random.default_rng(5), P.rate)
        self.assertEqual(check.call_args.args[0]['pid'], 'QB')
        self.assertEqual(check.call_args.args[1], 'run')
        self.assertEqual(out['fumble_by'], 'QB')
        book = G.StatBook(); book.record_fumble(out)
        self.assertEqual(book.p['QB']['fumbles'], 1)

    def test_carry_costs_running_workload_without_double_counting_snap(self):
        outcomes = []
        for carry in (False, True):
            off = offense(); state = G.TeamState(off)
            pending = G._PendingSnap(state)
            field, _ = G.field_units(off, pending, np.random.default_rng(2), True, '11')
            pending.commit(field, qb_carry=carry)
            outcomes.append(state.cond.get('QB'))
            self.assertEqual(state.snaps['QB'], 1)
            self.assertEqual(state.cond.snaps['QB'], 1)
            self.assertEqual(state.snap_counts['offense']['players']['QB'], 1)
        self.assertLess(outcomes[1], outcomes[0])


class DesignedRunDrive(unittest.TestCase):
    def drive(self, live=False, injured=False, force=True):
        off, defense = offense(), unit()
        state, dst = G.TeamState(off, coach={'starter_protection': .2}), G.TeamState(defense)
        if injured is True: state.out.add('QB')
        seen, contacts = [], []
        original = S.designed_qb_run_chance
        def chance(o, d, oc, dc, rate, **kw):
            value = original(o, d, oc, dc, rate, **kw)
            seen.append((o['qb']['pid'], value, oc['qb_run_aggression']))
            return 1. if force and value > 0 else value
        def injury(p, pos, contact, *args, **kw):
            contacts.append((p['pid'], contact))
            if injured == 'during' and p['pid'] == 'QB' and contact == 1.6 and 'QB' not in state.out:
                state.out.add('QB')
                return dict(kind='ankle', weeks_out=1)
        def co(down, distance, margin, ytg, rng, **kw):
            return dict(is_pass=False, scheme='power', personnel='11', down=down,
                        ydstogo=distance, score_diff=margin)
        dc = lambda *args, **kw: dict(call(), front='3-4 one', box=6)
        book = G.StatBook(); G.LAST_KICKOFF.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(S, 'designed_qb_run_chance', side_effect=chance))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **kw: (oc, None)))
            stack.enter_context(patch.object(E, 'penalty_check', return_value=None))
            stack.enter_context(patch.object(E, 'fumble_check', return_value=None))
            stack.enter_context(patch.object(state, 'hurt', side_effect=injury))
            stack.enter_context(patch.object(dst, 'hurt', return_value=None))
            args = (off, defense, 45, 700, 3, 0, np.random.default_rng(134), P.resolve_play, co, dc, P.rate)
            kw = dict(book=book, off_state=state, def_state=dst)
            if live:
                stepper = G.drive_steps(*args, **kw)
                while True:
                    try: next(stepper)
                    except StopIteration as done:
                        drive = done.value; break
            else: drive = G.run_drive(*args, **kw)
        return drive, book, seen, contacts

    def test_batch_and_live_share_rushing_clock_book_and_contact(self):
        a, ab, _, contacts = self.drive()
        b, bb, _, _ = self.drive(live=True)
        rows = lambda dr: [(p.get('type'), p.get('clock'), p.get('yards'), p.get('carrier')) for p in dr.log]
        self.assertEqual(rows(a), rows(b)); self.assertEqual(ab.p, bb.p)
        runs = [p for p in a.log if p.get('qb_run') and not p.get('nullified')]
        self.assertTrue(runs)
        self.assertEqual(ab.p['QB']['rush_att'], len(runs))
        self.assertEqual(ab.p['QB']['pass_plays'], 0)
        self.assertTrue(all(p.get('live_seconds', 0) > 0 for p in runs))
        self.assertIn(('QB', 1.6), contacts)
        self.assertIn(('HB', 1.0), contacts)
        self.assertLess(a.clock, 700)

    def test_injured_mobile_starter_does_not_lend_ability_to_pocket_backup(self):
        dr, book, seen, _ = self.drive(injured=True, force=False)
        self.assertTrue(seen)
        self.assertTrue(all(pid == 'backup' and chance == 0 and abs(risk-.8)<1e-10
                            for pid, chance, risk in seen))
        self.assertFalse(any(p.get('qb_run') for p in dr.log))
        self.assertEqual(book.p.get('QB', {}).get('rush_att', 0), 0)

    def test_contact_injury_removes_runner_before_the_next_call(self):
        dr, book, seen, _ = self.drive(injured='during')
        self.assertTrue(any(p.get('type') == 'injury' and p.get('pid') == 'QB' for p in dr.log))
        self.assertEqual(seen[0][0], 'QB')
        self.assertTrue(any(pid == 'backup' and chance == 0 for pid, chance, risk in seen[1:]))
        self.assertEqual(book.p['QB']['rush_att'], 1)


if __name__ == '__main__': unittest.main()
