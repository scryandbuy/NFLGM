"""Empty personnel must not bypass the coach's QB-carry decision."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import events as E
import game as G
import offense_roles as OR
import plays as P
import playcall as PC
import schemes as S
from test_designed_qb_runs import offense
from test_defensive_rush import unit, call


class EmptyRunChoices(unittest.TestCase):
    def setUp(self):
        # The game initializes these from league rosters; the isolated caller
        # fixture supplies neutral reference grades instead.
        self.baselines = patch.dict(PC.DEPTH_BASE, short=.7, medium=.7, deep=.7)
        self.baselines.start()
        self.addCleanup(self.baselines.stop)

    def test_declined_keep_audibles_with_actual_eleven_and_no_fake_handoff(self):
        off = OR.field(offense(60), '00')
        original = copy.deepcopy(off)
        oc = dict(is_pass=False, personnel='00', scheme='power', qb_run=False,
                  down=4, ydstogo=9, seconds=140, score_diff=-7)
        self.assertTrue(S.answer_empty_run(off, oc, 40, np.random.default_rng(9), P.rate))
        self.assertEqual(off, original)
        self.assertEqual(oc['personnel'], '00')
        self.assertTrue(oc['is_pass'])
        self.assertFalse(oc['qb_run'])
        self.assertFalse(oc['play_action'])
        self.assertNotEqual(oc['concept'], 'screen')
        with patch.object(P, '_pass_play', return_value=dict(type='incomplete', yards=0)) as passed:
            P.resolve_play(off, unit(), oc, call(), 40, np.random.default_rng(5))
        passed.assert_called_once()

    def test_explicit_keep_handoff_sneak_and_pass_remain_unchanged(self):
        for package, extra in [('00', {'qb_run': True}), ('11', {}),
                               ('00', {'sneak': True}), ('00', {'is_pass': True})]:
            off = OR.field(offense(), package)
            oc = dict(is_pass=False, personnel=package, scheme='power')
            oc.update(extra)
            before = copy.deepcopy(oc)
            rng = np.random.default_rng(44)
            state = copy.deepcopy(rng.bit_generator.state)
            self.assertFalse(S.answer_empty_run(off, oc, 40, rng, P.rate))
            self.assertEqual(oc, before)
            self.assertEqual(rng.bit_generator.state, state)

    def drive(self, approve=False, live=False, try_play=False, no_backup=False,
              explicit=False, protect=False):
        off, defense = offense(), unit('4-3', 'nickel')
        state, dst = G.TeamState(off), G.TeamState(defense)
        if no_backup: state.out.add('backup')
        observed = []
        def co(down, distance, margin, ytg, rng, **kw):
            return dict(is_pass=False, scheme='power', personnel='00',
                        down=down, ydstogo=distance, score_diff=margin, qb_run=explicit)
        def resolve(o, d, oc, dc, ytg, rng):
            observed.append((copy.deepcopy(o), copy.deepcopy(oc)))
            if oc['is_pass']:
                return dict(type='complete', yards=ytg, touchdown=True,
                            target='WR0', passer=o['qb']['pid'])
            return dict(type='run', yards=ytg, touchdown=True,
                        carrier_pid=(o['qb'] if oc.get('qb_run') else o.get('rb') or o['qb'])['pid'],
                        qb_run=oc.get('qb_run'))
        book = G.StatBook()
        with ExitStack() as stack:
            choice = stack.enter_context(patch.object(S, 'designed_qb_run_chance', return_value=1. if approve else 0.))
            stack.enter_context(patch('playcall.audible', side_effect=lambda oc, *a, **kw: (oc, None)))
            stack.enter_context(patch.object(E, 'penalty_check', return_value=None))
            stack.enter_context(patch.object(E, 'special_teams_penalty_check', return_value=None))
            stack.enter_context(patch.object(state, 'hurt', return_value=None))
            stack.enter_context(patch.object(dst, 'hurt', return_value=None))
            defensive_answers = []
            def cd(oc, *a, **kw):
                defensive_answers.append(copy.deepcopy(oc))
                return dict(call('4-3', 'nickel'), front='4-3', box=6)
            if protect:
                stack.enter_context(patch.object(G, 'end_of_half_plan', return_value=dict(choice='kneel', hurry=False)))
            if try_play:
                result = G.attempt_two_point(off, defense, np.random.default_rng(17),
                    resolve, co, cd, P.rate, off_state=state, def_state=dst, book=book)
            else:
                args = (off, defense, 45, 1900 if protect else 700, 2 if protect else 3, 0, np.random.default_rng(17),
                        resolve, co, cd, P.rate)
                kw = dict(off_state=state, def_state=dst, book=book)
                if protect: kw['half_end'] = 1800
                if live:
                    gen = G.drive_steps(*args, **kw)
                    while True:
                        try: next(gen)
                        except StopIteration as done:
                            result = done.value; break
                else:
                    result = G.run_drive(*args, **kw)
        return observed, state, result, book, choice.call_args_list, defensive_answers

    def test_actual_drive_respects_both_choices_and_charges_once(self):
        passed, kept = self.drive(), self.drive(approve=True)
        self.assertTrue(passed[0][0][1]['is_pass'])
        self.assertTrue(kept[0][0][1]['qb_run'])
        for rows, state, result, book, _, _ in (passed, kept):
            self.assertIsNone(rows[0][0]['rb'])
            self.assertEqual(state.snaps['QB'], 1)
            self.assertEqual(sum(state.snap_counts['offense']['players'].values()), 11)
        self.assertLess(kept[1].cond.get('QB'), passed[1].cond.get('QB'))
        self.assertEqual(passed[3].p['QB'].get('rush_att', 0), 0)
        self.assertEqual(kept[3].p['QB']['rush_att'], 1)
        live = self.drive(live=True)
        self.assertEqual(passed[2].log, live[2].log)
        self.assertEqual(passed[3].p, live[3].p)

    def test_empty_try_also_needs_an_approved_keep(self):
        passed, kept = self.drive(try_play=True), self.drive(try_play=True, approve=True)
        self.assertTrue(passed[0][0][1]['is_pass'])
        self.assertTrue(kept[0][0][1]['qb_run'])
        self.assertLess(kept[1].cond.get('QB'), passed[1].cond.get('QB'))
        self.assertEqual(kept[1].snaps['QB'], 1)

    def test_try_uses_actual_backup_availability_and_preserves_explicit_keep(self):
        ordinary = self.drive(try_play=True)
        alone = self.drive(try_play=True, no_backup=True)
        self.assertEqual(ordinary[4][0].kwargs['healthy_backups'], 1)
        self.assertEqual(alone[4][0].kwargs['healthy_backups'], 0)
        selected = self.drive(try_play=True, explicit=True)
        self.assertEqual(selected[4], [])
        self.assertTrue(selected[0][0][1]['qb_run'])

    def test_clock_protection_selects_back_before_defense_answers(self):
        rows, state, result, book, _, defensive_answers = self.drive(protect=True)
        self.assertEqual(defensive_answers[0]['personnel'], '11')
        self.assertEqual(rows[0][0]['rb']['pos'], 'HB')
        self.assertFalse(rows[0][1]['is_pass'])
        self.assertFalse(rows[0][1]['qb_run'])
        self.assertEqual(book.p['QB'].get('rush_att', 0), 0)


if __name__ == '__main__':
    unittest.main()
