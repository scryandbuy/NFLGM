"""Replay a copied offseason through opening rosters; source save stays read-only.

Uses Session.advance with all32 CPU teams. Human presentation prompts are
omitted; production cap/cutdown logic still executes. Does not simulate games.
"""
import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path
import roster_needs as RN
import cutdown as CD
from audit_financial_franchise import AuditSession


def snapshot(session,label):
    rows=[]
    for t in session.L.teams.values():
        r=RN.assess(t);counts=Counter(p.pos for p in t.active())
        rows.append(dict(team=t.abbr,active=len(t.active()),cap=round(t.cap_space,4),
            dead=round(t.cap.dead,4),dead_next=round(t.cap.dead_next,4),front=r['front'],
            personnel=t.gm.off_personnel,score=round(r['score'],3),counts=dict(counts),
            essential=RN.essential_coverage(t,report=r)['shortages'],
            starters=[dict(role=a['role'],pid=a['player'].pid if a['player'] else None,
                name=a['player'].name if a['player'] else None,pos=a['player'].pos if a['player'] else None,
                grade=round(a['grade'],2) if a['grade'] is not None else None) for a in r['assignments']],
            roster=[dict(pid=p.pid,name=p.name,pos=p.pos,ovr=round(p.ovr,2)) for p in t.active()]))
    return dict(label=label,year=session.L.year,stop=session.stop,teams=rows)


def run(source,output):
    started=time.monotonic()
    raw=json.loads(Path(source).read_text(encoding='utf-8-sig'))
    if 'session' in raw:raw=json.loads(raw['session'])
    raw['_user_team']=None
    s=AuditSession.load(json.dumps(raw));s.user_team=None;s.L.user_team=None
    if s.stop[0]!='offseason':raise ValueError('Use an offseason save')
    out=dict(source=str(source),commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        method='AllCPU Session.advance; no games; copied saved RNG; human prompts omitted',
        snapshots=[snapshot(s,'loaded')],steps=[],transactions=[],error=None)
    count=len(s.L.transactions)
    try:
        for _ in range(24):
            old=s.stop
            label=s.OFFSEASON[old[1]][1] if old[0]=='offseason' else old[0]
            print('ADVANCE',old,label,flush=True)
            stage_started=time.monotonic()
            result=s.advance()
            advance_seconds=time.monotonic()-stage_started
            out['steps'].append(dict(before=old,after=s.stop,result=result,advance_seconds=round(advance_seconds,3)))
            measured=time.monotonic()
            out['snapshots'].append(snapshot(s,label))
            out['steps'][-1]['snapshot_seconds']=round(time.monotonic()-measured,3)
            out['transactions']=s.L.transactions[count:]
            Path(output).write_text(json.dumps(out,indent=2,default=str),encoding='utf-8')
            if s.stop[0]=='week':break
            if s.stop==old and not s.draft_live():
                if old[0]=='wire' and result.get('done')=='Cap compliance cuts are on waivers':
                    continue
                raise RuntimeError('Advance blocked: '+str(result))
        else:raise RuntimeError('Did not reach opening week within24 advances')
        out['final_violations']=CD.violations(s.L)
    except Exception as exc:
        out['error']=repr(exc)
        raise
    finally:
        out['elapsed_seconds']=round(time.monotonic()-started,3)
        out['transactions']=s.L.transactions[count:]
        Path(output).write_text(json.dumps(out,indent=2,default=str),encoding='utf-8')
    print('COMPLETE',s.stop,'violations',out['final_violations'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('save');parser.add_argument('output')
    args=parser.parse_args();run(args.save,args.output)
