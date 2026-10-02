"""Compare full-calendar financial observations with their reloaded saves."""
import argparse
import json
import math
from pathlib import Path

from audit_financial_franchise import AuditSession
import financial_plan as FP


def verify(folder):
    folder = Path(folder)
    snapshots = json.loads((folder / 'snapshots.json').read_text())
    results = []
    for path in sorted(folder.glob('checkpoint_*.json')):
        year = int(path.stem.split('_')[-1])
        expected = next(s for s in snapshots if s['year'] == year and s['label'] == 'end_offseason')
        session = AuditSession.load(path.read_text())
        rng_before = json.dumps(session.rng.bit_generator.state, sort_keys=True)
        transactions_before = len(session.L.transactions)
        differences = []
        for team in expected['teams']:
            actual = FP.snapshot(session.L, session.L.teams[team['team']])
            for before, after in zip(team['financial_plan']['years'], actual['years']):
                for key, value in before.items():
                    if not math.isclose(value, after[key], rel_tol=1e-9, abs_tol=1e-6):
                        differences.append([team['team'], before['year'], key, value, after[key]])
        unchanged = rng_before == json.dumps(session.rng.bit_generator.state, sort_keys=True)
        unchanged &= transactions_before == len(session.L.transactions)
        results.append(dict(year=year, teams=32, differences=differences, rng_and_transactions_unchanged=unchanged))
    (folder / 'final-reload-verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(dict(folder=str(folder), results=results)))
    return all(not r['differences'] and r['rng_and_transactions_unchanged'] for r in results)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('folders', nargs='+')
    results = [verify(folder) for folder in ap.parse_args().folders]
    raise SystemExit(0 if all(results) else 1)
