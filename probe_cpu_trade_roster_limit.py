"""Replay initial Session setup and two weeks; observe actual kickoff rosters."""
import json
from pathlib import Path
import session as S
import season as SN

s=S.Session.new(team=None,seed=93030)
s.step_cutdown()
for _ in range(5):
    if s.step_clear_wire() is not False: break
else: raise RuntimeError('Wire not clear')
r=SN.SeasonRunner(s.L,s.rng)
rows=[]
play=r.play
def capture(home,away,week,playoffs=False):
    row=dict(year=s.L.year,week=week,home=home,away=away,
        active={a:len(s.L.teams[a].active()) for a in (home,away)},
        ir={a:len(s.L.teams[a].ir) for a in (home,away)})
    rows.append(row)
    if max(row['active'].values())>53: print('OVERFULL_KICKOFF',json.dumps(row),flush=True)
    return play(home,away,week,playoffs)
r.play=capture
r.play_week(1)
week1={a:len(t.active()) for a,t in s.L.teams.items()}
r.play_week(2)
out=dict(seed=93030,base='ef4620a',week1=week1,kickoffs=rows,
    moves=[e for e in s.L.transactions if e['week'] in (1,2) and
           (e.get('team') in ('LV','CAR') or e.get('a') in ('LV','CAR') or e.get('b') in ('LV','CAR'))])
path=Path(__file__).resolve().parents[2]/'outputs'/'cpu-trade-roster-limit-probe.json'
path.write_text(json.dumps(out,default=lambda o:o.item() if hasattr(o,'item') else str(o),indent=2),encoding='utf8')
print(path,flush=True)
