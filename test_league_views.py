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
        for a,div in [('GB','NFC North'),('MIN','NFC North'),('KC','AFC West')]:
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
        rows=next(b['rows'] for b in v['advanced'] if b['title']=='Defensive EPA per Play')
        self.assertEqual([r['pid'] for r in rows],[str(i) for i in range(8)])
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
    def test_snapshots_preferred(self):
        self.L.history={'2026':{'stats':dict(team=[{'kept':True}]),'awards':dict(rows=[{'name':'Original'}])}}
        self.assertEqual(V.stats(None,self.L,'GB',2026)['team'],[{'kept':True}])
        self.assertEqual(V.awards(None,self.L,'GB',2026)['rows'],[{'name':'Original'}])
    def test_both_trade_sides(self):
        self.L.transactions=[dict(kind='trade',year=2027,a='KC',b='GB',a_sends=[],b_sends=[])]
        row=V.transactions(None,self.L,'GB')['rows'][0]
        self.assertTrue(row['mine']);self.assertIn('NFC North',row['divisions'])
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
