"""Read-only fixed-seed production-game diagnostics for cf70245."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
import league
import season
from calibrate import Collector, TARGETS


def run():
    collector = Collector()
    games, violations = [], []
    penalties = Counter()
    # Each team plays once per seed; fresh rosters, no season progression.
    seeds = [100141, 100142]
    for seed in seeds:
        lg = league.build_league(rng=np.random.default_rng(seed))
        runner = season.SeasonRunner(lg, np.random.default_rng(seed + 1000))
        teams = sorted(lg.teams)
        np.random.default_rng(seed).shuffle(teams)
        for home, away in zip(teams[::2], teams[1::2]):
            result = runner.play(home, away, 1)
            collector.add(result)
            scored = dict(home=0, away=0)
            flags = Counter()
            for side, drive in result['drives']:
                credited = side if drive.points >= 0 else ('away' if side == 'home' else 'home')
                scored[credited] += abs(drive.points)
                previous = None
                for play in drive.log:
                    clock = play.get('clock')
                    if clock is not None:
                        if clock < 0 or clock > 3600 or (previous is not None and clock > previous):
                            violations.append(dict(seed=seed, home=home, away=away, kind='drive_clock', previous=previous, play=play))
                        previous = clock
                    # Accepted penalties have their own log row. Return and try
                    # events may also carry the same flag; do not double count.
                    if play.get('type') == 'penalty':
                        flags[play['penalty']] += 1
            if scored != {s: result[s] for s in ('home', 'away')}:
                violations.append(dict(seed=seed, home=home, away=away, kind='score', reconstructed=scored, actual={s:result[s] for s in scored}))
            penalties.update(flags)
            games.append(dict(seed=seed, home=home, away=away, home_score=result['home'], away_score=result['away'], drives=len(result['drives']), penalties=dict(flags)))
            print(f'{len(games)}/32: {home} {result["home"]}-{result["away"]} {away}', flush=True)
    got = collector.report('Week 3 targeted-fix production slice')
    misses = [dict(metric=n, value=float(got[n]), target=t, tolerance=tol) for n,t,tol,_ in TARGETS if abs(got[n]-t)>tol]
    output = dict(commit='cf70245', seeds=seeds, runner_seed_offset=1000,
        scope='32 fresh-roster games; every team once per seed; not a full-season calibration',
        games=games, violations=violations, penalties=dict(penalties), register=got, misses=misses,
        collector=json.loads(collector.to_json()))
    Path('week3_register_audit.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(f'Invariant violations: {len(violations)}', flush=True)


if __name__ == '__main__':
    run()
