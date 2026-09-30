"""Selected defensive identity reaches the field, survives reload, and ends on hire."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import coaching_pool as CP
import defense_roles as DR
import gm_engine as GE
import identity_catalog as IC
import offense_roles as OR
import schemes
import season
from session import Session
import views_club as VC
import views_frontoffice as VF


class IdentityFrontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = Session.new('GB', seed=23).save()

    def setUp(self):
        self.s = Session.load(self.saved)
        self.t = self.s.L.teams['GB']
        self.t.gm.def_front = '4-3'
        self.s.runner = season.SeasonRunner(self.s.L, self.s.rng)

    def assert_front(self, s, front):
        t = s.L.teams['GB']; s.runner.refresh('GB')
        chart = VC.depth(s, s.L, 'GB', 'Base')
        self.assertEqual(chart['front'], front)
        self.assertEqual(t.gm.def_front, front)
        self.assertEqual(s.runner.states['GB'].roster['front_family'], front)
        prefs = s.runner.states['GB'].base_plan.front_pref
        self.assertTrue(all(DR.front_family(f) == front for f in prefs))
        calls = [schemes.call_defense({'personnel': '11'}, 1, 10, np.random.default_rng(seed),
                                      lean={'front_pref': prefs}) for seed in range(100)]
        self.assertTrue(all(call['front_family'] == front for call in calls))
        self.assertEqual(len({p['pid'] for c in chart['sides']['defense'] for p in c['slots'] if p['start']}), 11)

    def test_hybrid_overrides_four_three_and_survives_reload_and_offensive_change(self):
        result = self.s.frontoffice_act('apply_identity', key='hybrid_34')
        self.assertTrue(result['ok'])
        self.assert_front(self.s, '3-4')
        loaded = Session.load(self.s.save())
        loaded.frontoffice_act('apply_identity', key='heavy_12')
        self.assert_front(loaded, '3-4')
        self.assertEqual(loaded.L.teams['GB'].identity['defence'], 'hybrid_34')
        loaded.frontoffice_act('apply_identity', key='quarters_match')
        self.assert_front(loaded, '4-3')

    def test_legacy_archetype_action_uses_same_application_path(self):
        self.assertTrue(self.s.frontoffice_act('apply_archetype', key='hybrid_34')['ok'])
        self.assert_front(self.s, '3-4')

    def test_manual_front_change_updates_identity_label(self):
        self.s.frontoffice_act('apply_identity', key='hybrid_34')
        self.s.frontoffice_act('set_identity', changes={'def_front': '4-3'})
        self.assert_front(self.s, '4-3')
        # A customized set of dials is shown as its nearest matching identity.
        self.assertEqual(self.t.identity['defence'], IC.nearest_archetype(self.t.gm, 'defence'))

    def test_new_head_coach_resets_selected_identity(self):
        self.s.frontoffice_act('apply_identity', key='hybrid_34')
        hired = copy.deepcopy(self.s.L.teams['MIN'].gm)
        hired.def_front = '4-3'; hired.name = 'New Coach'
        with patch.object(CP, 'owner_hire', return_value=(hired, {})), patch('position_change.convert_misfits', return_value=[]):
            CP.fire_and_hire(self.s.L, self.t, self.s.rng)
        self.assertIsNone(self.t.identity)
        self.assert_front(self.s, '4-3')
        self.assertEqual(VF.club_identity(self.s.L, self.t)['defence'], IC.nearest_archetype(hired, 'defence'))

    def test_pending_head_coach_hire_also_resets_identity(self):
        self.s.frontoffice_act('apply_identity', key='hybrid_34')
        hired = copy.deepcopy(self.s.L.teams['MIN'].gm)
        hired.def_front = '4-3'; hired.name = 'New Coach'
        self.s.L.pending_hires = {'GB': {'second': hired.name}}
        self.s.L.coach_pool = [hired]
        CP.complete_pending_hire(self.s.L, 'GB', self.s.rng, take_first=False)
        self.assertIsNone(self.t.identity)
        self.assert_front(self.s, '4-3')

    def test_chart_labels_and_package_starters_keep_canonical_pins(self):
        for key, front in (('hybrid_34', '3-4'), ('quarters_match', '4-3')):
            self.s.frontoffice_act('apply_identity', key=key)
            for package in DR.PACKAGE_NAMES:
                chart = VC.depth(self.s, self.s.L, 'GB', package)
                cols = {c['pos']: c for c in chart['sides']['defense']}
                if front == '3-4':
                    left, right = ('LE', 'RE') if package == 'Goal Line' else ('34LE', '34RE')
                    self.assertEqual(cols[left]['title'], 'LE')
                    self.assertEqual(cols[right]['title'], 'RE')
                else:
                    self.assertEqual(cols['LEDG']['title'], 'LEDG')
                    self.assertEqual(cols['REDG']['title'], 'REDG')
                    self.assertEqual(cols['MIKE']['title'], 'MLB')
                starters = [p['pid'] for c in cols.values() for p in c['slots'] if p['start']]
                self.assertEqual(len(starters), 11, (front, package))
                self.assertEqual(len(set(starters)), 11, (front, package))
        self.assertEqual(OR.PACKAGES['13'], dict(HB=1, FB=0, TE=3, WR=1))
        self.assertEqual(OR.PACKAGES['22'], dict(HB=1, FB=1, TE=2, WR=1))


if __name__ == '__main__': unittest.main()
