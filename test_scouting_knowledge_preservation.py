"""Earned scouting information stays coherent across decisions and reloads."""
import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

import numpy as np
import character_assessment as CA
import draft_plan as DP
import practice_squad as PS
import scouting as SC
import targets as TG
from league import League, Player
from test_draft_planning import fixture


def prospect():
    p = Player('observed-WR', 'Observed Receiver', 'WR', 22,
               {key: 80 for key in TG.DEPTH_WEIGHTS['WR']},
               potential=90, potential_range=(86, 94))
    p.xp_spent['_tape'] = 0
    p.traits = dict(work_ethic=55, discipline=55)
    return p


class ScoutingKnowledgePreservationTests(unittest.TestCase):
    def test_grade_and_draft_proxy_summarize_same_observed_vector(self):
        p = prospect()
        view = dict(e_phys=6, e_skill=-2, e_pot=1, adj=0, reads=1, flags=[])
        SC._refresh(view, p)
        self.assertAlmostEqual(TG.position_score(SC.scouted_ratings(p, view), p.pos), 79.84)
        self.assertEqual(view['ovr'], 79.8)
        proxy = DP.observed_prospect(N(scouting={'MIN': {p.pid: view}}), 'MIN', p)
        self.assertEqual(proxy.ovr, round(TG.position_score(proxy.ratings, p.pos), 1))

    def test_medical_discount_stays_separate_and_tape_fades_with_visit(self):
        p = prospect(); p.xp_spent.update(_tape=8, _tape_role='inflated')
        p.potential_range = (76, 84)  # Keep the uncertainty bounds away from the 99 cap.
        base = dict(e_phys=6, e_skill=-2, e_pot=1, adj=0, reads=2, flags=[])
        normal = copy.deepcopy(base); medical = dict(base, adj=-2)
        SC._refresh(normal, p); SC._refresh(medical, p)
        self.assertEqual(SC.scouted_ratings(p, normal), SC.scouted_ratings(p, medical))
        self.assertAlmostEqual(normal['ovr']-medical['ovr'], 2)
        self.assertAlmostEqual(normal['pot_hi']-normal['pot_lo'],
                               medical['pot_hi']-medical['pot_lo'])
        visited = dict(base, flags=['visited']); SC._refresh(visited, p)
        self.assertLess(visited['ovr'], normal['ovr'])
        self.assertEqual(visited['ovr'], round(TG.position_score(SC.scouted_ratings(p, visited), p.pos), 1))
        self.assertEqual(p.xp_spent['_tape'], 8)

    def test_grade_respects_attribute_clipping(self):
        p = prospect()
        for physical, skill in ((40, -70), (-70, 40)):
            view = dict(e_phys=physical, e_skill=skill, e_pot=0, adj=-1, flags=[])
            SC._refresh(view, p)
            attrs = SC.scouted_ratings(p, view)
            self.assertTrue(all(30 <= value <= 99 for value in attrs.values()))
            self.assertEqual(view['ovr'], round(max(30, TG.position_score(attrs, p.pos)-1), 1))

    def test_migration_uses_only_existing_evidence_and_is_idempotent(self):
        league, _ = fixture(); p = league.player('rookie-WR0')
        view = league.scouting['MIN'][p.pid]
        view.update(ovr=99, e_phys=6, e_skill=-2, adj=-2, cert=.56, reads=3,
                    flags=['medical', 'visited'], e_skill0=-4)
        p.xp_spent.pop('_tape')  # Old save lacking tape must not earn a fresh draw.
        before = copy.deepcopy(view); truth = copy.deepcopy(p.to_dict())
        with patch.object(SC.np.random, 'default_rng', side_effect=AssertionError('new evidence')):
            self.assertTrue(SC.migrate(league))
            expected = round(TG.position_score(SC.scouted_ratings(p, view), p.pos)-2, 1)
            self.assertEqual(view['ovr'], expected)
            self.assertEqual(league.consensus[p.pid]['ovr'], expected)
            self.assertFalse(SC.migrate(league))
        for key, value in before.items():
            if key != 'ovr': self.assertEqual(view[key], value)
        self.assertEqual(p.to_dict(), truth)

    def test_load_migrates_scalar_and_consensus_without_mutating_payload(self):
        league, _ = fixture(); p = league.player('rookie-WR0')
        view = league.scouting['MIN'][p.pid]
        view.update(ovr=99, e_phys=6, e_skill=-2, adj=-2, cert=.56, reads=3)
        expected = SC.observed_overall(p, view)
        saved = league.save(); original = copy.deepcopy(saved)
        loaded = League.load(saved)
        self.assertEqual(saved, original)
        self.assertEqual(loaded.scouting['MIN'][p.pid]['ovr'], expected)
        self.assertEqual(loaded.consensus[p.pid]['ovr'], expected)
        for key in ('pot_lo', 'pot_hi', 'e_phys', 'e_skill', 'cert', 'reads', 'adj'):
            self.assertEqual(loaded.scouting['MIN'][p.pid][key], view[key])
        again = League.load(loaded.save())
        self.assertEqual(again.scouting, loaded.scouting)
        self.assertEqual(again.consensus, loaded.consensus)

    def test_migration_retains_historical_and_incomplete_reads(self):
        league, _ = fixture(); p = league.player('rookie-WR0')
        p.draft_overall = 10; p.team = 'MIN'
        historical = copy.deepcopy(league.scouting['MIN'][p.pid])
        incomplete = league.scouting['MIN']['rookie-WR1']; del incomplete['e_skill']
        incomplete_before = copy.deepcopy(incomplete)
        SC.migrate(league)
        self.assertEqual(league.scouting['MIN'][p.pid], historical)
        self.assertEqual(incomplete, incomplete_before)

    def test_practice_cannot_replace_stronger_visit_but_keeps_counting(self):
        p = prospect(); view = {}
        CA.visit(p, 'MIN', view, {'character': 'sharp'}, 3)
        bank = p.xp_spent['_character_observations']['MIN']
        earned = copy.deepcopy(bank)
        for week in range(1, 19): CA.observe_practice(p, 'MIN', 2028, week)
        self.assertEqual(bank, earned)
        self.assertEqual(CA.player_report(p, 'MIN')[0]['source'], 'Visit and references')
        self.assertEqual(p.xp_spent['_character_practice']['MIN']['weeks'], 18)

    def test_practice_improves_weak_prior_and_retains_evidence_at_floor(self):
        p = prospect()
        CA.area_report(p, 'MIN', {}, {'character': 'normal'}, .5)
        for week in range(1, 19): CA.observe_practice(p, 'MIN', 2028, week)
        read = p.xp_spent['_character_observations']['MIN']['work_ethic']
        self.assertEqual(read['source'], 'Team practices')
        self.assertEqual(read['error'], 5)
        self.assertEqual(read['evidence'], 18)

    def test_legacy_character_migration_recovers_strong_saved_visit_without_reroll(self):
        p = prospect(); view = {}
        CA.visit(p, 'MIN', view, {'character': 'sharp'}, 3)
        strong = copy.deepcopy(view['character_assessments'])
        p.xp_spent['_character_observations']['MIN']['work_ethic'] = dict(
            value=80, error=11.5, source='Team practices', evidence=3)
        league = N(players={p.pid: p}, scouting={'MIN': {p.pid: view}})
        with patch.object(CA, '_read', side_effect=AssertionError('rerolled')):
            CA.migrate(league)
        self.assertEqual(p.xp_spent['_character_observations']['MIN'], strong)
        view['character_assessments']['work_ethic']['value'] = 1
        self.assertNotEqual(p.xp_spent['_character_observations']['MIN']['work_ethic']['value'], 1)

    def test_udfa_scout_recommendations_rank_the_displayed_room_read(self):
        players = [N(pid=f'U{i}', name=f'Prospect {i}', pos='WR', college='College',
                     draft_round=None, draft_year=2028, team=None,
                     ovr=50 if i == 0 else 70+i) for i in range(6)]
        lookup = {p.pid: p for p in players}
        league = N(year=2028, user_team='MIN', free_agents=list(lookup),
                   teams={'MIN': N()}, player=lookup.get,
                   scouting={'MIN': {p.pid: {'ovr': 95 if p.pid == 'U0' else 60} for p in players}})
        with patch('inbox.post') as post, patch.object(PS, 'inbox_player', side_effect=lambda p: p.pid):
            self.assertEqual(PS.udfa_camp(league, np.random.default_rng(1)), 0)
        rows = post.call_args.kwargs['payload']['mail_sections'][0]['rows']
        self.assertEqual(rows[0], ['U0', 'WR', '95'])
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(p.team is None for p in players))


if __name__ == '__main__':
    unittest.main()
