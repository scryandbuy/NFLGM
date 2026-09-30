"""Matched fixed-roster register; historical timing variants are diagnosis only."""
import argparse
import collections
import json
from pathlib import Path
import subprocess
import time

import calibrate as C
import game as G


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', default='fixed', choices=(
        'fixed', 'baseline', 'old-presnap', 'old-live', 'old-both'))
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.variant != 'fixed':
        source = subprocess.check_output(['git', 'show', '31764be:game.py'], text=True)
        if args.variant in ('old-presnap', 'old-both'):
            needle = "if pen and pen['nullifies']:\n"
            assert source.count(needle) == 1
            source = source.replace(needle, needle + "            _tick(dr, play_seconds('penalty'))\n")
        if args.variant in ('old-live', 'old-both'):
            needle = '_tick(dr, min(6.0, play_seconds(t, hurry=hurry_p, timeout=used_p)))'
            assert source.count(needle) == 1
            source = source.replace(needle, "_tick(dr, play_seconds(t, hurry=hurry_p, timeout=used_p, tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5)) + (0 if used_p else play_seconds('penalty')))")
        exec(compile(source, '<diagnostic-clock-variant>', 'exec'), G.__dict__)
    counts = collections.Counter()
    original = C.Collector.add
    def add(self, result):
        counts['games'] += 1
        for _, drive in result['drives']:
            for event in drive.log:
                counts['presnap'] += event.get('timing') == 'before_snap'
                counts['nullified'] += bool(event.get('nullified'))
                counts['ready_seconds'] += event.get('ready_seconds', 0)
        original(self, result)
    C.Collector.add = add
    start = time.monotonic()
    got = C.run(seed=args.seed, verbose=False)
    misses = {name: float(got[name]) for name, target, tolerance, _ in C.TARGETS
              if abs(got[name] - target) > tolerance}
    payload = dict(variant=args.variant, seed=args.seed, seconds=round(time.monotonic()-start, 1),
                   metrics=got, misses=misses, counts=dict(counts))
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({k: payload[k] for k in ('variant', 'seed', 'seconds', 'misses', 'counts')}))
    print({k: got[k] for k in ('offensive_plays_per_gm', 'drives_per_game', 'points_per_team')})


if __name__ == '__main__':
    main()
