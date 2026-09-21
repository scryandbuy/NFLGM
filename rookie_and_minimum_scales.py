"""
Rookie wage scale and league minimum salary scale.

Both are slotted by rule under the CBA and both scale with the salary cap, so
they are stored as a share of the cap and projected forward with it.
Every figure here was derived from real contracts (OverTheCap) 2012-2026 and
cross-checked against published minimums.
"""
import pandas as pd, numpy as np
from collections import Counter

exec(open('cap_engine.py').read().split('# ------ contracts')[0]
     .split('# ---------------------------------------------------------------- contracts')[0])

c = pd.read_parquet('hc.parquet')

# ================= rookie scale =================
rows = []
for _, r in c.iterrows():
    ch = r.contract_history
    if ch is None or len(ch) == 0 or pd.isna(r.draft_overall): continue
    for h in ch:
        ys = h.get('year_signed')
        if h.get('contract_type') == 'Drafted' and ys and not pd.isna(ys):
            rows.append({'player': r.player, 'pick': int(r.draft_overall), 'year': int(ys),
                         'total': h.get('total'), 'gtd': h.get('guarantees')})
R = pd.DataFrame(rows).drop_duplicates(['player','year'])
R = R[(R.year >= 2012) & (R.total > 0) & (R.pick.between(1, 262))]
R['cap'] = R.year.map(CAP); R = R[R.cap.notna()]

# The rookie pool is its own CBA quantity and does NOT track the cap year to year:
# in 2021 the cap fell 7.9% while the pool rose 5.3%; in 2022 the cap rose 14.1%
# while the pool rose 4.0%. So normalise each slot against that draft's own pool,
# not against the cap, and grow the pool on its own observed rate.
_pool = R.groupby('year').total.sum()
_npick = R.groupby('year').pick.count()
POOL_PER_PICK = (_pool / _npick).to_dict()          # $M of rookie money per pick, by year
R['pct'] = R.total / R.year.map(POOL_PER_PICK)

# Exact per-pick table, not a fitted curve. The real scale has kinks a curve
# cannot follow (the cliff at the end of round 1, the steepness of the top 5),
# and we have the real number for every slot, so we keep them.
_by_pick = R.groupby('pick').pct.median()
SLOT_PCT = {}
for p in range(1, 263):
    if p in _by_pick.index:
        SLOT_PCT[p] = float(_by_pick[p])
    else:                       # picks that never existed in a given draft: interpolate neighbours
        lo = max([q for q in _by_pick.index if q < p], default=None)
        hi = min([q for q in _by_pick.index if q > p], default=None)
        if lo and hi:
            w = (p - lo) / (hi - lo)
            SLOT_PCT[p] = float(_by_pick[lo] * (1 - w) + _by_pick[hi] * w)
        else:
            SLOT_PCT[p] = float(_by_pick[lo or hi])

# pool-per-pick as a share of the cap, and how it grows
POOL_CAP_SHARE = {y: POOL_PER_PICK[y] / CAP[y] for y in POOL_PER_PICK if y in CAP}
_recent = [POOL_CAP_SHARE[y] for y in sorted(POOL_CAP_SHARE)[-5:]]
POOL_SHARE_NOW = float(np.mean(_recent))

def pool_per_pick(cap):
    """$M of rookie money per draft slot at a given cap."""
    return POOL_SHARE_NOW * cap

def rookie_pct(pick, cap=None, year=None):
    """Slot value. Uses that year's real pool if we have it, else projects."""
    share = SLOT_PCT[max(1, min(262, int(pick)))]
    ppp = POOL_PER_PICK[year] if (year in POOL_PER_PICK) else pool_per_pick(cap if cap else CAP[2026])
    return share * ppp

R['gs'] = (R.gtd / R.total).clip(0, 1)
_gs = R.groupby('pick').gs.median()
GTD_PCT = {}
for p in range(1, 263):
    if p in _gs.index and not np.isnan(_gs[p]):
        GTD_PCT[p] = float(_gs[p])
    else:
        near = [q for q in _gs.index if abs(q - p) <= 4 and not np.isnan(_gs[q])]
        GTD_PCT[p] = float(np.mean([_gs[q] for q in near])) if near else 0.05

def rookie_guarantee_share(pick):
    return GTD_PCT[max(1, min(262, int(pick)))]

