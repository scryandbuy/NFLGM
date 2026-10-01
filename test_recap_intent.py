import unittest
from types import SimpleNamespace as NS
import game_recap as R
import ticker
from test_game_recap import play, drive


class RecapIntentTests(unittest.TestCase):
    def test_nullification_wins_over_fumble_score_and_safety(self):
        for extras in (dict(fumble=True, fumble_lost=True),
                       dict(fumble=True, fumble_lost=True, defensive_td=True),
                       dict(safety=True)):
            p = play(yards=14, nullified=True, **extras)
            line = ticker.play_line(NS(player=lambda pid: None), p, 'CHI', 'GB')
            self.assertEqual(line['kind'], 'neutral')
            self.assertTrue(line['text'].endswith('Play nullified by penalty.'))

    def test_pregame_blitz_uses_defense_and_actual_pressure(self):
        against = [play(yards=2, blitz=True, pressured=i < 5) for i in range(10)]
        findings = R.assess_choice({'blitz_rate': .05}, [play(yards=30)] * 20, against)
        self.assertEqual([f['label'] for f in findings], ['Pressure calls', 'Pass-rush pressure'])
        self.assertIn('2.0 yards per play', findings[0]['text'])
        self.assertIn('5/10', findings[1]['text'])
        self.assertIn('blitzing', R.choices({'blitz_rate': .05}))
        self.assertNotIn('30.0', str(findings))

    def test_unknown_setting_is_not_graded_from_offensive_yardage(self):
        result = R.assess_choice({'unknown_setting': 1}, [play(yards=30)] * 10, [])
        self.assertEqual(result[0]['verdict'], 'ungraded')

    def test_one_deep_play_does_not_make_whole_recommendation_positive(self):
        rows = [play(yards=73.8, depth='deep')] + [play(yards=5)] * 27
        rec = dict(text='Attack corners', changes={'pass_bias': .05, 'depth_mix': (-.1, 0, .1)})
        result = R.review_choices([rec], rows, [])[0]
        self.assertIn('not enough evidence', result['conclusion'])
        self.assertIn('1 play.', result['findings'][1]['text'])

    def test_small_comparison_and_unchanged_productivity_do_not_claim_payoff(self):
        rec = {'play_action_rate': .05}
        result = R.assess_choice(rec, [play(yards=9.4, play_action=True)] * 6, [],
                                before=([play(yards=7.2, play_action=True)] * 4, []))[0]
        self.assertEqual(result['verdict'], 'limited')
        unchanged = R.assess_choice({'pass_bias': .05}, [play(yards=9.8)] * 18, [],
                                   before=([play(yards=9.5)] * 25, []))[0]
        self.assertIn('No meaningful change', unchanged['text'])
        self.assertNotIn('Paid off', unchanged['text'])

    def test_reported_clock_control_cases_ignore_ypc_decline(self):
        for old_runs, old_snaps, old_ypc, runs, snaps, ypc, margin in (
                (16, 29, 7, 30, 38, 6.1, 31), (22, 40, 5.5, 26, 36, 5.6, 20)):
            first = [play('run', old_ypc)] * old_runs + [play()] * (old_snaps-old_runs)
            after = [play('run', ypc, score_diff=21, snap_interval=40)] * runs
            after += [play(score_diff=21, snap_interval=37)] * (snaps-runs)
            rec = dict(text='Up two scores: shorten the game, run it', review_key='clock_control',
                       changes={'tempo': -.2, 'pass_bias': -.05, 'heavy_lean': .3})
            result = R.review_choices([rec], after, [], (first, []), final_margin=margin)[0]
            self.assertEqual(len(result['findings']), 1)
            self.assertEqual(result['findings'][0]['verdict'], 'positive')
            self.assertIn('protected the win', result['findings'][0]['text'])

    def test_clock_control_is_not_auto_success_for_a_win(self):
        rows = [play('run', 1, score_diff=14, snap_interval=20)] * 10
        self.assertEqual(R.clock_control_finding(rows, [], 14)['verdict'], 'mixed')
        self.assertEqual(R.clock_control_finding(rows, [], -3)['verdict'], 'negative')
        rows = [play('run', 6, score_diff=14, snap_interval=40)] * 10
        rows[0] = dict(rows[0], fumble_lost=True)
        self.assertEqual(R.clock_control_finding(rows, [], 14)['verdict'], 'mixed')
        self.assertEqual(R.clock_control_finding([play('run',6)] * 10, [], 14)['verdict'], 'limited')

    def test_tempo_measures_intervals_not_rushing(self):
        old = [play('run', 7, snap_interval=32)] * 10
        now = [play('run', 6.1, snap_interval=40)] * 10
        rows = R.assess_choice({'tempo': -.2, 'pass_bias': -.05}, now, [], (old, []))
        tempo = next(x for x in rows if x['label'] == 'Tempo')
        self.assertEqual(tempo['verdict'], 'positive')
        self.assertNotIn('yards', tempo['text'])

    def test_pace_does_not_cross_stoppages_and_does_not_mutate_game(self):
        rows = [play('run', 4, clock=1700), play('run', 4, clock=1660),
                dict(type='timeout', clock=1654), play(clock=1654),
                dict(type='period', quarter=4, clock=900), play(clock=900)]
        d = drive(3, rows); d.score_diff = 21
        result = R.plays(dict(drives=[('home', d)]), 'home', 2)
        self.assertEqual(R.pace(result), (1, 40))
        self.assertNotIn('snap_interval', rows[0])
        self.assertEqual(result[0]['score_diff'], 21)

    def test_blitz_opportunity_uses_only_passes_against_blitz(self):
        rec = dict(text='Throw into it', review_key='blitz_opportunity', changes={'depth_mix':(-.03,.03,0)})
        rows = [play(yards=2, blitz=True)] * 10 + [play(yards=30)] * 20
        result = R.review_choices([rec], rows, [])[0]
        self.assertIn('2.0 net yards per dropback', result['findings'][0]['text'])
        self.assertEqual(result['findings'][0]['verdict'], 'negative')

    def test_puka_is_contained_despite_one_explosive(self):
        rows = [play(yards=y, target='puka') for y in (20, 8, 8, 7, 5, 5, 5)]
        rows += [play('incomplete', 0, target='puka')] * 5
        grade, text = R.receiver_assessment(rows, 'puka', 'Puka Nacua')
        self.assertEqual(grade, 'positive')
        self.assertIn('one explosive allowed', text)
        self.assertIn('1 catch of 20+', text)


if __name__ == '__main__':
    unittest.main()
