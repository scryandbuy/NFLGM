import copy
import json
import unittest
from types import SimpleNamespace as NS
import game_recap as GR


def drive(q, rows): return NS(start_quarter=q, log=rows)
def play(ty='complete',yards=6,clock=2000,**kw):
    return dict(type=ty,yards=yards,clock=clock,**kw)


class RecapTests(unittest.TestCase):
    def setUp(self):
        self.L=NS(phase="regular", year=2026,week=9,user_team='GB',notes_sent={},inbox=[],
                  teams={'GB':NS(staff={'oc':NS(name='Test Coach')})})
        self.res=dict(home=24,away=17,drives=[
            ('home',drive(1,[play('sack',-6,pressured=True),play('run',8),play(nullified=True,yards=99)])),
            ('away',drive(1,[play('interception',0)])),
            ('home',drive(3,[play(clock=1700),play('run',5,clock=1000)])),
            ('home',drive(5,[play(yards=80,clock=500)]))],
            coaching_review={'pregame':{'changes':{'protection':'six'},'taken':['Keep a back in']},
                'halftime':[{'text':'Quick game','changes':{'protection':'six'},'taken':True}]})

    def test_summary_halves_and_duplicate_after_reload_delete(self):
        m=GR.post(self.L,'GB','MIN',1,self.res)
        self.assertEqual(m['week'],1)
        self.assertIn('Test Coach',m['sender'])
        self.assertIn('Before the adjustment: pressure or sacks on 1/1',m['body'])
        self.assertIn('Results after halftime include overtime',m['body'])
        self.assertIn('Overtime offense:',m['body'])
        self.assertNotIn('99',m['body'])
        self.L.notes_sent=json.loads(json.dumps(self.L.notes_sent)); self.L.inbox=[]
        self.assertIsNone(GR.post(self.L,'GB','MIN',1,self.res))

    def test_away_playoff_and_no_cpu_email(self):
        self.L.user_team='MIN'; self.L.teams['MIN']=NS(staff={})
        m=GR.post(self.L,'GB','MIN',19,self.res,True)
        self.assertIn('Loss, 17–24 against GB',m['body'])
        self.assertIsNone(GR.post(self.L,'CHI','DET',19,self.res,True))

    def test_no_override_and_no_half_acceptance(self):
        self.res['coaching_review']={'pregame':{'changes':{}},'halftime':[]}
        text=GR.post(self.L,'GB','MIN',1,self.res)['body']
        self.assertIn('no pregame overrides',text)
        self.assertIn('No halftime recommendations were accepted',text)

    def test_capture_is_frozen_and_ignores_old_week(self):
        self.L.user_week_plan={'year':2026,'week':1,'changes':{'protection':'six'},'taken':['Protect']}
        st=NS(plan=NS(protection='six'))
        c=GR.capture(self.L,st,1)
        self.L.user_week_plan['taken'].clear(); st.plan.protection='empty'
        self.assertEqual(c['installed']['protection'],'six')
        self.assertEqual(c['taken'],['Protect'])
        self.assertEqual(GR.capture(self.L,st,2)['changes'],{})

    def test_manual_override_is_not_credited_to_replaced_advice(self):
        self.L.user_week_plan=dict(year=2026,week=1,changes={'pass_bias':.06},taken=['Run more'],
                                  manual={'pass_bias':.06},suggestions={'Run more':{'pass_bias':-.06}})
        snap=GR.capture(self.L,NS(plan=NS(pass_bias=.06)),1)
        self.assertEqual(snap['recommendations'][0]['changes'],{})
        review=GR.review_choices(snap['recommendations'],[],[])[0]
        self.assertIn('manual settings replaced',review['conclusion'])
        self.assertEqual(review['findings'],[])

    def test_pressure_counts_sack_once_and_scramble_as_dropback(self):
        s=GR.stats([play('sack',-3,pressured=True),play('scramble',8,is_pass=True)])
        self.assertEqual((s['pressure'],s['passes'],s['runs']),(1,2,0))

    def test_missing_snapshot_does_not_invent_decisions(self):
        self.res.pop('coaching_review')
        self.assertIn('kickoff plan was not recorded',GR.post(self.L,'GB','MIN',1,self.res)['body'])

