"""Compare matched accelerated offseasons; do not treat carryover as Week 1."""
import argparse
import json
import statistics
from pathlib import Path


def summarize(snapshot):
    teams = snapshot['teams']
    rooms = sorted(t['cap'] for t in teams)
    q = statistics.quantiles(rooms, n=4, method='inclusive')
    return dict(snapshot['summary'], room_p25=q[0], room_p75=q[2],
                maximum_room=max(rooms), minimum_roster=min(t['active'] for t in teams),
                maximum_roster=max(t['active'] for t in teams),
                mean_dead=statistics.mean(t['dead'] for t in teams),
                teams_with_uncovered_roles=sum(bool(t['uncovered']) for t in teams),
                minimum_funded_room=min(t['financial_plan']['funded_room'] for t in teams))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('baseline', type=Path)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    a, b = [json.loads(p.read_text(encoding='utf-8')) for p in (args.baseline, args.candidate)]
    assert a['seed'] == b['seed'], 'Use paired seeds'
    assert [x['summary']['phase'] for x in a['snapshots']] == [x['summary']['phase'] for x in b['snapshots']]
    assert a['snapshots'][0]['summary'] == b['snapshots'][0]['summary'], 'Initial states differ'
    rows = [dict(phase=x['summary']['phase'], baseline=summarize(x), candidate=summarize(y))
            for x, y in zip(a['snapshots'], b['snapshots'])]
    result = dict(seed=a['seed'], methodology=a['methodology'], phases=rows,
                  limitations=['Single accelerated offseason, not a multi-season calibration',
                               'Different acquisitions change subsequent random draws',
                               'No same-phase real NFL Week 1 target has been fitted',
                               'Synthetic alphabetical draft order; no games, injuries, retirement or regression'])
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(rows[-1], indent=2))


if __name__ == '__main__':
    main()
