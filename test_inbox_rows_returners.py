import unittest
from types import SimpleNamespace as NS
import inbox
import rosters as R
import game
from unittest.mock import Mock, patch
import numpy as np


def player(pid,pos,grade,ret):
    import targets as TG
    p=dict.fromkeys(TG.DEPTH_WEIGHTS[pos],grade)
    p.update(pid=pid,pos=pos,kick_ret_rating=ret,speed_rating=ret,agility_rating=ret,juke_move_rating=ret,carry_rating=ret)
    return p


class InboxRowsTests(unittest.TestCase):
    def test_saved_signing_digest_keeps_one_player_per_row(self):
        league=NS(players={})
        body='Two signed. J. Doe (WR, 84) to GB for $10.5m x 2; Alex Reed (HB, 80) to MIN for $3.2m x 1.'
        rows=inbox.body_rows(league,dict(body=body))
        self.assertEqual(rows,['Two signed.','J. Doe (WR, 84) to GB for $10.5m x 2','Alex Reed (HB, 80) to MIN for $3.2m x 1.'])

    def test_injury_and_contract_lists_preserve_parenthetical_details(self):
        league=NS(players={})
        body='John Smith (WR) is out 2 weeks (ankle). Bob Jones (HB) is out a week (knee).'
        self.assertEqual(len(inbox.body_rows(league,dict(body=body))),2)
        rows=inbox.body_rows(league,dict(body='Deals up: Smith (WR, 84; $9.5m), Jones (HB, 80; $2m).'))
        self.assertEqual(rows,['Deals up:','Smith (WR, 84; $9.5m)','Jones (HB, 80; $2m).'])

    def test_plain_prose_and_explicit_rows(self):
        league=NS(players={})
        body='Your owner expects improvement. You have $10.5m in cap room.'
        self.assertEqual(inbox.body_rows(league,dict(body=body)),[body])
        self.assertEqual(inbox.body_rows(league,dict(body=body,payload={'body_rows':['First player','Second player']})),['First player','Second player'])

    def test_injury_prose_uses_full_reading_width(self):
        league=NS(players={})
        body='His hands will be off Sunday; the risk of making the elbow worse is small. The trainers would let him go; Penix Jr. is the drop-off.'
        self.assertEqual(inbox.body_rows(league,dict(kind='injury_decision',body=body)),[body])


class ReturnerPriorityTests(unittest.TestCase):
    def setUp(self):
        self.wr1=player('wr1','WR',99,99);self.wr2=player('wr2','WR',85,90)
        self.hb1=player('hb1','HB',99,99);self.hb2=player('hb2','HB',75,80)
        self.cb=player('cb','CB',70,75)
        self.depth={'WR':[self.wr1,self.wr2],'HB':[self.hb1,self.hb2],'CB':[self.cb]}
        self.rows=[p for men in self.depth.values() for p in men]

    def test_automatic_roles_protect_primary_starters(self):
        for slot in ('KR','PR'):
            self.assertEqual(R._returner(self.rows,{},slot,self.depth)['pid'],'wr2')
            self.assertEqual({p['pid'] for p in R.return_order(self.rows,{},slot,self.depth)[-2:]},{'wr1','hb1'})

    def test_user_pins_override_protection(self):
        self.assertEqual(R._returner(self.rows,{'KR':['hb1']},'KR',self.depth)['pid'],'hb1')
        self.assertEqual(R._returner(self.rows,{'PR':['wr1']},'PR',self.depth)['pid'],'wr1')

    def test_injury_promotions_change_return_duties_and_honor_backup_pins(self):
        ros=dict(depth=self.depth,depth_pins={},kr=self.wr2,pr=self.wr2)
        self.assertEqual(game.returner_for(ros,NS(out={'wr1'}),None)['pid'],'hb2')
        ros['depth_pins']={'KR':['wr1','cb']}
        self.assertEqual(game.returner_for(ros,NS(out={'wr1'}),None)['pid'],'cb')

    def test_emergency_uses_healthy_primary_but_never_injured_player(self):
        ros=dict(depth=self.depth,depth_pins={},kr=self.wr2)
        self.assertIn(game.returner_for(ros,NS(out={'wr2','hb2','cb'}),None)['pid'],('wr1','hb1'))
        self.assertEqual(game.returner_for(ros,NS(out={p['pid'] for p in self.rows}),None),{})

    def test_all_seed_teams_avoid_primary_starters(self):
        league=R.load_league()
        self.assertEqual(len(league),32)
        for team,ros in league.items():
            primary={ros['depth'][pos][0]['pid'] for pos in ('HB','WR') if ros['depth'].get(pos)}
            for slot in ('kr','pr'):
                self.assertNotIn(ros[slot]['pid'],primary,(team,slot))

    def test_punt_uses_healthy_replacement_and_credits_his_stats(self):
        ros=dict(depth=self.depth,depth_pins={},pr=self.wr2)
        state=NS(out={'wr2'},new_series=lambda:None,adjust=lambda *args:None)
        original=game.Drive
        def fourth(*args,**kwargs):
            drive=original(*args,**kwargs);drive.down=4;return drive
        book=Mock();book._get.return_value={}
        result=dict(type='punt',how='return',ret=7,new_yardline=75,touchback=False)
        with patch.object(game,'Drive',fourth), patch.object(game,'fourth_down_decision',return_value='punt'), patch('events.special_teams_penalty_check',return_value=None), patch.object(game,'punt',return_value=result) as kick:
            game.run_drive({'p':{'pid':'punter'}},ros,70,600,4,0,np.random.default_rng(4),None,None,None,None,book=book,def_state=state)
        self.assertEqual(kick.call_args.args[2]['pid'],'hb2')
        book.special.assert_any_call('pr','hb2',ret=7)

    def test_chart_and_game_rosters_agree_for_all_teams(self):
        import session, views_club
        s=session.Session.new('GB',seed=91)
        for abbr in s.L.teams:
            view=views_club.depth(s,s.L,abbr)
            ros=s.L.roster_dicts(abbr)
            for col in view['sides']['specialists']:
                if col['pos'] in ('KR','PR'):
                    self.assertEqual(col['slots'][0]['pid'],ros[col['pos'].lower()]['pid'],(abbr,col['pos']))


if __name__=='__main__':unittest.main()
