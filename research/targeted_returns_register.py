"""Paired-start full-game register for return and quarterback-run changes.

Run separately in baseline and candidate checkouts with the same seeds.
Each club plays once per seed; this is a targeted slice, not a season forecast.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

import league
import season
from calibrate import Collector, TARGETS


def run(seeds):
    collector = Collector()
    counts = Counter()
    punt_yards, kickoff_yards, scramble_yards = [], [], []
    violations = []
    examples = []
    for seed in seeds:
        lg = league.build_league(rng=np.random.default_rng(seed))
        runner = season.SeasonRunner(lg, np.random.default_rng(seed + 1000))
        teams = sorted(lg.teams)
        np.random.default_rng(seed).shuffle(teams)
        for home, away in zip(teams[::2], teams[1::2]):
            result = runner.play(home, away, 1)
            collector.add(result)
            scored = dict(home=0, away=0)
            for side, drive in result['drives']:
                credited = side if drive.points >= 0 else ('away' if side == 'home' else 'home')
                scored[credited] += abs(drive.points)
                for play in drive.log:
                    if not isinstance(play, dict) or play.get('nullified'):
                        continue
                    kind = play.get('type')
                    if kind == 'punt':
                        counts['punts'] += 1
                        if play.get('how') == 'return':
                            counts['punt_returns'] += 1
                            punt_yards.append(float(play.get('ret', 0) or 0))
                            if play.get('touchdown'):
                                counts['punt_return_td'] += 1
                                if len(examples) < 6:
                                    examples.append(dict(seed=seed, home=home, away=away,
                                                         kind=kind, yards=play.get('ret'),
                                                         pursuit=play.get('punt_pursuit')))
                    elif kind == 'kickoff':
                        counts['kickoffs'] += 1
                        counts['kickoff_touchbacks'] += int(bool(play.get('touchback')))
                        if not play.get('touchback') and play.get('returner'):
                            counts['kickoff_returns'] += 1
                            kickoff_yards.append(float(play.get('ret', 0) or 0))
                            if play.get('touchdown'):
                                counts['kickoff_return_td'] += 1
                                if len(examples) < 6:
                                    examples.append(dict(seed=seed, home=home, away=away,
                                                         kind=kind, yards=play.get('ret')))
                    elif kind == 'scramble':
                        counts['scrambles'] += 1
                        scramble_yards.append(float(play.get('yards', 0) or 0))
                    elif kind == 'sack':
                        counts['sacks'] += 1
            if scored != {side: result[side] for side in ('home', 'away')}:
                violations.append(dict(seed=seed, home=home, away=away,
                                       reconstructed=scored,
                                       actual={side: result[side] for side in ('home', 'away')}))
    got = collector.got()
    misses = {name: dict(value=round(float(got[name]), 3), target=target,
                         tolerance=tolerance)
              for name, target, tolerance, _ in TARGETS
              if abs(got[name] - target) > tolerance}
    def avg(values):
        return round(float(np.mean(values)), 3) if values else 0.
    return dict(scope='One independent game per club per seed; full game engine, no offseason',
                seeds=list(seeds), games=collector.ngames, counts=dict(counts),
                punt_return_average=avg(punt_yards), kickoff_return_average=avg(kickoff_yards),
                scramble_average=avg(scramble_yards),
                scramble_short_pct=round(100 * sum(y <= 3 for y in scramble_yards) /
                                        max(1, len(scramble_yards)), 3),
                register={key: round(float(value), 3) for key, value in got.items()},
                misses=misses, score_violations=violations, return_examples=examples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, nargs='+', default=[100641, 100642, 100643, 100644])
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    report = run(args.seeds)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('games', 'counts', 'punt_return_average',
                                                  'kickoff_return_average', 'scramble_average',
                                                  'scramble_short_pct', 'misses', 'score_violations')}, indent=2))
