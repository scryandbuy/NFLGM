"""Replay the supplied missing-QB save; default covers the remaining 2028 season."""
import argparse
import hashlib
import json,time
from pathlib import Path
from session import Session
import game_availability as GA
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--save',type=Path,default=Path('../../outputs/practice-audit-4c9665f-93030-final/season-2028-week1.json'))
parser.add_argument('--through',type=int,choices=range(2,19),default=18)
parser.add_argument('--report',type=Path,default=Path('../../outputs/emergency-fieldability-20260930/native-season-replay.json'))
args=parser.parse_args()
args.report.parent.mkdir(parents=True,exist_ok=True)
s=Session.load(args.save.read_text(encoding='utf8'))
injured_qbs=[p.pid for p in s.L.teams['NE'].roster if p.pos=='QB' and p.out_until is not None]
started=time.time(); report={'base':'4c9665f','year':s.L.year,'through_week':args.through,'weeks':[],'repairs':[],
                            'availability_sha256':hashlib.sha256(Path(GA.__file__).read_bytes()).hexdigest()}
original=GA.ensure
def checked(L,t,desk,wk,playoffs=False):
 n=len(L.transactions); ans=original(L,t,desk,wk,playoffs)
 moves=L.transactions[n:]
 if moves:
  assert len(t.active())<=53,(t.abbr,len(t.active()))
  assert t.cap_space>=-.0005,(t.abbr,t.cap_space)
  report['repairs'].append({'team':t.abbr,'week':wk,'cap':t.cap_space,'roster':len(t.active()),'moves':moves})
 return ans
GA.ensure=checked
try:
 s.runner.roll_week(1)
 for wk in range(2,args.through+1):
  s.stop=('week',wk); s.played=False
  played=s.runner.play_games(wk); GA.require_scores(s.L,wk)
  s.played=True
  report['weeks'].append({'week':wk,'games':len(played),'seconds':round(time.time()-started,1)})
  print(report['weeks'][-1],flush=True)
  if wk==2:
   assert all(s.L.player(pid).team=='NE' and s.L.player(pid) in s.L.teams['NE'].roster for pid in injured_qbs)
   before=[tuple(g) for g in s.L.schedule]; transactions=list(s.L.transactions)
   s=Session.load(s.save())
   assert [tuple(g) for g in s.L.schedule]==before
   assert s.L.transactions==transactions
   repeated=s.runner.play_games(wk)
   assert s.L.transactions==transactions,'repeat produced transactions'
   assert len(repeated)==len(played)
   report['save_reload_retry']='passed'
  if wk<args.through:s.runner.roll_week(wk)
 regular=[g for g in s.L.schedule if g[0]<=args.through]
 assert all(g[3] is not None and g[4] is not None for g in regular)
 if args.through==18: assert len(regular)==272
 totals={a:tuple(t.record) for a,t in s.L.teams.items()}
 for a,record in totals.items():
  games=[g for g in regular if a in g[1:3]]
  wins=sum((ap>hp if a==away else hp>ap) for w,away,home,ap,hp in games)
  ties=sum(ap==hp for w,away,home,ap,hp in games)
  assert record==(wins,len(games)-wins-ties,ties),(a,record,wins,ties)
 report['games']=len(regular);report['standings_match_schedule']=True
 report['NE_qbs']=[{'pid':p.pid,'name':p.name,'injured_until':p.out_until,
                    'on_ir':p in s.L.teams['NE'].ir} for p in s.L.teams['NE'].roster if p.pos=='QB']
 report['status']='passed'
except Exception as exc:
 import traceback
 report['status']='failed';report['error']=repr(exc);traceback.print_exc()
finally:
 report['elapsed_seconds']=round(time.time()-started,1)
 args.report.write_text(json.dumps(report,indent=2,default=str),encoding='utf8')
 print(json.dumps({k:v for k,v in report.items() if k not in ('weeks','repairs')}),flush=True)
if report['status']!='passed': raise SystemExit(1)
