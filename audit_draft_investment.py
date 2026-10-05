"""Read-only saved-draft counterfactuals. Never writes to the supplied save."""
import argparse, json
from pathlib import Path
import numpy as np
from league import League, DraftPick
from draft_day import Draft
import draft as D


def prepare(raw):
    L=League.load(json.loads(json.dumps(raw)))
    results=L.last_draft['results']; drafted={r[2] for r in results}
    L.draft_pool=[L.players[pid] for pid in L.consensus if pid in L.players]
    for t in L.teams.values():
        t.roster[:]=[p for p in t.roster if p.pid not in drafted]
    return L,results


def review(path):
    raw=json.loads(Path(path).read_text(encoding='utf-8'))
    L,results=prepare(raw);level=D.league_starter_level(L);taken=set();late=[]
    user=raw.get('_user_team','GB')
    for sel,a,pid in results:
        if (a==user and sel>160) or pid in taken:
            p=D.board(L,a,sel,level,taken)[0][1]
            late.append(dict(selection=sel,team=a,old=L.players[pid].name,new=p.name,pos=p.pos,ovr=round(p.ovr)))
        else:p=L.players[pid]
        L.teams[a].roster.append(p);p.team=a;taken.add(p.pid)
    report=dict(late_continuation=late,user_receivers=[p.name for p in L.teams[user].roster if p.pos=='WR'])
    L,results=prepare(raw)
    draft=Draft(L,np.random.default_rng(3),L.last_draft['year'],user_team=user,level=level)
    draft.picks=[DraftPick(draft.year,(sel-1)//32+1,a,a,selection=sel) for sel,a,pid in results]
    # Restore available picks at their saved owners. On-clock trade collateral
    # is assigned to its offering club below for the corresponding preview.
    for t in L.teams.values():
        for pk in t.picks:
            if pk.year==draft.year:pk.used_on=None
    trades={r[0]:r for r in L.last_draft['trade_log']}; checks=[]
    for sel,a,pid in results:
        draft.i=sel-1
        if sel in (1,12,17):
            board=draft.board_for(a)
            checks.append(dict(selection=sel,team=a,old=L.players[pid].name,
                               old_rank=next(i+1 for i,(_,p) in enumerate(board) if p.pid==pid),
                               preferred=board[0][1].name))
        if sel in trades:
            _,buyer,seller,sent=trades[sel]
            extra=[]
            for label in sent:
                if label.startswith('pick '):
                    n=int(label.split()[1]);extra.append(DraftPick(draft.year,(n-1)//32+1,buyer,buyer,selection=n))
            L.teams[buyer].picks.extend(extra)
            asset=draft._target_asset(buyer,draft.current(),L.players[pid])
            checks.append(dict(selection=sel,team=buyer,target=L.players[pid].name,
                               old_premium=1.2,new_premium=round(asset['draft_target_premium'],3),paid=sent))
            for pk in extra:L.teams[buyer].picks.remove(pk)
        L.teams[a].roster.append(L.players[pid]);draft.taken.add(pid)
    report['original_choice_checks']=checks
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('save');parser.add_argument('--out')
    args=parser.parse_args();result=review(args.save)
    text=json.dumps(result,indent=2)
    if args.out:Path(args.out).write_text(text,encoding='utf-8')
    print(text)
