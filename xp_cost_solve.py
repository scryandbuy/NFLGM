"""Solve the cost constants against the §5 guardrail table.

Takes real players by position and age from the league, hands each the
ledger's big-year XP for his position, spends it the best way (most overall
per XP, which now weighs an attribute's price against its weight), and
reports the overall gain against the table."""
import numpy as np, sys, itertools, copy
import league as LG, xp as XP, targets as TG

TABLE = {'WR': [4.9, 4.3, 2.6, 1.8, 0.7], 'QB': [5.2, 4.3, 3.2, 2.5, 2.0],
         'HB': [4.2, 3.7, 2.3, 1.4, 1.1], 'EDGE': [3.8, 3.3, 1.8, 1.2, 1.0]}
AGES = [22, 25, 28, 31, 34]
BIG_YEAR = {'WR': 28000, 'QB': 39000, 'HB': 32000, 'EDGE': 28000}
POS = {'WR': ['WR'], 'QB': ['QB'], 'HB': ['HB'], 'EDGE': ['LEDG', 'REDG']}

def best_spend(p, budget):
    """Most overall per XP: pick the attribute with the highest weight/cost."""
    w = TG.DEPTH_WEIGHTS[p.pos]; tot = sum(w.values())
    q = copy.copy(p); q.ratings = dict(p.ratings); q.xp_spent = dict(p.xp_spent); q.xp = budget
    ovr0 = q.ovr
    while True:
        best, val = None, 0.0
        for k, wt in w.items():
            if q.ratings.get(k, 70) >= 99: continue
            v = (wt / tot) / XP.cost_per_point(q, k)
            if v > val: best, val = k, v
        if best is None or XP.buy(q, best) is None: break
    return q.ovr - ovr0

def evaluate(L, verbose=False):
    err = []; rows = {}
    for grp, poss in POS.items():
        row = []
        for age, target in zip(AGES, TABLE[grp]):
            # real men of about that age at that spot, top half by overall so
            # they are the starters a big year happens to
            cands = sorted([p for p in L.players.values() if p.pos in poss and abs(p.age - age) <= 1.5],
                           key=lambda p: -p.ovr)
            cands = cands[:max(3, len(cands) // 2)]
            if not cands: row.append(None); continue
            for c in cands: c.age = float(age)          # pin the age for the test
            g = np.mean([best_spend(c, BIG_YEAR[grp]) for c in cands])
            row.append(g); err.append(g - target)
        rows[grp] = row
    if verbose:
        print(f'  {"":5s}' + ''.join(f'{a:>12d}' for a in AGES))
        for grp, row in rows.items():
            print(f'  {grp:5s}' + ''.join(f'{(g if g is not None else float("nan")):6.1f}/{t:4.1f} ' for g, t in zip(row, TABLE[grp])))
    return float(np.sqrt(np.mean(np.square(err)))), rows

if __name__ == '__main__':
    rng = np.random.default_rng(1)
    L = LG.build_league(rng=rng)
    if len(sys.argv) > 1 and sys.argv[1] == 'grid':
        best = None
        for base, esc, slope in itertools.product((500, 600, 700, 800, 900), (1.02, 1.03, 1.04, 1.05, 1.06), (0.05, 0.07, 0.09, 0.12, 0.15)):
            XP.BASE_COST, XP.ESCALATOR, XP.AGE_SLOPE = base, esc, slope
            e, _ = evaluate(copy.deepcopy(L))
            if best is None or e < best[0]: best = (e, base, esc, slope)
        print('best rmse %.2f at base %d escalator %.3f age slope %.2f' % best)
        XP.BASE_COST, XP.ESCALATOR, XP.AGE_SLOPE = best[1:]
    print(f'BASE {XP.BASE_COST} ESCALATOR {XP.ESCALATOR} AGE_SLOPE {XP.AGE_SLOPE} PHYSICAL x{XP.PHYSICAL_MULT}   (gain / table)')
    e, _ = evaluate(copy.deepcopy(L), verbose=True)
    print(f'  rmse {e:.2f}')


def best_spend_inplace(p):
    """The same greedy spend, on the real player. Returns the overall gain."""
    w = TG.DEPTH_WEIGHTS.get(p.pos)
    if not w: return 0.0
    tot = sum(w.values()); ovr0 = p.ovr
    while True:
        best, val = None, 0.0
        for k, wt in w.items():
            if p.ratings.get(k, 70) >= 99: continue
            v = (wt / tot) / XP.cost_per_point(p, k)
            if v > val: best, val = k, v
        if best is None or XP.buy(p, best) is None: break
    return p.ovr - ovr0
