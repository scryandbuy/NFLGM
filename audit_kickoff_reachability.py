import json
from collections import Counter
from unittest.mock import patch
import numpy as np
from league import League
from season import SeasonRunner
import game as G, plays as P, kick_returns as K
L=League.load(open(r'C:/Users/HP/Downloads/nflgm-2032-offseason-2.json',encoding='utf-8').read())
R=SeasonRunner(L,np.random.default_rng(1)); units={a:R._units(a) for a in sorted(L.teams)}; names=list(units)
original=K._kickoff_breakaway

def baseline(start,gained,returner,coverage,kicker,rng,rate):
    defenders=sorted(coverage,key=lambda p:-rate(p,K.YAC['tackler']['angle']))[:2]
    out=P.resolve_yards_after(returner,defenders,start,rng,contact_at=gained,in_space=True,track_tackler=True)
    return dict(yards=out['yards'],tackler=next((p for p in coverage if p.get('pid')==out.get('tackler')),None),contacts=[])
reports={}
for mode,fn in [('baseline',baseline),('candidate',original)]:
    c=Counter(); examples=[]; scorers=Counter(); contacts=Counter()
    with patch.object(K,'_kickoff_breakaway',side_effect=fn):
        for i in range(12000):
            rng=np.random.default_rng(700700+i)
            a=units[names[i%32]]; b=units[names[(i%32+1+i//32%31)%32]]
            p=G.returner_for(b,None,P.rate,kind='kr')
            out=G.kickoff(p,rng,P.rate,kicking=K.unit(a,None,P.rate),receiving=K.unit(b,None,P.rate,True,p.get('pid')),kicker=a['k'],short_kick_bias=0.)
            c['kicks']+=1;c['returns']+=not out.get('touchback',False);c['td']+=bool(out.get('touchdown'));c['opportunity']+=bool(out.get('breakaway_opportunity'));c['yards']+=out.get('ret',0)
            if out.get('touchdown'): scorers[p['pid']]+=1
            for x in out.get('kickoff_pursuit',[]): contacts[x['leverage'] + (' reachable' if x['reachable'] else ' unreachable')]+=1
            if out.get('touchdown') and len(examples)<4:examples.append(dict(pid=p['pid'],yards=out['ret']))
    reports[mode]=dict(counts=dict(c),examples=examples,contacts=dict(contacts),scorers=[dict(pid=pid,name=L.player(pid).name,td=n,speed=L.player(pid).ratings.get('speed_rating')) for pid,n in scorers.most_common()])
print(json.dumps(reports,indent=2))
