"""
RE-SOLVE THE PROTECTION CLOCK INSIDE GAMES.

RUSHER_BASE was solved for a bare four-man rush on the bench so that the
minimum of four arrivals landed on 2.72s. Inside games the blitz multiplier,
the simulated-pressure protection error and the hot route all shorten it,
and nothing measured the blend: attempts were leaving the hand at 2.55s.

The clock is a physical quantity and the sack curve is a function of it, so
both constants are solved together: RUSHER_BASE so time to throw ON ATTEMPTS
lands on 2.72, the sack constant so the sack share of dropbacks lands on 6.6.
Nothing here touches what the quarterback decides to do with the time.

Every arrival scales with RUSHER_BASE except a free runner (fixed 0.6s) and
the 0.35s floor, so a scale factor on the traced times is a close stand-in
for changing the constant, and the result is then verified by re-running.
"""
import numpy as np, sys
import plays as P

REAL_TTT, REAL_SACK = 2.72, 6.60
# The trace sees every dropback BEFORE a mobile quarterback turns a collapsed
# pocket into a scramble (game.py), and the register counts sacks after it.
# In-game sacks ran 7.11% of attempts+sacks while the trace's own roll gave
# 8.45%, so the register target is lifted by that ratio for the solve here,
# and the result is confirmed by the register itself.
TRACE_SACK_RATIO = 8.45 / 7.11
SACK_K, SACK_DECAY, HOT_SURVIVE = 16.0, 2.40, 0.35


def trace(weeks=6, seed=2026):
    import passing_diag as D
    P.PASS_TRACE = []
    D.run(weeks=weeks, seed=seed, verbose=False)
    tr = [t for t in P.PASS_TRACE if t.get('path') == 'clock']; P.PASS_TRACE = None
    return tr


def evaluate(tr, f, K, rng):
    """Time to throw on attempts and sack share, under a scale f and sack constant K."""
    t = np.array([x['time'] for x in tr]) * f
    hot = np.array([x['hot'] for x in tr])
    p = np.clip(K * np.exp(-SACK_DECAY * t), 0, .85)
    p = np.where(hot, p * HOT_SURVIVE, p)
    sacked = rng.random(len(t)) < p
    return t[~sacked].mean(), sacked.mean() * 100


if __name__ == '__main__':
    weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    tr = trace(weeks)
    rng = np.random.default_rng(0)
    cur = evaluate(tr, 1.0, SACK_K, rng)
    print(f'{len(tr)} dropbacks traced. current: ttt {cur[0]:.3f}  sack {cur[1]:.2f}%')
    print(f'  raw clock mean {np.mean([x["time"] for x in tr]):.3f}, hot routes '
          f'{np.mean([x["hot"] for x in tr])*100:.1f}% of dropbacks')
    # alternate the two one-dimensional solves; they converge in a few passes
    f, K = 1.0, SACK_K
    for _ in range(6):
        lo, hi = 0.8, 1.4
        for _i in range(40):
            mid = (lo + hi) / 2
            if evaluate(tr, mid, K, np.random.default_rng(1))[0] > REAL_TTT: hi = mid
            else: lo = mid
        f = (lo + hi) / 2
        lo, hi = 4.0, 60.0
        for _i in range(40):
            mid = (lo + hi) / 2
            if evaluate(tr, f, mid, np.random.default_rng(1))[1] > REAL_SACK * TRACE_SACK_RATIO: hi = mid
            else: lo = mid
        K = (lo + hi) / 2
    got = evaluate(tr, f, K, np.random.default_rng(2))
    print(f'\n  scale {f:.4f}  ->  RUSHER_BASE {P.RUSHER_BASE:.2f} -> {P.RUSHER_BASE*f:.3f}')
    print(f'  sack constant {SACK_K} -> {K:.2f}')
    print(f'  predicted: ttt {got[0]:.3f} (2.72)  sack {got[1]:.2f}% before scrambles ({REAL_SACK*TRACE_SACK_RATIO:.2f})')
