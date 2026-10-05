"""Scheduled scouting earns saved knowledge, never fresh UI rolls or talent."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import character_assessment as CA
import scouting as SC
import inseason_scouting as IS
from league import League, DraftPick, Player
import targets as TG
from test_draft_planning import fixture, set_grade


def setup():
    league, team = fixture()
    league.user_team = 'MIN'
    league.next_class = list(league.draft_pool)
    league.draft_pool = []
    league.set_phase('regular')
    for p in league.next_class:
        p.traits = dict(work_ethic=35, discipline=45)
    SC.scout(league, np.random.default_rng(35))
    return league, team


class InseasonScoutingTests(unittest.TestCase):
    def test_specialists_manual_only_and_roster_reasons(self):
        L, _ = setup()
        needs = {pos: dict(need=0) for ps in IS.GROUPS.values() for pos in ps}
        needs['LS'] = dict(need=100, starter=100)
        needs['WR'] = dict(need=12, starter=10)
        needs['LT'] = dict(need=11, future=10, expiring=1)
        with patch('draft_plan.assess', return_value={'positions': needs}):
            view = IS.priorities(L, 'MIN')
            self.assertEqual({x['group'] for x in view['suggestions']}, {'Receivers', 'Offensive Line'})
            self.assertTrue(any('expiring contracts' in x['why'] for x in view['suggestions']))
            self.assertTrue(any('stronger starter' in x['why'] for x in view['suggestions']))
            self.assertIn('Specialists', view['groups'])
            chosen = IS.set_priorities(L, 'MIN', group1='Specialists', group2='Receivers', prospect_pid='rookie-QB1')
            self.assertEqual(chosen['group1'], 'Specialists')
            chosen = IS.set_priorities(L, 'MIN', use_scout=True)
            self.assertNotIn('Specialists', (chosen['group1'], chosen['group2']))
        with patch('inseason_scouting._choices', return_value=[]):
            self.assertNotIn('Specialists', [x['group'] for x in IS.priorities(L, 'MIN')['suggestions']])

    def test_saved_automatic_specialist_refreshes_but_manual_choice_survives(self):
        L, _ = setup()
        specialist = copy.deepcopy(L.next_class[0])
        specialist.pid = 'test-punter'
        specialist.pos = 'P'
        L.next_class.append(specialist)
        L.scouting['MIN'][specialist.pid] = copy.deepcopy(next(iter(L.scouting['MIN'].values())))
        row = IS._state(L, IS._pool(L))['clubs'].setdefault('MIN', {})
        row.update(group1='Specialists', group2='Receivers', prospect_pid=specialist.pid)
        self.assertNotEqual(IS.priorities(L, 'MIN')['prospect_pid'], specialist.pid)
        chosen = IS.set_priorities(L, 'MIN', prospect_pid=specialist.pid)
        self.assertEqual(chosen['prospect_pid'], specialist.pid)
        self.assertEqual(IS.priorities(L, 'MIN')['prospect_pid'], specialist.pid)
        chosen = IS.set_priorities(L, 'MIN', use_scout=True)
        self.assertNotEqual(chosen['prospect_pid'], specialist.pid)
        self.assertNotIn('Specialists', (chosen['group1'], chosen['group2']))

    def test_individual_selection_uses_saved_reads_and_is_stable(self):
        L, _ = setup()
        first = IS._defaults(L, 'MIN', IS._pool(L))['prospect_pid']
        for p in L.next_class:
            p.potential = 99
            p.ratings = {k: 99 for k in p.ratings}
        self.assertEqual(first, IS._defaults(L, 'MIN', IS._pool(L))['prospect_pid'])
        self.assertNotIn(next(p.pos for p in L.next_class if p.pid == first), ('K','P','LS'))

    def test_selection_and_reading_are_read_only_except_saved_priorities(self):
        L, _ = setup()
        before = copy.deepcopy(L.to_dict())
        for _ in range(4):
            IS.priorities(L, 'MIN'); IS.reports(L, 'MIN')
        self.assertEqual(before, L.to_dict())
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        IS.set_priorities(L, 'MIN', group1='Offensive Line')
        self.assertEqual(IS.priorities(L, 'MIN')['prospect_pid'], 'rookie-QB1')
        IS.set_priorities(L, 'MIN', prospect_pid='rookie-WR2')
        self.assertEqual(IS.priorities(L, 'MIN')['group1'], 'Offensive Line')
        after = L.to_dict(); after.pop('scouting_season'); before.pop('scouting_season')
        self.assertEqual(before, after)

    def test_bad_selections_are_atomic(self):
        L, _ = setup(); before = L.to_dict()
        for kwargs in (dict(group1='Nonsense'), dict(prospect_pid='QB0')):
            with self.assertRaises(ValueError): IS.set_priorities(L, 'MIN', **kwargs)
        with self.assertRaises(ValueError): IS.set_priorities(L, 'BAD', group1='QB')
        self.assertEqual(before, L.to_dict())

    def test_only_even_regular_weeks_and_no_catchup(self):
        L, _ = setup()
        L.week = 7
        self.assertEqual(IS.priorities(L, 'MIN')['next_report_week'], 8)
        for week in (0, 1, 3, 19, 20, True, '2'):
            self.assertEqual(IS.cross_checks(L, week), {})
        for phase in ('offseason', 'preseason', 'playoffs'):
            L.set_phase(phase)
            self.assertEqual(IS.cross_checks(L, 2), {})
        L.set_phase('regular')
        rows = IS.cross_checks(L, 8)['MIN']
        self.assertTrue(0 < len(rows) <= 30)
        self.assertEqual({r['week'] for r in IS.reports(L, 'MIN')}, {8})
        self.assertEqual(IS.cross_checks(L, 6), {})

    def test_two_group_boosts_plus_baseline_and_prospect_are_deduplicated(self):
        L, _ = setup()
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        rows = IS.cross_checks(L, 2)['MIN']
        self.assertLessEqual(len(rows), 30)
        self.assertEqual(sum(r['pos'] == 'WR' and r['focus'] == 'Position Group' for r in rows), 3)
        self.assertEqual(sum(r['pos'] == 'LEDG' and r['focus'] == 'Position Group' for r in rows), 3)
        self.assertEqual(next(r['focus'] for r in rows if r['pid'] == 'rookie-QB1'), 'Prospect')
        group_pid = next(r['pid'] for r in rows if r['pos'] == 'WR')
        other, _ = setup()
        IS.set_priorities(other, 'MIN', group1='Receivers', group2='Edge', prospect_pid=group_pid)
        rows = IS.cross_checks(other, 2)['MIN']
        self.assertLessEqual(len(rows), 30)
        self.assertEqual(len({r['pid'] for r in rows}), len(rows))

    def test_repeat_toggle_and_reload_cannot_reroll(self):
        L, _ = setup()
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        saved = L.save()
        first = IS.cross_checks(L, 2)
        second = League.load(saved)
        second.user_team = 'MIN'  # Session restores ownership outside League.load.
        self.assertEqual(first, IS.cross_checks(second, 2))
        earned = copy.deepcopy(L.scouting)
        IS.set_priorities(L, 'MIN', prospect_pid='rookie-LT1')
        self.assertEqual(IS.cross_checks(L, 2), {})
        reloaded = League.load(L.save())
        reloaded.user_team = 'MIN'
        self.assertEqual(IS.cross_checks(reloaded, 2), {})
        self.assertEqual(reloaded.scouting, earned)
        self.assertEqual(IS.reports(reloaded, 'MIN'), IS.reports(L, 'MIN'))
        self.assertEqual(IS.priorities(reloaded, 'MIN')['prospect_pid'], 'rookie-LT1')

    def test_reports_detached_and_do_not_expose_hidden_values(self):
        L, _ = setup()
        new = IS.cross_checks(L, 2)
        new['MIN'][0]['after']['ovr'] = -500
        rows = IS.reports(L, 'MIN')
        self.assertNotEqual(rows[0]['after']['ovr'], -500)
        original = copy.deepcopy(rows)
        rows[0]['character'][0]['summary'] = 'Changed'
        self.assertEqual(IS.reports(L, 'MIN'), original)
        text = str(original)
        for field in ('e_skill', 'e_phys', 'e_pot', 'potential', 'medical', "'value':", "'error':", 'ratings'):
            self.assertNotIn(field, text)
        for row in original:
            self.assertLess(row['after']['pot_lo'], row['after']['pot_hi'])

    def test_diminishing_knowledge_without_changing_talent_or_sim_rng(self):
        L, _ = setup()
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        p = L.player('rookie-QB1')
        truth = {x.pid: (copy.deepcopy(x.ratings), x.potential, x.potential_range, x.dev, x.xp, copy.deepcopy(x.traits)) for x in L.next_class}
        live_rng = np.random.default_rng(65); L.rng_state = copy.deepcopy(live_rng.bit_generator.state)
        live = copy.deepcopy(L.rng_state)
        certs = [SC.certainty(L.scouting['MIN'][p.pid])]
        for week in range(2, 19, 2):
            IS.cross_checks(L, week)
            certs.append(SC.certainty(L.scouting['MIN'][p.pid]))
        gains = np.diff(certs)
        self.assertTrue(any(x > 0 for x in gains))
        self.assertTrue(all(x >= 0 for x in gains))
        self.assertTrue(all(gains[i+1] <= gains[i] + 1e-9 for i in range(len(gains)-1)))
        self.assertLessEqual(certs[-1], IS.INSEASON_CERT_MAX)
        self.assertEqual(L.rng_state, live)
        self.assertEqual(live_rng.bit_generator.state, live)
        self.assertEqual(truth, {x.pid: (x.ratings, x.potential, x.potential_range, x.dev, x.xp, x.traits) for x in L.next_class})
        self.assertTrue(all('medical' not in v['flags'] and 'visited' not in v['flags'] for v in L.scouting['MIN'].values()))
        self.assertLessEqual(len(IS.reports(L, 'MIN')), 270)

    def test_only_selected_prospects_receive_football_looks_and_groups_rotate(self):
        L, _ = setup()
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        before = copy.deepcopy(L.scouting['MIN'])
        first = IS.cross_checks(L, 2)['MIN']
        selected = {r['pid'] for r in first}
        for pid, v in L.scouting['MIN'].items():
            if pid not in selected:
                self.assertEqual({k: val for k, val in v.items() if k != 'character_assessments'},
                                 {k: val for k, val in before[pid].items() if k != 'character_assessments'})
        second = IS.cross_checks(L, 4)['MIN']
        self.assertFalse({r['pid'] for r in first if r['pos'] == 'WR'} & {r['pid'] for r in second if r['pos'] == 'WR'})

    def test_cpu_defaults_use_roster_needs_without_prospect_truth(self):
        L, t = setup()
        t.roster = [p for p in t.roster if p.pos != 'QB']
        expected = IS.priorities(L, 'MIN')
        self.assertEqual(expected['group1'], 'QB')
        for p in L.next_class:
            set_grade(p, 20); p.potential = 99; p.traits = dict(work_ethic=100, discipline=100)
        self.assertEqual(IS.priorities(L, 'MIN'), expected)
        t.ir = [t.roster[0]]; t.roster[0].out_until = 30
        self.assertEqual(IS.priorities(L, 'MIN'), expected)

    def test_new_class_resets_history_and_prospect_but_keeps_group(self):
        L, _ = setup()
        IS.set_priorities(L, 'MIN', group1='Receivers', group2='Edge', prospect_pid='rookie-QB1')
        IS.cross_checks(L, 18)
        L.year += 1
        self.assertEqual(IS.cross_checks(L, 2), {})  # old class cannot replay its year
        for p in L.next_class:
            old = p.pid; p.pid = 'next-' + old; L.players.pop(old); L.players[p.pid] = p
        SC.scout(L, np.random.default_rng(92))
        self.assertEqual(IS.reports(L, 'MIN'), [])
        self.assertEqual(IS.priorities(L, 'MIN')['group1'], 'Receivers')
        self.assertTrue(IS.priorities(L, 'MIN')['prospect_pid'].startswith('next-'))
        new = IS.cross_checks(L, 2)['MIN']
        self.assertTrue(new)
        self.assertEqual({r['week'] for r in IS.reports(L, 'MIN')}, {2})

    def test_background_tape_judge_and_visit_upgrade(self):
        L, _ = setup(); p = L.player('rookie-QB1')
        views = {}
        for mode in ('none', 'normal', 'sharp'):
            v = {}; CA.background(p, 'MIN', v, dict(character=mode), 4, 1); views[mode] = v
        self.assertNotIn('work_ethic', CA.assessments(views['none']))
        self.assertIn('discipline', CA.assessments(views['none']))
        normal = views['normal']['character_assessments']['work_ethic']
        sharp = views['sharp']['character_assessments']['work_ethic']
        self.assertLess(sharp['error'], normal['error'])
        self.assertEqual(CA.report(views['normal'])[0]['confidence'], 'Limited')
        self.assertIn('Tentative', CA.report(views['normal'])[0]['explanation'])
        v = views['normal']
        self.assertTrue(CA.visit(p, 'MIN', v, dict(character='normal'), 4))
        self.assertEqual(CA.report(v)[0]['source'], 'Visit and references')
        improved = copy.deepcopy(v)
        CA.background(p, 'MIN', v, dict(character='normal'), 4, 9)
        self.assertEqual(v, improved)
        self.assertFalse(CA.visit(p, 'MIN', v, dict(character='normal'), 4))

    def test_legacy_character_penalty_not_reassessed_or_double_charged(self):
        L, _ = setup(); p = L.player('rookie-QB1')
        v = dict(character_read=20, flags=['character'], adj=-2)
        CA.background(p, 'MIN', v, dict(character='normal'), 4, 9)
        self.assertTrue(v['character_assessments']['work_ethic']['legacy_adjusted'])
        self.assertEqual(v['adj'], -2)
        self.assertFalse(CA.visit(p, 'MIN', v, dict(character='normal'), 4))

    def test_suggestions_respond_to_owned_picks_and_prior_focus(self):
        L, t = setup()
        # Equal needs isolate the owned-pick and cumulative-focus signals.
        need = {pos: dict(need=6, starter=5) for positions in IS.GROUPS.values() for pos in positions}
        for p in L.next_class:
            L.consensus[p.pid]['rank'] = 250
        L.consensus['rookie-WR1']['rank'] = 10
        L.consensus['rookie-QB1']['rank'] = 90
        with patch('draft_plan.assess', return_value={'positions': need}):
            t.picks = [DraftPick(L.year, 1, 'MIN', 'MIN', selection=10)]
            self.assertEqual(IS.priorities(L, 'MIN')['suggestions'][0]['group'], 'Receivers')
            t.picks = [DraftPick(L.year, 3, 'GB', 'MIN', selection=90)]
            self.assertEqual(IS.priorities(L, 'MIN')['suggestions'][0]['group'], 'QB')
            IS.set_priorities(L, 'MIN', group1='QB', group2='Receivers')
            for week in (2, 4, 6): IS.cross_checks(L, week)
            suggestions = IS.priorities(L, 'MIN')['suggestions']
            self.assertNotIn('QB', [s['group'] for s in suggestions])
            self.assertNotIn('Receivers', [s['group'] for s in suggestions])
            chosen = IS.set_priorities(L, 'MIN', use_scout=True)
            self.assertEqual([chosen['group1'], chosen['group2']], [s['group'] for s in suggestions])

    def test_baseline_touches_every_position_with_small_quality_scaled_gains(self):
        L, _ = setup()
        for pos in {pos for ps in IS.GROUPS.values() for pos in ps} - {p.pos for p in L.next_class}:
            p = Player('rookie-' + pos, pos, pos, 22, {k: 70 for k in TG.DEPTH_WEIGHTS[pos]},
                       potential=80, potential_range=(77, 83))
            p.traits = dict(work_ethic=40, discipline=50)
            L.next_class.append(p); L.players[p.pid] = p
        SC.scout(L, np.random.default_rng(55))
        strong = copy.deepcopy(L)
        before = copy.deepcopy(L.scouting['MIN'])
        with patch.object(SC, 'scout_q', return_value=0.):
            weak_rows = IS.cross_checks(L, 2)['MIN']
        coverage = L.scouting_season['clubs']['MIN']['baseline_positions']
        self.assertEqual(set(coverage), {p.pos for p in L.next_class})
        self.assertEqual(sum(coverage.values()), len(coverage))
        with patch.object(SC, 'scout_q', return_value=1.):
            strong_rows = IS.cross_checks(strong, 2)['MIN']
        self.assertEqual(strong.scouting_season['clubs']['MIN']['baseline_positions'], coverage)
        for row in weak_rows:
            if row['focus'] != 'Baseline' or not any(r['pid'] == row['pid'] and r['focus'] == 'Baseline' for r in strong_rows): continue
            pid = row['pid']
            weak_gain = SC.certainty(L.scouting['MIN'][pid]) - SC.certainty(before[pid])
            strong_gain = SC.certainty(strong.scouting['MIN'][pid]) - SC.certainty(before[pid])
            self.assertGreater(strong_gain, weak_gain)
            self.assertLess(strong_gain, .01)
        self.assertLessEqual(len(IS.reports(strong, 'MIN')), 30)

    def test_decision_markers_persist_without_inbox_and_reset_per_class(self):
        L, _ = setup()
        self.assertFalse(IS.decision_resolved(L, 1))
        IS.mark_decision_resolved(L, 1)
        IS.mark_decision_resolved(L, 1)
        L.inbox = []
        loaded = League.load(L.save())
        loaded.user_team = 'MIN'
        self.assertTrue(IS.decision_resolved(loaded, 1))
        self.assertFalse(IS.decision_resolved(loaded, 2))
        self.assertEqual(len(loaded.scouting_season['clubs']['MIN']['resolved_cycles']), 1)
        loaded.year += 1
        self.assertFalse(IS.decision_resolved(loaded, 1))
        loaded.next_class = loaded.next_class[:-1]
        self.assertFalse(IS.decision_resolved(loaded, 1))

    def test_cpu_rotates_advice_and_keeps_only_latest_verbose_batch(self):
        L, _ = setup(); L.user_team = None
        for week in (2, 4, 6):
            suggested = [s['group'] for s in IS.priorities(L, 'MIN')['suggestions']]
            IS.cross_checks(L, week)
            last = IS.priorities(L, 'MIN')['focus_history'][-1]
            self.assertEqual([last['group1'], last['group2']], suggested)
        self.assertEqual(len(IS.priorities(L, 'MIN')['focus_history']), 3)
        self.assertEqual({r['week'] for r in IS.reports(L, 'MIN')}, {6})


if __name__ == '__main__':
    unittest.main()
