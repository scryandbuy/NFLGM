"""Development evidence must distinguish quality, workload, and missing data."""
import copy
import math
import unittest
from types import SimpleNamespace

from dev_evaluation import assessment


def grade(pos, **line):
    return assessment(SimpleNamespace(pos=pos), line)


def scale(line, factor):
    return {key: value * factor for key, value in line.items()}


class DevelopmentEvidence(unittest.TestCase):
    def test_better_full_time_lineman_beats_weaker_part_timer(self):
        starter = grade('LT', snaps=1000, pb_snaps=600, pb_wins=570,
                        rb_snaps=400, rb_wins=280, sacks_allowed=3, pressures_allowed=15)
        backup = grade('LT', snaps=400, pb_snaps=240, pb_wins=192,
                       rb_snaps=160, rb_wins=80, sacks_allowed=4, pressures_allowed=16)
        self.assertGreater(starter['score'], backup['score'])
        self.assertTrue(starter['credible'])
        self.assertFalse(backup['credible'])

    def test_blocking_efficiency_is_not_divided_by_volume_twice(self):
        line = dict(snaps=400, pb_snaps=240, pb_wins=204, rb_snaps=160,
                    rb_wins=96, sacks_allowed=2, pressures_allowed=12)
        a, b = grade('RG', **line), grade('LG', **scale(line, 2))
        self.assertAlmostEqual(a['score'], b['score'])
        self.assertEqual(a['group'], b['group'])
        self.assertGreater(b['confidence'], a['confidence'])
        self.assertEqual(a['score'], grade('RG', **dict(line, snaps=9999))['score'])

    def test_no_blocking_evidence_is_not_a_bad_grade(self):
        self.assertIsNone(grade('LT', snaps=1000))
        self.assertIsNone(grade('C', pb_snaps=50, pb_wins=50))
        one_phase = grade('RT', pb_snaps=700, pb_wins=665)
        self.assertFalse(one_phase['credible'])
        self.assertLess(one_phase['confidence'], .75)
        self.assertNotEqual(one_phase['group'], grade('RT', pb_snaps=500, rb_snaps=300)['group'])

    def test_coverage_deflections_matter_at_equal_exposure(self):
        low = grade('CB', def_plays=800, tackles=35, pass_def=3, int_def=2)
        high = grade('CB', def_plays=800, tackles=35, pass_def=16, int_def=2)
        self.assertGreater(high['score'], low['score'])

    def test_coverage_proxy_cannot_demote_quiet_shutdown_corner(self):
        for pos in ('CB', 'FS', 'SS'):
            quiet = grade(pos, def_plays=1000, pass_def=0, int_def=0)
            self.assertFalse(quiet['credible'])
            self.assertLess(quiet['confidence'], .75)
            self.assertIn('No individual coverage', quiet['reason'])

    def test_shared_team_epa_is_not_individual_coverage_quality(self):
        a = grade('CB', def_plays=700, pass_def=10, def_epa=300)
        b = grade('CB', def_plays=700, pass_def=10, def_epa=-300)
        self.assertEqual(a, b)

    def test_coverage_rate_and_sample_are_separate(self):
        line = dict(def_plays=200, pass_def=4, int_def=1, tackles=12)
        a, b = grade('CB', **line), grade('CB', **scale(line, 4))
        self.assertAlmostEqual(a['score'], b['score'])
        self.assertGreater(b['confidence'], a['confidence'])
        self.assertIsNone(grade('CB', def_plays=10, int_def=2))

    def test_defensive_exposure_does_not_double_count_total_snaps(self):
        line = dict(def_plays=600, tackles=65, sacks=3, pressures=15)
        self.assertEqual(grade('MIKE', **line), grade('MIKE', **dict(line, snaps=1200)))

    def test_rush_efficiency_applies_to_rushers_and_uses_actual_reps(self):
        line = dict(def_plays=600, pr_reps=300, pr_wins=30, pressures=20, sacks=6)
        for pos in ('LEDG', 'REDG', 'DT'):
            a = grade(pos, **line)
            b = grade(pos, **dict(line, pr_wins=75))
            self.assertGreater(b['score'], a['score'])
            self.assertTrue(a['credible'])
        a = grade('WILL', **line)
        b = grade('WILL', **dict(line, pr_wins=75))
        self.assertEqual(a['score'], b['score'])
        self.assertFalse(grade('DT', def_plays=600, sacks=4)['credible'])

    def test_qb_epa_counts_scrambles_once(self):
        line = dict(pass_att=380, pass_plays=450, pass_epa=90,
                    rush_plays=30, rush_epa=15, rush_att=70)
        a = grade('QB', **line)
        self.assertEqual(a['opportunities'], 480)
        self.assertAlmostEqual(a['score'], 100 * 105 / 480)
        self.assertTrue(a['credible'])
        b = grade('QB', **scale(line, .5))
        self.assertAlmostEqual(a['score'], b['score'])
        self.assertFalse(b['credible'])

    def test_qb_fallback_is_not_compared_to_epa_units(self):
        line = dict(pass_att=400, pass_yds=3000, pass_td=22, ints=10, sacked=30)
        legacy = grade('QB', **line)
        modern = grade('QB', **dict(line, pass_plays=430, pass_epa=40))
        self.assertNotEqual(legacy['group'], modern['group'])
        self.assertIsNone(grade('QB', pass_att=8, pass_plays=8, pass_epa=20))

    def test_skill_injured_half_season_keeps_rate_but_not_confidence(self):
        line = dict(snaps=700, tgt=100, rec=65, rec_yds=950, rec_td=8)
        full, half = grade('WR', **line), grade('WR', **scale(line, .5))
        self.assertAlmostEqual(full['score'], half['score'])
        self.assertTrue(full['credible'])
        self.assertFalse(half['credible'])
        self.assertLess(grade('WR', **dict(line, fumbles_lost=5))['score'], full['score'])

    def test_empty_blocking_te_box_score_does_not_mean_poor_receiver(self):
        self.assertIsNone(grade('TE', snaps=700, tgt=4, rec=3, rec_yds=12))

    def test_blocking_heavy_te_cannot_be_demoted_by_receiving_grade(self):
        line = dict(snaps=700, tgt=60, rec=40, rec_yds=400, rec_td=3)
        receiving = grade('TE', **line)
        blocker = grade('TE', **dict(line, pb_snaps=200, pb_wins=190))
        self.assertTrue(receiving['credible'])
        self.assertFalse(blocker['credible'])
        self.assertLess(blocker['confidence'], .75)
        self.assertIn('Blocking-heavy', blocker['reason'])

    def test_fb_is_graded_on_recorded_blocking_not_just_carries(self):
        good = grade('FB', pb_snaps=100, pb_wins=95, rb_snaps=100, rb_wins=80,
                     rush_att=4, rush_yds=8)
        poor = grade('FB', pb_snaps=100, pb_wins=60, rb_snaps=100, rb_wins=40,
                     sacks_allowed=4, pressures_allowed=20, rush_att=4, rush_yds=8)
        self.assertGreater(good['score'], poor['score'])
        self.assertTrue(good['credible'])

    def test_fb_missing_lead_blocking_evidence_is_not_credible(self):
        self.assertIsNone(grade('FB', snaps=500, rush_att=4, rush_yds=8))
        proxy = grade('FB', snaps=500, pb_snaps=150, pb_wins=140, rush_att=10)
        self.assertLess(proxy['confidence'], .75)
        self.assertFalse(proxy['credible'])

    def test_kicker_is_graded_without_scrimmage_snap_floor(self):
        good = grade('K', fg_att=30, fg_made=28, xp_att=40, xp_made=39)
        poor = grade('K', fg_att=30, fg_made=20, xp_att=40, xp_made=35)
        self.assertTrue(good['credible'])
        self.assertGreater(good['score'], poor['score'])
        self.assertEqual(good, grade('K', snaps=0, fg_att=30, fg_made=28, xp_att=40, xp_made=39))

    def test_kicker_short_sample_perfection_is_not_full_season_evidence(self):
        self.assertIsNone(grade('K', fg_att=1, fg_made=1, fg_long=65))
        self.assertIsNone(grade('K', xp_att=60, xp_made=60))
        a = grade('K', fg_att=10, fg_made=10, xp_att=10, xp_made=10)
        b = grade('K', fg_att=30, fg_made=30, xp_att=30, xp_made=30)
        self.assertEqual(a['score'], b['score'])
        self.assertFalse(a['credible'])
        self.assertTrue(b['credible'])

    def test_punter_uses_net_and_placement_without_scrimmage_snaps(self):
        a = grade('P', punts=60, punt_net_yds=2400, punt_in20=24, punt_tb=3)
        b = grade('P', punts=60, punt_net_yds=2040, punt_in20=12, punt_tb=9)
        self.assertTrue(a['credible'])
        self.assertGreater(a['score'], b['score'])
        self.assertLess(grade('P', punts=60, punt_net_yds=2400, punt_in20=24, punt_tb=12)['score'], a['score'])

    def test_punter_short_season_changes_confidence_not_rate(self):
        line = dict(punts=60, punt_net_yds=2400, punt_in20=24, punt_tb=6)
        a, b = grade('P', **line), grade('P', **scale(line, .25))
        self.assertEqual(a['score'], b['score'])
        self.assertFalse(b['credible'])
        self.assertIsNone(grade('P', punts=1, punt_net_yds=65))
        self.assertIsNone(grade('P', punts=60, punt_yds=3000))

    def test_ls_and_unknown_positions_are_ungraded(self):
        self.assertIsNone(grade('LS', snaps=300, fg_att=30, fg_made=30))
        self.assertIsNone(grade('UNKNOWN', snaps=1000))

    def test_inputs_are_unchanged_and_results_finite(self):
        line = dict(punts=50, punt_net_yds=2000, punt_in20=None, punt_tb=float('inf'))
        original = copy.deepcopy(line)
        result = assessment(SimpleNamespace(pos='P'), line)
        self.assertEqual(original, line)
        self.assertTrue(math.isfinite(result['score']))
        self.assertEqual(result['score'], 40)
        self.assertIsNone(grade('LT', pb_snaps=float('nan'), rb_snaps='bad'))


if __name__ == '__main__':
    unittest.main()
