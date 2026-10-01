"""Observational per-game pass-rush export. Call install(path) before run.
No RNG draws, simulation edits, or game-state mutation; JSONL can be deduped
by (year,week,home,away) after a checkpoint restart.
"""
import json
from collections import Counter
from pathlib import Path

def install(path):
 import season as SN
 import defense_roles as DR
 target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
 original=SN.SeasonRunner._record
 def record(runner,home,away,week,result,book,playoffs=False):
  reps,wins=Counter(),Counter()
  for side,drive in result['drives']:
   for play in drive.log:
    if play.get('nullified'): continue
    for pid,won in play.get('pr_reps') or []:
     reps[pid]+=1; wins[pid]+=bool(won)
  bad=[dict(pid=pid,book=[line.get('pr_reps',0),line.get('pr_wins',0)],log=[reps[pid],wins[pid]])
       for pid,line in book.p.items() if (line.get('pr_reps',0),line.get('pr_wins',0))!=(reps[pid],wins[pid])]
  rows=[]
  for team in (home,away):
   state=runner.states[team]; counts=state.last_snap_counts.get('defense',{})
   for p in runner.L.teams[team].active():
    if p.pos not in DR.DEFENSE: continue
    depth=state.roster.get('depth',{}).get(p.pos,[])
    line=book.p.get(p.pid,{})
    rows.append(dict(pid=p.pid,name=p.name,team=team,pos=p.pos,ovr=round(p.ovr,3),age=p.age,
      front=DR.coach_front(runner.L.teams[team].gm),
      rank=next((i+1 for i,m in enumerate(depth) if m.get('pid')==p.pid),None),
      snaps=counts.get('players',{}).get(p.pid,0),team_snaps=counts.get('total',0),
      condition=round(state.cond.get(p.pid),3),fatigue=state.jaded.get(p.pid,0),
      reps=line.get('pr_reps',0),wins=line.get('pr_wins',0),pressures=line.get('pressures',0),sacks=line.get('sacks',0)))
  event=dict(year=runner.L.year,week=week,home=home,away=away,playoffs=playoffs,
     hs=result['home'],away_score=result['away'],injuries=result.get('injuries',[]),mismatches=bad,players=rows)
  with target.open('a',encoding='utf-8') as f:f.write(json.dumps(event,default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n')
  return original(runner,home,away,week,result,book,playoffs)
 SN.SeasonRunner._record=record
