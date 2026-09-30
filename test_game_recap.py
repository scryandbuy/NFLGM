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
        self.L=NS(year=2026,week=9,user_team='GB',notes_sent={},inbox=[],
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
        self.assertIn('first half pressure or sacks on 1/1',m['body'])
        self.assertIn('second half pressure or sacks on 0/1',m['body'])
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

    def test_pressure_counts_sack_once_and_scramble_as_dropback(self):
        s=GR.stats([play('sack',-3,pressured=True),play('scramble',8,is_pass=True)])
        self.assertEqual((s['pressure'],s['passes'],s['runs']),(1,2,0))

    def test_missing_snapshot_does_not_invent_decisions(self):
        self.res.pop('coaching_review')
        self.assertIn('kickoff plan was not recorded',GR.post(self.L,'GB','MIN',1,self.res)['body'])

class RecapSimulationTests(unittest.TestCase):
    def test_direct_playoff_game_posts_once_and_saves(self):
        from session import Session
        from season import SeasonRunner
        s=Session.new('GB',seed=27)
        s.L.user_week_plan={'year':s.L.year,'week':19,'changes':{'protection':'six'},'taken':['Keep a back in']}
        runner=SeasonRunner(s.L,s.rng)
        res=runner.play('MIN','GB',19,playoffs=True)
        self.assertIsNotNone(res)
        reviews=[m for m in s.L.inbox if (m.get('payload') or {}).get('game_key','').startswith('game-recap-')]
        self.assertEqual(len(reviews),1)
        self.assertIn('Keep a back in',reviews[0]['body'])
        restored=Session.load(s.save())
        self.assertIsNone(GR.post(restored.L,'MIN','GB',19,res,True))

if __name__=='__main__': unittest.main()
