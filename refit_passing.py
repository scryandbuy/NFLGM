"""
REFIT THE COMPLETION SCALARS INSIDE REAL GAMES.

Runs the register loop with plays.PASS_TRACE bound, so every attempt records
the pre-scalar quantity the completion roll was built from (separation or
zone window, accuracy, concept, read, disguise, pressure, all multiplied
together). Then, for each path (man / zone) and depth, solves the one scalar
k such that

    mean over attempts of clip(k * base, .02, .97) x (1 - drop gate) = real

Real completion on attempts: behind 78.4, short 71.0, medium 56.0, deep 39.4.
Man completes ~8 points below zone (FTN), so the depth target is split:
man = real - 5, zone = real + 2.5, which weights back to the depth figure at
the engine's own 1/3 : 2/3 man-zone target mix.
"""
import numpy as np, collections, sys
import plays as P, matchups as M

REAL = dict(short=71.0, medium=56.0, deep=39.4)
REAL_BEHIND = 78.4
MAN_OFF, ZONE_OFF = -5.0, 2.5


def trace(weeks=6, seed=2026):
    import passing_diag as D
    P.PASS_TRACE = []
    out = D.run(weeks=weeks, seed=seed, verbose=False)
    tr = [t for t in P.PASS_TRACE if t['path'] in ('man', 'zone')]; P.PASS_TRACE = None
    return tr, out


def solve(base, target, lo=.02, hi=.97):
    """The k that puts the mean clipped probability on the target."""
    base = np.asarray(base, float)
    f = lambda k: np.clip(k * base, lo, hi).mean() - target
    a, b = 0.2, 6.0
    for _ in range(60):
        mid = (a + b) / 2
        if f(mid) > 0: b = mid
        else: a = mid
    return (a + b) / 2


if __name__ == '__main__':
    weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    tr, out = trace(weeks)
    # drop gate: share of caught-by-the-roll balls that are then dropped
    bd = out['by_depth']
    print(f'{len(tr)} attempts traced\n')
    print(f"  {'path':5s} {'depth':7s} {'n':>5s} {'mean base':>10s} {'cur k':>6s} {'cur p':>6s} "
          f"{'target':>7s} {'new k':>6s}")
    new_man, new_zone = {}, {}
    for path in ('man', 'zone'):
        for d in ('short', 'medium', 'deep'):
            rows = [t for t in tr if t['path'] == path and t['depth'] == d and not t['screen']]
            if not rows: continue
            base = [t['base'] for t in rows]
            cur_p = np.mean([t['p'] for t in rows])
            # drops come off after the roll, so the roll must land higher
            gate = bd[d]['drop'] / max(bd[d]['comp'] + bd[d]['drop'], 1e-9)
            tgt = (REAL[d] + (MAN_OFF if path == 'man' else ZONE_OFF)) / 100 / (1 - gate)
            k = solve(base, tgt)
            cur_k = {'short': 1.494, 'medium': 1.171, 'deep': 0.802}[d] \
                if path == 'man' else M.ZONE_SCALE[d]
            (new_man if path == 'man' else new_zone)[d] = round(k, 3)
            print(f"  {path:5s} {d:7s} {len(rows):5d} {np.mean(base):10.3f} {cur_k:6.2f} "
                  f"{cur_p*100:6.1f} {tgt*100:7.1f} {k:6.3f}")
    scr = [t for t in tr if t['screen']]
    print(f"\n  screens: {len(scr)} traced, mean p before rescue {np.mean([t['p'] for t in scr])*100:.1f}"
          f"  (behind-the-line completion now {bd['behind']['comp']:.1f}, real {REAL_BEHIND})")
    acc = collections.defaultdict(list)
    for t in tr: acc[t['depth']].append(t['acc'])
    print('  mean QB accuracy by depth (AVG is 0.70): ' +
          ', '.join(f'{d} {np.mean(v):.3f}' for d, v in acc.items()))
    print('  mean pressure on attempts: %.3f' % np.mean([t['pressure'] for t in tr]))
    print(f"\n  DEPTH_MULT -> {new_man}\n  ZONE_SCALE -> {new_zone}")
