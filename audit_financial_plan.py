"""Matched CPU offseason replay without game simulation or coefficient overrides.

Use --engine-root to run this same harness against an immutable baseline. The
financial snapshot is observational when loaded against that older engine.
This is an accelerated roster-market probe, not a full-season NFL comparison.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--engine-root',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--seed',type=int,default=30102)
    ap.add_argument('--finish-roster',action='store_true')
    ap.add_argument('--decision-log',type=Path,help='Optional observational financial decisions (JSONL)')
    args=ap.parse_args()
    root=args.engine_root.resolve();os.chdir(root);sys.path.insert(0,str(root))
    import numpy as np
    import league as LG
    import market as M
    import contracts as CT
    import tags as T
    import roster_needs as RN
    spec=importlib.util.spec_from_file_location('financial_probe',Path(__file__).with_name('financial_plan.py'))
    F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
    rng=np.random.default_rng(args.seed)
    started=time.monotonic()
    L=LG.build_league(rng=rng);L.user_team=None
    if args.decision_log:
        import atexit
        import financial_plan as policy
        args.decision_log.parent.mkdir(parents=True,exist_ok=True)
        stream=args.decision_log.open('w',encoding='utf-8')
        atexit.register(stream.close)
        evaluate=policy.evaluate
        def observed(league,team,**kw):
            result=evaluate(league,team,**kw)
            a=result['after'];b=result['before']
            row=dict(year=league.year,phase=league.phase,team=team.abbr,
                     action=kw.get('action'),gain=kw.get('gain',0),
                     essential=kw.get('essential',False),approved=result['approved'],
                     reason=result['reason'],raw_before=b['raw_room'],raw_after=a['raw_room'],
                     funded_before=b['funded_room'],funded_after=a['funded_room'],
                     reserve=a['soft_reserve'],reserve_used=result['reserve_used'],
                     players=[dict(pid=p.pid,pos=p.pos,ovr=p.ovr) for p,c in kw.get('additions',())])
            stream.write(json.dumps(row)+'\n');stream.flush()
            return result
        policy.evaluate=observed
    snapshots=[]
    def capture(phase):
        teams=[]
        for t in L.teams.values():
            budget=F.snapshot(L,t)
            r=RN.assess(t)
            teams.append(dict(team=t.abbr,active=len(t.active()),cap=t.cap_space,
                              score=r['score'],uncovered=r['uncovered'],dead=t.cap.dead,
                              dead_next=t.cap.dead_next,financial_plan=budget))
        rooms=[t['cap'] for t in teams]
        summary=dict(phase=phase,year=L.year,median_room=statistics.median(rooms),
                     below_1m=sum(x<1 for x in rooms),negative=sum(x<-.0005 for x in rooms),
                     mean_score=statistics.mean(t['score'] for t in teams),
                     mean_active=statistics.mean(t['active'] for t in teams))
        snapshots.append(dict(summary=summary,teams=teams))
        print(json.dumps(summary),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(seed=args.seed,root=str(root),
            methodology='Accelerated offseason: age/contracts advance but no games, injuries, retirement or regression simulated. Same seed and harness in baseline and candidate. Not a completed multi-season franchise health study.',
            snapshots=snapshots,transactions=len(L.transactions),seconds=time.monotonic()-started),indent=2),encoding='utf-8')
    capture('initial_2026_roster')
    L.set_phase('offseason');L.season_closed_year=L.year
    L.roll_year(rng);L.advance_contracts()
    # Actual cleanup + tag/expiry paths prepare a market; no invented FA roster.
    CT.run(L,rng);T.run(L,rng);CT.enforce(L,rng)
    L.set_phase('free_agency')
    capture('market_open')
    for phase in (1,2,3):
        L.fa_step=phase
        pool=M._pool(L)
        bids=M.ai_bids(L,pool,phase,rng)
        signed,waiting,msgs=M.resolve_phase(L,pool,bids,phase,rng)
        for msg in msgs: M.inbox_add(L,msg,rng)
        M.resolve_offer_sheets(L,rng)
        capture('free_agency_'+str(phase))
    M.sign_the_leftovers(L,[p for p in M._pool(L) if p.team is None],rng)
    capture('market_close')
    if args.finish_roster:
        # A real draft class and picks, then normal roster/waiver finalization.
        import draft_class as DC
        import scouting as SC
        import draft as D
        import franchise as FR
        DC.build(L,rng,draft_year=L.year);SC.scout(L,rng)
        for t in L.teams.values():
            for pk in t.picks:
                if pk.year==L.year-1 and not pk.selection:
                    pk.selection=(pk.round-1)*32+sorted(L.teams).index(pk.original)+1
        D.run(L,rng,year=L.year-1)
        M.fill_out_rosters(L,[p for p in M._pool(L) if p.team is None],rng)
        L.set_phase('camp');FR.settle_final_rosters(L,rng)
        L.set_phase('regular');L.week=1
        capture('week1_after_roster_finalization')
    print('Finished',round(time.monotonic()-started,1),'seconds',flush=True)


if __name__=='__main__': main()
