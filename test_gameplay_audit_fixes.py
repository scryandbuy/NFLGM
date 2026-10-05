import collections
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import gameday
import game_recap as GR
import gameplan_week as GW
import views_gameplan as VG
import events as E
import plays as P


class FieldAccounting(unittest.TestCase):
    def capture(self, rows, *, start=50, end=40, result='Punt', points=0):
        league=NS(week=1, player=lambda pid:None, teams={t:NS(roster=[]) for t in ('GB','TB')})
        drive=NS(log=rows,off={},start=start,yardline=end,quarter=1,start_quarter=1,
                 clock=3400,plays=len(rows),first_downs=1,result=result,points=points)
        res=dict(home=points,away=0,drives=[('home',drive)])
        return gameday.capture(league,[('GB','TB',res,NS(p={}))],'GB')['game']['team_stats']['GB']

    def test_settled_conversion_and_goal_touchdown_match_recap(self):
        rows=[dict(type='complete',yards=2.8,down=3,ydstogo=3,converted=True),
              dict(type='complete',yards=5,down=4,ydstogo=14,touchdown=True,converted=True),
              dict(type='run',yards=12,down=3,ydstogo=2,converted=False,fumble_lost=True),
              dict(type='complete',yards=15,down=4,ydstogo=3,converted=True,nullified=True)]
        line=self.capture(rows)
        self.assertEqual(line['third'],'1/2')
        self.assertEqual(line['fourth'],'1/1')
        self.assertEqual(GR.stats(rows)['converted'],1)
        self.assertTrue(GR.converted(dict(type='run',yards=2.8,ydstogo=3)))

    def test_red_zone_requires_live_opportunity_not_long_score_or_knees(self):
        td=dict(type='complete',yards=65,yardline=65,touchdown=True)
        self.assertEqual(self.capture([td],start=65,end=0,result='Touchdown',points=7)['red_zone'],'0/0')
        short=dict(type='run',yards=10,yardline=10,touchdown=True)
        self.assertEqual(self.capture([short],start=10,end=0,result='Touchdown',points=7)['red_zone'],'1/1')
        self.assertEqual(self.capture([dict(short,nullified=True)],start=10,end=10)['red_zone'],'0/0')
        self.assertEqual(self.capture([dict(type='kneel',yards=-1,yardline=10)],start=10,end=11,result='End of game')['red_zone'],'0/0')
        kick=dict(type='field_goal',yards=0,yardline=15,made=True)
        self.assertEqual(self.capture([kick],start=15,end=15,result='Field goal',points=3)['red_zone'],'0/1')

    def test_blitz_review_keeps_cost_and_pressure(self):
        rows=[dict(type='complete',yards=15,blitz=True,pressured=True) for _ in range(10)]
        findings=GR.assess_choice({'blitz_rate':.05},[],rows)
        self.assertEqual([x['label'] for x in findings],['Pressure calls','Pass-rush pressure'])
        self.assertEqual(findings[0]['verdict'],'negative')
        self.assertEqual(findings[1]['verdict'],'positive')


class CoverageDenominator(unittest.TestCase):
    def league(self):
        return NS(year=2029,tendencies={},teams={t:NS(record=(1,0,0)) for t in ('GB','TB')})

    def record(self,l,passes=40,runs=60):
        rows=[dict(type='complete',is_pass=True,in_man=True)]*passes+[dict(type='run',is_pass=False)]*runs
        GW.record_game(l,'GB','TB',dict(drives=[('home',NS(log=rows,result='Punt')),('away',NS(log=[dict(type='run')]*40,result='Punt'))]))

    def test_run_mix_does_not_change_known_man_percentage(self):
        for runs in (0,20,60,100):
            l=self.league();self.record(l,runs=runs)
            self.assertEqual(GW.tendencies(l,'TB')['man'],1.)

    def test_legacy_counts_do_not_contaminate_new_sample(self):
        l=self.league();l.tendencies={2029:{'TB':collections.Counter(plays=80,passes=50,man=90,def_snaps=100)}}
        self.assertIsNone(GW.tendencies(l,'TB')['man'])
        self.assertIsNone(VG._league_tend(l)['man'])
        self.record(l)
        self.assertEqual(GW.tendencies(l,'TB')['man'],1.)
        self.assertEqual(l.tendencies[2029]['TB']['man'],130)

    def test_sack_without_coverage_observation_is_not_recorded_as_zone(self):
        l=self.league()
        rows=[dict(type='complete',is_pass=True,in_man=True)]*30+[dict(type='sack',is_pass=True)]*10
        GW.record_game(l,'GB','TB',dict(drives=[('home',NS(log=rows,result='Punt')),
            ('away',NS(log=[dict(type='run')]*40,result='Punt'))]))
        self.assertEqual(GW.tendencies(l,'TB')['man'],1.)
        self.assertEqual(l.tendencies[2029]['TB']['def_pass_snaps'],30)