class RecapJudgmentTests(unittest.TestCase):
    def test_run_deep_protection_and_defense_judgments(self):
        strong = [play('run', 8) for _ in range(8)]
        self.assertEqual(GR.assessment(strong, 'run')[0], 'positive')
        self.assertEqual(GR.assessment(strong, 'run', True)[0], 'negative')
        deep = [play(yards=2, depth='deep') for _ in range(6)]
        self.assertEqual(GR.assessment(deep, 'deep')[0], 'negative')
        pressured = [play('sack', -5, pressured=True) for _ in range(4)] + [play() for _ in range(6)]
        self.assertEqual(GR.assessment(pressured, 'protection')[0], 'negative')
        self.assertEqual(GR.assessment(deep[:2], 'deep')[0], 'limited')
        self.assertEqual(GR.assessment([], 'deep')[0], 'ungraded')

    def test_giveaways_not_hidden_by_explosive_average(self):
        rows = [play(yards=20) for _ in range(8)] + [play('interception', 0)]
        grade, text = GR.assessment(rows, 'passing')
        self.assertEqual(grade, 'mixed'); self.assertIn('lost possessions', text)

    def test_each_advice_has_own_conclusion_and_ot_counts(self):
        L = NS(phase="regular", year=2026, week=2, user_team='GB', notes_sent={}, inbox=[], teams={'GB':NS(staff={})})
        recs = [dict(text='Run it', changes={'pass_bias':-.06}), dict(text='Deep shots', changes={'depth_mix':(-.05,0,.05)})]
        result = dict(home=31, away=24, overtime=True, drives=[
            ('home',drive(1,[play('run',8) for _ in range(6)])),
            ('home',drive(3,[play(yards=2,depth='deep',clock=900) for _ in range(6)])),
            ('home',drive(5,[play('run',10,clock=500) for _ in range(5)]))],
            coaching_review={'pregame':dict(changes={'pass_bias':-.06},recommendations=recs),
                             'halftime':[recs[0]], 'overtime':[recs[0]]})
        msg = GR.post(L,'GB','LAC',2,result)
        sections = {x['title']:x for x in msg['payload']['recap']['sections']}
        self.assertEqual(len(sections['Pregame plan']['reviews']),2)
        self.assertEqual(sections['Pregame plan']['reviews'][0]['findings'][0]['verdict'],'positive')
        self.assertEqual(sections['Pregame plan']['reviews'][1]['findings'][0]['verdict'],'negative')
        self.assertIn('10.0 yards per designed run',sections['Halftime adjustments']['reviews'][0]['findings'][0]['text'])
        self.assertIn('Overtime adjustments',sections)
        self.assertNotIn('not proof of cause', msg['body'])
        self.assertNotIn('exclude overtime',msg['body'])

    def test_play_period_metadata_and_nullified_snaps(self):
        res = dict(drives=[('home',drive(4,[play(clock=0,quarter=5),play(clock=0,quarter=5,nullified=True)]))])
        self.assertEqual(len(GR.plays(res,'home',3)),1)
        self.assertEqual(len(GR.plays(res,'home','after_break')),1)
        self.assertEqual(len(GR.plays(res,'home',2)),0)


