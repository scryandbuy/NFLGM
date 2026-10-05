import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import inbox as IB
from league import League, Team
from session import Session


def fixture():
    s = Session.__new__(Session); s.L = League(2029); s.L.set_phase('playoffs')
    s.user_team = s.L.user_team = 'GB'; s.L.week = 21
    for abbr, conf, record in [('GB', 'United', [13,4,0]), ('CAR', 'United', [12,5,0]),
                               ('MIA', 'Continental', [9,8,0]), ('PIT', 'Continental', [7,10,0])]:
        t = Team(abbr, conf + ' North', conf); t.record = record; t.league = s.L; s.L.teams[abbr] = t
    matches = [('Continental','PIT','MIA'), ('United','GB','CAR')]
    s.post_live = N(seeds={'United':['GB','CAR'], 'Continental':['A','B','C','PIT','D','E','MIA']},
                    alive={'United':{1:'GB',2:'CAR'},'Continental':{4:'PIT',7:'MIA'}}, games=[],
                    schedule_round=lambda rnd: matches)
    s.runner = N(week=21, injury_week=lambda wk: None)
    return s, matches


class PlayoffRoundMailTests(unittest.TestCase):
    def test_prep_posts_one_row_per_game_with_seeds_records_and_venue(self):
        s, matches = fixture()
        with patch('gameplan_week.post_report'):
            s._playoff_prep(2)
        msg = s.L.inbox[-1]
        self.assertEqual(msg['payload']['mail_intro']['text'],
                         'You host No. 2 Carolina (12-5) in the Conference Championship.')
        section = msg['payload']['mail_sections'][0]
        self.assertEqual(section['columns'], ['Away Team','Home Team','Venue'])
        self.assertEqual([[c['text'] for c in row] for row in section['rows']],
                         [['No. 7 Miami (9-8)','No. 4 Pittsburgh (7-10)','Pittsburgh Stadium'],
                          ['No. 2 Carolina (12-5)','No. 1 Green Bay (13-4)','Green Bay Stadium']])
        self.assertNotIn('The round', msg['body'])
        self.assertIn('league:bracket', msg['payload'].values())
        self.assertEqual(IB.mail_layout(League.load(s.L.save()).inbox[-1])['mail_sections'],
                         msg['payload']['mail_sections'])

    def test_away_ties_and_eliminated_user(self):
        s, matches = fixture(); s.L.teams['GB'].record = [12,4,1]
        _, body, sections = s._round_letter(s.post_live,'CONF',matches,'CAR',matches[1])
        self.assertEqual(body,'You visit No. 1 Green Bay (12-4-1) in the Conference Championship.')
        _, body, sections = s._round_letter(s.post_live,'CONF',matches,'DEN',None)
        self.assertEqual(body,''); self.assertEqual(len(sections[0]['rows']),2)

    def test_bye_explains_reseeding(self):
        s, matches = fixture()
        _, body, _ = s._round_letter(s.post_live,'WC',matches[:1],'GB',None)
        self.assertIn('lowest remaining seed',body)
        self.assertNotIn('worst',body)

    def test_final_letter_still_handles_pending_and_scheduled_final(self):
        s, matches = fixture()
        _, body, sections = s._round_letter(s.post_live,'SB',[],'GB',None)
        self.assertIn('not yet decided',body); self.assertEqual(sections,[])
        subject, body, sections = s._round_letter(s.post_live,'SB',[('','GB','PIT')],'GB',('','GB','PIT'))
        self.assertIn('Championship Game',subject); self.assertIn('Road to the final',body)

    def test_existing_letter_gets_rows_without_mutating_saved_message(self):
        s, _ = fixture()
        msg = IB.news(s.L,'Conference Championships',
            'Your Conference Championship game: vs Carolina at home. They finished 12-5.\n\n'
            'The round\nThe 7 seed Miami (9-8) at The 4 seed Pittsburgh (7-10), Pittsburgh Stadium\n'
            'The 2 seed Carolina (12-5) at The 1 seed Green Bay (13-4), Green Bay Stadium',
            payload=dict(link='league:bracket'))
        original = copy.deepcopy(msg); layout = IB.mail_layout(msg)
        self.assertEqual(len(layout['mail_sections'][0]['rows']),2)
        self.assertEqual(layout['mail_intro']['text'],
                         'You host Carolina (12-5) in the Conference Championship.')
        self.assertEqual(msg,original)
        msg['body'] += '\nAn unrelated sentence.'
        self.assertNotIn('mail_sections',IB.mail_layout(msg))


if __name__ == '__main__': unittest.main()
