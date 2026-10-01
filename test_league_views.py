import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import views_league as V
import advanced_stats as AS

class LeagueViews(unittest.TestCase):
    def setUp(self):
        self.players={}
        self.L=N(year=2027,week=0,stats={2026:{}},teams={},schedule=[],history={},awards={},almanac={},transactions=[])
        self.L.player=lambda pid:self.players.get(pid)
        for a,div in [('GB','United North'),('MIN','United North'),('KC','Continental West')]:
            self.L.teams[a]=N(abbr=a,division=div,roster=[],record=[0,0,0],gm=N(name='Replacement',prestige=50))
        self.patches=[patch.object(V,'rail',lambda *a:{}),patch.object(V,'club',lambda a:dict(abbr=a,name=a))]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in self.patches])
    def player(self,pid,pos,line,team='GB'):
        p=N(pid=pid,name=pid,pos=pos,team=team,career={2026:dict(line,team='GB',pos=pos)})
        self.players[pid]=p;self.L.stats[2026][pid]=line;self.L.teams[team].roster.append(p)
        return p
    def test_filter_before_limit_and_epa_order(self):
        for i in range(40):self.player(str(i),'CB',dict(snaps=1000,def_plays=300,def_epa=i-20))
        self.player('lineman','LT',dict(snaps=900,pb_snaps=400,pb_wins=300))
        v=V.stats(None,self.L,'GB',2026)
        self.assertEqual([r['pid'] for r in v['tables']['blocking']['rows']],['lineman'])
        box=next(b for b in v['advanced'] if b['title']==AS.DEF_EPA_LABEL)
        self.assertEqual([r['pid'] for r in box['rows']],[str(i) for i in range(39,31,-1)])
        self.assertIn('Higher is better',box['note'])
    def test_defensive_ranking_matches_booked_sign_and_preserves_negatives(self):
        from collections import defaultdict
        import copy
        lines=defaultdict(lambda: defaultdict(float))
        book=N(_get=lambda pid: lines[pid])
        for pid,epa in [('allowed',2.2),('stopped',-2.2)]:
            AS.book_play(book,{'type':'run'}, {'qb':{'pid':'qb'},'rb':{'pid':'rb'}},
                         {'dl':[{'pid':pid}]},epa)
            self.player(pid,'DT',dict(lines[pid]))
        before=copy.deepcopy(self.L.stats)
        ranked=AS.leaders(self.L,2026,'def_epa_per_play')
        self.assertEqual([p.pid for p,_,_ in ranked],['stopped','allowed'])
        self.assertAlmostEqual(ranked[0][1],0.2)
        self.assertAlmostEqual(ranked[1][1],-0.2)
        self.assertEqual(self.L.stats,before)
        self.assertLess(AS.line_metrics({'pass_plays':10,'pass_epa':-1,
                                      'pass_cmp':4,'xcomp':5,'cpoe_att':10})['cpoe'],0)
    def test_snapshot_advanced_leaders_are_rebuilt_without_mutating_history(self):
        import copy
        for i in range(12):self.player(str(i),'CB',dict(def_plays=300,def_epa=i-6))
        self.L.history={'2026':{'stats':{'advanced':[{'title':'Defensive EPA per Play','rows':[]}],
                                       'team':[{'kept':True}]}}}
        before=copy.deepcopy(self.L.history)
        view=V.stats(None,self.L,'GB',2026)
        self.assertEqual(view['advanced'][0]['rows'][0]['pid'],'11')
        self.assertEqual(view['team'],[{'kept':True}])
        self.assertEqual(self.L.history,before)
    def test_snapshot_without_raw_lines_does_not_keep_wrong_defensive_leaders(self):
        self.L.stats={}
        self.L.history={'2026':{'stats':{'advanced':[{'title':'Defensive EPA per Play','rows':[]},
                                                   {'title':'EPA per Dropback','rows':[]}]}}}
        view=V.stats(None,self.L,'GB',2026)
        self.assertEqual([b['title'] for b in view['advanced']],['EPA per Dropback'])
    def test_defensive_player_stats_and_career_explain_shared_metric(self):
        from views_club import _season_line
        for pos in ['DT','CB']:
            p=self.player(pos,pos,dict(def_plays=300,def_epa=-6))
            view=_season_line(self.L,p,2026)
            self.assertEqual(view['cols'][-1],AS.DEF_EPA_LABEL)
            self.assertIn('not an individual grade',view['epa_note'])
            self.assertEqual(view['row'][-1],'-0.02')
    def test_old_team_totals_and_identity(self):
        self.player('qb','QB',dict(pass_yds=3400,pass_att=400,pass_plays=400),team='MIN')
        self.L.history={'2026':{'schedule':{'all_games':[dict(week=w,done=True,away={'abbr':'MIN'},home={'abbr':'GB'},hp=10,ap=5) for w in range(1,18)]}}}
        v=V.stats(None,self.L,'GB',2026)
        row=next(r for r in v['team'] if r['club']['abbr']=='GB')
        self.assertEqual((row['pf'],row['pa'],row['pyds']),(10,5,200))
        self.assertEqual(v['tables']['passing']['rows'][0]['team'],'GB')
    def test_historical_awards(self):
        self.player('winner','QB',dict(pass_yds=3400),team='MIN')
        self.L.awards={2026:dict(mvp='winner',coty='GB',all_pro_1=['winner'])}
        self.L.almanac={'coaching':{'GB':[dict(name='Original',frm=2026,to=2026)]}}
        v=V.awards(None,self.L,'GB',2026)
        self.assertEqual(v['rows'][0]['team']['abbr'],'GB')
        self.assertEqual(v['first'][0]['team']['abbr'],'GB')
        self.assertEqual(next(r['name'] for r in v['rows'] if r['code']=='COTY'),'Original')
        self.L.almanac={}
        self.assertEqual(next(r['name'] for r in V.awards(None,self.L,'GB',2026)['rows'] if r['code']=='COTY'),'Coach name not retained')
    def test_second_team_fullback_is_kept_in_awards_view(self):
        self.player('first_fb','FB',dict(snaps=200),team='GB')
        self.player('second_fb','FB',dict(snaps=150),team='MIN')
        self.players['second_fb'].career[2026]['team']='MIN'
        self.L.awards={2026:dict(all_pro_1=['first_fb'],all_pro_2=['second_fb'])}
        second=V.awards(None,self.L,'GB',2026)['second']
        self.assertEqual([(r['pid'],r['pos'],r['team']['abbr']) for r in second],
                         [('second_fb','FB','MIN')])
    def test_staff_exit_reason_is_reported_accurately(self):
        self.assertEqual(V._staff_departure_action('new head coach brought his own'),'Replaced')
        self.assertEqual(V._staff_departure_action('unit bottom-eight two years running'),'Fired')
        self.assertEqual(V._staff_departure_action('contract up, walked'),'Departed')
        self.assertEqual(V._staff_departure_action('hired as head coach by MIA'),'Promoted')
    def test_head_coach_exit_and_hire_survive_save_and_reach_carousel(self):
        import copy
        import numpy as np
        import coaching_pool as CP
        import league as LG
        L=LG.build_league(rng=np.random.default_rng(11))
        t=L.teams['MIA']; old=t.gm.name
        hired=copy.deepcopy(t.gm); hired.name='New Coach'; hired.age=45
        with patch.object(CP,'owner_hire',return_value=(hired,{})), patch('position_change.convert_misfits',return_value=[]):
            CP.fire_and_hire(L,t,np.random.default_rng(12))
        coach_moves=[x for x in L.transactions if x.get('team')=='MIA' and x.get('kind') in ('fire','gm_change')]
        self.assertEqual([(x['kind'],x.get('coach') or x.get('hired')) for x in coach_moves],
                         [('fire',old),('gm_change','New Coach')])
        L.log('staff_out',team='MIA',role='oc',name='Former OC',why='released by the user')
        L.log('staff_in',team='MIA',role='oc',name='New OC',why='hired by the user')
        loaded=LG.League.load(L.save())
        rows=[x for x in V.coaching(None,loaded,'GB')['carousel'] if x['club']['abbr']=='MIA']
        self.assertEqual([(x['action'],x['person']) for x in rows[:4]],
                         [('Hired','New OC'),('Released','Former OC'),
                          ('Hired','New Coach'),('Fired',old)])
        tx=[x for x in V.transactions(None,loaded,'GB')['rows'] if x['team'] and x['team']['abbr']=='MIA']
        self.assertTrue({'staff_in','staff_out','fire','gm_change'}.issubset({x['kind'] for x in tx}))
    def test_snapshots_preferred(self):
        self.L.history={'2026':{'stats':dict(team=[{'kept':True}]),'awards':dict(rows=[{'name':'Original'}])}}
        self.assertEqual(V.stats(None,self.L,'GB',2026)['team'],[{'kept':True}])
        self.assertEqual(V.awards(None,self.L,'GB',2026)['rows'],[{'name':'Original'}])
    def test_both_trade_sides(self):
        self.L.transactions=[dict(kind='trade',year=2027,a='KC',b='GB',a_sends=[],b_sends=[])]
        row=V.transactions(None,self.L,'GB')['rows'][0]
        self.assertTrue(row['mine']);self.assertIn('United North',row['divisions'])
    def test_transactions_keep_coaching_ledger_and_legacy_departure(self):
        self.L.transactions=[dict(kind='gm_change',year=2027,team='GB',hired='New Coach'),
                             dict(kind='staff_out',year=2027,team='MIN',role='dc',name='Old DC',why='unit bottom-eight two years running')]
        with patch('almanac.coaching_history',return_value=[dict(name='Former Coach',to=2027)]):
            view=V.transactions(None,self.L,'GB')
            self.assertEqual(view['coaching_moves'],V._coaching_moves(self.L))
        self.assertEqual([(x['action'],x['person']) for x in view['coaching_moves']],
                         [('Fired','Old DC'),('Hired','New Coach'),('Departed','Former Coach')])
        self.assertTrue(all(x['division']=='United North' for x in view['coaching_moves']))
    def test_structured_transaction_columns_preserve_terms_and_both_trade_assets(self):
        self.player('Receiver','WR',{})
        self.L.transactions=[dict(kind='sign',year=2027,team='GB',pid='Receiver',years=2,apy=3.5),
                             dict(kind='trade',year=2027,a='KC',b='GB',a_sends=['Receiver'],b_sends=['2028 R2'])]
        trade,sign=V.transactions(None,self.L,'GB')['rows']
        self.assertEqual((sign['person'],sign['role'],sign['detail']),('Receiver','WR','2 years · $3.5m per year'))
        self.assertEqual(trade['detail'],'Sent: Receiver (WR)')
        self.assertEqual(trade['detail_secondary'],'Received: 2028 R2')
        self.assertIn('Receiver',trade['line'])
    def test_coaching_filter_keeps_older_moves_and_poaches(self):
        self.L.transactions=[dict(kind='staff_hire',year=2024,team='GB',role='oc',name='Old hire'),
                             dict(kind='poach',year=2027,team='MIN',role='dc',name='Poached coach')]
        rows=V.transactions(None,self.L,'GB')['coaching_moves']
        self.assertEqual([x['person'] for x in rows],['Poached coach','Old hire'])
        self.assertEqual(rows[0]['action'],'Poached')
    def test_old_missing_stats_not_today(self):
        self.assertEqual(V.stats(None,self.L,'GB',2026)['team'],[])
    def test_game_affiliation_survives_trade(self):
        self.test_old_team_totals_and_identity()
        self.L.game_stats={'2026-1-GB-MIN':{'qb':dict(team='GB',pass_yds=200)},'2026-2-MIN-KC':{'qb':dict(team='MIN',pass_yds=300)}}
        rows=V.stats(None,self.L,'GB',2026)['team']
        self.assertEqual(next(r['pyds'] for r in rows if r['club']['abbr']=='GB'),round(200/17))
        self.assertEqual(next(r['pyds'] for r in rows if r['club']['abbr']=='MIN'),round(300/17))
    def test_record_stats_preserves_game_team(self):
        from league import League
        p=self.player('qb','QB',{})
        p.record_season=lambda year,line:None
        self.L.game_stats={};self.L.post_stats={}
        League.record_stats(self.L,2027,'qb',{'pass_yds':100},game='2027-1-GB-MIN')
        p.team='MIN'
        League.record_stats(self.L,2027,'qb',{'pass_yds':200},game='2027-2-MIN-KC')
        self.assertEqual(self.L.game_stats['2027-1-GB-MIN']['qb']['team'],'GB')
        self.assertEqual(self.L.game_stats['2027-2-MIN-KC']['qb']['team'],'MIN')

if __name__=='__main__':unittest.main()
