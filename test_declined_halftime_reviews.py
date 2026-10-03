"""Every current halftime concern can earn a relevant, selective declined note."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import game_recap as GR
import halftime as HT
from test_game_recap import play, drive


def rows(n, ty='complete', yards=0, **kw):
    return [play(ty, yards, **kw) for _ in range(n)]


class DeclinedHalftimeReviews(unittest.TestCase):
    def scenarios(self):
        return {
            'run_working': (rows(5,'run',6)+rows(15,yards=2), [], (rows(8,'run',6), []), '15 dropbacks'),
            'run_stalled': (rows(10,'run',2), [], (rows(10,'run',2), []), '10 runs'),
            'protection': (rows(4,'sack',-5)+rows(12), [], (rows(12), []), '4 sacks'),
            'deep_stalled': (rows(5,'incomplete',depth='deep'), [], (rows(4,'incomplete',depth='deep'), []), '0 completions on 5'),
            'deep_working': (rows(14,yards=2,depth='short'), [], (rows(3,yards=30,depth='deep'), []), 'only 0 deep shots'),
            'screens_stalled': (rows(6,screen=True), [], (rows(4,screen=True), []), '6 logged screens'),
            'blitz_opportunity': (rows(6,'run',2,blitz=True)+rows(4,yards=10,blitz=True), [], (rows(4,yards=10,blitz=True), []), 'ran 6 times'),
            'third_offense': (rows(6,down=3,ydstogo=8), [], (rows(4,down=3,ydstogo=8), []), '0/6 third downs'),
            'turnovers': (rows(2,'interception')+rows(12), [], (rows(2,'interception'), []), '2 more turnovers'),
            'run_defense': ([], rows(10,'run',6), ([], rows(8,'run',6)), '10 runs'),
            'pass_defense': ([], rows(14,yards=10), ([], rows(10,yards=10)), '14 dropbacks'),
            'deep_defense': ([], rows(4,yards=25,depth='deep'), ([], rows(3,yards=25,depth='deep')), '4 of 4 deep throws'),
            'pressure_defense': ([], rows(14,yards=8), ([], rows(12,yards=8)), 'only 0/14'),
            'third_defense': ([], rows(6,yards=10,down=3,ydstogo=8), ([], rows(4,yards=10,down=3,ydstogo=8)), '6/6 third downs'),
            'screens_defense': ([], rows(6,yards=9,screen=True), ([], rows(4,yards=9,screen=True)), 'Their screens'),
            'hurry': (rows(8,'run',2,down=1,score_diff=-14), [], ([], []), 'down at least two scores'),
            'clock_control': (rows(8,'incomplete',down=1,score_diff=14), [], ([], []), '8 incompletions stopped the clock'),
        }

    def test_every_concern_has_relevant_bad_result_evidence(self):
        for key, (own, against, before, expected) in self.scenarios().items():
            with self.subTest(key=key):
                text = GR.declined_evidence(key, own, against, before)
                self.assertIsNotNone(text)
                self.assertIn(expected, text)
                rec = dict(text='Advice', review_key=key, changes={})
                review = GR.declined_reviews([rec], own, against, before)
                self.assertEqual(len(review), 1)
                self.assertEqual(review[0]['findings'][0]['text'], text)

    def test_no_concern_is_blameworthy_without_evidence(self):
        for key in self.scenarios():
            with self.subTest(key=key):
                self.assertIsNone(GR.declined_evidence(key, [], [], ([], [])))

    def test_third_down_review_does_not_use_general_yardage(self):
        before = rows(4,down=3,ydstogo=8)
        after = rows(5,yards=9,down=3,ydstogo=8)+rows(30,yards=0,down=1)
        self.assertIsNone(GR.declined_evidence('third_offense',after,[],(before,[])))
        # Defensive third-down success likewise is not erased by unrelated big plays.
        self.assertIsNone(GR.declined_evidence('third_defense',[],rows(5,down=3,ydstogo=8)+rows(30,yards=30,down=1),([],rows(4,yards=10,down=3,ydstogo=8))))

    def test_improved_problem_and_successful_alternative_do_not_get_notes(self):
        self.assertIsNone(GR.declined_evidence('run_stalled',rows(10,'run',3.2),[],(rows(10,'run',2),[])))
        self.assertIsNone(GR.declined_evidence('run_working',rows(5,'run',6)+rows(15,yards=10),[],(rows(8,'run',6),[])))
        self.assertIsNone(GR.declined_evidence('deep_working',rows(15,yards=8),[],(rows(3,yards=30,depth='deep'),[])))
        self.assertIsNone(GR.declined_evidence('screens_defense',[],rows(6,yards=7,screen=True),([],rows(4,yards=10,screen=True))))
        # Low pressure alone is not costly if coverage shut down the passing game.
        self.assertIsNone(GR.declined_evidence('pressure_defense',[],rows(14,yards=2),([],rows(12,yards=8))))

    def test_opportunity_advice_needs_current_relevant_opportunity(self):
        first = rows(4,yards=10,blitz=True)
        # Many bad runs against a normal front do not validate throwing into a blitz.
        self.assertIsNone(GR.declined_evidence('blitz_opportunity',rows(8,'run',1)+rows(4,yards=10,blitz=True),[],(first,[])))

    def test_tempo_uses_current_score_and_early_downs(self):
        for key, score in [('hurry',14),('clock_control',-14)]:
            ty = 'run' if key == 'hurry' else 'incomplete'
            self.assertIsNone(GR.declined_evidence(key,rows(10,ty,down=1,score_diff=score),[],([],[])))
        self.assertIsNone(GR.declined_evidence('clock_control',rows(10,'incomplete',down=3,score_diff=14),[],([],[])))
        self.assertIsNone(GR.declined_evidence('hurry',rows(10,'run',2,down=1),[],([],[])))

    def test_equivalent_accepted_advice_suppresses_rejected_note(self):
        cases = [('run_stalled', {'pass_bias':.06}, {'pass_bias':.05}),
                 ('third_offense', {'depth_mix':(.06,-.03,-.03)}, {'depth_mix':(.08,-.05,-.03)}),
                 ('pressure_defense', {'blitz_lean':.06}, {'blitz_lean':.03})]
        for key,ch,other in cases:
            with self.subTest(key=key):
                own,against,before,_ = self.scenarios()[key]
                rec = dict(text='Advice',review_key=key,changes=ch)
                self.assertEqual(GR.declined_reviews([rec],own,against,before,accepted=[{'changes':other}]),[])

    def test_more_than_two_worthwhile_decisions_are_allowed(self):
        recs = [dict(text=key,review_key=key,changes={}) for key in ('protection','third_offense','turnovers')]
        own = rows(4,'sack',-5)+rows(6,down=3,ydstogo=8)+rows(2,'interception')
        reviews = GR.declined_reviews(recs,own,[],(rows(4,down=3,ydstogo=8),[]))
        self.assertEqual(len(reviews),3)

    def test_post_uses_score_at_drive_not_final_score(self):
        L = NS(phase="regular", year=2026,week=2,user_team='GB',notes_sent={},inbox=[],teams={'GB':NS(staff={})})
        d = drive(3,rows(8,'incomplete',clock=900,down=1)); d.score_diff=14
        rec = dict(text='Shorten the game',review_key='clock_control',changes={'tempo':-.2,'pass_bias':-.05})
        result = dict(home=17,away=24,drives=[('home',d)],coaching_review={'halftime_declined':[rec]})
        self.assertIn('8 incompletions stopped the clock',GR.post(L,'GB','DAL',2,result)['body'])

    def test_all_generated_recommendations_have_evidence_categories(self):
        base = HT.first_half([], 'home')[0]
        # Isolated triggers avoid the six-recommendation display limit.
        scenarios = [
            ({'runs':8,'run_yds':48,'passes':12},{},0),
            ({'runs':8,'run_yds':16},{},0),
            ({'passes':12,'sacks':4,'pressures':2},{},0),
            ({'deep':4,'deep_cmp':0},{},0),
            ({'deep':3,'deep_cmp':3,'deep_yds':90},{},0),
            ({'screens':4,'screen_yds':0},{},0),
            ({'blitz_faced':5,'blitz_yds':50},{},0),
            ({'third':5,'third_conv':0},{},0),
            ({'int':2},{},0),
            ({},{'runs':8,'run_yds':48},0),
            ({},{'passes':12,'pass_yds':120,'pressures':4},0),
            ({},{'deep_cmp':3},0),
            ({},{'passes':12,'pass_yds':60},0),
            ({},{'third':5,'third_conv':4},0),
            ({},{'screens':4,'screen_yds':36},0),
            ({},{},-14), ({},{},14)]
        seen=set()
        for own,opp,margin in scenarios:
            with patch.object(HT,'first_half',return_value=(dict(base,**own),dict(base,**opp))):
                recs=HT.recommendations(None,'GB','DAL',[],'home',{'home':max(0,margin),'away':max(0,-margin)},None,None)
            for rec in recs: seen.add(rec['review_key'])
        self.assertEqual(seen,set(self.scenarios()))


if __name__ == '__main__': unittest.main()