class RecapAccountingTests(unittest.TestCase):
    def test_passing_turnover_does_not_downgrade_rushing(self):
        rows = [play('run', 6.8) for _ in range(32)] + [play('sack', -4, is_pass=True, fumble_lost=True)]
        grade, text = GR.assessment(rows, 'run')
        self.assertEqual(grade, 'positive')
        self.assertNotIn('turnover', text)
        self.assertEqual(GR.stats(rows)['turnovers'], 1)

    def test_rushing_turnover_does_not_downgrade_passing_or_protection(self):
        rows = [play(yards=8, is_pass=True) for _ in range(10)] + [play('run', 4, fumble_lost=True)]
        for metric in ('passing', 'protection'):
            self.assertEqual(GR.assessment(rows, metric)[0], 'positive')
        self.assertEqual(GR.assessment([play('run',8) for _ in range(8)] + rows[-1:], 'run')[0], 'mixed')

    def test_halftime_run_verdict_ignores_passing_turnovers_and_deduplicates_rates(self):
        before = [play('run', 6.3) for _ in range(16)]
        after = [play('run', 7.4) for _ in range(16)] + [play('interception',0,is_pass=True)]
        finding = GR.assess_choice({'pass_bias':-.06},after,[],before=(before,[]))[0]
        self.assertEqual(finding['verdict'],'positive')
        self.assertEqual(finding['text'].count('6.3'),1)
        self.assertEqual(finding['text'].count('7.4'),1)
        self.assertIn('16 runs before, 16 after',finding['text'])
        self.assertNotIn('turnover',finding['text'])

    def test_halftime_real_rushing_turnover_still_qualifies_verdict(self):
        before = [play('run', 5) for _ in range(8)]
        after = [play('run', 8) for _ in range(8)]
        after[0]['fumble_lost']=True
        finding=GR.assess_choice({'pass_bias':-.06},after,[],before=(before,[]))[0]
        self.assertEqual(finding['verdict'],'mixed')
        self.assertIn('turnover',finding['text'])

    def test_legacy_fractional_conversion_matches_field_spot(self):
        import game
        import numpy as np
        for gained,need in [(0.7,1),(0.4,1),(9.6,10),(9.4,10),(2.5,3)]:
            dr=game.Drive({}, {}, 44, 1800, 2, 0, np.random.default_rng(1))
            dr.down=3;dr.togo=need
            game._advance(dr,gained)
            self.assertEqual(GR.stats([play('run',gained,down=3,ydstogo=need)])['converted'],
                             int(dr.down==1))

    def test_recorded_field_result_wins_over_fractional_estimate(self):
        rows=[play('run',.4,down=3,ydstogo=1,converted=True),
              play('run',1.2,down=3,ydstogo=1,converted=False)]
        self.assertEqual(GR.stats(rows)['converted'],1)
        self.assertTrue(GR.converted(rows[0]))
        self.assertFalse(GR.converted(rows[1]))

    def test_turnovers_and_wiped_plays_are_not_conversions(self):
        for extra in ({'fumble_lost':True},{'defensive_td':True},{'nullified':True}):
            self.assertEqual(GR.stats([play('run',20,down=3,ydstogo=10,converted=True,**extra)])['converted'],0)
        self.assertEqual(GR.stats([play('run',20,down=3,nullified=True)])['third'],0)


class RecapSimulationTests(unittest.TestCase):
    def test_direct_playoff_game_posts_once_and_saves(self):
        from session import Session
        from season import SeasonRunner
        s=Session.new('GB',seed=27)
        s.L.user_week_plan={'year':s.L.year,'week':19,'changes':{'protection':'six'},'taken':['Keep a back in']}
        runner=SeasonRunner(s.L,s.rng)
        res=runner.play('MIN','GB',19,playoffs=True)
        self.assertIsNotNone(res)
        third_plays=[p for side in ('home','away') for p in GR.plays(res,side) if p.get('down')==3]
        self.assertTrue(third_plays)
        self.assertTrue(all('converted' in p for p in third_plays))
        self.assertEqual(GR.stats(third_plays)['converted'],sum(p['converted'] for p in third_plays))
        reviews=[m for m in s.L.inbox if (m.get('payload') or {}).get('game_key','').startswith('game-recap-')]
        self.assertEqual(len(reviews),1)
        self.assertIn('Keep a back in',reviews[0]['body'])
        restored=Session.load(s.save())
        self.assertIsNone(GR.post(restored.L,'MIN','GB',19,res,True))

if __name__=='__main__': unittest.main()
