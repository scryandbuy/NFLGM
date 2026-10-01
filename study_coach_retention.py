"""Controlled 17-week retention decisions after three scheme changes, no games."""
import json
from pathlib import Path
import numpy as np
import league as LG, gm_engine as GE, extensions as E

rng=np.random.default_rng(93043); L=LG.build_league(rng=rng); L.user_team=None
tracked={'GB':('3-4','12','gap'),'DEN':('multiple','21','zone'),'ATL':('4-3','10','gap')}
for abbr,(front,pers,blocking) in tracked.items():
    t=L.teams[abbr]; t.gm.def_front=front; t.gm.off_personnel=pers; t.gm.off_blocking=blocking
    t.identity=None; t.scheme=GE.scheme_of(t.gm)
eligible=[]
for a in tracked:
    t=L.teams[a]
    for ps in t.depth.values():
        for p in ps[:1]:
            if E.eligible(p,L) and p.age<=E.AGE_LIMIT.get(p.pos,31) and p.ovr>=76:
                eligible.append(dict(team=a,pid=p.pid,name=p.name,pos=p.pos,fit=GE.scheme_fit(p.ratings,p.pos,t),apy=p.apy))
before={p.pid:p.contract.years for a in tracked for p in L.teams[a].active() if p.contract}
moves=[]
for week in range(1,18):
    moves.extend(x for x in E.in_season_round(L,rng,week) if x[0] in tracked)
accepted=[]
for a in tracked:
    t=L.teams[a]
    for p in t.active():
        if p.contract and p.pid in before and p.contract.years>before[p.pid]:
            accepted.append(dict(team=a,pid=p.pid,name=p.name,fit=GE.scheme_fit(p.ratings,p.pos,t),apy=p.apy,years=p.contract.years))
out=dict(seed=93043,eligible=eligible,moves=moves,accepted=accepted,limitation='17 retention rounds on unchanged calendar/ratings; no games or statistical frequency estimate')
Path('../../outputs/coaching-retention-93043.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
