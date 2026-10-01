"""Controlled construction-only study. No games, wins or performance inferred."""
import argparse, copy, json, time
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import numpy as np
import league as LG, coaching_pool as CP, gm_engine as GE, roster_needs as RN
import contracts as CT, market as MK, trades as TR, newgens as NG, scouting as SC
import draft as DFT, cutdown as CD, regression as RG, practice_squad as PS
import extensions as EXT, tags as TAG, waivers as WV

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--years',type=int,default=3); ap.add_argument('--seed',type=int,default=93041); ap.add_argument('--output',required=True)
    args=ap.parse_args(); rng=np.random.default_rng(args.seed); start=time.time()
    L=LG.build_league(rng=rng); L.user_team=None
    L.set_phase('offseason'); CD.finalize(L,rng)
    tracked={'GB':('3-4','12','gap'),'DEN':('multiple','21','zone'),'ATL':('4-3','10','gap')}
    result=dict(seed=args.seed,limitations='Construction only: no games, seasonal production, injury, XP, retirement or owner performance feedback. Incoming hires controlled; draft order synthetic alphabetical, not standings. Initial rosters normalized to53. Not a causal comparison against unchanged coaches.',snapshots=[],decisions=[],draft_counts=[])
    previous={a:set() for a in tracked}
    def save():
        Path(args.output).write_text(json.dumps(result,indent=2,default=str))
    def snap(stage):
        for a in tracked:
            t=L.teams[a]; report=RN.assess(t); men=list(t.active()); ids={p.pid for p in men}
            fit,misfits=CP.roster_fit(t,t.gm)
            result['snapshots'].append(dict(year=L.year,stage=stage,team=a,coach=t.gm.name,front=t.gm.def_front,personnel=t.gm.off_personnel,blocking=t.gm.off_blocking,
                count=len(men),positions=dict(Counter(p.pos for p in men)),fit=fit,misfits=len(misfits),cap=t.cap_space,
                quality=report['_package_scores'],needs=report['package_needs'],demand=report['package_demand'],
                arrivals=[dict(pid=p.pid,name=p.name,pos=p.pos,ovr=p.ovr,fit=GE.scheme_fit(p.ratings,p.pos,t)) for p in men if p.pid not in previous[a]],departures=sorted(previous[a]-ids)))
            previous[a]=ids
        save(); print(stage,L.year,round(time.time()-start,1),flush=True)
    snap('before_hire')
    for a,(front,pers,blocking) in tracked.items():
        g=copy.deepcopy(L.teams[a].gm); g.name='Study '+a; g.def_front=front; g.off_personnel=pers; g.off_blocking=blocking
        g.background='former head coach'
        with patch.object(CP,'owner_hire',return_value=(g,{})):
            CP.fire_and_hire(L,L.teams[a],rng)
    snap('after_hire')
    for _ in range(args.years):
        log_start=len(L.transactions)
        L.set_phase('offseason'); RG.tick_ages(L); RG.run(L,rng,tick_age=False)
        L.roll_year(rng); L.advance_contracts(); CT.run(L,rng); CT.enforce(L,rng)
        EXT.ai_round(L,rng); TAG.run(L,rng); CT.enforce(L,rng)
        snap('contracts')
        MK.run(L,rng); snap('free_agency')
        TR.run(L,rng,rounds=2); snap('trades')
        NG.build(L,rng,draft_year=L.year); L.draft_pool=L.next_class; L.next_class=[]; SC.scout(L,rng)
        order={a:i for i,a in enumerate(sorted(L.teams))}
        for t in L.teams.values():
            for pick in t.picks:
                if pick.year==L.year-1: pick.selection=(pick.round-1)*32+order[pick.original]+1
        drafted=DFT.run(L,rng,year=L.year-1)
        assert len(drafted)==224, f'Invalid study draft: {len(drafted)} picks'
        result['draft_counts'].append(dict(year=L.year,picks=len(drafted)))
        PS.udfa_camp(L,rng); snap('draft')
        for t in L.teams.values():
            for p in list(PS.squad(t)): PS.release_from_squad(L,t.abbr,p.pid)
        PS.reset_season(L); CD.finalize(L,rng); WV.process(L,rng,0); PS.fill_squads(L,rng); snap('cutdown')
        result['decisions'].extend(x for x in L.transactions[log_start:] if x.get('team') in tracked or x.get('a') in tracked or x.get('b') in tracked)
        save()

if __name__=='__main__': main()
