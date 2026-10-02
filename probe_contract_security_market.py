from pathlib import Path
import sys, json, time, hashlib, statistics, argparse
from collections import Counter
sys.path.insert(0, str(Path.cwd()))
import numpy as np
import session as SS
import market as MK
import contracts as CT
import morale as MO
from cap_engine import CAP

parser=argparse.ArgumentParser(description='Disposable extension/FA comparison; source save is never overwritten.')
parser.add_argument('--save', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--label', default='revised')
parser.add_argument('--seed', type=int, default=481)
args=parser.parse_args()
label, seed, source, out=args.label, args.seed, args.save, args.output
out.mkdir(parents=True, exist_ok=True)
initial=source.read_bytes(); digest=hashlib.sha256(initial).hexdigest()
s=SS.Session.load(initial.decode('utf8')); s.rng=np.random.default_rng(seed)
L=s.L; L.negotiations=[]
start=len(L.transactions); clock=time.monotonic()
def status(stage): print(json.dumps(dict(label=label,seed=seed,stage=stage,seconds=round(time.monotonic()-clock,1))),flush=True)
s.step_extensions(); status('extensions')
for phase in (1,2,3):
    MK.open_round(L,s.rng,phase,user_team=s.user_team)
    MK.resolve_round(L,s.rng,phase,user_team=s.user_team)
    status('market_round_'+str(phase))
MK.close_market(L,s.rng,user_team=s.user_team); status('market_close')
events=L.transactions[start:]
signed=[e for e in events if e['kind']=='sign' and e.get('team') != s.user_team]
extended=[e for e in events if e['kind']=='extension' and e.get('team') != s.user_team]
contracts=[L.player(e['pid']).contract for e in signed if L.player(e['pid']).contract is not None]
apys=[e['apy'] for e in signed]
terms=Counter(e['years'] for e in signed)
future=[]
for t in L.teams.values():
    if t.abbr==s.user_team: continue
    future.append(sum(p.contract.cap_hit(1) for p in t.active() if p.contract and p.contract.years>1)+t.cap.dead_next)
over=[(t.abbr,round(t.cap_space,3)) for t in L.teams.values() if t.abbr!=s.user_team and t.cap_space < -.001]
memory_before={p.pid:p.xp_spent.get('_negotiation_profile') for p in L.players.values() if p.xp_spent.get('_negotiation_profile')}
payload=s.save(); restored=SS.Session.load(payload)
assert memory_before == {p.pid:p.xp_spent.get('_negotiation_profile') for p in restored.L.players.values() if p.xp_spent.get('_negotiation_profile')}
assert s.rng.bit_generator.state == restored.rng.bit_generator.state
assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
report=dict(label=label,seed=seed,source_sha256=digest,seconds=round(time.monotonic()-clock,1),
            cpu_signings=len(signed),cpu_extensions=len(extended),mean_apy=statistics.mean(apys) if apys else 0,
            term_distribution=dict(terms),unsigned=len(L.free_agents),
            mean_bonus_share=statistics.mean(c.sb/max(.001,sum(c.base)+c.sb) for c in contracts) if contracts else 0,
            cpu_over_cap=over,maximum_next_year_commitment=max(future),
            released=len([e for e in events if e['kind']=='release']),
            largest_annual_pay=max(apys,default=0),profiles_preserved=len(memory_before),
            cap=CAP[L.year],source_untouched=True,save_reload_pass=True)
(out/f'contract-security-{label}-{seed}.json').write_text(json.dumps(report,indent=2),encoding='utf8')
(out/f'contract-security-{label}-{seed}-save.json').write_text(payload,encoding='utf8')
print(json.dumps(report),flush=True)
assert not over,over
