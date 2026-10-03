"""Race-aware patience and fair-price seller shopping, not forced liquidation."""
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import trade_engine as TE
import trades as TR
import roster_needs as RN
import targets as TG
from gm_engine import GM
from league import League, Team, Player
from cap_engine import Contract


def league_fixture():
    league=League(2026);league.user_team='T15';league.week=9
    for i in range(16):
        abbr=f'T{i:02}'
        team=Team(abbr,f'D{i//4}','United',gm=GM())
        team.league=league;team.record=[5,3,0];league.teams[abbr]=team
    league.set_phase('regular')
    team=league.teams['T00'];team.record=[2,6,0]
    counts=dict(QB=2,HB=3,FB=1,WR=6,TE=3,LT=2,LG=2,C=2,RG=2,RT=2,
                LEDG=2,REDG=2,DT=4,MIKE=2,WILL=2,SAM=2,CB=5,FS=2,SS=2,K=1,P=1,LS=1)
    for pos,count in counts.items():
        for i in range(count):
            ratings={k:78 for k in TG.DEPTH_WEIGHTS[pos]}
            p=Player(f'{pos}{i}',f'{pos} {i}',pos,24,ratings,team=team.abbr,contract=Contract(3,[1]*3))
            league.players[p.pid]=p;team.roster.append(p)
    vet=league.players['WR0'];vet.age=29;vet.contract=Contract(1,[5])
    vet.ratings={k:82 for k in TG.DEPTH_WEIGHTS['WR']}
    team.sync_cap()
    return league,team,vet


def ctx(team):return dict(team.ctx(),**TE.race_context(team))