class PocketDecisions(unittest.TestCase):
    def chance(self,mobility=.85,pursuit=.7,**kw):
        qb={'pid':'qb','rating':mobility}
        defenders=[dict(pid=str(i),pos='MIKE' if i<2 else 'CB',rating=pursuit) for i in range(6)]
        args=dict(separation=.25,pressure=.25)
        args.update(kw)
        return E.pocket_run_chance(qb,defenders,lambda p,w:p['rating'],**args)

    def test_action_and_restraint_use_visible_read_and_context(self):
        base=self.chance()
        self.assertGreater(base,0)
        self.assertGreater(self.chance(mobility=.95),base)
        self.assertLess(self.chance(mobility=.60),base/4)
        self.assertLess(self.chance(pursuit=.95),base)
        self.assertGreater(self.chance(aggression=.9),self.chance(aggression=.1))
        self.assertLess(self.chance(down=4,distance=18),base)
        self.assertLess(self.chance(seconds=9,margin=-3),base/5)
        for kw in ({'screen':True},{'hot':True},{'swing':True},{'time_available':1.2},{'separation':.9,'pressure':.1}):
            self.assertEqual(self.chance(**kw),0)
        self.assertGreater(self.chance(read='second'),base)
        self.assertGreater(self.chance(man=True),base)

    def test_seeded_equal_opportunities_preserve_quarterback_differences(self):
        sample=np.random.default_rng(731).random(5000)
        pocket=int(sum(sample<self.chance(mobility=.60)))
        mobile=int(sum(sample<self.chance(mobility=.95)))
        self.assertGreater(mobile,4*pocket)
        self.assertLess(mobile,1500)

    def test_decision_precedes_throw_and_keeps_pass_rush_evidence(self):
        from test_fourth_down_routes import FourthDownRoutes
        FourthDownRoutes.setUpClass();fixture=FourthDownRoutes()
        with patch.object(E,'pocket_run_chance',return_value=1), \
             patch.object(P,'resolve_throw',side_effect=AssertionError('throw already resolved')), \
             patch.object(P,'resolve_zone',side_effect=AssertionError('throw already resolved')):
            outcomes=[fixture.play(seed,down=2) for seed in range(12)]
        scrambles=[x for x in outcomes if x['type']=='scramble']
        self.assertTrue(scrambles)
        self.assertTrue(any(x['type']=='sack' for x in outcomes))
        for out in scrambles:
            self.assertEqual(out['scramble_kind'],'decision')
            self.assertNotIn('target',out)
            self.assertIn('pr_reps',out)
            self.assertIn('rush_pressures',out)
            self.assertIn('pb_award',out)
            self.assertIn('coverage_evidence',out)

    def test_sack_escape_probability_is_unchanged(self):
        self.assertAlmostEqual(E.scramble_chance({},1.,1.4,lambda *args:.7),.0512*1.85)

    def test_scramble_does_not_copy_previous_throws_completion_expectation(self):
        with patch.object(P,'LAST_XCOMP',.95),patch.object(P,'_pass_play',return_value={
                'type':'scramble','yards':6,'tackler':'d'}):
            out=P.resolve_play({'qb':{'pid':'qb'}},{},{'is_pass':True},{},50,np.random.default_rng(1))
        self.assertIsNone(out['xcomp'])

    def test_season_callers_carry_coach_risk_and_book_scramble_as_dropback(self):
        import game as G
        import rosters
        from season import _deps
        teams=rosters.load_league();co,cd=_deps()
        for caution in (.1,.9):
            off,deff=teams['GB'],teams['DEN']
            st=G.TeamState(off,coach={'starter_protection':caution});dst=G.TeamState(deff)
            seen=[]
            def call(*args,**kwargs):
                result=co(*args,**kwargs)
                result.update(is_pass=True,depth='medium',concept='dagger')
                return result
            def resolve(off,deff,oc,dc,ytg,rng):
                seen.append(oc['qb_run_aggression'])
                return P.resolve_play(off,deff,oc,dc,ytg,rng)
            book=G.StatBook();G.LAST_KICKOFF.clear()
            with patch.object(E,'pocket_run_chance',return_value=1):
                dr=G.run_drive(off,deff,75,700,3,0,np.random.default_rng(81),
                               resolve,call,cd,P.rate,.5,book,st,dst)
            self.assertTrue(seen)
            for value in seen:self.assertAlmostEqual(value,1-caution)
            scrambles=[p for p in dr.log if p.get('type')=='scramble' and not p.get('nullified')]
            self.assertTrue(scrambles)
            line=book.p[off['qb']['pid']]
            self.assertEqual(line['rush_att'],len(scrambles))
            self.assertEqual(line['pass_plays']-line['pass_att']-line['sacked'],len(scrambles))
            self.assertTrue(all(p.get('passer')==off['qb']['pid'] for p in scrambles))

if __name__=='__main__':unittest.main()
