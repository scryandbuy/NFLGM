import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import standings_and_seeding as S
import season
import views
import gameplan_week as GW

class TiebreakTests(unittest.TestCase):
    def state(self, names=('GB','MIN','DET','CHI'), games=()):
        return S.Season.live(dict.fromkeys(names,'United North'),dict.fromkeys(names,'United'), games,2028)

    def test_equal_points_share_rank(self):
        s=self.state()
        s.pf.update(GB=100,MIN=100,DET=90,CHI=80)
        s.pa.update(GB=50,MIN=50,DET=60,CHI=70)
        self.assertEqual(s.rank_all('GB'),-2)
        self.assertEqual(s.rank_all('MIN'),-2)
        self.assertEqual(s.rank_all('DET'),-6)

    def test_strength_uses_aggregate_records_and_repeat_opponents(self):
        s=self.state()
        s.rec['MIN']=[1,0,0]; s.rec['DET']=[1,3,0]
        s.opps['GB']=['MIN','DET','DET']
        self.assertAlmostEqual(s.sos('GB'),3/9)
        s.games=[('GB','MIN',7,0),('GB','DET',7,0)]
        self.assertAlmostEqual(s.sov('GB'),2/5)

    def test_common_game_minimum_is_context_specific(self):
        s=self.state(games=[('GB','DET',7,0),('MIN','DET',0,7)])
        self.assertIsNone(s.common_pct('GB',['GB','MIN']))
        self.assertEqual(s.common_pct('GB',['GB','MIN'],minimum=1),1)
        with patch.object(s,'h2h_pct',return_value=None), patch.object(s,'div_pct',return_value=.5):
            self.assertEqual(S.break_tie(s,['MIN','GB'],True)[0],'GB')

    def test_restart_includes_previously_eliminated_clubs(self):
        s=self.state(('A','B','C'))
        def h2h(team,group):
            if len(group)==3: return 1 if team in ('A','B') else 0
            return 1 if team == ('A' if 'A' in group else 'C') else 0
        with patch.object(s,'h2h_pct',side_effect=h2h):
            self.assertEqual(S.break_tie(s,['A','B','C'],True),['A','C','B'])

    def test_conference_net_points_excludes_other_conference(self):
        s=self.state(games=[('GB','MIN',10,7),('GB','CHI',0,40)])
        s.CONF['CHI']='Continental'
        self.assertEqual(s.net_conf('GB'),3)
        self.assertEqual(s.net_all('GB'),-37)

    def test_net_touchdowns_before_draw(self):
        s=self.state(('GB','MIN'))
        s.net_touchdowns={'GB':1,'MIN':3}
        self.assertEqual(S.break_tie(s,['GB','MIN'],True),['MIN','GB'])

    def test_wildcard_preserves_original_division_order(self):
        s=self.state(('A','B','C','D'))
        # C was below B in the original division tie, even if a new two-team
        # comparison after removing the champion would put C ahead.
        with patch.object(S,'division_ranks',return_value={'A':1,'B':2,'C':3,'D':4}), patch.object(S,'order',side_effect=lambda st,ts,same:list(reversed(ts)) if same else list(ts)):
            self.assertEqual(S.seed_conference(s,'United',3),['A','B','C','D'])

    def test_draw_stable_and_independent_of_input_order(self):
        s=self.state()
        a=S.break_tie(s,s.teams,True)
        self.assertEqual(a,S.break_tie(s,list(reversed(s.teams)),True))
        self.assertEqual(a,S.break_tie(self.state(),s.teams,True))

    def test_header_and_overview_use_head_to_head(self):
        games=[(1,'GB','MIN',7,14),(2,'CHI','GB',0,7),(2,'DET','MIN',7,0)]
        teams={a:NS(abbr=a,division='United North',conf='United',record=[1,1,0]) for a in ('GB','MIN','DET','CHI')}
        L=NS(teams=teams,schedule=games,year=2028,week=3)
        rank=season.StandingsView(L).standings()['GB']['div_rank']
        self.assertTrue(views._division_place(L,'GB').startswith(str(rank)))
        with patch.object(views,'club',side_effect=lambda a:{'abbr':a}), patch.object(views,'_form',return_value=[]):
            rows=views._division_standings(L,'GB')['rows']
        self.assertLess([r['club']['abbr'] for r in rows].index('MIN'),[r['club']['abbr'] for r in rows].index('GB'))

    def test_touchdowns_recorded_and_missing_old_games_not_invented(self):
        L=NS(year=2028,schedule=[(1,'MIN','GB',7,14)],teams={a:NS(division='N',conf='U') for a in ('GB','MIN')})
        res={'drives':[('home',NS(result='Touchdown',log=[])),('away',NS(result='Defensive touchdown',log=[])),('away',NS(result='Touchdown',log=[]))]}
        GW.record_team_performance(L,'GB','MIN',1,res)
        self.assertEqual(season.StandingsView(L).season_state().net_td('GB'),1)
        L.team_game_stats={}
        self.assertIsNone(season.StandingsView(L).season_state().net_td('GB'))

if __name__=='__main__': unittest.main()
