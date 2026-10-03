"""Broader tentative background knowledge, without extra football certainty."""
import copy
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import character_assessment as CA
import inseason_scouting as IS
import scouting as SC
import spring as SP
import staff as ST
from league import League
from test_inseason_scouting import setup


class AreaBackgroundTests(unittest.TestCase):
    def test_area_report_is_limited_and_does_not_touch_football_or_medical(self):
        L, _ = setup(); p = L.next_class[0]; view = L.scouting['MIN'][p.pid]
        before = copy.deepcopy(view); truth = copy.deepcopy(p.to_dict())
        self.assertTrue(CA.area_report(p, 'MIN', view, {'character': 'sharp'}, 1.))
        report = CA.report(view)[0]
        self.assertEqual(report['confidence'], 'Limited')
        self.assertEqual(report['source'], 'Area background report')
        self.assertIn('Tentative', report['explanation'])
        for key in before:
            if key != 'character_assessments': self.assertEqual(view[key], before[key])
        after = p.to_dict(); after.pop('xp_spent'); truth.pop('xp_spent')
        self.assertEqual(after, truth)

    def test_area_cannot_replace_better_knowledge_or_legacy_or_tape_policy(self):
        L, _ = setup(); p = L.next_class[0]
        tape = {}
        self.assertFalse(CA.area_report(p, 'MIN', tape, {'character': 'none'}, .9))
        self.assertEqual(tape, {})
        for v in ({'character_read': 20, 'flags': ['character'], 'adj': -2}, {}):
            if not v: CA.visit(p, 'MIN', v, {'character': 'normal'}, 4.)
            original = copy.deepcopy(v)
            self.assertFalse(CA.area_report(p, 'MIN', v, {'character': 'normal'}, .9))
            self.assertEqual(v, original)

    def test_repeated_area_read_cannot_reroll_and_visit_can_improve_it(self):
        L, _ = setup(); p = L.next_class[0]; view = {}
        CA.area_report(p, 'MIN', view, {'character': 'normal'}, .2)
        saved = copy.deepcopy(view)
        self.assertFalse(CA.area_report(p, 'MIN', view, {'character': 'normal'}, 1.))
        self.assertEqual(view, saved)
        self.assertTrue(CA.visit(p, 'MIN', view, {'character': 'normal'}, 4.))
        self.assertLess(CA.assessments(view)['work_ethic']['error'], CA.assessments(saved)['work_ethic']['error'])

    def test_whole_cycle_adds_background_without_extra_football_or_report_rows(self):
        L, _ = setup(); baseline = copy.deepcopy(L)
        with patch.object(IS, '_area_background', return_value=0):
            old_rows = IS.cross_checks(baseline, 2)
        new_rows = IS.cross_checks(L, 2)
        self.assertEqual(new_rows, old_rows)
        self.assertGreater(IS.background_coverage(L, 'MIN')['assessed'], IS.background_coverage(baseline, 'MIN')['assessed'])
        self.assertEqual(L.consensus, baseline.consensus)
        for pid, v in L.scouting['MIN'].items():
            self.assertEqual({k: val for k, val in v.items() if k != 'character_assessments'},
                             {k: val for k, val in baseline.scouting['MIN'][pid].items() if k != 'character_assessments'})
        loaded = League.load(L.save()); loaded.user_team = 'MIN'
        self.assertEqual(IS.cross_checks(loaded, 2), {})
        self.assertEqual(IS.background_coverage(loaded, 'MIN'), IS.background_coverage(L, 'MIN'))
        self.assertEqual(IS.cross_checks(loaded, 4), IS.cross_checks(L, 4))

    def test_coverage_getter_is_safe_read_only_and_quality_buys_breadth(self):
        L, _ = setup(); strong = copy.deepcopy(L)
        before = copy.deepcopy(L.to_dict())
        self.assertEqual(IS.background_coverage(L, 'MIN')['assessed'], 0)
        self.assertEqual(before, L.to_dict())
        with patch.object(SC, 'scout_q', return_value=0.): IS.cross_checks(L, 2)
        with patch.object(SC, 'scout_q', return_value=1.): IS.cross_checks(strong, 2)
        self.assertGreater(IS.background_coverage(strong, 'MIN')['assessed'], IS.background_coverage(L, 'MIN')['assessed'])


