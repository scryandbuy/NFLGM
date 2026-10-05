"""Read-only production audit; observational wrappers never draw simulation RNG.

Run: python audit_longitudinal_teams.py --seed 93030 --years 3 --output PATH
Uses actual Session.advance with no human team; user-only UI/review rendering
and human blocking prompts are omitted. All 32 teams
receive normal AI decisions. No outcome/contract/roster coefficients are changed.
"""
import argparse
import collections
import functools
import json
import math
import os
import subprocess
import time
import numpy as np
from pathlib import Path

import franchise as F
import league as LG
import roster_needs as RN
import offense_roles as OR
import defense_roles as DR
import session as S
from calibrate import Collector, TARGETS


def json_default(value):
    if isinstance(value,np.generic): return value.item()
    return str(value)


class AuditSession(S.Session):
    """Suppress human presentation only, preserving calendar/AI orchestration."""
    def blocking(self): return []
    def next_label(self): return {'title':str(self.stop)}
    def _post_review(self,*a,**k): pass
    def _snapshot_season(self,*a,**k): pass
    def _ir_ready_notes(self,*a,**k): pass
    def _capture_gameday(self,*a,**k): pass


def player(p):
    if p is None:
        return None
    c = p.contract
    return dict(pid=p.pid, name=p.name, pos=p.pos, age=p.age, ovr=round(p.ovr, 3),
                team=p.team, apy=round(p.apy, 3), cap_hit=round(p.cap_hit(), 3),
                years=c.years if c else 0, retired=p.retired,
                entry_year=p.entry_year, out_until=p.out_until)


def team_report(t, full=False):
    active = t.active()
    r = RN.assess(t)
    floors, groups = RN.roster_floors(t)
    counts = collections.Counter(p.pos for p in active)
    by_variant = collections.defaultdict(list)
    for row in r['package_assignments']:
        by_variant[row['variant']].append(row)
    bad = []
    for variant, rows in by_variant.items():
        pids = [x['player'].pid for x in rows if x['player'] is not None]
        if len(pids) != 11 or len(set(pids)) != 11:
            bad.append(dict(variant=variant, count=len(pids), unique=len(set(pids))))
    result = dict(team=t.abbr, active=len(active), roster=len(t.roster),
        ps=len(t.practice_squad), ir=len(t.ir), record=list(t.record),
        front=DR.coach_front(t.gm), offense=OR.base_package(t.gm),
        cap_space=round(t.cap_space, 4), full_cap_space=round(t.cap.space('season'), 4),
        dead=round(t.cap.dead, 4), dead_next=round(t.cap.dead_next, 4),
        cap=round(t.cap.cap, 4), phase=t.phase, paid_week=t.cap.paid_week,
        score=round(r['score'], 5), counts=dict(counts), uncovered=r['uncovered'],
        package_bad=bad, max_need=round(max(r['needs'].values()), 4),
        needs={k:round(v, 4) for k,v in r['needs'].items()},
        position_short={k:v-counts[k] for k,v in floors.items() if counts[k]<v},
        group_short={k:v-sum(counts[p] for p in RN.GROUPS[k]) for k,v in groups.items()
                     if sum(counts[p] for p in RN.GROUPS[k]) < v},
        mean_ovr=round(sum(p.ovr for p in active)/max(1,len(active)),3),
        mean_age=round(sum(p.age for p in active)/max(1,len(active)),3),
        expiring=sum(bool(p.contract and p.contract.years<=1) for p in t.roster),
        roster_ids=[p.pid for p in t.roster], ps_ids=[p.pid for p in t.practice_squad],
        ir_ids=[p.pid for p in t.ir])
    if full:
        result['players'] = [player(p) for p in t.roster]
        result['squad_players'] = [player(p) for p in t.practice_squad]
    return result


