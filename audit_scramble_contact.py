"""Paired opportunities, not a season simulation or NFL calibration."""
import json
import subprocess
import types
from pathlib import Path
import numpy as np
import events
import plays


def run(n=5000):
    old = types.ModuleType('baseline_events')
    exec(compile(subprocess.check_output(['git', 'show', '42e597c:events.py']).decode(),
                 'baseline_events', 'exec'), old.__dict__)
    defenders = [dict(pid=f'd{i}', pos=pos) for i, pos in enumerate(
        ['LEDG', 'DT', 'DT', 'REDG', 'MIKE', 'WILL', 'CB', 'CB', 'CB', 'SS', 'FS'])]
    result = []
    for label, qb in [('neutral', dict(pid='qb', pos='QB')),
                      ('strong_runner', dict(pid='qb', pos='QB', speed_rating=90,
                       accel_rating=90, agility_rating=90, break_tackle_rating=90,
                       strength_rating=85))]:
        for goal in (3, 10, 50):
            rows = []
            for seed in range(n):
                a = old.resolve_scramble(qb, defenders, goal, np.random.default_rng(seed), plays.rate)
                b = events.resolve_scramble(qb, defenders, goal, np.random.default_rng(seed), plays.rate)
                rows.append((a, b))
            contacted = [b for a, b in rows if 'pre_goal_contact_yards' in b]
            result.append(dict(qb=label, goal_distance=goal, opportunities=n,
                baseline_mean_yards=round(float(np.mean([a['yards'] for a,b in rows])), 4),
                new_mean_yards=round(float(np.mean([b['yards'] for a,b in rows])), 4),
                baseline_td=sum(a['touchdown'] for a,b in rows),
                new_td=sum(b['touchdown'] for a,b in rows),
                contacted_td=sum(b['touchdown'] for b in contacted),
                broken_tackles=sum(b.get('broken_tackles', 0) for b in contacted),
                contacts=len(contacted),
                front_first_contacts=sum(b['pre_goal_contact_by'] in ['d0','d1','d2','d3'] for b in contacted),
                untouched_changed=sum(a != {k:v for k,v in b.items() if k != 'tackler'}
                                      for a,b in rows if a['touchdown'])))
    return result


if __name__ == '__main__':
    output = run()
    Path('research/scramble_contact_opportunities_20261005.json').write_text(
        json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))
