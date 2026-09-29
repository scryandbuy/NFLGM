import numpy as np
import rosters,game,schemes,plays,season,gameplan as GP,gameplan_week as GW
from types import SimpleNamespace
teams=rosters.load_league(); home,away=teams['GB'],teams['MIN']
base=GP.Gameplan(); hs=game.TeamState(home,plan=base.copy()); aws=game.TeamState(away,plan=base.copy())
target=away['depth']['WR'][1]['pid']
league=SimpleNamespace(year=2026,user_week_plan=dict(year=2026,week=1,changes=dict(blitz_rate=.10,tempo=.15,protection='full_slide',travel=True,travel_target=target,bracket=None)))
GW.user_plan(league,hs,1)
co,cd=season._deps(); observed={'blitz':[], 'protection':[], 'target':[], 'snaps':0}
def defense(oc,*args,**kw):
 observed['blitz'].append(kw.get('lean',{}).get('blitz'))
 return cd(oc,*args,**kw)
def resolve(off,deff,oc,dc,*args):
 observed['snaps']+=1
 observed['protection'].append(oc.get('protection_pref'))
 observed['target'].append(dc.get('travel_target'))
 men=[p for p in [off['qb'],off.get('rb')]+off['ol']+off['wr'] if p]
 assert len(men)==len({p['pid'] for p in men})==11
 return plays.resolve_play(off,deff,oc,dc,*args)
res=game.play_game(home,away,np.random.default_rng(41),resolve,co,defense,plays.rate,home_state=hs,away_state=aws,book=game.StatBook())
assert any(x is not None and x > base.blitz_lean+.1 for x in observed['blitz'])
assert 'full_slide' in observed['protection']; assert target in observed['target']
print('Full-game wiring passed:',observed['snaps'],'unique-eleven snaps; blitz adjustment, full-slide protection, named shadow delivered to live calls;',res['home'],res['away'])
