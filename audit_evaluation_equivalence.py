"""Run against either checkout, in fresh processes with the same saved state."""
import argparse, dataclasses, hashlib, json, sys, time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--code-root',required=True)
parser.add_argument('--fixture',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--case',choices=['awards','bids','candidates','extensions','cutdown'],required=True)
args=parser.parse_args()
sys.path.insert(0,args.code_root)
import session as S, views_league as VL, market as MK, roster_needs as RN

class AuditSession(S.Session):
    def blocking(self):return []
    def next_label(self):return {'title':str(self.stop)}
    def _ensure_scout_focus(self):pass
    def _resign_card(self):pass
    def _post_review(self,*a,**k):pass
    def _snapshot_season(self,*a,**k):pass
    def _ir_ready_notes(self,*a,**k):pass
    def _capture_gameday(self,*a,**k):pass

VL.rail=lambda *a,**k:{}
fixture=Path(args.fixture).read_text(encoding='utf8')
s=AuditSession.load(fixture)
start=time.perf_counter()
if args.case=='awards':
    assert s.stop==('offseason',0), s.stop
    result=s.advance()
elif args.case=='bids':
    result=MK.ai_bids(s.L,MK._pool(s.L),1,s.rng)
elif args.case=='candidates':
    pool=MK._pool(s.L)
    result={a:RN.candidate_gains(t,pool) for a,t in s.L.teams.items()}
elif args.case=='extensions':
    import extensions as EXT
    result=EXT.ai_round(s.L,s.rng)
else:
    import cutdown as CD
    result=CD.finalize(s.L,s.rng)
seconds=time.perf_counter()-start
def encode(x):
    if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
    if isinstance(x,set):return sorted(x)
    if hasattr(x,'item'):return x.item()
    if hasattr(x,'pid'):return x.pid
    raise TypeError(type(x).__name__)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,default=encode).encode()).hexdigest()
row=dict(case=args.case,code_root=args.code_root,seconds=seconds,
         fixture_sha=hashlib.sha256(fixture.encode()).hexdigest(),
         result_sha=digest(result),state_sha=digest(json.loads(s.save())),
         rng=s.rng.bit_generator.state,transactions=len(s.L.transactions))
Path(args.output).write_text(json.dumps(row,indent=2),encoding='utf8')
print(json.dumps(row),flush=True)
