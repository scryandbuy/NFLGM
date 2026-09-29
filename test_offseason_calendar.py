"""Empty offseason wire transitions and annual user cutdown protection."""
import copy
import json
import unittest
from unittest.mock import patch

import session as SS
import waivers as WV


class OffseasonCalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = SS.Session.new('GB', seed=47).save()

    def fresh(self):
        s = SS.Session.load(self.baseline)
        s.L.set_phase('offseason')
        s.L.waivers = []
        return s

    def test_roll_skips_empty_wire_but_preserves_resign_decision(self):
        s = self.fresh()
        s.stop = ('offseason', 3)
        with patch.object(s, 'step_roll'), patch.object(SS.TRD, 'run'), \
                patch.object(s, 'step_extensions') as extensions:
            s.advance()
        self.assertEqual(s.stop, ('offseason', 5))
        extensions.assert_not_called()
        self.assertEqual(len([m for m in s.L.inbox
                              if (m.get('payload') or {}).get('key') == f'resign-{s.L.year}']), 1)

    def test_old_empty_wire_save_loads_into_resign_once_without_rng_draw(self):
        s = self.fresh()
        s.stop = ('offseason', 4)
        state = copy.deepcopy(s.rng.bit_generator.state)
        loaded = SS.Session.load(s.save())
        again = SS.Session.load(loaded.save())
        self.assertEqual(loaded.stop, ('offseason', 5))
        self.assertEqual(again.stop, loaded.stop)
        self.assertEqual(state, again.rng.bit_generator.state)
        self.assertEqual(len(loaded.L.inbox), len(again.L.inbox))

    def test_direct_advance_from_empty_wire_does_not_lock_tags(self):
        s = self.fresh()
        s.stop = ('offseason', 4)
        state = copy.deepcopy(s.rng.bit_generator.state)
        with patch.object(s, 'step_extensions') as extensions, \
                patch.object(SS.WV, 'process') as process:
            s.advance()
        self.assertEqual(s.stop, ('offseason', 5))
        extensions.assert_not_called()
        process.assert_not_called()
        self.assertEqual(state, s.rng.bit_generator.state)

    def test_nonempty_wire_survives_reload_and_resolves_on_advance(self):
        s = self.fresh()
        p = next(p for p in s.L.teams['ATL'].active() if p.accrued < 4)
        s.L.release(p.pid)
        self.assertIn(p.pid, [e['pid'] for e in WV.pending(s.L)])
        s.stop = ('offseason', 4)
        s._open_fa_if_due()
        s = SS.Session.load(s.save())
        self.assertEqual(s.stop, ('offseason', 4))
        s.advance()
        self.assertEqual(s.stop, ('offseason', 5))
        self.assertNotIn(p.pid, [e['pid'] for e in WV.pending(s.L)])

    def test_later_cutdown_blocks_without_changing_roster_or_rng(self):
        s = self.fresh()
        s.stop = ('offseason', 13)
        # The previous season's played flag must not bypass the camp guard.
        s.played = True
        roster = [p.pid for p in s.L.teams['GB'].active()]
        self.assertGreater(len(roster), 53)
        state = copy.deepcopy(s.rng.bit_generator.state)
        self.assertTrue(any(b['kind'] == 'roster' for b in s.blocking()))
        self.assertEqual(s.advance()['done'], 'Blocked')
        self.assertEqual(s.stop, ('offseason', 13))
        self.assertEqual(roster, [p.pid for p in s.L.teams['GB'].active()])
        self.assertEqual(state, s.rng.bit_generator.state)

    def test_draft_ui_completion_moves_to_camp_and_preserves_results(self):
        import views_draft
        s = self.fresh()
        s.L.year += 1
        s.L.draft_pool, s.L.next_class = s.L.next_class, []
        pk = next(pk for pk in s.L.teams['GB'].picks if pk.year == s.L.year - 1)
        pk.selection = 1
        s.stop = ('offseason', 11)
        s.advance()
        self.assertTrue(s.draft_live())
        result = views_draft.act_pick(s, s.L, 'GB', s.L.draft_pool[0].pid)
        self.assertTrue(result['done'])
        self.assertEqual(s.stop, ('offseason', 12))
        history = json.loads(json.dumps(s.L.last_draft))
        self.assertEqual(len(history['results']), 1)
        s = SS.Session.load(s.save())
        with patch.object(s, 'step_camp'), patch.object(SS.TRD, 'run'):
            s.advance()
        self.assertEqual(s.stop, ('offseason', 13))
        self.assertEqual(s.L.last_draft, history)
        # Legacy saves left at the draft stop must retain the same history too.
        s.stop = ('offseason', 11)
        s.advance()
        self.assertEqual(s.stop, ('offseason', 12))
        self.assertEqual(s.L.last_draft, history)


if __name__ == '__main__':
    unittest.main()
