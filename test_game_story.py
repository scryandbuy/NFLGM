import json
import unittest
from types import SimpleNamespace as NS
from game_story import build

class StoryTests(unittest.TestCase):
    def setUp(self):
        self.league=NS(player=lambda pid:NS(name='Test Receiver'))
    def drive(self,points,q=1,clock=3000,log=None,result='',start=75):
        return NS(points=points,quarter=q,start_quarter=q,clock=clock,log=log or [],result=result,start=start)
    def test_large_lead_close_finish_is_not_called_a_comeback_win(self):
        d=self.drive
        res=dict(home=27,away=24,drives=[('home',d(24,2,1801)),('away',d(7,2,1800)),
            ('away',d(11,4,500)),('home',d(3,4,212)),('away',d(6,4,145)),
            ('home',d(0,4,0,[dict(type='run',down=3,ydstogo=4,yards=7),dict(type='kneel')]))])
        story=build(self.league,'GB','DET',res);text=' '.join(story['paragraphs'])
        self.assertIn('holds off',story['headline']);self.assertIn('24–7 lead into halftime',text)
        self.assertIn('third down on the ground',text);self.assertNotIn('rallies past',story['headline'])
        self.assertEqual(json.loads(json.dumps(story)),story)
    def test_away_comeback_and_overtime(self):
        res=dict(home=10,away=13,overtime=True,drives=[('home',self.drive(10)),('away',self.drive(10,4,0)),('away',self.drive(3,5,300))])
        story=build(self.league,'DET','GB',res)
        self.assertIn('Green Bay rallies',story['headline']);self.assertIn('in overtime',' '.join(story['paragraphs']))
    def test_incomplete_scoring_evidence_cannot_invent_lead(self):
        story=build(self.league,'GB','DET',dict(home=27,away=24,drives=[('home',self.drive(24))]))
        self.assertNotIn('built a',' '.join(story['paragraphs']));self.assertNotIn('halftime',' '.join(story['paragraphs']))
    def test_nullified_touchdown_is_not_a_highlight(self):
        p=dict(type='complete',yards=99,touchdown=True,nullified=True,target='p')
        story=build(self.league,'GB','DET',dict(home=3,away=0,drives=[('home',self.drive(3,log=[p]))]))
        self.assertNotIn('99',' '.join(story['paragraphs']))
    def test_defensive_score_credited_to_other_team(self):
        story=build(self.league,'GB','DET',dict(home=0,away=7,drives=[('home',self.drive(-7))]))
        self.assertIn('Detroit',story['headline']);self.assertNotIn('Green Bay took',' '.join(story['paragraphs']))
    def test_tie_no_winner_or_kneel_win(self):
        story=build(self.league,'GB','DET',dict(home=0,away=0,overtime=True,drives=[]))
        self.assertIn('finish level',story['headline']);self.assertNotIn('win over',' '.join(story['paragraphs']))
    def test_named_highlight_uses_actual_target(self):
        story=build(self.league,'GB','DET',dict(home=7,away=0,drives=[('home',self.drive(7,log=[dict(type='complete',yards=47,touchdown=True,target='p')]))]))
        self.assertIn('Test Receiver',' '.join(story['paragraphs']))

if __name__=='__main__':unittest.main()
