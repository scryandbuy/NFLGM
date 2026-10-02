import copy
import unittest
from collections import Counter
from types import SimpleNamespace as N
import numpy as np
import gameplan_week as GW
import gameplan as GP
import schemes

ATTRS = ('pass_block_rating','pass_block_power_rating','pass_block_finesse_rating',
         'power_moves_rating','finesse_moves_rating','strength_rating','block_shed_rating',
         'accel_rating','agility_rating','speed_rating')

def player(pid,pos,grade=70):
    return N(pid=pid,name=pid,pos=pos,ovr=grade,out_until=None,
             ratings={a:grade for a in ATTRS})

def team(abbr,front='4-3'):
    counts={'QB':1,'HB':1,'TE':2,'WR':4,'LT':2,'LG':2,'C':2,'RG':2,'RT':2,
            'LEDG':2,'REDG':2,'DT':4,'MIKE':2,'WILL':2,'SAM':2,'CB':4,'FS':2,'SS':2}
    return N(abbr=abbr,depth={pos:[player(f'{abbr}-{pos}-{i}',pos) for i in range(n)] for pos,n in counts.items()},
             gm=N(def_front=front,off_personnel='11',name='Coach',prestige=50,tree=''),
             depth_pins={},record=[0,0,0])

class ProtectionAdviceTests(unittest.TestCase):
    def setUp(self):
        self.me=team('GB');self.opp=team('KC')
        self.L=N(year=2027,teams={'GB':self.me,'KC':self.opp},game_stats={},tendencies={},schedule=[])
    def read(self,week=5):return GW.protection_read(self.L,self.me,self.opp,week)
    def grade(self,team,pos,value,index=0):
        team.depth[pos][index].ratings={a:value for a in ATTRS}
    def games(self,sacks=0,pressure=0,weeks=(1,2,3),year=2027,affiliation='GB'):
        for week in weeks:
            book={'qb':dict(team=affiliation,pass_plays=30,sacked=sacks)}
            for pos in ('LT','LG','C','RG','RT'):
                p=self.me.depth[pos][0]
                book[p.pid]=dict(team=affiliation,pb_snaps=30,pressures_allowed=pressure)
            self.L.game_stats[f'{year}-{week}-KC-GB']=book
    def test_even_matchup_needs_no_extra_protection(self):
        self.assertFalse(self.read()['recommend'])
    def test_elite_line_does_not_get_help_just_for_opponent_name(self):
        for pos in ('LT','LG','C','RG','RT'):self.grade(self.me,pos,95)
        for pos in ('LEDG','REDG','DT'):self.grade(self.opp,pos,90)
        self.assertFalse(self.read()['recommend'])
    def test_interior_weak_link_is_not_hidden_by_strong_tackles(self):
        self.grade(self.me,'LT',95);self.grade(self.me,'RT',95);self.grade(self.me,'RG',50)
        r=self.read();self.assertTrue(r['recommend']);self.assertEqual(r['matchups'][0]['role'],'RG')
        self.assertIn('GB-RG-0',r['why'])
    def test_edges_match_opposite_tackles(self):
        self.grade(self.opp,'LEDG',90)
        r=self.read();self.assertTrue(r['recommend']);self.assertEqual(r['matchups'][0]['role'],'RT')
    def test_injured_blocker_uses_backup_in_grade_and_advice(self):
        self.grade(self.me,'LT',95);self.grade(self.me,'LT',50,1)
        before=GW.unit_grades(self.L,self.me)['pass block']
        self.assertFalse(self.read()['recommend'])
        self.me.depth['LT'][0].out_until=8
        self.assertLess(GW.unit_grades(self.L,self.me)['pass block'],before)
        r=self.read();self.assertTrue(r['recommend']);self.assertIn('GB-LT-1',r['why'])
    def test_injured_rusher_does_not_trigger(self):
        self.grade(self.opp,'LEDG',95);self.opp.depth['LEDG'][0].out_until=8
        self.assertFalse(self.read()['recommend'])
    def test_pinned_order_preserved(self):
        self.grade(self.me,'LT',50,1)
        self.me.depth['LT'].reverse()
        self.assertIn('GB-LT-1',self.read()['why'])
    def test_base_fronts_and_nickel_supported(self):
        self.grade(self.opp,'REDG',90)
        for front in ('4-3','3-4','multiple'):
            self.opp.gm.def_front=front
            r=self.read();self.assertTrue(r['recommend'],front)
            self.assertEqual(r['matchups'][0]['role'],'LT')
    def test_two_moderate_mismatches_trigger_but_one_does_not(self):
        self.grade(self.me,'LT',60)
        self.assertFalse(self.read()['recommend'])
        self.grade(self.me,'RT',60)
        self.assertTrue(self.read()['recommend'])
    def test_week_one_report_can_recommend_without_display_ranks(self):
        self.grade(self.opp,'LEDG',90)
        r=GW.opponent_report(self.L,'GB','KC',1)
        self.assertTrue(all(x is None for x in r['my_units'].values()))
        self.assertEqual(len([s for s in r['suggestions'] if 'protection' in s['changes']]),1)
    def test_week_one_coach_projection_is_labeled_and_expires_with_tape(self):
        self.opp.gm.shell=.61; self.opp.gm.coverage=.2
        early=GW.opponent_report(self.L,'GB','KC',1)
        self.assertTrue(all(x is None for x in early['units'].values()))
        projected=[s for s in early['suggestions'] if s.get('basis')=='projection']
        self.assertEqual(len(projected),1)
        self.assertIn('Pregame projection',projected[0]['why'])
        self.assertIn('two-high',projected[0]['text'])
        self.L.tendencies={self.L.year:{'KC':Counter(plays=60,passes=30,def_snaps=60)}}
        measured=GW.opponent_report(self.L,'GB','KC',2)
        self.assertIsNotNone(measured['tendencies'])
        self.assertFalse(any(s.get('basis')=='projection' for s in measured['suggestions']))
    def test_week_one_roster_edge_is_projected_without_old_tendencies(self):
        self.L.tendencies={self.L.year-1:{'KC':{'plays':60,'passes':30,'def_snaps':60}}}
        for p in self.me.depth['WR'][:3]: p.ovr=90
        early=GW.opponent_report(self.L,'GB','KC',1)
        self.assertIsNone(early['tendencies'])
        projected=[s for s in early['suggestions'] if s.get('basis')=='projection']
        self.assertEqual(len(projected),1)
        self.assertIn('receivers grade',projected[0]['why'])
    def test_saved_empty_current_report_is_refreshed_once(self):
        self.opp.gm.shell=.61; self.opp.gm.coverage=.2
        self.L.user_team='GB'; self.L.inbox=[dict(kind='game_plan',year=self.L.year,
            status='unread',body='Week 1. 0 suggestions from the assistants.',
            payload={'report':dict(week=1,me='GB',opp='KC',suggestions=[])})]
        self.assertTrue(GW.refresh_open_report(self.L,1))
        self.assertEqual(len(self.L.inbox),1)
        self.assertEqual(self.L.inbox[0]['status'],'unread')
        self.assertEqual(len(self.L.inbox[0]['payload']['report']['suggestions']),1)
        self.assertIn('1 suggestion from the assistants',self.L.inbox[0]['body'])
        self.assertFalse(GW.refresh_open_report(self.L,1))
    def test_sustained_heavy_sacks_can_trigger_without_rating_mismatch(self):
        self.games(sacks=4)
        r=self.read();self.assertTrue(r['recommend']);self.assertIn('12 sacks on 90',r['why'])
    def test_one_bad_game_and_tiny_samples_do_not_trigger(self):
        self.games(sacks=6,weeks=(1,));self.assertFalse(self.read()['recommend'])
        self.games(sacks=2,weeks=(1,2))
        for book in self.L.game_stats.values():book['qb']['pass_plays']=10
        self.assertFalse(self.read()['recommend'])
    def test_moderate_sacks_need_current_matchup_support(self):
        self.games(sacks=3)
        self.assertFalse(self.read()['recommend'])
        self.grade(self.me,'LT',62)
        self.assertTrue(self.read()['recommend'])
    def test_lost_blocking_reps_need_sample_and_matchup(self):
        self.games(pressure=5)
        self.assertFalse(self.read()['recommend'])
        self.grade(self.me,'LT',62)
        r=self.read();self.assertTrue(r['recommend']);self.assertIn('15 of 90 recent blocking reps',r['why'])
    def test_recent_window_ignores_old_future_and_wrong_team_books(self):
        self.games(sacks=8,weeks=(1,))
        self.games(weeks=(2,3,4));self.games(sacks=8,weeks=(5,6))
        self.games(sacks=8,weeks=(2,3,4),year=2026)
        r=self.read();self.assertFalse(r['recommend']);self.assertEqual(r['sacks'],0)
        self.L.game_stats={};self.games(sacks=8,affiliation='KC')
        self.assertFalse(self.read()['recommend'])
    def test_one_outlier_among_three_games_does_not_trigger(self):
        self.games(weeks=(1,2));self.games(sacks=12,pressure=20,weeks=(3,))
        self.grade(self.me,'LT',62)
        self.assertFalse(self.read()['recommend'])
    def test_missing_legacy_evidence_does_not_invent_pressure(self):
        self.games(sacks=8)
        for book in self.L.game_stats.values():
            for s in book.values():s.pop('team')
        self.assertFalse(self.read()['recommend'])
    def test_blitz_only_retains_quick_game_alternative(self):
        tr=dict(blitz=.35,two_high=.4,box8=.1,man=.3,pa_rate=.1,deep=.1,pass_rate=.6)
        from unittest.mock import patch
        with patch.object(GW,'tendencies',return_value=tr):r=GW.opponent_report(self.L,'GB','KC',5)
        self.assertFalse(any('protection' in s['changes'] for s in r['suggestions']))
        self.assertTrue(any('screen_boost' in s['changes'] for s in r['suggestions']))
    def test_acceptance_reaches_protection_caller_without_mutating_report_inputs(self):
        self.grade(self.opp,'LEDG',90);before=copy.deepcopy(self.L)
        r=GW.opponent_report(self.L,'GB','KC',5)
        suggestion=next(s for s in r['suggestions'] if 'protection' in s['changes'])
        base=GP.Gameplan();state=N(plan=base.copy(),base_plan=base)
        self.assertEqual(self.L,before)
        self.L.user_week_plan=dict(year=2027,week=5,changes=suggestion['changes'])
        GW.user_plan(self.L,state,5)
        self.assertTrue(state.plan.protection_locked)
        self.assertEqual(schemes.choose_protection('11',4,'medium',np.random.default_rng(1),preference=state.plan.protection),'six_bob')