def measure(output):
    """Optional real-class paired coverage/runtime/save-size experiment."""
    from session import Session
    session = Session.new('GB', seed=274)
    session.L.set_phase('regular')
    base = session.L; base.user_team = None
    live_rng = copy.deepcopy(session.rng.bit_generator.state)
    result = {'seed': 274, 'prospects': len(base.next_class), 'teams': len(base.teams), 'cohorts': {}}

    def coverage(L):
        all_rows = [IS.background_coverage(L, a) for a in L.teams]
        regular = [IS.background_coverage(L, a) for a, t in L.teams.items() if SC.room(t)['character'] != 'none']
        fractions = [r['assessed'] / max(1, r['total']) for r in regular]
        return dict(non_tape_rooms=len(regular), all_room_share=sum(r['assessed'] for r in all_rows)/sum(r['total'] for r in all_rows),
                    non_tape_share=sum(r['assessed'] for r in regular)/sum(r['total'] for r in regular),
                    non_tape_p10_p50_p90=[round(float(x), 4) for x in np.quantile(fractions, [.1, .5, .9])],
                    limited_share_of_assessed=sum(r['limited'] for r in regular)/max(1,sum(r['assessed'] for r in regular)))

    for label, q in (('weak', .2), ('average', .5), ('strong', .85)):
        paired = {}
        leagues = {}
        for mode in ('baseline', 'area_reports'):
            L = copy.deepcopy(base)
            with patch.object(ST, 'scout_quality', return_value=q):
                SC.scout(L, np.random.default_rng(374))
                started = time.perf_counter()
                if mode == 'baseline':
                    with patch.object(IS, '_area_background', return_value=0):
                        for week in range(2,19,2): IS.cross_checks(L, week)
                else:
                    real_area = IS._area_background
                    area_seconds = 0.; area_count = 0
                    def timed_area(*args, **kwargs):
                        nonlocal area_seconds, area_count
                        tick = time.perf_counter()
                        count = real_area(*args, **kwargs)
                        area_seconds += time.perf_counter() - tick
                        area_count += count
                        return count
                    with patch.object(IS, '_area_background', side_effect=timed_area):
                        for week in range(2,19,2): IS.cross_checks(L, week)
                seconds = time.perf_counter() - started
                paired[mode] = dict(end_season=coverage(L), seconds_9_cycles=seconds,
                                    serialized_bytes=len(L.save().encode('utf-8')))
                if mode == 'area_reports':
                    paired[mode].update(area_seconds_9_cycles=area_seconds, area_count=area_count)
                leagues[mode] = L
        # Area work must not move one football grade/ceiling/certainty/consensus.
        self_check = True
        for a, room in leagues['baseline'].scouting.items():
            for pid, v in room.items():
                other = leagues['area_reports'].scouting[a][pid]
                if {k:x for k,x in v.items() if k != 'character_assessments'} != {k:x for k,x in other.items() if k != 'character_assessments'}:
                    self_check = False
        assert self_check
        assert leagues['baseline'].consensus == leagues['area_reports'].consensus
        for mode, L in leagues.items():
            with patch.object(ST, 'scout_quality', return_value=q):
                rng = np.random.default_rng(474)
                SC.senior_bowl(L, rng, event_year=L.year + 1)
                L.year += 1; L.draft_pool = L.next_class; L.next_class = []
                SP.combine(L, rng); SP.pro_days(L, rng); SP.visits(L, rng)
                paired[mode]['at_draft'] = coverage(L)
        paired['football_reads_identical'] = True
        result['cohorts'][label] = paired
        print(label, json.dumps(paired), flush=True)
    assert session.rng.bit_generator.state == live_rng
    result['live_rng_unchanged'] = True
    Path(output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    unittest.main()
