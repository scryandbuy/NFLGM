from pathlib import Path
import json,numpy as np
from league import League
import veteran_market as VM
L=League.load(json.load(open('C:/Users/HP/Downloads/nflgm-2030-week-9.json',encoding='utf8')))
moves=VM.review(L,np.random.default_rng(203009),'weekly',week=9,user_team='GB')
rows=[]
for team,pid,out in moves:
 p=L.player(pid);q=L.player(out) if out else None
 rows.append(dict(team=team,incoming=p.name,age=p.age,ovr=p.ovr,outgoing=q.name if q else None,out_age=q.age if q else None,out_ovr=q.ovr if q else None,cap=round(L.teams[team].cap_space,2),contract=vars(p.contract)))
Path('research/weekly_fa_value_2030.json').write_text(json.dumps(rows,default=str,indent=2))
print('TOTAL',len(moves))
L.save()
L.week=10
more=VM.review(L,np.random.default_rng(203010),'weekly',week=10,user_team='GB')
print('FOLLOWUP',[(t,L.player(p).name,L.player(o).name if o else None) for t,p,o in more])
L.save()
