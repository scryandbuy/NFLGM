import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import character_assessment as CA
import scouting as SC
import spring as SP
import personality as PT
from league import League
from test_cap_accounting import fixture, player


class CharacterAssessmentTests(unittest.TestCase):
    def setup_player(self, traits=None):
        league = fixture(); p = player(league)
        p.traits = dict(work_ethic=10, discipline=10, financial_priority=95, loyalty=5, ambition=80)
        p.traits.update(traits or {})
        p.potential_range = (80, 90)
        view = dict(e_phys=0, e_skill=0, e_pot=0, reads=1, flags=[])
        SC._refresh(view, p)
        league.scouting = {'GB': {p.pid: view}}
        league.teams['GB'].staff = {'scout': N(staff_traits=[])}
        return league, p, view

    def test_old_prospect_gets_stable_display_read_without_trait_or_risk_change(self):
        league, p, view = self.setup_player()
        league.draft_pool = [p]
        traits = copy.deepcopy(p.traits)
        original = copy.deepcopy(view)
        CA.migrate(league)
        self.assertEqual(CA.report(view)[1]['source'], 'Film assessment')
        self.assertEqual(CA.report(view)[0]['summary'], 'Not assessed')
        self.assertEqual(p.traits, traits)
        self.assertEqual(CA.draft_risk(view, N(risk=.5)), CA.draft_risk(original, N(risk=.5)))
        saved = copy.deepcopy(view)
        CA.migrate(league)
        self.assertEqual(view, saved)

    def test_old_prospect_keeps_existing_discipline_read(self):
        league, p, view = self.setup_player()
        league.draft_pool = [p]
        CA.film(p, 'GB', view)
        saved = copy.deepcopy(view)
        CA.migrate(league)
        self.assertEqual(view, saved)

    def test_tape_room_sees_film_but_no_preparation_or_secret_personality(self):
        _, p, view = self.setup_player()
        CA.film(p, 'GB', view)
        self.assertFalse(CA.visit(p, 'GB', view, {'character': 'none'}, 4))
        report = CA.report(view)
        self.assertEqual(report[0]['summary'], 'Not assessed')
        self.assertEqual(report[1]['source'], 'Film assessment')
        self.assertEqual(report[1]['confidence'], 'Limited')
        self.assertFalse(any(key in str(report) for key in ('financial_priority', 'loyalty', 'ambition', 'value', 'error')))

    def test_tape_first_scout_trades_background_precision_for_football_looks(self):
        league, p, view = self.setup_player()
        league.teams['GB'].staff['scout'].staff_traits = ['tape']
        room = SC.room(league.teams['GB'])
        self.assertEqual(room['character'], 'tape')
        self.assertGreater(room['looks_mult'], 1.)
        league.teams['GB'].staff['scout'].staff_traits = ['tape', 'grinder']
        self.assertGreater(SC.room(league.teams['GB'])['looks_mult'], room['looks_mult'])
        normal = copy.deepcopy(view)
        self.assertTrue(CA.area_report(p, 'GB', normal, {'character': 'normal'}, .5))
        self.assertTrue(CA.area_report(p, 'MIN', view, room, .5))
        self.assertGreater(CA.assessments(view)['work_ethic']['error'],
                           CA.assessments(normal)['work_ethic']['error'])
        self.assertTrue(CA.visit(p, 'MIN', view, room, 4))
        self.assertEqual(CA.report(view)[0]['source'], 'Visit and references')

    def test_visit_flags_do_not_change_talent_or_ceiling_and_cannot_reroll(self):
        league, p, view = self.setup_player()
        before = copy.deepcopy(view); rng = np.random.default_rng(5); rng_before = copy.deepcopy(rng.bit_generator.state)
        SP._character(league, 'GB', league.teams['GB'], p, 0, rng)
        for key in ('ovr', 'pot_lo', 'pot_hi'):
            self.assertEqual(view[key], before[key])
        self.assertIn('Work ethic concern', CA.flags(view))
        read = copy.deepcopy(view)
        p.traits['work_ethic'] = 95
        SP._character(league, 'GB', league.teams['GB'], p, 0, rng)
        self.assertEqual(view, read)
        self.assertEqual(rng.bit_generator.state, rng_before)

    def test_character_judge_reduces_observed_error(self):
        errors = {'normal': [], 'sharp': []}
        for i in range(200):
            p = N(pid=f'rookie-{i}', traits={'work_ethic': 50, 'discipline': 50}, xp_spent={})
            for mode in errors:
                view = {}
                CA.visit(p, 'GB', view, {'character': mode}, 8)
                errors[mode].append(abs(view['character_assessments']['work_ethic']['value']-50))
        self.assertLess(np.mean(errors['sharp']), .6*np.mean(errors['normal']))

    def test_visit_precision_preserves_scout_quality_and_room_tradeoff(self):
        p = N(pid='visit-quality', traits={'work_ethic': 50, 'discipline': 50}, xp_spent={})
        reads = {}
        for quality, sd in (('weak', 5.25), ('middle', 3.75), ('strong', 2.25)):
            for mode in ('normal', 'tape', 'sharp'):
                view = {}
                self.assertTrue(CA.visit(p, 'GB', view, {'character': mode}, sd))
                reads[(quality, mode)] = view['character_assessments']['work_ethic']['error']
        for mode in ('normal', 'tape', 'sharp'):
            self.assertGreater(reads[('weak', mode)], reads[('middle', mode)])
            self.assertGreater(reads[('middle', mode)], reads[('strong', mode)])
        for quality in ('weak', 'middle', 'strong'):
            self.assertGreater(reads[(quality, 'tape')], reads[(quality, 'normal')])
            self.assertLess(reads[(quality, 'sharp')], reads[(quality, 'normal')])
        self.assertAlmostEqual(reads[('middle', 'normal')], 6.8)
        self.assertAlmostEqual(reads[('middle', 'tape')], 8.5)

    def test_visit_improves_prior_read_without_raising_work_ethic(self):
        p = N(pid='visit-prior', traits={'work_ethic': 40, 'discipline': 50}, xp_spent={})
        view = {'character_assessments': {'work_ethic': dict(value=48, error=4., stage='background')}}
        self.assertTrue(CA.visit(p, 'GB', view, {'character': 'normal'}, 5.25))
        self.assertAlmostEqual(view['character_assessments']['work_ethic']['error'], 3.4)
        self.assertEqual(p.traits['work_ethic'], 40)
        saved = copy.deepcopy(view)
        self.assertFalse(CA.visit(p, 'GB', view, {'character': 'normal'}, 2.25))
        self.assertEqual(view, saved)

    def test_cpu_risk_uses_knowledge_not_hidden_truth(self):
        _, p, view = self.setup_player()
        gm = N(risk=.5)
        self.assertEqual(CA.draft_risk(view, gm), 0)
        CA.visit(p, 'GB', view, {'character': 'sharp'}, 0)
        concern = CA.draft_risk(view, gm)
        self.assertGreater(concern, 0)
        p.traits = dict(work_ethic=100, discipline=100)
        self.assertEqual(CA.draft_risk(view, gm), concern)
        limited = copy.deepcopy(view)
        for read in limited['character_assessments'].values(): read['error'] = 22
        self.assertLess(CA.draft_risk(limited, gm), concern)
        self.assertLess(CA.draft_risk(view, N(risk=1)), CA.draft_risk(view, N(risk=0)))

    def test_cpu_board_applies_observed_risk_without_changing_grades(self):
        import draft
        from test_draft_planning import fixture as draft_fixture
        league, team = draft_fixture(); p = league.player('rookie-WR0')
        view = league.scouting['MIN'][p.pid]
        before = copy.deepcopy(view)
        with patch.object(draft, 'slot_value', side_effect=lambda slot: -slot):
            clean = dict((p.pid, value) for value, p in draft.board(league, 'MIN', 20, {}, set()))
            view['character_assessments'] = {'work_ethic': dict(value=10, error=4, source='Visit and references')}
            concerned = dict((p.pid, value) for value, p in draft.board(league, 'MIN', 20, {}, set()))
            self.assertLess(concerned[p.pid], clean[p.pid])
            p.traits = {'work_ethic': 100, 'discipline': 100}
            hidden = dict((p.pid, value) for value, p in draft.board(league, 'MIN', 20, {}, set()))
            self.assertEqual(hidden, concerned)
        for key in ('ovr', 'pot_lo', 'pot_hi'): self.assertEqual(view[key], before[key])

    def test_legacy_flags_keep_saved_grades_and_are_not_double_counted(self):
        league, p, view = self.setup_player()
        view.update(character_read=20, flags=['character'], adj=-2)
        SC._refresh(view, p)
        before = copy.deepcopy(view)
        league.teams['GB'].staff = {}
        blob = league.save(); original = copy.deepcopy(blob)
        loaded = League.load(blob); actual = loaded.scouting['GB'][p.pid]
        self.assertEqual(blob, original)
        for key in ('ovr', 'pot_lo', 'pot_hi', 'adj'):
            self.assertEqual(actual[key], before[key])
        self.assertEqual(CA.draft_risk(actual, N(risk=0)), 0)
        self.assertEqual(CA.player_report(loaded.player(p.pid), 'GB')[0]['status'], 'concern')
        self.assertEqual(CA.player_report(loaded.player(p.pid), 'MIN')[0]['status'], 'unknown')
        again = League.load(loaded.save())
        self.assertEqual(again.scouting, loaded.scouting)

    def test_viewing_assessments_does_not_mutate_anything(self):
        _, p, view = self.setup_player()
        before = copy.deepcopy((p.to_dict(), view))
        for _ in range(5): CA.report(view); CA.flags(view); CA.player_report(p, 'GB')
        self.assertEqual((p.to_dict(), view), before)

    def test_practice_observations_require_participation_weeks_and_persist(self):
        league, p, _ = self.setup_player({'work_ethic': 90})
        for _ in range(10): CA.observe_practice(p, 'GB', 2026, 1)
        self.assertEqual(CA.player_report(p, 'GB')[0]['status'], 'unknown')
        CA.observe_practice(p, 'GB', 2026, 2); CA.observe_practice(p, 'GB', 2026, 3)
        report = CA.player_report(p, 'GB')[0]
        self.assertEqual(report['source'], 'Team practices')
        self.assertEqual(report['status'], 'strength')
        self.assertEqual(CA.player_report(p, 'MIN')[0]['status'], 'unknown')
        league.teams['GB'].staff = {}
        self.assertEqual(CA.player_report(League.load(league.save()).player(p.pid), 'GB')[0], report)

    def test_one_penalty_does_not_replace_scout_assessment(self):
        _, p, view = self.setup_player({'discipline': 95})
        CA.visit(p, 'GB', view, {'character': 'sharp'}, 0)
        report = CA.player_report(p, 'GB', {'penalty_opportunities': 30, 'penalties_committed': 1,
                                           'penalties_accepted': 0, 'penalty_yards': 0})[1]
        self.assertEqual(report['status'], 'strength')
        self.assertEqual(report, CA.player_report(p, 'GB')[1])
        self.assertNotIn('game_record', report)
        self.assertEqual(CA.player_report(p, 'GB')[0]['label'], 'Work Ethic')
        self.assertEqual(CA.describe('discipline')['explanation'], '')

    def test_prospect_card_never_reveals_true_traits(self):
        import views_draft as VD
        league, p, view = self.setup_player()
        league.draft_pool = [p]; league.consensus = {p.pid: dict(ovr=75, rank=30)}
        p.name = 'Rookie Example'; p.age = 22; p.xp_spent = {}; p.team = None
        CA.visit(p, 'GB', view, {'character': 'sharp'}, 0)
        session = N(user_team='GB', draft=None, stop=('week', 1))
        with patch.object(VD, 'rail', return_value={}):
            card = VD.prospect_card(session, league, 'GB', p.pid)
        self.assertEqual(card['personality'], '')
        self.assertEqual(len(card['character_report']), 2)
        self.assertIn('Work ethic concern', card['words'])
        self.assertNotIn('wants to be paid', str(card))
        self.assertNotIn('follows the money', str(card))
        self.assertNotIn('wants the ball', str(card))

    def test_prospect_card_hides_tentative_and_legacy_badges(self):
        import views_draft as VD
        league, p, view = self.setup_player()
        league.draft_pool = [p]; league.consensus = {p.pid: dict(ovr=75, rank=30)}
        p.age = 22; p.team = None
        view.update(flags=['character', 'discipline'], character_read=10)
        CA.film(p, 'GB', view)
        session = N(user_team='GB', draft=None, stop=('week', 1))
        with patch.object(VD, 'rail', return_value={}):
            card = VD.prospect_card(session, league, 'GB', p.pid)
        self.assertNotIn('Work ethic concern', card['words'])
        self.assertNotIn('Discipline concern', card['words'])
        self.assertEqual(len(card['character_report']), 2)

    def test_practice_work_ethic_and_dev_have_independent_bounded_effects(self):
        import practice as P
        import xp
        from test_practice_engine import setup, plan
        league, runner, players = setup(); p = players[-1]
        with patch('staff.xp_mult', return_value=1.):
            rows = []
            for dev in xp.DEV_MULT:
                p.dev = dev; amounts = []
                for ethic in (20, 50, 80):
                    p.traits = {'work_ethic': ethic, 'discipline': 0}
                    amount = P._xp_award(league, league.teams['A'], p, 1., 1., False, 0)
                    amounts.append(amount['xp'])
                    p.traits['discipline'] = 100
                    self.assertEqual(P._xp_award(league, league.teams['A'], p, 1., 1., False, 0), amount)
                    self.assertLessEqual(amount['xp'], amount['xp_ceiling'])
                self.assertAlmostEqual(amounts[0]/amounts[1], .88)
                self.assertAlmostEqual(amounts[2]/amounts[1], 1.12)
                rows.append(amounts)
            self.assertTrue(all(rows[i][1] < rows[i+1][1] for i in range(len(rows)-1)))
            with patch('practice.BASE_INJURY_RISK', 0):
                before = copy.deepcopy(p.xp_spent)
                forecast = P.preview(league, runner, 'A', 1, plan('standard'))
                self.assertEqual(p.xp_spent, before)
                result = P.resolve(league, runner, 'A', 1, plan('standard'))
                expected = next(r['xp'] for r in forecast['players'] if r['pid'] == p.pid)
                self.assertAlmostEqual(p.xp, expected)
                self.assertAlmostEqual(p.xp_spent['_earned']['practice'], expected)
                P.resolve(league, runner, 'A', 1, plan('standard'))
                self.assertAlmostEqual(p.xp, expected)


if __name__ == '__main__': unittest.main()
