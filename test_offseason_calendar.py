"""Staff renewal stop, retained waiver processing and annual cutdown protection."""
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

    def test_roll_opens_staff_contracts_before_player_resign_decision(self):
        s = self.fresh()
        s.stop = ('offseason', 3)
        with patch.object(s, 'step_roll'), patch.object(SS.TRD, 'run'), \
                patch.object(s, 'step_extensions') as extensions:
            s.advance()
        self.assertEqual(s.stop, ('offseason', 4))
        extensions.assert_not_called()
        self.assertEqual(len([m for m in s.L.inbox
                              if (m.get('payload') or {}).get('key') == f'staff-renewals-{s.L.year}']), 1)

    def test_old_wire_slot_loads_into_staff_contracts_without_rng_draw(self):
        s = self.fresh()
        s.stop = ('offseason', 4)
        state = copy.deepcopy(s.rng.bit_generator.state)
        loaded = SS.Session.load(s.save())
        again = SS.Session.load(loaded.save())
        self.assertEqual(loaded.stop, ('offseason', 4))
        self.assertEqual(again.stop, loaded.stop)
        self.assertEqual(state, again.rng.bit_generator.state)
        self.assertEqual(len(loaded.L.inbox), len(again.L.inbox))

    def test_staff_advance_with_no_expirations_preserves_player_decisions(self):
        s = self.fresh()
        s.stop = ('offseason', 4)
        state = copy.deepcopy(s.rng.bit_generator.state)
        with patch.object(s, 'step_extensions') as extensions, patch.object(SS.TRD, 'run'), \
                patch.object(SS.WV, 'process') as process:
            s.advance()
        self.assertEqual(s.stop, ('offseason', 5))
        extensions.assert_not_called()
        process.assert_called_once()
        self.assertEqual(state, s.rng.bit_generator.state)

    def test_expiry_decisions_save_reload_block_and_complete(self):
        import staff
        s=self.fresh();s.stop=('offseason',4)
        c=s.L.teams['GB'].staff['oc'];c.years=0
        before=copy.deepcopy(s.rng.bit_generator.state)
        self.assertEqual(s.advance()['done'],'Blocked')
        self.assertEqual(before,s.rng.bit_generator.state)
        self.assertTrue(s.frontoffice_act('staff_expiry',role='oc')['ok'])
        s=SS.Session.load(s.save())
        self.assertTrue(s.frontoffice('staff')['cards'][0]['let_expire'])
        with patch.object(SS.TRD,'run'):s.advance()
        self.assertEqual(s.stop,('offseason',5))
        self.assertIsNone(s.L.teams['GB'].staff['oc'])
        self.assertTrue(any(x.name==c.name for x in s.L.staff_pool))

    def test_real_runner_staff_change_preserves_plan_and_updates_kicker(self):
        import staff, season
        s=self.fresh();s.L.set_phase('regular');s.stop=('week',1)
        s.runner=season.SeasonRunner(s.L,s.rng)
        s.L.user_week_plan={'week':1,'changes':{'pass_bias':.08},'accepted':[0]}
        before=copy.deepcopy(s.L.user_week_plan)
        c=staff.Coach('Replacement ST','st',90,50,'kicker management',45,3,None)
        c.staff_traits=[];s.L.staff_pool.append(c)
        self.assertTrue(s.frontoffice_act('staff_release',role='st')['ok'])
        self.assertTrue(s.frontoffice_act('staff_hire',name=c.name)['ok'])
        self.assertEqual(before,s.L.user_week_plan)
        self.assertAlmostEqual(s.runner.states['GB'].roster['k']['st_noise'],staff.kick_noise_mult(s.L.teams['GB']))
        self.assertEqual(s.runner.states['GB'].staff_fx['short_kick_bias'],staff.short_kick_bias(s.L.teams['GB']))

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
        s.stop = ('offseason', 14)
        # The previous season's played flag must not bypass the camp guard.
        s.played = True
        roster = [p.pid for p in s.L.teams['GB'].active()]
        self.assertGreater(len(roster), 53)
        state = copy.deepcopy(s.rng.bit_generator.state)
        self.assertTrue(any(b['kind'] == 'roster' for b in s.blocking()))
        self.assertEqual(s.advance()['done'], 'Blocked')
        self.assertEqual(s.stop, ('offseason', 14))
        self.assertEqual(roster, [p.pid for p in s.L.teams['GB'].active()])
        self.assertEqual(state, s.rng.bit_generator.state)

    def test_draft_ui_completion_moves_to_camp_and_preserves_results(self):
        import views_draft
        s = self.fresh()
        s.L.year += 1
        s.L.draft_pool, s.L.next_class = s.L.next_class, []
        pk = next(pk for pk in s.L.teams['GB'].picks if pk.year == s.L.year - 1)
        pk.selection = 1
        s.stop = ('offseason', 12)
        s.advance()
        self.assertTrue(s.draft_live())
        result = views_draft.act_pick(s, s.L, 'GB', s.L.draft_pool[0].pid)
        self.assertTrue(result['done'])
        self.assertEqual(s.stop, ('offseason', 13))
        history = json.loads(json.dumps(s.L.last_draft))
        self.assertEqual(len(history['results']), 1)
        s = SS.Session.load(s.save())
        with patch.object(s, 'step_camp'), patch.object(SS.TRD, 'run'):
            s.advance()
        self.assertEqual(s.stop, ('offseason', 14))
        self.assertEqual(s.L.last_draft, history)
        # Legacy saves left at the draft stop must retain the same history too.
        s.stop = ('offseason', 12)
        s.advance()
        self.assertEqual(s.stop, ('offseason', 13))
        self.assertEqual(s.L.last_draft, history)


if __name__ == '__main__':
    unittest.main()
