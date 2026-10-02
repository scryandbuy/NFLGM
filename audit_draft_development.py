"""Compare development opportunities across generated classes, without seasons.

Run from the repository: python audit_draft_development.py --classes 8
"""
import argparse
import collections
import copy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

import draft_class as DC
import newgens as NG
from league import League


def probabilities(rank, pos):
    class Capture:
        def choice(self, size, p):
            self.p = p.copy()
            return 0
    rng = Capture()
    DC.draw_dev(rank, rng, pos=pos)
    return rng.p


def audit(count=8):
    records = []
    per_position = collections.defaultdict(lambda: dict(
        players=0, old_expected=np.zeros(4), new_expected=np.zeros(4),
        old_observed=np.zeros(4, dtype=int), new_observed=np.zeros(4, dtype=int)))
    original_shape = DC.shape_class
    for seed in range(300, 300 + count):
        L = League(2028)
        captured = {}

        def capture(men, rng=None):
            old_rng = np.random.default_rng()
            old_rng.bit_generator.state = copy.deepcopy(rng.bit_generator.state)
            ranked = sorted((p for p in men if p.pos not in ('K', 'P', 'LS')), key=lambda p: -p.ovr)
            ranks = DC.development_percentiles(men)
            for i, p in enumerate(ranked):
                old_rank = i / max(1, len(ranked)-1)
                captured[p.pid] = dict(pos=p.pos, old_rank=old_rank, new_rank=ranks[p.pid],
                    old_dev=DC.draw_dev(old_rank, old_rng, pos=p.pos), ovr=p.ovr)
            for p in men:
                if p.pos in ('K', 'P', 'LS'):
                    captured[p.pid] = dict(pos=p.pos, old_rank=.5, new_rank=.5,
                        old_dev=DC.draw_dev(.5, old_rng, pos=p.pos), ovr=p.ovr)
            return original_shape(men, rng=rng)

        with patch.object(DC, 'shape_class', side_effect=capture):
            NG.build(L, np.random.default_rng(seed), 2029)
        row = dict(seed=seed, strength=L.class_strength,
                   old_observed=dict(collections.Counter(x['old_dev'] for x in captured.values())),
                   new_observed=dict(collections.Counter(p.dev for p in L.next_class)),
                   top_opportunities={})
        for p in L.next_class:
            old = captured[p.pid]
            data = per_position[p.pos]
            data['players'] += 1
            data['old_expected'] += probabilities(old['old_rank'], p.pos)
            data['new_expected'] += probabilities(old['new_rank'], p.pos)
            data['old_observed'][DC.DEV_ORDER.index(old['old_dev'])] += 1
            data['new_observed'][DC.DEV_ORDER.index(p.dev)] += 1
            best = row['top_opportunities'].get(p.pos)
            if best is None or old['ovr'] > best['ovr']:
                row['top_opportunities'][p.pos] = dict(ovr=old['ovr'],
                    old_probabilities=probabilities(old['old_rank'], p.pos).tolist(),
                    new_probabilities=probabilities(old['new_rank'], p.pos).tolist())
        records.append(row)
        print(f"Seed {seed}: old {row['old_observed']} -> new {row['new_observed']}", flush=True)

    totals = {key: np.sum([v[key] for v in per_position.values()], axis=0).tolist()
              for key in ('old_expected', 'new_expected', 'old_observed', 'new_observed')}
    return dict(classes=count, tiers=DC.DEV_ORDER, position_weight=DC.DEV_POSITION_WEIGHT,
                totals=totals, positions={pos: {k: v.tolist() if isinstance(v, np.ndarray) else v
                                               for k, v in data.items()}
                                         for pos, data in per_position.items()}, classes_detail=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--classes', type=int, default=8)
    parser.add_argument('--output', default='draft_development_audit_20261001.json')
    args = parser.parse_args()
    result = audit(args.classes)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['totals'], indent=2))
