"""Replay saved roster failures through production repairs and calendar gates."""
import argparse
import json
from pathlib import Path
import time

from audit_financial_franchise import AuditSession, team_report
import cutdown as CD
import financial_plan as FP
import practice_squad as PS
import views_league


def run(path, output, play=False):
    raw = json.loads(Path(path).read_text())
    saved = raw.get('session', raw)
    session = AuditSession.load(saved if isinstance(saved, str) else json.dumps(saved))
    # Omit presentation generation, without altering the production advance.
    views_league.rail = lambda *a, **k: {}
    L = session.L
    start = time.monotonic()
    before = CD.violations(L)
    first_move = len(L.transactions)
    advances = []
    if session.stop[0] == 'wire':
        for _ in range(12):
            result = session.advance()
            advances.append(dict(result=result, stop=list(session.stop), violations=CD.violations(L)))
            print(json.dumps(advances[-1]), flush=True)
            if session.stop[0] == 'week': break
        assert session.stop[0] == 'week', advances
    else:
        CD.finalize(L, session.rng)
    problems = CD.violations(L)
    assert not problems, problems
    reports = [team_report(t) for t in L.teams.values()]
    assert all(not t['package_bad'] for t in reports)
    repaired_moves = len(L.transactions)
    assert CD.repair_depth(L) == 0
    assert len(L.transactions) == repaired_moves
    acquired = set()
    for e in L.transactions[first_move:]:
        key = (e.get('team'), e.get('pid'))
        if e.get('kind') in ('sign', 'ps_callup', 'ps_poach'): acquired.add(key)
        if e.get('kind') == 'release':
            assert key not in acquired, ('Acquisition churn', e)
    checks = {}
    for abbr,t in L.teams.items():
        checks[abbr] = dict(size=len(t.active()), cap=t.cap_space,
            depth=PS.essential_depth(t)['shortages'],
            punters=[p.pid for p in t.by_pos('P')],
            financial=FP.snapshot(L,t)['years'])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    Path(str(output)+'.save.json').write_text(session.save())
    game_result = None
    if play:
        game_result = session.advance()
        assert session.played, game_result
    result = dict(source=str(path), year=L.year, before=before, advances=advances,
        teams=checks, reports=reports, transactions=L.transactions[first_move:repaired_moves],
        second_depth_pass_moves=0, game_result=game_result, seconds=time.monotonic()-start)
    output.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(dict(output=str(output), year=L.year, advances=len(advances),
        roster_repairs=len(result['transactions']), played=bool(game_result), seconds=result['seconds'])), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('save'); p.add_argument('output'); p.add_argument('--play',action='store_true')
    a=p.parse_args(); run(a.save,a.output,a.play)
