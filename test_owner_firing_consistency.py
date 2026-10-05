"""Completed employment evidence is shared without rewriting season priors."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import firing_model as FM
import offseason_calendar as OC
import postseason as PS
from gm_engine import GM
from league import League
from test_cap_accounting import fixture


class OwnerFiringEvidence(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.year = 2029
        for t in self.L.teams.values():
            t.gm = GM(name=t.abbr); t.tenure = 3; t.expected_cached = .6
            t.record = [3, 14, 0]
            t.history = [dict(year=2028, win_pct=11/17, made_playoffs=True, record=[11,6,0]),
                         dict(year=2029, win_pct=3/17, made_playoffs=False, record=[3,14,0])]
        self.t = self.L.teams['GB']

    def test_full_record_replaces_prior_only_for_employment(self):
        prior = self.t.hist()
        self.assertNotAlmostEqual(prior['win_pct'], 3/17)
        evidence = FM.team_evidence(self.t)
        self.assertAlmostEqual(evidence['win_pct'], 3/17)
        self.assertAlmostEqual(evidence['prev_win_pct'], 11/17)
        self.assertEqual(self.t.hist(), prior)
        self.assertGreater(FM.fire_chance_offseason(evidence), FM.fire_chance_offseason(prior))

    def test_ties_count_as_half_and_early_season_prior_stays(self):
        self.t.record = [7,7,3]
        self.assertEqual(FM.team_evidence(self.t)['win_pct'], .5)
        self.t.record = [0,1,0]
        self.assertEqual(FM.team_evidence(self.t)['win_pct'], self.t.hist()['win_pct'])

    def test_young_starter_credit_is_same_for_display_and_decision(self):
        with patch.object(self.t, 'starter', return_value=NS(age=24, ovr=80)):
            evidence = FM.team_evidence(self.t)
            self.assertTrue(evidence['qb_continuity'])
            self.assertEqual(FM.team_job_security(self.t), FM.job_security(evidence))
            self.assertLess(FM.fire_chance_offseason(evidence), FM.fire_chance_offseason(evidence, qb_dev=False))
        for qb in (None, NS(age=27, ovr=95), NS(age=24, ovr=70)):
            with patch.object(self.t, 'starter', return_value=qb):
                self.assertFalse(FM.team_evidence(self.t)['qb_continuity'])

    def test_rollover_capture_survives_json_and_does_not_borrow_new_starter(self):
        self.t.owner_patience = .9
        with patch.object(self.t, 'starter', return_value=NS(age=24, ovr=80)):
            context = json.loads(json.dumps(OC.team_context(self.L)))
        self.L.year = 2030; self.t.record = [0,0,0]; self.t.owner_patience = .1
        with patch.object(self.t, 'starter', return_value=NS(age=30, ovr=80)):
            captured = FM.team_evidence(self.t, record=context['records']['GB'],
                history=context['histories']['GB'], season_year=2029)
        self.assertEqual(captured, context['histories']['GB'])
        self.assertEqual(captured['owner_patience'], .9)
        legacy = dict(context['histories']['GB']); legacy.pop('qb_continuity')
        with patch.object(self.t, 'starter', return_value=NS(age=22, ovr=99)):
            old = FM.team_evidence(self.t, record=context['records']['GB'], history=legacy, season_year=2029)
        self.assertFalse(old['qb_continuity'])
        self.assertAlmostEqual(old['win_pct'], 3/17)
        for record in (None, context['records']['GB']):
            missing = FM.team_evidence(self.t, record=record, season_year=2029)
            self.assertAlmostEqual(missing['win_pct'], 3/17)
            self.assertAlmostEqual(missing['prev_win_pct'], 11/17)

    def test_retention_uses_one_security_definition_and_no_repeat_roll(self):
        context = OC.team_context(self.L)
        expected = FM.job_security(context['histories']['GB'])
        self.L.year = 2030; self.t.record = [0,0,0]
        rng = NS(random=Mock(return_value=.999))
        with patch('coaching_pool.fire_and_hire') as hire:
            PS.run_firings(self.L, rng, clubs=['GB'], season_year=2029, context=context)
            PS.run_firings(self.L, rng, clubs=['GB'], season_year=2029, context=context)
        hire.assert_not_called(); rng.random.assert_called_once()
        self.assertEqual(self.t.tenure, 4)
        self.assertEqual(self.t.gm.job_security, expected)
        self.assertEqual(FM.team_job_security(self.t), expected)
        loaded = League.load(copy.deepcopy(self.L.save()))
        self.assertEqual(FM.team_job_security(loaded.teams['GB']), expected)
        loaded.teams['GB'].record = [1,0,0]
        self.assertEqual(FM.team_job_security(loaded.teams['GB']), FM.job_security(FM.team_evidence(loaded.teams['GB'])))

    def test_final_record_can_change_firing_while_good_season_retains(self):
        old = FM.fire_chance_offseason(self.t.hist())
        new = FM.fire_chance_offseason(FM.team_evidence(self.t))
        rng = NS(random=lambda: (old + new) / 2)
        with patch('coaching_pool.fire_and_hire', return_value=(None, [])) as hire:
            self.assertEqual(PS.run_firings(self.L, rng, clubs=['GB']), [('GB','pending a search')])
        hire.assert_called_once()
        other = self.L.teams['MIN']; other.record = [13,4,0]
        with patch('coaching_pool.fire_and_hire') as hire:
            self.assertEqual(PS.run_firings(self.L, NS(random=lambda:.5), clubs=['MIN']), [])
        hire.assert_not_called()

    def test_patient_and_impatient_owners_can_disagree_without_a_veto(self):
        other = self.L.teams['MIN']
        self.t.owner_patience = .95; other.owner_patience = .05
        with patch.object(self.t, 'starter', return_value=None), patch.object(other, 'starter', return_value=None):
            patient = FM.fire_chance_offseason(FM.team_evidence(self.t))
            impatient = FM.fire_chance_offseason(FM.team_evidence(other))
            self.assertLess(patient, impatient)
            self.assertGreater(patient, 0)
            self.assertLess(impatient, 1)
            roll = (patient + impatient) / 2
            with patch('coaching_pool.fire_and_hire', return_value=(None, [])) as hire:
                fired = PS.run_firings(self.L, NS(random=lambda: roll), clubs=['GB', 'MIN'])
            self.assertEqual(fired, [('MIN', 'pending a search')])
            hire.assert_called_once()

    def test_new_coach_security_survives_no_results_without_inherited_pressure(self):
        self.t.record = [0,0,0]; self.t.tenure = 0; self.t.gm = GM(job_security=.82)
        self.assertEqual(FM.team_job_security(self.t), .82)
        before = copy.deepcopy(self.L.save())
        FM.team_evidence(self.t); FM.team_job_security(self.t)
        self.assertEqual(self.L.save(), before)

    def test_retained_hot_seat_reaches_existing_gm_horizon_without_erasing_style(self):
        security = FM.job_security(FM.team_evidence(self.t))
        self.assertLess(security, .35)
        patient = GM(job_security=security, patience=.9, aggression=.2)
        impatient = GM(job_security=security, patience=.5, aggression=.7)
        a = patient.shift({'win_pct':.5}); b = impatient.shift({'win_pct':.5})
        self.assertAlmostEqual(a.patience, .5)
        self.assertAlmostEqual(b.patience, .1)
        self.assertGreater(a.patience, b.patience)
        self.assertLess(a.aggression, b.aggression)
        self.assertEqual(patient.patience, .9)


if __name__ == '__main__': unittest.main()
