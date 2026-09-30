"""Replay final offseason snapshots without rerunning the seasons."""
import json
import sys
from pathlib import Path
import cutdown as CD
from session import Session


def run(path):
    s = Session.load(Path(path).read_text(encoding='utf-8'))
    L = s.L
    L.user_team = None
    L.phase = 'offseason'
    for team in L.teams.values(): team.phase = 'season'
    before = {a: dict(size=len(t.active()), cap=round(t.cap_space, 3))
              for a, t in L.teams.items()}
    transaction_count = len(L.transactions)
    print('loaded', str(path), flush=True)
    CD.finalize(L, s.rng)
    result = dict(path=str(path), before=before,
                  after={a: dict(size=len(t.active()), cap=round(t.cap_space, 3))
                         for a, t in L.teams.items()}, problems=CD.violations(L))
    result['repair_moves'] = L.transactions[transaction_count:]
    for attempt in range(5):
        if s.step_clear_wire() is not False: break
    result['wire_attempts'] = attempt+1
    result['wire_phase'] = L.phase
    result['wire_problems'] = CD.violations(L)
    print(json.dumps(dict(path=str(path), changed={a:dict(before=before[a],after=v)
          for a,v in result['after'].items() if v!=before[a]},
          problems=result['problems'], wire_phase=L.phase,
          wire_attempts=attempt+1, wire_problems=result['wire_problems'])), flush=True)
    return result


if __name__ == '__main__':
    results = [run(p) for p in sys.argv[2:]]
    Path(sys.argv[1]).write_text(json.dumps(results, indent=2), encoding='utf-8')
    if any(r['problems'] or r['wire_problems'] or r['wire_phase']!='regular'
           for r in results): raise SystemExit(1)
