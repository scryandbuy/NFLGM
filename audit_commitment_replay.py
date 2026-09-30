"""Reconstruct saved camp decisions, not a bit-identical full offseason replay.

Stage snapshots supply ownership and grades; native final checkpoints supply
ratings/coach data. Released contracts are rebuilt from observed hit/dead/year
values. This isolates roster selection; cap cleanup remains a separate gate.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from cap_engine import Contract
from session import Session
import cutdown as CD
import roster_needs as RN
import market as M


def camp_team(session, row, events, year):
    t = session.L.teams[row['team']]
    t.roster = [session.L.player(pid) for pid in row['roster_ids']]
    t.ir = [session.L.player(pid) for pid in row['ir_ids']]
    for q in t.roster:
        q.team = t.abbr; q.xp_spent.pop('_ps', None)
        r = next(r for r in row['players'] if r['pid'] == q.pid)
        if abs(q.ovr-r['ovr']) > .002:
            raise ValueError(f'Checkpoint ratings changed for {q.pid}; cannot replay this stage')
        release = next((e for e in events if e['year']==year and e['kind']=='release'
                        and e.get('pid')==q.pid and e.get('team')==t.abbr
                        and e.get('audit_stage') in ('cutdown.finalize','wire')), None)
        if release or not q.contract:
            yrs = max(1, r['years'])
            bonus = (release.get('dead',0)+release.get('dead_next',0)) if release else 0
            q.contract = Contract(yrs, [max(0,r['cap_hit']-bonus/yrs)]*yrs,
                                  signing_bonus=bonus, signed=year)
    return t


def run(root):
    results = []
    for seed in (93030,93031):
        folder=root/f'team-study-{seed}'
        cases=[x for x in json.loads((folder/'summary.json').read_text())['first_camp_draft_cuts']
               if x['draft']['round']==2]
        snapshots=json.loads((folder/'snapshots.json').read_text())
        events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
        for year in sorted({x['draft']['year'] for x in cases}):
            s=Session.load((folder/f'checkpoint_{year}.json').read_text())
            snap=next(x for x in snapshots if x['year']==year and x['label']=='step_camp')
            for abbr in sorted({x['draft']['team'] for x in cases if x['draft']['year']==year}):
                row=next(t for t in snap['teams'] if t['team']==abbr)
                t=camp_team(s,row,events,year);rows=CD.rows_for(t)
                with patch.object(RN,'retention_value',return_value=0):
                    before=RN.select_cutdown(t,rows)
                after=RN.select_cutdown(t,rows)
                old_missing,old_quality=RN.lineup_strength(t,[p for p in t.active() if p.pid in before])
                missing,quality=RN.lineup_strength(t,[p for p in t.active() if p.pid in after])
                for x in cases:
                    d=x['draft']
                    if d['year']!=year or d['team']!=abbr:continue
                    p=s.L.player(d['pid'])
                    r=dict(seed=seed,year=year,team=abbr,pid=p.pid,name=p.name,pos=p.pos,
                           ovr=round(p.ovr,3),retention=round(RN.retention_value(t,p),3),
                           selected_before=p.pid in before,selected_after=p.pid in after,
                           size=len(after),missing_before=old_missing,missing=missing,
                           quality_change=round(quality-old_quality,3),
                           observed_destination=x['destination_at_regular_gate'],
                           incoming=sorted(after-before),outgoing=sorted(before-after))
                    results.append(r); print(json.dumps(r),flush=True)
    return results


def miami(root):
    folder=root/'team-study-93031'
    s=Session.load((folder/'checkpoint_2027.json').read_text())
    snaps=json.loads((folder/'snapshots.json').read_text())
    row=next(t for x in snaps if x['label']=='step_extensions' for t in x['teams'] if t['team']=='MIA')
    t=s.L.teams['MIA'];t.roster=[s.L.player(pid) for pid in row['roster_ids']];t.ir=[]
    a=s.L.player('P0060');b=s.L.player('P0862')
    initial=RN.assess(t)['score'];gain=RN.move_gain(t,b)
    bid=M.Offer('MIA',b.pid,29.10,3,planning_gain=gain)
    a.team='MIA';a.xp_spent.pop('_ps',None)
    a.contract=Contract(3,[9.85,13.137,8.631],signing_bonus=17.402,signed=2027)
    t.roster.append(a);t.sync_cap()
    # Isolate role reconsideration from later cap cleanup; this reconstructed
    # state has substantial observed FA room, not a reconstructed cap ledger.
    with patch.object(M,'power',return_value=100):
        revised=M.reconsider_bid(s.L,b,bid)
    report=RN.assess(t,t.active()+[b]);roles={p.pid:[] for p in (a,b)}
    shares={p.pid:0 for p in (a,b)}
    for r in report['package_assignments']:
        p=r['player']
        if p is not None and p.pid in roles:
            roles[p.pid].append(r['role']);shares[p.pid]+=r['weight']
    result=dict(initial_score=initial,after_first=RN.assess(t)['score'],
                second_gain=RN.move_gain(t,b),original_offer=29.10,
                revised_offer=revised.apy if revised else None,
                roles={pid:sorted(set(v)) for pid,v in roles.items()},shares=shares,
                limitation='Role replay only; final-checkpoint cap ledger is not pre-FA funding')
    print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('study_root');parser.add_argument('output')
    a=parser.parse_args();results=run(Path(a.study_root))
    Path(a.output).write_text(json.dumps(dict(rookies=results,miami=miami(Path(a.study_root))),indent=2),encoding='utf8')