class Audit:
    def __init__(self, folder, resume=False):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.stage = 'initial'
        self.start = time.monotonic()
        self.samples = collections.Counter()
        self.snapshots = []
        self.register = Collector()
        self.register_by_year = {}
        mode='r+' if resume else 'w'
        self.moves = self.folder.joinpath('moves.jsonl').open(mode, encoding='utf8')
        self.events = self.folder.joinpath('events.jsonl').open(mode, encoding='utf8')
        self.kickoffs = self.folder.joinpath('kickoffs.jsonl').open(mode, encoding='utf8')
        self.games = self.folder.joinpath('games.jsonl').open(mode, encoding='utf8')

    def checkpoint(self, session, history):
        state=session.save()
        data=dict(session=state,history=history,snapshots=len(self.snapshots),
                  offsets={k:getattr(self,k).tell() for k in ('events','moves','kickoffs','games')},
                  samples=list(self.samples.items()),elapsed=time.monotonic()-self.start,
                  register=self.register.to_json(),
                  register_by_year={year:c.to_json() for year,c in self.register_by_year.items()})
        temporary=self.folder/'checkpoint.pending.json'
        temporary.write_text(json.dumps(data,default=json_default),encoding='utf8')
        temporary.replace(self.folder/'checkpoint.json')

    def write(self, stream, row):
        stream.write(json.dumps(row, default=json_default, allow_nan=False)+'\n')
        stream.flush()

    def snapshot(self, L, label):
        teams = [team_report(t, True) for t in L.teams.values()]
        owners = collections.defaultdict(list)
        invalid = []
        for t in L.teams.values():
            for p in t.roster + t.practice_squad:
                owners[p.pid].append(t.abbr)
                if p.team != t.abbr or p.retired:
                    invalid.append((t.abbr, p.pid, p.team, p.retired))
        row = dict(label=label, year=L.year, week=L.week, phase=L.phase,
            elapsed=round(time.monotonic()-self.start, 2), teams=teams,
            free_agents=len(L.free_agents), living=sum(not p.retired for p in L.players.values()),
            regular_games=sum(1 for w,a,h,ap,hp in L.schedule if w<=18 and ap is not None),
            playoff_games=sum(1 for w,a,h,ap,hp in L.schedule if w>18 and ap is not None),
            multiple_owners={k:v for k,v in owners.items() if len(v)>1}, invalid_owners=invalid,
            event_counts=dict(collections.Counter(e['kind'] for e in L.transactions)))
        self.snapshots.append(row)
        with self.folder.joinpath('snapshots.json').open('w', encoding='utf8') as out:
            json.dump(self.snapshots, out, default=json_default)
        print(json.dumps(dict(snapshot=label, year=L.year, week=L.week,
            active_range=[min(t['active'] for t in teams),max(t['active'] for t in teams)],
            over_cap=sum(t['full_cap_space']<-.01 for t in teams),
            gaps=sum(bool(t['uncovered']) for t in teams),
            mean_score=round(sum(t['score'] for t in teams)/32,2), elapsed=row['elapsed']),default=json_default),flush=True)

    def context(self, L, abbr, p=None, alternatives=False):
        t = L.teams[abbr]
        r = RN.assess(t)
        row = dict(score=r['score'], cap_space=t.cap_space, counts=dict(r['counts']),
                   needs=r['needs'], uncovered=r['uncovered'])
        if p is not None:
            row['incumbents'] = [player(q) for q in t.by_pos(p.pos)]
            row['candidate_gain'] = RN.move_gain(t, arrival=p, baseline=r)
        if p is not None and alternatives:
            candidates = [L.player(pid) for pid in L.free_agents]
            candidates = [q for q in candidates if q and not q.retired and q.team is None
                          and q.pos==p.pos and q.pid!=p.pid]
            candidates = sorted(candidates,key=lambda q:(-q.ovr,q.pid))[:6]
            gains = RN.candidate_gains(t,candidates,baseline=r)
            row['same_position_street_alternatives'] = [dict(player(q), gain=gains[q.pid]) for q in candidates]
        return row

    def install(self):
        audit = self
        original_log = LG.League.log
        @functools.wraps(original_log)
        def log(L,kind,**detail):
            original_log(L,kind,**detail)
            audit.write(audit.events,dict(L.transactions[-1], audit_stage=audit.stage))
        LG.League.log = log

        for action in ('sign','release','trade'):
            original = getattr(LG.League,action)
            def factory(action, original):
                @functools.wraps(original)
                def call(L,*args,**kwargs):
                    key = (L.year,audit.stage,action)
                    p = L.player(args[0]) if action!='trade' else None
                    # All trades; first 12 moves of each stage/year; all costly contracts.
                    detailed = (action=='trade' or audit.samples[key]<12 or (p and p.apy>=10)
                                or (action=='sign' and args[2].cap_hit(0)>=8))
                    if detailed:
                        audit.samples[key]+=1
                        abbrs = list(args[:2]) if action=='trade' else [args[1] if action=='sign' else p.team]
                        abbrs = [a for a in abbrs if a in L.teams]
                        row = dict(action=action,stage=audit.stage,year=L.year,week=L.week,
                                   player=player(p),before={a:audit.context(L,a,p,action=='sign') for a in abbrs})
                        if action=='sign':
                            c=args[2]
                            row['new_contract']=dict(years=c.years,cap_hit=c.cap_hit(0),base=list(c.base),bonus=c.sb)
                        if action=='trade':
                            row['assets'] = {args[0]:[player(L.player(x)) if isinstance(x,str) else str(x) for x in args[2]],
                                             args[1]:[player(L.player(x)) if isinstance(x,str) else str(x) for x in args[3]]}
                    result=original(L,*args,**kwargs)
                    if detailed:
                        row['after']={a:audit.context(L,a) for a in abbrs}
                        audit.write(audit.moves,row)
                    return result
                return call
            setattr(LG.League,action,factory(action,original))

        # Coarse stage boundaries keep instrumentation outside personnel algorithms.
        stages = [(F.SN,'run_season'),(F.PS,'close_season'),(F.RG,'run'),(F.RT,'run'),
                  (F.CT,'run'),(F.EXT,'ai_round'),(F.TG,'run'),(F.MK,'run'),
                  (F.TRD,'run'),(F.DFT,'run'),(F.PSQ,'udfa_camp'),(F.CD,'finalize'),
                  (F.WV,'process'),(F.PSQ,'fill_squads')]
        for module,name in stages:
            original=getattr(module,name)
            label=module.__name__+'.'+name
            def factory(original,label):
                @functools.wraps(original)
                def call(L,*args,**kwargs):
                    old=audit.stage
                    audit.stage=label
                    print(f'START {L.year} week {L.week}: {label}',flush=True)
                    result=original(L,*args,**kwargs)
                    # Weekly trade/PS hooks are retained in events, snapshot only offseason.
                    if old not in ('season.run_season','week','playoffs') and label not in ('practice_squad.fill_squads','waivers.process'):
                        audit.snapshot(L,label)
                    audit.stage=old
                    return result
                return call
            setattr(module,name,factory(original,label))
        original_week=F.SN.SeasonRunner.roll_week
        @functools.wraps(original_week)
        def play_week(runner,week,*args,**kwargs):
            result=original_week(runner,week,*args,**kwargs)
            print(f'WEEK {runner.L.year} {week} complete ({time.monotonic()-audit.start:.1f}s)',flush=True)
            if week in (1,9,18): audit.snapshot(runner.L,f'week_{week}')
            return result
        F.SN.SeasonRunner.roll_week=play_week
        original_play=F.SN.SeasonRunner.play
        @functools.wraps(original_play)
        def play(runner,home,away,week,playoffs=False):
            audit.write(audit.kickoffs,dict(year=runner.L.year,week=week,home=home,away=away,
                active={a:len(runner.L.teams[a].active()) for a in (home,away)},
                ir={a:len(runner.L.teams[a].ir) for a in (home,away)}))
            result=original_play(runner,home,away,week,playoffs)
            year=str(runner.L.year)
            if not playoffs:
                audit.register.add(result)
                audit.register_by_year.setdefault(year,Collector()).add(result)
            audit.write(audit.games,dict(year=runner.L.year,week=week,home=home,away=away,
                playoffs=playoffs,score=[result['home'],result['away']],
                injuries=len(result.get('injuries',[])),overtime=result.get('overtime'),
                env=result.get('env'),drives=[dict(side=side,start=d.start,
                    start_quarter=d.start_quarter,clock=d.clock,plays=d.plays,
                    first_downs=d.first_downs,result=d.result,points=d.points,
                    log=d.log) for side,d in result['drives']]))
            return result
        F.SN.SeasonRunner.play=play


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--seed',type=int,default=93030)
    ap.add_argument('--years',type=int,default=3)
    ap.add_argument('--output',required=True)
    ap.add_argument('--resume',action='store_true')
    args=ap.parse_args()
    import networkx as nx
    assert callable(nx.max_weight_matching), 'Install networkx before running the calendar'
    audit=Audit(args.output,args.resume)
    audit.install()
    # These functions only render the human rail/review; None is not a team.
    import views_league as VL
    VL.rail=lambda *a,**k: {}
    if args.resume:
        data=json.loads((audit.folder/'checkpoint.json').read_text(encoding='utf8'))
        f=AuditSession.load(data['session'])
        history=data['history']
        audit.snapshots=json.loads((audit.folder/'snapshots.json').read_text(encoding='utf8'))[:data['snapshots']]
        for k,offset in data['offsets'].items():
            stream=getattr(audit,k); stream.seek(offset); stream.truncate()
        audit.samples=collections.Counter({tuple(k):v for k,v in data['samples']})
        audit.register=Collector.from_json(data['register'])
        audit.register_by_year={year:Collector.from_json(text)
                                for year,text in data['register_by_year'].items()}
        audit.start=time.monotonic()-data['elapsed']
        print('RESUMED',f.L.year,f.stop,flush=True)
    else:
        f=AuditSession.new(team=None,seed=args.seed)
        history=[]
        audit.snapshot(f.L,'initial')
    base=subprocess.check_output(['git','rev-parse','HEAD'],text=True,
                                 cwd=Path(__file__).resolve().parent).strip()
    audit.folder.joinpath('methodology.json').write_text(json.dumps(dict(seed=args.seed,years=args.years,
        base=base,driver='Session.advance / all-CPU (human UI methods omitted)',all_32_cpu=True,
        python_hash_seed=os.getenv('PYTHONHASHSEED'),networkx=nx.__version__,
        limitations=__doc__),indent=2),encoding='utf8')
    try:
        if not args.resume:
            for attempt in range(6):
                f.advance()
                if f.stop==('week',1): break
            else: raise RuntimeError('Initial wire did not clear')
            audit.snapshot(f.L,'initial_cutdown')
            audit.checkpoint(f,history)
        completed=sum(s['label']=='end_offseason' for s in audit.snapshots)
        for cycle in range(completed,args.years):
            year=audit.snapshots[0]['year']+cycle
            for advance in range(120):
                old_stop=f.stop
                name=f.OFFSEASON[old_stop[1]][1] if old_stop[0]=='offseason' else old_stop[0]
                audit.stage=name
                result=f.advance()
                if result.get('done')=='Blocked': raise RuntimeError(result)
                if old_stop[0]=='offseason': audit.snapshot(f.L,name)
                if f.stop==('offseason',0) and old_stop[0]=='playoffs':
                    audit.snapshot(f.L,'season_closed')
                    history.append(dict(year=f.L.year,standings=f.standings,champion=f.post.champion))
                audit.checkpoint(f,history)
                if f.L.year>year and f.stop==('week',1): break
            else: raise RuntimeError('Calendar did not complete year within 120 advances')
            audit.snapshot(f.L,'end_offseason')
            audit.folder.joinpath(f'checkpoint_{f.L.year}.json').write_text(f.save(),encoding='utf8')
            audit.folder.joinpath('history.json').write_text(json.dumps(history,default=str,indent=2),encoding='utf8')
            audit.checkpoint(f,history)
        if audit.register.ngames:
            audit.folder.joinpath('register.json').write_text(json.dumps(dict(
                base=base,games=audit.register.ngames,all=audit.register.got(),
                by_year={year:dict(games=c.ngames,metrics=c.got())
                         for year,c in audit.register_by_year.items()},
                targets=[dict(metric=name,target=real,tolerance=tol,control=ctrl)
                         for name,real,tol,ctrl in TARGETS]),
                default=json_default,indent=2),encoding='utf8')
    finally:
        audit.moves.close()
        audit.events.close()
        audit.kickoffs.close()
        audit.games.close()


if __name__=='__main__':
    main()
