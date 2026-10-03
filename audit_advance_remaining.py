"""Fresh-process full-draft / camp cutdown / waiver / save comparison."""
import argparse,sys,json,time,hashlib,dataclasses
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--code-root',required=True);p.add_argument('--case',choices=['fixture','draft','cutdown','waivers','save'],required=True);p.add_argument('--output',required=True);p.add_argument('--fixture',required=True);a=p.parse_args();sys.path.insert(0,a.code_root)
import session as S
s=S.Session.new('GB',seed=91) if a.case=='fixture' else S.Session.load(Path(a.fixture).read_text(encoding='utf8'))
if a.case=='fixture':Path(a.fixture).write_text(s.save(),encoding='utf8');print('fixture ready',flush=True);sys.exit()
if a.case=='draft':
 import draft_day as DD
 L=s.L;L.year=2027;L.phase='offseason';L.season_closed_year=2026;s.stop=('offseason',12)
 L.draft_pool,L.next_class=L.next_class,[];order=sorted(L.teams)
 for t in L.teams.values():
  for pk in t.picks:
   if pk.year==2026:pk.selection=(pk.round-1)*32+order.index(pk.original)+1
 s.draft=DD.Draft(L,s.rng,2026,user_team='GB',auto_pick=True)
start=time.perf_counter()
if a.case=='draft':s.draft.sim_all();result={'picks':[(n,t,p.pid) for n,t,p in s.draft.results],'trades':s.draft.trades}
elif a.case=='cutdown':
 import cutdown as CD
 result=CD.finalize(s.L,s.rng)
elif a.case=='waivers':s.stop=('wire',);result=s.step_clear_wire()
else:
 raw=s.save();result=None
seconds=time.perf_counter()-start
raw=s.save()
if a.case=='cutdown':Path(str(Path(a.output).with_suffix('.fixture.json'))).write_text(raw,encoding='utf8')
def default(x):
 if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
 if hasattr(x,'pid'):return x.pid
 if isinstance(x,set):return sorted(x)
 if hasattr(x,'item'):return x.item()
 raise TypeError(type(x).__name__)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,default=default).encode()).hexdigest()
row=dict(case=a.case,seconds=seconds,save_bytes=len(raw),result_sha=digest(result),state_sha=digest(json.loads(raw)),rng=s.rng.bit_generator.state,transactions=len(s.L.transactions))
if a.case=='draft':row.update(picks=len(s.draft.results),trades=len(s.draft.trades))
Path(a.output).write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)