class TradeWindows(unittest.TestCase):
    def test_small_record_does_not_create_panic_or_buying(self):
        league,team,_=league_fixture()
        persona=TE.GM_ARCHETYPES['balanced']
        for record in ([0,1,0],[0,3,0],[3,0,0]):
            team.record=record
            self.assertEqual(TE.window(ctx(team)),'middling')
            self.assertEqual(TE.situational_shift(persona,ctx(team)),persona)

    def test_wait_six_games_before_selling(self):
        _,team,_=league_fixture()
        team.record=[0,5,0]
        self.assertEqual(TE.window(ctx(team)),'middling')
        team.record=[0,6,0]
        self.assertIn(TE.window(ctx(team)),('retooling','rebuilding'))

    def test_weak_division_and_wildcard_race_each_protect_losing_team(self):
        league,team,_=league_fixture()
        for t in league.teams.values():
            if t.division==team.division and t is not team:t.record=[3,5,0]
        self.assertEqual(TE.window(ctx(team)),'middling')
        for t in league.teams.values():
            if t is not team:t.record=[3,5,0]
        league.teams['T01'].record=[7,1,0]
        c=ctx(team)
        self.assertGreater(c['division_gap'],1)
        self.assertLessEqual(c['wildcard_gap'],1)
        self.assertEqual(TE.window(c),'middling')

    def test_ties_and_byes_use_games_behind_not_raw_wins(self):
        league,team,_=league_fixture();team.record=[2,4,2]
        league.teams['T01'].record=[4,3,0]
        c=TE.race_context(team)
        self.assertEqual(c['games_played'],8)
        self.assertEqual(c['division_gap'],2)
        league.teams['T02'].record=[3,3,2];league.teams['T03'].record=[3,4,1]
        self.assertEqual(TE.race_context(team)['division_gap'],1.5)

    def test_contender_and_genuine_seller_receive_opposite_pick_priorities(self):
        _,team,_=league_fixture()
        seller=ctx(team)
        team.record=[6,2,0];buyer=ctx(team)
        pick=dict(kind='pick',pick=80,years_out=1)
        self.assertGreater(TE.team_price(pick,seller,50),TE.team_price(pick,buyer,50))
        self.assertEqual(TE.window(buyer),'contending')

    def test_unknown_race_is_conservative_and_fixture_safe(self):
        self.assertEqual(TE.race_context(N())['games_played'],0)
        c=dict(win_pct=.2,avg_age=30,phase='regular',games_played=8)
        self.assertEqual(TE.window(c),'middling')
        self.assertEqual(TE.window(dict(win_pct=.2,avg_age=30)),'rebuilding')

    def test_genuine_seller_shops_replaceable_expiring_veteran(self):
        league,team,vet=league_fixture();before=RN.assess(team)
        self.assertIn(vet,TR.seller_veterans(league,team,before))
        def asset(_l,_t,p,*args,**kw):
            return dict(pid=p.pid,obj=p,trade_value=10,age=p.age,pos=p.pos,kind='player')
        with patch.object(TR,'player_asset',side_effect=asset):
            assets,_=TR.surplus_and_needs(league,team,{},np.random.default_rng(3))
        offered=next(a for a in assets if a['pid']==vet.pid)
        self.assertTrue(offered['seller_veteran'])
        self.assertEqual(offered['trade_value'],10)
        self.assertNotIn('cap_casualty',offered)
        self.assertNotIn('ask',offered)

    def test_young_core_long_control_qb_and_unsigned_rights_are_not_shopped(self):
        for change in ('young','long','quarterback','unsigned','tendered'):
            league,team,vet=league_fixture()
            if change=='young':vet.age=25
            if change=='long':vet.contract=Contract(4,[1]*4)
            if change=='quarterback':vet.pos='QB'
            if change=='unsigned':vet.contract=None
            if change=='tendered':vet.fa_class='tendered'
            self.assertNotIn(vet,TR.seller_veterans(league,team,RN.assess(team)))

    def test_hurt_backups_and_ir_cannot_make_veteran_expendable(self):
        for injury in ('out','ir'):
            league,team,vet=league_fixture()
            for p in list(team.roster):
                if p.pos=='WR' and p is not vet:
                    if injury=='out':p.out_until=99
                    else:team.ir.append(p)
            healthy=[p for p in team.active() if p.out_until is None]
            self.assertNotIn(vet,TR.seller_veterans(league,team,RN.assess(team,healthy)))

    def test_bad_record_does_not_override_caps_or_user_control(self):
        for blocked in ('cap','user','early','deadline','race'):
            league,team,vet=league_fixture()
            if blocked=='cap':team.cap.cap=1
            if blocked=='user':league.user_team=team.abbr
            if blocked=='early':team.record=[0,3,0]
            if blocked=='deadline':league.week=10
            if blocked=='race':team.record=[4,4,0]
            self.assertEqual(TR.seller_veterans(league,team,RN.assess(team)),[])

    def test_direct_cpu_run_is_closed_after_deadline(self):
        league,_,_=league_fixture();league.week=10
        with patch.object(TR.VAL,'pool_from_league',side_effect=AssertionError('must stop before market work')):
            self.assertEqual(TR.run(league,np.random.default_rng(9)),[])

    def test_young_core_can_be_asked_about_at_a_premium(self):
        league,team,vet=league_fixture();vet.age=25;vet.contract=Contract(3,[3]*3)
        with patch.object(TR,'player_asset',side_effect=lambda l,t,p,*a,**k:dict(pid=p.pid,trade_value=10)):
            offers=TR.stars_at(league,team,{},np.random.default_rng(1),'WR')
        self.assertTrue(TR._young_core(vet))
        offer=next(a for a in offers if a['pid']==vet.pid)
        self.assertTrue(offer['star'])
        self.assertGreater(offer['ask'],1.0)

    def test_contender_quarterback_and_elite_receiver_can_be_asked_about(self):
        league,team,receiver=league_fixture();team.record=[6,2,0]
        quarterback=league.players['QB0']
        for p in (quarterback,receiver):
            p.age=26
            p.contract=Contract(3,[10]*3)
            p.ratings={k:96 for k in TG.DEPTH_WEIGHTS[p.pos]}
        with patch.object(TR,'player_asset',side_effect=lambda l,t,p,*a,**k:dict(pid=p.pid,trade_value=30)):
            for group,p in (('QB',quarterback),('WR',receiver)):
                offers=TR.stars_at(league,team,{},np.random.default_rng(1),group)
                offer=next(a for a in offers if a['pid']==p.pid)
                self.assertGreater(offer['ask'],1.0)

    def test_ui_and_cpu_context_use_same_window(self):
        _,team,_=league_fixture()
        self.assertEqual(team.ctx()['games_played'],8)
        self.assertEqual(TE.window(team.ctx()),TE.window(TR.context(team)))

    def test_shopping_is_read_only(self):
        league,team,vet=league_fixture();before=league.save()
        self.assertIn(vet,TR.seller_veterans(league,team,RN.assess(team)))
        self.assertEqual(league.save(),before)


if __name__=='__main__':unittest.main()
