import unittest
import game_recap as G

class ContextTests(unittest.TestCase):
    def test_productive_passing_one_turnover(self):
        rows=[dict(type='complete',yards=10)]*29+[dict(type='interception',yards=0)]
        self.assertEqual(G.assessment(rows,'passing')[0],'positive')
        self.assertIn('1 turnover',G.assessment(rows,'passing')[1])

    def test_takeaways_and_scores_survive_highlight_limit(self):
        own=G.stats([dict(type='run',yards=7,down=3,ydstogo=1)]*15)
        against=G.stats([dict(type='interception',yards=0,defensive_td=i<2) for i in range(4)])
        good,_=G.strengths(own,against)
        self.assertIn('4 times',good[0]); self.assertIn('2 defensive touchdowns',good[0])

    def test_olave_containment_with_one_touchdown(self):
        rows=[dict(type='complete',target='WR',yards=60/7,touchdown=i==0) for i in range(7)]
        rows += [dict(type='incomplete',target='WR',yards=0)]*5
        verdict,text=G.receiver_assessment(rows,'WR','Olave')
        self.assertEqual(verdict,'positive');self.assertIn('touchdown conceded',text)
        self.assertNotIn('1 receiving touchdowns',text)

    def test_coverage_keeps_takeaways_visible(self):
        rows=[dict(type='complete',yards=6)]*56+[dict(type='interception',yards=0)]*4
        verdict,text=G.assessment(rows,'passing',True)
        self.assertEqual(verdict,'positive');self.assertIn('4 takeaways',text)

    def test_concise_email_drops_repeated_numeric_detail(self):
        result=G.concise_finding(dict(label='Passing depth',verdict='limited',text='Long numeric breakdown'))
        self.assertEqual(result['text'],'Too few relevant plays to judge.')
        result=G.concise_finding(dict(label='Clock control',verdict='positive',text='Detailed timing evidence'))
        self.assertIn('protected the win',result['text'])

    def test_blitz_pressure_is_not_graded_by_run_yards(self):
        rows=[dict(type='run',yards=20,blitz=True)]*10
        rows += [dict(type='complete',yards=3,blitz=True,pressured=False)]*5
        findings=G.assess_choice({'blitz_lean':1},[],rows)
        self.assertEqual(len(findings),2)
        pressure=next(f for f in findings if f['label']=='Pass-rush pressure')
        cost=next(f for f in findings if f['label']=='Pressure calls')
        self.assertEqual(pressure['verdict'],'limited')
        self.assertEqual(cost['verdict'],'negative')
