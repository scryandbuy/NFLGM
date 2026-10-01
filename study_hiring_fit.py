"""Compare hiring fit and package projection, not the owner's total hire score."""
import copy,json,itertools
from pathlib import Path
import numpy as np
import league as LG, coaching_pool as CP,gm_engine as GE,roster_needs as RN
L=LG.build_league(rng=np.random.default_rng(93045));out=[]
for abbr in ('GB','DEN','ATL'):
    team=L.teams[abbr];oldgm=team.gm;oldscheme=team.scheme;rows=[]
    for front,pers,blocking in itertools.product(('4-3','3-4','multiple'),('11','12','21','10'),('zone','gap')):
        g=copy.deepcopy(oldgm);g.def_front=front;g.off_personnel=pers;g.off_blocking=blocking
        fit,_=CP.roster_fit(team,g)
        team.gm=g;team.scheme=GE.scheme_of(g)
        assessment=RN.assess(team)
        rows.append(dict(front=front,personnel=pers,blocking=blocking,fit=fit,package_score=sum(assessment['_package_scores'].values())))
        team.gm=oldgm;team.scheme=oldscheme
    pairs=[(a,b) for a in rows for b in rows if a['fit']>b['fit']+.05 and a['package_score']<b['package_score']-2]
    if pairs:
        a,b=max(pairs,key=lambda ab:ab[1]['package_score']-ab[0]['package_score'])
        out.append(dict(team=abbr,fit_preferred=a,package_preferred=b))
Path('../../outputs/coaching-hiring-fit-93045.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
