import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import events as E
import kick_returns as KR
import advanced_stats as AS
import ticker


RATE = lambda p, weights: sum(p.get(k, 70) * w for k, w in weights.items()) / 100 / sum(weights.values())


class ReturnTests(unittest.TestCase):
    def setUp(self):
        G.LAST_KICKOFF.clear()
        self.rng = np.random.default_rng(8)
        self.man = dict(pid='ret', pos='WR')
        self.off = dict(k=dict(pid='k'), p=dict(pid='p'), kr=self.man, pr=self.man)
        self.deff = dict(k=dict(pid='dk'), pr=dict(pid='pr'), kr=dict(pid='kr'))

    def test_return_distance_scores_and_is_bounded(self):
        with patch.object(E, 'fumble_check', return_value=None):
            for start in (12., 70., 95.):
                r = KR.resolve(start, 150, self.man, self.rng, RATE)
                self.assertEqual((r['ret'], r['new_yardline'], r['touchdown']), (start, 0., True))

    def test_both_kick_functions_preserve_the_return_touchdown(self):
        rng=NS(random=lambda:.99, normal=lambda *a:45., gamma=lambda *a:150.)
        with patch.object(E,'fumble_check',return_value=None), patch.dict(G.PUNT,return_rate=1.):
            punt=G.punt(75,{},self.man,rng,RATE)
            kick=G.kickoff(self.man,rng,RATE)
        self.assertEqual((punt['ret'],punt['new_yardline'],punt['touchdown']),(70.,0.,True))
        self.assertEqual((kick['ret'],kick['new_yardline'],kick['touchdown']),(95.,0.,True))

    def test_coverage_and_blocks_change_identical_return_draw(self):
        weak=dict(tackle_rating=30, speed_rating=30, run_block_rating=30)
        strong=dict(tackle_rating=95, speed_rating=95, run_block_rating=95)
        with patch.object(E,'fumble_check',return_value=None):
            a=KR.resolve(95,25,self.man,self.rng,RATE,[strong],[weak])
            b=KR.resolve(95,25,self.man,self.rng,RATE,[weak],[strong])
        self.assertLess(a['ret'],b['ret'])
        self.assertGreaterEqual(a['ret'],25*.85-.1)
        self.assertLessEqual(b['ret'],25*1.15+.1)

    def test_existing_ball_security_rates_are_used(self):
        with patch.object(E,'fumble_check',return_value=None) as check:
            for event in ('punt_return','kick_return'):
                KR.resolve(95,25,self.man,self.rng,RATE,event=event,weather=1.3)
                self.assertEqual(check.call_args.args[1],event)
                self.assertEqual(check.call_args.kwargs['env_mult'],1.3)

    def test_muff_and_forced_fumble_book_once(self):
        for forced in (False,True):
            with patch.object(E,'fumble_check',return_value=dict(lost=True,forced=forced)):
                r=KR.resolve(70,150,self.man,self.rng,RATE,[dict(pid='cov')])
            self.assertFalse(r['touchdown']);self.assertGreater(r['new_yardline'],0)
            if not forced:self.assertEqual(r['ret'],0)
            b=G.StatBook();KR.book_return(b,'pr',r)
            self.assertEqual((b.p['ret']['fumbles'],b.p['ret']['fumbles_lost'],b.p['cov']['fum_rec']),(1,1,1))
            self.assertEqual(b.p['cov']['ff'],int(forced))

    def test_return_flag_erases_score_and_books_only_legal_distance(self):
        r=dict(return_start=70.,new_yardline=0.,ret=70.,touchdown=True,returner='ret')
        KR.enforce_return_flag(r,dict(yards=10,penalty='Return Holding',on_offense=False))
        self.assertFalse(r['touchdown']);self.assertEqual(r['ret'],35)
        self.assertEqual(r['new_yardline'],45)
        b=G.StatBook();KR.book_return(b,'pr',r)
        self.assertEqual((b.p['ret']['pr_yds'],b.p['ret']['pr_td']),(35,0))

    def test_decline_return_flag_when_kicking_team_recovers(self):
        r=dict(new_yardline=60,ret=10,fumble_lost=True)
        before=copy.deepcopy(r);KR.enforce_return_flag(r,dict(yards=10))
        self.assertEqual({k:v for k,v in r.items() if k != 'declined_penalty'}, before)
        self.assertTrue(r['declined_penalty']['declined'])
        self.assertEqual(r['declined_penalty']['enforced_yards'], 0.)

    def test_units_exclude_injured_and_duplicate_players(self):
        man=dict(pid='a',pos='CB');inj=dict(pid='b',pos='CB')
        unit=KR.unit(dict(depth={'CB':[man,man,inj]}),NS(out={'b'}),RATE)
        self.assertEqual([p['pid'] for p in unit],['a'])

    def punt_drive(self, outcome, flag=None):
        original=G.Drive
        def fourth(*args,**kwargs):
            dr=original(*args,**kwargs);dr.down=4;return dr
        b=G.StatBook()
        with patch.object(G,'Drive',side_effect=fourth), patch.object(G,'punt',return_value=copy.deepcopy(outcome)), \
             patch.object(G,'end_of_half_plan',return_value=None), patch.object(G,'fourth_down_decision',return_value='punt'), \
             patch.object(E,'special_teams_penalty_check',side_effect=[None,flag]), \
             patch.object(G,'two_point_decision',return_value=False), \
             patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',points=1,made=True)):
            dr=G.run_drive(self.off,self.deff,75,400,4,0,self.rng,None,None,None,RATE,book=b)
        return dr,b

    def punt(self,**kw):
        r=dict(type='punt',blocked=False,how='return',returner='pr',ret=70.,return_start=70.,
               new_yardline=0.,gross=45,net=-25.,touchdown=True)
        r.update(kw);return r

    def test_punt_td_scores_for_receiver_with_try_and_separate_stats(self):
        dr,b=self.punt_drive(self.punt())
        self.assertEqual((dr.result,dr.points),('Defensive touchdown',-7))
        self.assertEqual((b.p['pr']['pr_td'],b.p['pr']['rec_td'],b.p['dk']['xp_made']),(1,0,1))
        self.assertLess(b.p['p']['st_epa'],-6)

    def test_lost_punt_return_keeps_kicking_team_ball(self):
        dr,b=self.punt_drive(self.punt(touchdown=False,fumble=True,fumble_lost=True,
                             fumble_by='pr',recoverer='cov',ret=10,new_yardline=60))
        self.assertEqual((dr.result,dr.next_yardline),('Recovered punt',40))
        self.assertEqual(b.p['pr']['fumbles_lost'],1)
        self.assertEqual(b.p['cov']['fum_rec'],1)

    def test_return_penalty_epa_uses_enforced_spot(self):
        dr,b=self.punt_drive(self.punt(),dict(penalty='Return Holding',yards=10,on_offense=False))
        self.assertEqual((dr.result,dr.next_yardline),('Punt',45))
        self.assertAlmostEqual(b.p['p']['st_epa'],-AS.ep(1,10,45)-AS.ep(4,10,75))
        self.assertNotIn('epa',dr.log[-1])

    def test_earlier_down_fg_uses_actual_state(self):
        dr=NS(result='Field goal',togo=10,yardline=25)
        b=G.StatBook();AS.book_special(b,dr,dict(type='field_goal',down=1,ydstogo=10,yardline=25),self.off)
        self.assertAlmostEqual(b.p['k']['st_epa'],3-AS.ep(1,10,25))

    def test_shared_kick_probability_weather_and_coaching(self):
        with patch.object(E,'special_teams_penalty_check',return_value=None), patch.object(G,'ENV',NS(kick_mult=.75)):
            for noise in (.7,1.,1.4):
                kicker=dict(st_noise=noise)
                fg=G.attempt_field_goal(16,kicker,NS(random=lambda:.90),RATE)
                xp=G.attempt_extra_point(kicker,NS(random=lambda:.90),RATE)
                self.assertEqual(fg['made'],xp['made'])
            self.assertFalse(fg['made'])

    def test_kickoff_score_at_zero_clock_and_lost_fumble(self):
        for scored in (True,False):
            kick=dict(type='kickoff',new_yardline=0 if scored else 50,ret=95 if scored else 45,
                      touchdown=scored,fumble_lost=not scored,returner='ret',clock=4)
            G.LAST_KICKOFF['r']=kick
            with patch.object(G,'two_point_decision',return_value=False), \
                 patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',points=1,made=True)):
                dr=G.run_drive(self.off,self.deff,kick['new_yardline'],0,4,0,self.rng,None,None,None,RATE)
            self.assertEqual(dr.result,'Touchdown' if scored else 'Turnover')
            self.assertEqual(dr.points,7 if scored else 0)
            self.assertFalse(G.pending_kick_outcome())

    def test_kickoff_td_survives_regulation_expiry_in_game_loop(self):
        original=G.drive_steps
        calls=[]
        def drive(*args,**kw):
            if G.pending_kick_outcome():return (yield from original(*args,**kw))
            G.LAST_KICKOFF.clear();calls.append(1)
            dr=G.Drive(*args[:7]);dr.clock=4;dr.result='Field goal';dr.points=3
            if len(calls)==1:dr.clock=1800;dr.result='End of half';dr.points=0
            return dr
        kicks=iter([dict(touchback=True,new_yardline=65),dict(touchback=True,new_yardline=65),dict(touchback=False,new_yardline=0,touchdown=True,ret=95)])
        def kick(*a,**kw):
            r=next(kicks);G.LAST_KICKOFF['r']=r;return r
        with patch.object(G,'drive_steps',side_effect=drive), patch.object(G,'kickoff_booked',side_effect=kick), \
             patch.object(G,'two_point_decision',return_value=False), \
             patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',points=1,made=True)):
            result=G.play_game(self.off,self.deff,self.rng,None,None,None,RATE)
        self.assertEqual((result['home'],result['away']),(3,7))
        self.assertEqual(len(result['drives']),3)

    def test_ot_second_team_return_td_wins_without_extra_point(self):
        original=G.run_drive
        def drive(*args,**kw):
            if G.pending_kick_outcome():return original(*args,**kw)
            G.LAST_KICKOFF.clear()
            dr=G.Drive(*args[:7]);dr.clock=200;dr.result='Field goal';dr.points=3
            return dr
        kicks=iter([dict(touchback=True,new_yardline=65),dict(touchback=False,new_yardline=0,touchdown=True,ret=95)])
        def kick(*a,**kw):
            r=next(kicks);G.LAST_KICKOFF['r']=r;return r
        with patch.object(G,'run_drive',side_effect=drive), patch.object(G,'kickoff_booked',side_effect=kick), \
             patch.object(G,'attempt_extra_point') as xp:
            score,drives,ending=G.play_overtime(self.off,self.deff,dict(home=20,away=20),self.rng,None,None,None,RATE)
        self.assertEqual(score,dict(home=26,away=23));self.assertEqual(ending,'decided')
        xp.assert_not_called()

    def test_return_narration_scoring_and_recovery_team(self):
        league=NS(player=lambda pid:NS(name='Returner'))
        for kind,scoring,recovery in [('punt','B','A'),('kickoff','A','B')]:
            line=ticker.play_line(league,dict(type=kind,touchdown=True,new_yardline=0,ret=70,carrier='r'),'A','B')
            self.assertIn('TOUCHDOWN, '+scoring,line['text'])
            line=ticker.play_line(league,dict(type=kind,fumble=True,fumble_lost=True,new_yardline=50,ret=20),'A','B')
            self.assertEqual(line['text'].count('FUMBLE'),1)
            self.assertIn('recovered by '+recovery,line['text'])

    def test_game_day_box_and_turnover_owner(self):
        import gameday
        import game_recap
        dr,b=self.punt_drive(self.punt(touchdown=False,fumble=True,fumble_lost=True,
                            fumble_by='pr',recoverer='cov',ret=10,new_yardline=60))
        names={pid:NS(pid=pid,name=pid) for pid in b.p}
        league=NS(week=1,player=lambda pid:names.get(pid),teams={
            'GB':NS(roster=[p for pid,p in names.items() if pid!='pr']),
            'MIN':NS(roster=[names['pr']])})
        res=dict(home=0,away=0,drives=[('home',dr)],overtime=False)
        saved=gameday.capture(league,[('GB','MIN',res,b)],'GB')['game']
        self.assertEqual(saved['team_stats']['GB']['turnovers'],0)
        self.assertEqual(saved['team_stats']['MIN']['turnovers'],1)
        self.assertEqual(saved['box']['returns'][0]['team'],'MIN')
        self.assertEqual(saved['box']['returns'][0]['pr_yds'],10)
        self.assertEqual(game_recap.return_summary(res,'away')['lost'],1)
        self.assertEqual(game_recap.return_summary(res,'home')['lost'],0)

    def test_return_stats_survive_season_postseason_and_json(self):
        import json
        from league import League
        career={}
        p=NS(team='GB',pos='WR',record_season=lambda yr,line:career.update({yr:dict(line)}))
        league=NS(stats={},post_stats={},game_stats={},player=lambda pid:p)
        b=G.StatBook();KR.book_return(b,'kr',dict(returner='ret',ret=95,touchdown=True))
        League.record_stats(league,2027,'ret',b.p['ret'],game='2027-1-GB-MIN')
        League.record_stats(league,2027,'ret',b.p['ret'],postseason=True,game='2027-20-GB-MIN')
        saved=json.loads(json.dumps(dict(stats=league.stats,post=league.post_stats,career=career)))
        for field in ('stats','post','career'):
            row=saved[field]['2027'] if field=='career' else saved[field]['2027']['ret']
            self.assertEqual((row['kr_td'],row['kr_yds']),(1,95))

    def test_playoff_overtime_continues_downs_and_preserves_all_drives(self):
        seen=[];book=G.StatBook()
        def drive(*args,**kw):
            G.LAST_KICKOFF.clear();seen.append((args,kw))
            dr=G.Drive(*args[:7]);dr.clock=0
            if len(seen)==1:
                dr.result='End of half';dr.down=3;dr.togo=7;dr.yardline=25
                book.special('pr','ret',ret=12)
            elif len(seen)==2:
                dr.result='Field goal';dr.points=3;dr.clock=200
            else:
                dr.result='Turnover';dr.clock=180
            return dr
        with patch.object(G,'run_drive',side_effect=drive), \
             patch.object(G,'kickoff_booked',return_value=dict(touchback=True,new_yardline=65)):
            score,drives,ending=G.play_overtime(self.off,self.deff,dict(home=20,away=20),self.rng,None,None,None,RATE,playoffs=True,book=book)
        self.assertEqual(score,dict(home=20,away=23))
        self.assertEqual(len(drives),3)
        self.assertEqual(seen[1][0][2:4],(25,900))
        self.assertEqual(seen[1][1]['start_state'],(3,7))
        self.assertEqual(book.p['ret']['pr_yds'],12)

    def test_opening_overtime_return_td_still_gives_other_team_possession(self):
        original=G.run_drive;seen=[]
        def drive(*args,**kw):
            seen.append(kw['pos'])
            if G.pending_kick_outcome():return original(*args,**kw)
            G.LAST_KICKOFF.clear()
            dr=G.Drive(*args[:7]);dr.clock=200;dr.result='Turnover';return dr
        kicks=iter([dict(touchback=False,new_yardline=0,touchdown=True,ret=95),dict(touchback=True,new_yardline=65)])
        def kick(*a,**kw):
            r=next(kicks);G.LAST_KICKOFF['r']=r;return r
        with patch.object(G,'run_drive',side_effect=drive), patch.object(G,'kickoff_booked',side_effect=kick), \
             patch.object(G,'two_point_decision',return_value=False), \
             patch.object(G,'attempt_extra_point',return_value=dict(type='extra_point',made=True,points=1)):
            score,drives,ending=G.play_overtime(self.off,self.deff,dict(home=20,away=20),self.rng,None,None,None,RATE)
        self.assertEqual(seen,['away','home'])
        self.assertEqual(score,dict(home=20,away=27))

    def test_register_does_not_misclassify_return_scores(self):
        from calibrate import Collector
        dr,b=self.punt_drive(self.punt())
        kick=NS(result='Touchdown',return_only=True,first_downs=0,plays=0,
                log=[dict(type='kickoff',touchdown=True,touchback=False)])
        collector=Collector();collector.add(dict(home=7,away=7,drives=[('home',dr),('away',kick)]))
        self.assertEqual(collector.drives_total,1)
        self.assertEqual(collector.res['Punt'],1)
        self.assertEqual(collector.res['Touchdown'],0)
        self.assertEqual(collector.res['Defensive touchdown'],0)


if __name__=='__main__':unittest.main()
