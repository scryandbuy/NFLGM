import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import gameday
import session


class BroadcastGameDay(unittest.TestCase):
    def setUp(self):
        self.players = {f'p{i}': NS(pid=f'p{i}', name=f'Player {i}', pos='WR') for i in range(12)}
        self.league = NS(player=self.players.get, teams={
            'GB': NS(roster=list(self.players.values())[:10], _elevated=[self.players['p10']]),
            'DET': NS(roster=[self.players['p11']])})
        self.book = NS(p={pid:dict(tgt=1,rec=0,pass_att=1,rush_att=1,tackles=1,sacks=.5) for pid in self.players})
        self.states = {a:NS(snap_counts={'offense':dict(total=20,players={'p0':10})},
                           last_snap_counts={'defense':dict(total=40,players={'p0':30})}) for a in ('GB','DET')}

    def test_all_participants_and_zero_catch_targets_keep_identity(self):
        box=gameday.box_score(self.league,self.book,'GB','DET',{})
        for category in ('passing','rushing','receiving','defense'):
            self.assertEqual(len(box[category]),12)
            self.assertEqual(len({r['pid'] for r in box[category]}),12)
        self.assertEqual(box['receiving'][0]['rec'],0)
        self.assertEqual(box['defense'][0]['sk'],.5)
        self.assertNotIn('snaps',box)

    def test_fresh_stats_are_read_only_and_use_correct_snap_snapshot(self):
        self.book.p['p0'].update(pb_snaps=10,pb_wins=8,rb_snaps=4,rb_wins=3,
            fg_att=3,fg_made=2,xp_att=4,xp_made=4,fg_long=51,
            punts=2,punt_yds=100,punt_net_yds=72,punt_in20=1,punt_tb=1,
            kr=2,kr_yds=45,kr_td=0,pr=3,pr_yds=50,pr_td=1)
        before=copy.deepcopy(self.book.p)
        live=gameday.box_score(self.league,self.book,'GB','DET',{},self.states,True)
        final=gameday.box_score(self.league,self.book,'GB','DET',{},self.states,False)
        self.assertEqual(live['snaps'][0]['pct'],50)
        self.assertEqual(final['snaps'][0]['pct'],75)
        self.assertEqual(live['blocking'][0]['pb_pct'],80)
        self.assertEqual(live['kicking'][0]['fg'],'2/3')
        self.assertEqual(live['punting'][0]['net'],36)
        self.assertEqual(live['returns'][0]['pr_td'],1)
        self.assertEqual(before,self.book.p)

    def test_injury_and_player_ids_survive_ticker(self):
        line=gameday.write_play(self.league,dict(type='injury',pid='p11',pos='CB',kind='ankle',weeks=2,side='def',clock=140),None,'GB','DET')
        self.assertEqual(line['injury']['team'],'DET')
        self.assertEqual(line['injury']['pid'],'p11')
        line=gameday.write_play(self.league,dict(type='complete',passer='p0',target='p1',yards=12,yardline=52,down=1,ydstogo=10,clock=140),'p0','GB','DET')
        self.assertEqual(line['target_pid'],'p1')
        self.assertEqual(line['yardline'],52)

    def test_capture_reads_health_injury_identity_including_special_teams(self):
        self.league.week=5
        result=dict(home=0,away=0,drives=[],injuries=[dict(player='p0',kind='ankle',source='special_teams')])
        record=gameday.capture(self.league,[('GB','DET',result,self.book)],'GB')['game']
        self.assertEqual(record['injuries'],[dict(pid='p0',name='Player 0',pos='WR',kind='ankle',team='GB',status='Out for this game')])

    def test_live_field_uses_postplay_state_and_hides_dead_ball_spot(self):
        dr=NS(yardline=44.5,down=2,togo=4.5,clock=2800,quarter=1,result=None)
        lv=dict(home='GB',away='DET',done=False,at='snap',halftime_open=False,current=dr,pos='home',book=self.book)
        runner=NS(live=lv,states=self.states,last_games=[],live_partial=lambda:dict(home=7,away=0))
        s=NS(L=NS(phase='regular'),runner=runner,user_team='GB')
        with patch('gameday.capture',return_value={'game':{}}), patch('views.gameday',return_value={}):
            v=session.Session.gameday_view(s)
            self.assertEqual(v['live']['field']['yardline'],44.5)
            self.assertEqual(v['live']['field']['down'],2)
            self.assertEqual(v['live']['clock'],'1:40')
            dr.result='Punt'
            v=session.Session.gameday_view(s)
            self.assertNotIn('field',v['live'])
            self.assertIsNone(v['live']['possession'])
            lv['halftime_open']=True
            self.assertNotIn('field',session.Session.gameday_view(s)['live'])


if __name__=='__main__': unittest.main()