class ProtectionChoiceTests(ProtectionAdviceTests):
    def suggestion(self):
        return GW.protection_suggestion(self.L,self.me,self.opp,5,
                                       opponent_tendencies={'blitz':.10})
    def test_full_slide_for_multiple_threats_including_interior(self):
        self.grade(self.opp,'DT',92);self.grade(self.opp,'REDG',90)
        self.assertEqual(self.suggestion()['changes']['protection'],'full_slide')
    def test_isolated_edge_keeps_six(self):
        self.grade(self.opp,'LEDG',90)
        self.assertEqual(self.suggestion()['changes']['protection'],'six')
    def empty_setup(self):
        for pos in ('LT','LG','C','RG','RT'):self.grade(self.me,pos,92)
        self.me.depth['HB'][0].ratings.update(catch_rating=90,route_run_short_rating=90,speed_rating=90)
        self.games(sacks=0)
    def test_empty_requires_positive_evidence(self):
        self.empty_setup()
        self.assertEqual(self.suggestion()['changes']['protection'],'empty')
        self.L.game_stats={};self.assertIsNone(self.suggestion())
    def test_empty_rejected_against_blitz_or_bad_receiving_back(self):
        self.empty_setup()
        self.assertIsNone(GW.protection_suggestion(self.L,self.me,self.opp,5,opponent_tendencies={'blitz':.4}))
        self.me.depth['HB'][0].ratings.update(catch_rating=40,route_run_short_rating=40,speed_rating=70)
        self.assertIsNone(self.suggestion())
    def test_new_choices_reach_actual_pass_resolver(self):
        from unittest.mock import patch
        import game,rosters,plays
        teams=rosters.load_league()
        for mode,expected,count in [('full_slide','six_slide',6),('empty','five',5)]:
            self.setUp()
            if mode=='empty':self.empty_setup()
            else:self.grade(self.opp,'DT',92);self.grade(self.opp,'REDG',90)
            advice=self.suggestion();self.assertEqual(advice['changes']['protection'],mode)
            base=GP.Gameplan();state=N(plan=base.copy(),base_plan=base)
            self.L.user_week_plan=dict(year=2027,week=5,changes=advice['changes'])
            GW.user_plan(self.L,state,5)
            self.assertTrue(state.plan.protection_locked)
            rng=np.random.default_rng(17)
            oc=schemes.call_offense(2,8,0,50,rng,lean={'protection':state.plan.protection})
            oc.update(is_pass=True,personnel='11',depth='medium',concept='dagger',down=2,ydstogo=8,play_action=False,shotgun=True)
            off,_=game.field_units(teams['GB'],None,rng,True,'11')
            defense,_=game.field_units(teams['DEN'],None,rng,False,'nickel','3-4')
            dc=schemes.call_defense(oc,2,8,rng);dc.update(front_family='3-4',personnel='nickel',rushers=4)
            with patch.object(plays,'resolve_protection',wraps=plays.resolve_protection) as resolve:
                plays._pass_play(off,defense,oc,dc,50,rng)
            self.assertEqual(resolve.call_args.kwargs['protection'],expected)
            self.assertEqual(len(resolve.call_args.args[0]),count)

if __name__=='__main__':unittest.main()
