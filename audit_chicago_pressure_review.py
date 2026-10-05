import json
from collections import defaultdict
import numpy as np
import rosters as R, plays as P, schemes as S, game as G, targets as T
teams=R.load_league(); rng=np.random.default_rng(203002)
bins=defaultdict(lambda:dict(n=0,complete=0,yards=0,explosive=0,sack=0,severity=0))
for i in range(1800):
 off,df=('GB','CHI') if i%2 else ('CHI','GB')
 oc=S.call_offense(2,8,0,77,rng,secs_left=1200,offense=teams[off],rate_fn=P.rate)
 oc.update(is_pass=True,down=2,ydstogo=8)
 dc=S.call_defense(oc,2,8,rng,yards_to_endzone=77,defense=teams[df],rate_fn=P.rate)
 o,_=G.field_units(teams[off],None,rng,True,oc['personnel'])
 d,_=G.field_units(teams[df],None,rng,False,dc['personnel'],dc.get('front_family'))
 p=P._pass_play(o,d,oc,dc,77,rng)
 key='sack' if p['type']=='sack' else ('pressured' if p.get('pressured') else 'clean')
 b=bins[key]; b['n']+=1;b['complete']+=p['type']=='complete';b['yards']+=p['yards'];b['explosive']+=p['type']=='complete' and p['yards']>=20;b['severity']+=p.get('pressure_severity',0)
print('PRODUCTION PASSES',json.dumps(dict(bins)))
for depth in ('short','medium','deep'):
 print('ACCURACY',depth,[(severity,round(P.resolve_throw(teams['GB']['qb'],depth,.42,severity,np.random.default_rng(1))['p'],3)) for severity in (0,.2,.6)])
pairs=[dict(receiver=dict(pid='chains',pos='WR'),defender={},separation=.42,route_air=6),dict(receiver=dict(pid='outlet',pos='HB'),defender={},separation=.65,route_air=1)]
for down in (2,4):
 for pressure in (0,.6):
  r=np.random.default_rng(8); n=sum(T.select_target(pairs,{},'curl_flat',r,lambda *args:.8,down=down,ydstogo=5,pressure=pressure)[0]['pid']=='outlet' for _ in range(2000))
  print('READ',down,pressure,'outlet',n,'of2000')
