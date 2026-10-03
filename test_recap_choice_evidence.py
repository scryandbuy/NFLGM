import unittest
from types import SimpleNamespace as NS
import game_recap as GR
from test_game_recap import play, drive


class RecapChoiceEvidence(unittest.TestCase):
    def test_protection_is_not_downgraded_by_clean_pocket_interceptions(self):
        rows = [play(yards=8) for _ in range(38)] + [play('sack', -5)] * 2
        rows += [play('interception', 0)] * 2
        grade, text = GR.assessment(rows, 'protection')
        self.assertEqual(grade, 'positive')
        self.assertIn('2/42 dropbacks', text)
        self.assertNotIn('turnover', text)
        self.assertNotIn('productive yardage', text)

    def test_less_play_action_reports_usage_and_separate_outcomes(self):
        rows = [play(yards=10, play_action=True)] * 3 + [play(yards=2, play_action=False)] * 9
        result = GR.assess_choice({'play_action_rate': -.1}, rows, [])[0]
        self.assertIn('3/12 plays (25%)', result['text'])
        self.assertIn('10.0 net yards per dropback (3 dropbacks)', result['text'])
        self.assertIn('2.0 net yards per dropback (9 dropbacks)', result['text'])
        self.assertEqual(result['verdict'], 'limited')

    def test_shorter_mix_has_depth_specific_evidence(self):
        rows = [play(yards=3, depth='short')] * 6 + [play(yards=12, depth='medium')] * 3
        rows += [play(yards=25, depth='deep')]
        result = GR.assess_choice({'depth_mix': (.1, 0, -.1)}, rows, [])[0]
        self.assertIn('Short: 6/10 (60%)', result['text'])
        self.assertIn('Intermediate: 3/10 (30%)', result['text'])
        self.assertIn('Deep: 1/10 (10%)', result['text'])
        self.assertEqual(result['verdict'], 'limited')

    def test_personnel_separate_from_coverage_and_legacy_unknown(self):
        previous = [play(def_personnel='base')] * 8 + [play(def_personnel='nickel')] * 2
        after = [play(def_personnel='dime')] * 8 + [play(def_personnel='base')] * 2
        findings = GR.assess_choice({'sub_lean': .2, 'man_rate': -.1}, [], after, ([], previous))
        personnel = next(f for f in findings if f['label'] == 'Defensive personnel')
        self.assertIn('8/10 plays (80%)', personnel['text'])
        self.assertIn('2/10 (20%)', personnel['text'])
        self.assertIn('requested direction', personnel['text'])
        legacy = GR.assess_choice({'sub_lean': .2}, [], [play()] * 10)[0]
        self.assertEqual(legacy['verdict'], 'ungraded')

    def test_drive_records_defensive_package_for_recap(self):
        from test_game_clock_decisions import ClockDecisions
        fixture = ClockDecisions()
        fixture.setUp()
        for live in (False, True):
            dr, _, _ = fixture.drive([dict(type='run', yards=1)],
                                     start=99, clock=1804, live=live)
            snap = next(p for p in dr.log if p['type'] == 'run')
            self.assertEqual(snap['def_personnel'], 'nickel')

    def test_positive_summary_does_not_claim_causation(self):
        self.assertIn('do not establish', GR.conclusion([{'verdict': 'positive'}]))

    def test_receiver_review_ignores_yards_to_everyone_else(self):
        lamb = [play(yards=5, target='lamb') for _ in range(4)]
        other = [play(yards=25, target='other', travelled=True) for _ in range(42)]
        league = NS(player=lambda pid: NS(name='CeeDee Lamb') if pid == 'lamb' else None)
        result = GR.assess_choice({'travel':True, 'bracket':'lamb'}, [], lamb + other, league=league)[0]
        self.assertEqual(result['verdict'], 'positive')
        self.assertIn('CeeDee Lamb: 4 catches on 4 targets for 20 yards', result['text'])
        self.assertNotIn('yards per play', result['text'])
        self.assertNotIn('46 plays', result['text'])

    def test_receiver_touchdowns_and_explosives_are_not_hidden(self):
        rows = [play(yards=25, target='lamb', touchdown=True) for _ in range(2)]
        rows += [play('incomplete', 0, target='lamb') for _ in range(4)]
        rows += [play(yards=99, target='lamb', nullified=True)]
        result = GR.assess_choice({'bracket':'lamb'}, [], rows)[0]
        self.assertEqual(result['verdict'], 'negative')
        self.assertIn('2 catches on 6 targets for 50 yards', result['text'])
        self.assertIn('2 receiving touchdowns; 2 catches of 20+ yards', result['text'])

    def test_no_receiver_id_never_falls_back_to_team_yards(self):
        result = GR.assess_choice({'travel':True}, [], [play(yards=30, travelled=True)] * 20)[0]
        self.assertEqual(result['verdict'], 'ungraded')
        zero = GR.assess_choice({'bracket':'lamb'}, [], [play(target='other')] * 20)[0]
        self.assertEqual(zero['verdict'], 'limited')
        self.assertIn('0 catches on 0 targets', zero['text'])

    def test_shadow_and_bracket_same_receiver_are_one_finding(self):
        self.assertEqual(len(GR.assess_choice({'travel_target':'lamb','bracket':'lamb'}, [], [])), 1)

    def test_reported_run_defense_improvement_is_a_success(self):
        before = [play('run', 5.7) for _ in range(13)]
        after = [play('run', 4.5) for _ in range(11)]
        result = GR.assess_choice({'box_bias':.06}, [], after, before=([], before))[0]
        self.assertEqual(result['verdict'], 'positive')
        self.assertIn('5.7 → 4.5 yards per designed run', result['text'])
        self.assertIn('(13 runs before, 11 after)', result['text'])
        self.assertEqual(result['text'].count('5.7'), 1)
        self.assertEqual(result['text'].count('4.5'), 1)
        self.assertNotIn('problem persisted', result['text'])
        self.assertNotIn('Did not hold up', result['text'])

    def test_tiny_improvement_does_not_claim_halftime_success(self):
        result = GR.assess_choice({'box_bias':.06}, [], [play('run',5.6)] * 10,
                                  before=([], [play('run',5.7)] * 10))[0]
        self.assertEqual(result['verdict'], 'negative')
        self.assertIn('No meaningful change', result['text'])

    def test_worsening_is_negative_even_if_absolute_grade_remains_good(self):
        result = GR.assess_choice({'box_bias':.06}, [], [play('run',3.4)] * 10,
                                  before=([], [play('run',2)] * 10))[0]
        self.assertEqual(result['verdict'], 'negative')
        self.assertIn('Worsened', result['text'])

    def test_small_before_sample_is_not_a_comparison_verdict(self):
        result = GR.assess_choice({'box_bias':.06}, [], [play('run',4.5)] * 10,
                                  before=([], [play('run',20)]))[0]
        self.assertIn('Too little before/after evidence', result['text'])
        self.assertNotIn('Improved after halftime', result['text'])

    def test_declined_protection_and_four_sacks_is_worth_mentioning(self):
        rec = dict(text='Keep a back in',changes={'protection':'six'})
        first = [play('sack',-5)] * 2 + [play(pressured=True)] * 8 + [play()] * 10
        second = [play('sack',-5)] * 4 + [play()] * 12
        items = GR.declined_reviews([rec], second, [], (first, []))
        self.assertEqual(len(items),1)
        self.assertIn('4 sacks after halftime on 16 dropbacks', items[0]['findings'][0]['text'])
        self.assertIn('left this recommendation off',items[0]['conclusion'])

    def test_minor_rejected_advice_results_stay_out(self):
        rec = dict(text='Keep a back in',changes={'protection':'six'})
        self.assertEqual(GR.declined_reviews([rec], [play('sack',-5)] + [play()] * 15, [], ([], [])), [])
        self.assertEqual(GR.declined_reviews([rec], [play('sack',-5)] * 4, [], ([], [])), [])

    def test_already_used_or_equivalent_accepted_protection_is_not_blamed(self):
        rec = dict(text='Keep a back in',changes={'protection':'six'})
        rows = [play('sack',-5)] * 4 + [play()] * 12
        self.assertEqual(GR.declined_reviews([rec], rows, [], ([], []), accepted=[rec]), [])
        self.assertEqual(GR.declined_reviews([rec], rows, [], ([], []), installed={'protection':'six'}), [])

    def test_declined_run_adjustment_not_blamed_when_results_improved(self):
        rec = dict(text='Load the box',changes={'box_bias':.06})
        self.assertEqual(GR.declined_reviews([rec], [], [play('run',4.5)] * 11,
                                             ([], [play('run',5.7)] * 13)), [])

    def test_post_renders_meaningful_declined_advice_separately(self):
        L = NS(phase="regular", year=2026, week=2, user_team='GB', notes_sent={}, inbox=[], teams={'GB':NS(staff={})})
        rec = dict(text='Keep a back in',changes={'protection':'six'},taken=False)
        result = dict(home=17,away=24,drives=[
            ('home',drive(1,[play('sack',-5)] * 3 + [play()] * 10)),
            ('home',drive(3,[play('sack',-5,clock=900)] * 4 + [play(clock=900)] * 12))],
            coaching_review={'pregame':{'changes':{}},'halftime':[], 'halftime_declined':[rec]})
        msg = GR.post(L,'GB','DAL',2,result)
        sections = {s['title']:s for s in msg['payload']['recap']['sections']}
        self.assertEqual(len(sections['Halftime advice not taken']['reviews']),1)
        self.assertIn('4 sacks after halftime',msg['body'])

    def test_rejected_deep_ball_advice_uses_deep_throws_only(self):
        rec = dict(text='Take away the deep ball', changes={'shell_lean':.1})
        short = [play(yards=20,depth='short',air=5)] * 20
        self.assertEqual(GR.declined_reviews([rec], [], short, ([], short)), [])
        deep = [play(yards=30,depth='deep',air=25)] * 3 + [play('incomplete',0,depth='deep',air=25)]
        result = GR.declined_reviews([rec], [], short + deep, ([], deep))
        self.assertIn('3 of 4 deep throws for 90 yards', result[0]['findings'][0]['text'])

    def test_rejected_screen_advice_needs_repeated_failure(self):
        rec = dict(text='Shelve screens',changes={'screen_boost':-.05})
        self.assertEqual(GR.declined_reviews([rec], [play(yards=0,screen=True)] * 2, [], ([], [])), [])
        result = GR.declined_reviews([rec], [play(yards=0,screen=True)] * 6, [], ([], []))
        self.assertEqual(len(result),1)

    def test_declined_snapshot_is_separate_and_frozen(self):
        from season import SeasonRunner
        runner = SeasonRunner.__new__(SeasonRunner)
        rec = dict(text='Keep a back in',changes={'protection':'six'},taken=False)
        result = dict(home=17,away=24)
        runner.live = dict(res=result,home='GB',away='DAL',week=19,start={},half_recs=[rec],
                           ot_recs=[],playoffs=True,book=None,half_plan_before={'protection':'empty'})
        runner.last_games=[]
        runner._record=lambda *a: None
        runner._close_live()
        self.assertEqual(result['coaching_review']['halftime'],[])
        rec['changes']['protection']='empty'
        self.assertEqual(result['coaching_review']['halftime_declined'][0]['changes']['protection'],'six')


if __name__ == '__main__':
    unittest.main()