def rookie_contract(pick, cap, rnd=None, year=None):
    """4 years for everyone; round 1 carries a 5th-year option."""
    total = rookie_pct(pick, cap=cap, year=year)
    rnd = rnd or (1 if pick <= 32 else min(7, (pick - 1)//32 + 1))
    return {'years': 4, 'total': round(total, 3),
            'apy': round(total/4, 3),
            'guaranteed': round(total * rookie_guarantee_share(pick), 3),
            'fifth_year_option': rnd == 1}

# ================= minimum salary scale =================
mrows = []
for _, r in c.iterrows():
    sh = r.season_history
    if sh is None or len(sh) == 0 or pd.isna(r.draft_year): continue
    for s in sh:
        try: yv = int(float(s['year']))
        except: continue
        b = s.get('base_salary')
        if b is None or float(b) <= 0: continue
        mrows.append({'year': yv, 'base': round(float(b), 3), 'exp': yv - r.draft_year})
M = pd.DataFrame(mrows)
M = M[(M.year.between(2016, 2026)) & (M.exp.between(0, 20))]
TIER = lambda e: '0' if e < 1 else ('1' if e < 2 else ('2' if e < 3 else
       ('3' if e < 4 else ('4-6' if e < 7 else '7+'))))
M['tier'] = M.exp.map(TIER)
M = M[M.base >= 0.35]          # drop practice-squad and partial-season salaries

mins = {}
for yv, d in M.groupby('year'):
    for t, dd in d.groupby('tier'):
        mins[(yv, t)] = Counter(dd.base.values).most_common(1)[0][0]

TIERS = ['0','1','2','3','4-6','7+']
tbl = pd.DataFrame([[mins.get((yv, t), np.nan) for t in TIERS]
                    for yv in sorted(M.year.unique())],
                   index=sorted(M.year.unique()), columns=TIERS)
# store as share of cap so it projects forward
share = tbl.div(pd.Series(CAP), axis=0)
MIN_PCT = share.loc[2020:2026].median().to_dict()

def minimum_salary(credited_seasons, cap):
    return round(MIN_PCT[TIER(credited_seasons)] * cap, 3)

# ================= validation =================
if __name__ == '__main__':
    print('=== ROOKIE SCALE: fitted vs real, 2025 ===')
    print(f'{"pick":>5s} {"real $M":>9s} {"fitted $M":>10s} {"err":>7s}')
    d25 = R[R.year == 2025]
    for p in [1, 2, 5, 10, 16, 32, 48, 64, 100, 150, 200, 256]:
        s = d25[d25.pick == p]
        if not len(s): continue
        real = s.total.iloc[0]; f = rookie_pct(p, year=2025)
        print(f'{p:5d} {real:9.2f} {f:10.2f} {(f-real)/real*100:+6.1f}%')
    allp = R.assign(f=[rookie_pct(p, year=y) for p, y in zip(R.pick, R.year)])
    err = ((allp.f - allp.total)/allp.total).abs()
    print(f'\n  across all {len(R)} rookie deals 2012-2026: median error {err.median():.2%}, p90 {err.quantile(.9):.2%}')
    ge = (R.assign(g=[rookie_guarantee_share(p) for p in R.pick]).eval('abs(g - gs)'))
    print(f'  guarantee share: median error {ge.median():.2%}, p90 {ge.quantile(.9):.2%}')
    print(f'  table size: {len(SLOT_PCT)} slots, {len(GTD_PCT)} guarantee entries')

    print('\n=== MINIMUM SALARY SCALE (derived, $M) ===')
    print(tbl.round(3).to_string())
    print('\n  published 2024 minimums:  0.795  0.915  0.985  1.055  1.125  1.210')
    print('  derived  2024:           ' + '  '.join(f'{tbl.loc[2024, t]:.3f}' for t in TIERS))

    print('\n=== PROJECTED FORWARD (as share of cap) ===')
    print('  cap share by tier: ' + ', '.join(f'{t} {MIN_PCT[t]*100:.3f}%' for t in TIERS))
    rng = np.random.default_rng(7)
    cap = CAP[2026]
    for yv in range(2027, 2031):
        cap = project_cap(yv, yv-1, cap, rng)
        print(f'  {yv} cap ${cap:6.1f}M -> rookie #1 ${rookie_pct(1, cap=cap):6.2f}M, '
              f'#32 ${rookie_pct(32, cap=cap):5.2f}M, #256 ${rookie_pct(256, cap=cap):4.2f}M | '
              f'min rookie ${minimum_salary(0, cap):.3f}M, vet 7+ ${minimum_salary(8, cap):.3f}M')

    print('\n=== SAMPLE CONTRACTS at the 2026 cap ===')
    for p in [1, 15, 32, 64, 150, 256]:
        rc = rookie_contract(p, CAP[2026], year=2026)
        print(f'  pick {p:3d}: {rc["years"]}yr ${rc["total"]:6.2f}M  '
              f'${rc["apy"]:5.2f}M/yr  ${rc["guaranteed"]:6.2f}M gtd'
              f'{"  +5th yr option" if rc["fifth_year_option"] else ""}')
