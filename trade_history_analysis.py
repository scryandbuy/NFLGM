import pandas as pd, numpy as np
from collections import Counter, defaultdict


# Derivation script. The body reads source data that is not part of the
# runtime, so it runs ONLY by hand - importing this module used to fail
# outright, which is how several engines ended up uncallable.
if __name__ == '__main__':
    T = pd.read_csv('rt_trades.csv', low_memory=False)
    ST = pd.read_csv('standings.csv', low_memory=False)
    T['trade_date'] = pd.to_datetime(T.trade_date, errors='coerce')
    T = T[T.season.between(2016, 2026)].copy()
    T['is_pick'] = T.pick_round.notna()
    T['is_player'] = T.pfr_id.notna()

    print(f'trades 2016-2026: {T.trade_id.nunique():,} deals, {len(T):,} assets moved')

    # ---------------- composition ----------------
    comp = []
    for tid, d in T.groupby('trade_id'):
        teams = sorted(set(d.gave) | set(d.received))
        comp.append(dict(trade_id=tid, season=d.season.iloc[0], date=d.trade_date.iloc[0],
                         n_teams=len(teams), picks=int(d.is_pick.sum()),
                         players=int(d.is_player.sum() & ~d.is_pick).sum() if False else int((d.is_player & ~d.is_pick).sum()),
                         cond=int((d.conditional == 1).sum())))
    C = pd.DataFrame(comp)
    def kind(r):
        if r.players == 0: return 'picks only'
        if r.picks == 0:   return 'players only'
        return 'players + picks'
    C['kind'] = C.apply(kind, axis=1)
    print('\n=== WHAT A TRADE LOOKS LIKE ===')
    for k, v in C.kind.value_counts().items(): print(f'  {k:18s} {v:4d}  ({v/len(C):.0%})')
    print(f'  three-team deals   {(C.n_teams >= 3).sum():4d}  ({(C.n_teams>=3).mean():.0%})')
    print(f'  contain conditions {(C.cond > 0).sum():4d}  ({(C.cond>0).mean():.0%})')
    print(f'\n  deals per season: {C.groupby("season").size().to_dict()}')

    # ---------------- timing ----------------
    C['month'] = C.date.dt.month
    print('\n=== WHEN TRADES HAPPEN ===')
    mo = C.month.value_counts().sort_index()
    names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
    for m, n in mo.items():
        bar = '#' * int(n/max(mo)*40)
        print(f'  {names.get(m,"?"):4s} {n:4d} {bar}')

    # ---------------- revealed pick prices ----------------
    # Pure pick-for-pick trades let us solve for what the market actually pays.
    PP = []
    for tid, d in T.groupby('trade_id'):
        if (d.is_player & ~d.is_pick).any(): continue
        if d.pick_number.isna().any(): continue
        if len(set(d.gave) | set(d.received)) != 2: continue
        sides = defaultdict(list)
        for _, r in d.iterrows(): sides[r.received].append(int(r.pick_number))
        if len(sides) != 2: continue
        (a, pa), (b, pb) = sides.items()
        PP.append((pa, pb))
    print(f'\n=== REVEALED PRICES from {len(PP)} pure pick-for-pick trades ===')

    # fit v(pick) so that the two sides of each trade balance, anchored at v(1)=1
    from scipy.optimize import least_squares
    GRID = np.array([1,4,8,12,16,24,32,40,48,64,80,96,112,128,160,192,224,262], float)
    def curve(theta, picks):
        return np.interp(picks, GRID, np.concatenate([[1.0], np.exp(theta)]))
    def resid(theta):
        out = []
        for pa, pb in PP:
            va = curve(theta, np.array(pa, float)).sum()
            vb = curve(theta, np.array(pb, float)).sum()
            out.append(np.log(max(va,1e-6)) - np.log(max(vb,1e-6)))
        return np.array(out)
    theta0 = np.log(np.linspace(0.85, 0.02, len(GRID)-1))
    sol = least_squares(resid, theta0, max_nfev=4000)
    raw = np.array([float(curve(sol.x, np.array([p], float))[0]) for p in range(1, 263)])
    # The free fit came back non-monotonic at the very top (pick 4 below pick 8),
    # where there are few observations. Pick value must decrease with pick number,
    # so enforce it rather than ship a curve that says pick 8 beats pick 4.
    from sklearn.isotonic import IsotonicRegression
    raw = IsotonicRegression(increasing=False, out_of_bounds='clip').fit_transform(
            np.arange(1, 263, dtype=float), raw)
    MARKET = {int(p): float(v) for p, v in zip(range(1, 263), raw)}
    print(f'  fit residual (log-space RMS): {np.sqrt(np.mean(sol.fun**2)):.3f}')
    print(f'  observations by pick band: '
          + ', '.join(f'{lo}-{hi}: {sum(1 for pa,pb in PP for q in pa+pb if lo<=q<=hi)}'
                      for lo,hi in [(1,16),(17,48),(49,100),(101,262)]))

    import trades as TR
    JJ = {1:3000,4:1800,8:1400,16:1000,32:590,48:420,64:270,96:116,128:45,160:27,200:13.6,256:2}
    print(f'\n  {"pick":>5s} {"MARKET (real trades)":>21s} {"OURS (outcomes)":>17s} {"JJ chart":>10s}')
    for p in [1,4,8,16,32,48,64,96,128,160,200,256]:
        jj = f'{JJ[p]/3000*100:9.1f}%' if p in JJ else ' '*10
        print(f'  {p:5d} {MARKET[p]*100:20.1f}% {TR.PICK_VALUE[p]*100:16.1f}% {jj}')

    # ---------------- where future picks land ----------------
    T['fut'] = T.pick_season - T.season
    fut = T[(T.is_pick) & (T.fut >= 1) & T.pick_number.notna()]
    print(f'\n=== FUTURE PICKS: where they actually landed ({len(fut)} traded) ===')
    for rd, d in fut.groupby('pick_round'):
        if rd > 4: continue
        lo, med, hi = d.pick_number.quantile([.1,.5,.9])
        print(f'  round {int(rd)}: landed between {lo:.0f} and {hi:.0f}, median {med:.0f}  (n={len(d)})')

    # ---------------- buyers and sellers ----------------
    rec = ST[ST.season.between(2016,2026)].set_index(['season','team'])
    def winpct(season, team):
        try:
            r = rec.loc[(season, team)]
            return (r.wins + 0.5*r.ties) / (r.wins + r.losses + r.ties)
        except Exception: return np.nan

    dl = T[(T.trade_date.dt.month.isin([10,11])) & T.trade_date.notna()]
    print(f'\n=== DEADLINE TRADES: are sellers bad and buyers good? ===')
    rows = []
    for tid, d in dl.groupby('trade_id'):
        pl = d[d.is_player & ~d.is_pick]
        pk = d[d.is_pick]
        if not len(pl) or not len(pk): continue
        seller = pl.gave.iloc[0]; buyer = pl.received.iloc[0]
        s, b = winpct(d.season.iloc[0], seller), winpct(d.season.iloc[0], buyer)
        if np.isnan(s) or np.isnan(b): continue
        rows.append((seller, s, buyer, b))
    R = pd.DataFrame(rows, columns=['seller','s_wpct','buyer','b_wpct'])
    print(f'  n={len(R)} player-for-pick deadline deals')
    print(f'  team GIVING UP the player: mean win pct {R.s_wpct.mean():.3f}')
    print(f'  team ACQUIRING the player: mean win pct {R.b_wpct.mean():.3f}')
    print(f'  buyer had the better record in {(R.b_wpct > R.s_wpct).mean():.0%} of deals')

    np.save('market_pick_values.npy', np.array([MARKET[p] for p in range(1,263)]))
    print('\nsaved market_pick_values.npy')
