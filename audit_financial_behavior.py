"""Controlled GM decision scenarios using real roster gains and market bids.

No NFL dollar-target fitting; fixtures vary budgets, needs and GM preferences.
The actual valuation/contract/financial functions are unmocked. This does not
simulate games or establish long-term franchise balance.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from cap_engine import Contract
from test_draft_planning import fixture, set_grade
import financial_plan as F
import market as M
import roster_needs as R


def setup(profile='balanced', room=12., hole=True):
    L, t = fixture()
    L.set_phase('free_agency'); t.picks=[]
    profiles = {
        'patient': (1.,0.,0.,1.,[2,8,0],.25),
        'balanced': (.5,.5,.5,.6,[5,5,0],.5),
        'urgent_contender': (0.,1.,1.,.25,[8,2,0],.75),
    }
    patience,risk,aggression,security,record,previous=profiles[profile]
    t.gm.patience=patience; t.gm.risk=risk; t.gm.aggression=aggression
    t.gm.job_security=security; t.record=record; t.history=[{'win_pct':previous}]
    p=copy.deepcopy(t.by_pos('LT')[0]);p.pid='target';p.name='Target tackle'
    p.team=None;p.contract=None;set_grade(p,88 if hole else 83)
    if hole:
        for q in t.by_pos('LT'):set_grade(q,60)
    L.players[p.pid]=p;L.free_agents=[p.pid]
    t.sync_cap();t.cap.dead+=t.cap.limit-t.cap.charges('season')-room
    return L,t,p


def run():
    rows=[]; checks=[]
    for profile in ('patient','balanced','urgent_contender'):
        for room in (8.,12.,20.,40.):
            for hole in (False,True):
                L,t,p=setup(profile,room,hole)
                gain=R.move_gain(t,p)
                budget=F.snapshot(L,t)
                decisions=[]
                for price in (1.,2.,4.,6.,8.,12.,20.):
                    d=F.evaluate(L,t,additions=[(p,Contract(1,[price]))],gain=gain,action='scenario')
                    decisions.append(dict(price=price,approved=d['approved'],reason=d['reason']))
                # Increasing the same deal's cost must never revive a rejection.
                flags=[d['approved'] for d in decisions]
                assert flags==sorted(flags,reverse=True), (profile,room,hole,decisions)
                bids=M.ai_bids(L,[p],1,np.random.default_rng(42))
                offers=bids.get(p.pid,[])
                rows.append(dict(profile=profile,cap_room=room,weak_starter=hole,
                    gain=gain,reserve=budget['soft_reserve'],decisions=decisions,
                    bids=[o.to_save() for o in offers]))
                if not hole:
                    assert not offers, 'A trivial upgrade should not become a market pursuit'
                if hole and room==40:
                    assert offers, 'A funded large upgrade should not be left unaddressed'
    checks.extend(['price monotonicity for all 24 situations',
                   'no bidding on trivial tackle improvement across profiles/budgets',
                   'all profiles pursue a major funded tackle improvement'])

    L,t,p=setup('urgent_contender',20)
    bids=M.ai_bids(L,[p],1,np.random.default_rng(42));offer=bids[p.pid][0]
    before=R.move_gain(t,p)
    rival=copy.deepcopy(p);rival.pid='already-acquired';rival.team=t.abbr;rival.contract=Contract(1,[1])
    set_grade(rival,95);t.roster.append(rival);L.players[rival.pid]=rival
    revised=M.reconsider_bid(L,p,offer)
    assert revised is None, 'An already-filled job should cancel the redundant target'
    checks.append('outstanding bid withdrawn after better player fills its job')
    return dict(methodology=__doc__,scenarios=rows,checks=checks,
                filled_job=dict(gain_before=before,gain_after=R.move_gain(t,p),bid_cancelled=True))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();result=run();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'situations':len(result['scenarios']),'checks':result['checks']}))
    for row in result['scenarios']:
        if row['weak_starter']:
            print(row['profile'],row['cap_room'],'gain',round(row['gain'],2),
                  'max approved price',max((x['price'] for x in row['decisions'] if x['approved']),default=0),
                  'bids',[(b['apy'],b['years']) for b in row['bids']])
