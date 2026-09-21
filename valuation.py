"""
Player valuation.

Same machinery as the rating engine, pointed the other way. There we asked
"what rating does a player on this contract usually have"; here we ask
"what contract does a player like this usually get".

No regression, no invented numbers: every valuation resolves to a weighted set
of real players on real contracts, plus adjustments fitted from those same
contracts. Output is a structure (years / annual value) with
a spread, because that spread is the range a negotiation argues inside.
"""
import pandas as pd, numpy as np
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n)

CAP_2026 = 301.0
S = pd.read_csv(_p('league_seed_2026.csv'), low_memory=False)
A = pd.read_csv(_p('advanced_stats_by_season.csv'), low_memory=False)

S['ovr'] = pd.to_numeric(S.overall, errors='coerce')
S['age'] = pd.to_numeric(S.age, errors='coerce')
S['apy'] = pd.to_numeric(S.apy, errors='coerce')
S['cappct'] = pd.to_numeric(S.apy_cap_pct, errors='coerce')
S['yrs'] = pd.to_numeric(S.years, errors='coerce')
# guaranteed money is cut from the game; the column is no longer read
S['signed'] = pd.to_numeric(S.year_signed, errors='coerce')
S['pick'] = pd.to_numeric(S.draft_overall, errors='coerce')

GRP = {'LT':'OT','RT':'OT','LG':'IOL','RG':'IOL','C':'IOL','LEDG':'EDGE','REDG':'EDGE',
       'DT':'DT','MIKE':'LB','WILL':'LB','SAM':'LB','FS':'S','SS':'S','CB':'CB','QB':'QB',
       'HB':'RB','FB':'RB','WR':'WR','TE':'TE','K':'K','P':'P','LS':'LS'}
S['grp'] = S.madden_position.map(GRP)

# ---------------------------------------------------------------- production
# One score per player, built only from metrics that exist for that position
# group, expressed as a percentile inside the group so units never matter.
PROD = {
  'QB':   [('ngs_pass_completion_percentage_above_expectation', 1), ('qbr_total', 1),
           ('qbr_epa_total', 1), ('pfr_pass_bad_throw_pct', -1), ('pfr_pass_on_tgt_pct', 1)],
  'WR':   [('ngs_rece_avg_separation', 1), ('ngs_rece_avg_yac_above_expectation', 1),
           ('receiving_yards', 1), ('pfr_rec_brk_tkl', 1), ('pfr_rec_drop_percent', -1)],
  'TE':   [('ngs_rece_avg_separation', 1), ('receiving_yards', 1), ('pfr_rec_brk_tkl', 1)],
  'RB':   [('ngs_rush_rush_yards_over_expected_per_att', 1), ('rushing_yards', 1),
           ('pfr_rush_brk_tkl', 1), ('pfr_rush_yac_att', 1)],
  'EDGE': [('pfr_def_prss', 1), ('pfr_def_sk', 1), ('pfr_def_qbkd', 1), ('pfr_def_hrry', 1)],
  'DT':   [('pfr_def_prss', 1), ('pfr_def_sk', 1), ('pfr_def_comb', 1)],
  'LB':   [('pfr_def_comb', 1), ('pfr_def_prss', 1), ('pfr_def_rat', -1)],
  'CB':   [('pfr_def_cmp_percent', -1), ('pfr_def_yds_tgt', -1), ('pfr_def_rat', -1),
           ('pfr_def_int', 1)],
  'S':    [('pfr_def_cmp_percent', -1), ('pfr_def_rat', -1), ('pfr_def_comb', 1)],
  'OT':   [('snap_off_pct', 1), ('snap_off_snaps', 1)],
  'IOL':  [('snap_off_pct', 1), ('snap_off_snaps', 1)],
}

def production_scores(seasons=(2024, 2025, 2026)):
    a = A[A.season.isin(seasons)].copy()
    agg = a.groupby('gsis_id').mean(numeric_only=True).reset_index()
    agg = agg.merge(S[['gsis_id','grp','madden_position']], on='gsis_id', how='inner')
    out = {}
    for grp, metrics in PROD.items():
        d = agg[agg.grp == grp]
        if len(d) < 12: continue
        parts = []
        for col, sign in metrics:
            if col not in d.columns or d[col].notna().sum() < 8: continue
            r = d[col].rank(pct=True)
            parts.append(r if sign > 0 else (1 - r))
        if not parts: continue
        sc = pd.concat(parts, axis=1).mean(axis=1)
        for gid, v in zip(d.gsis_id, sc):
            if not np.isnan(v): out[gid] = float(v)
    return out

PRODUCTION = production_scores()
S['prod_score'] = S.gsis_id.map(PRODUCTION)
print(f'production score computed for {S.prod_score.notna().sum():,} of {len(S):,} players')

# ---------------------------------------------------------------- comp engine
# Universe: every player in the league on a real contract. Value is expressed
# as a share of the cap so deals signed in different years are comparable.
UNI = S[(S.cappct > 0) & (S.ovr.notna()) & (S.age.notna()) & (S.grp.notna())].copy()
UNI = UNI[UNI.pick.notna() | (UNI.yrs >= 1)]

BW_OVR, BW_AGE, BW_PROD = 4.0, 2.0, 0.30
FACTORS = ['prod_f', 'contract_age', 'pedigree']

# COMPARABILITY IS FOUR THINGS: position, overall, age and production. Rating
# alone pays a great player on a bad team; production alone overpays a man in
# a good system. Both are in, and both are weights on the comp set rather than
# only corrections applied afterwards.

# How thin a comp set has to get before it is not a comp set at all. Puka
# Nacua at 98 overall and 25 years old drew six comps and a range of $10.6M to
# $44M, which is not a valuation, it is a shrug. An outlier has no peers his
# own age, so age is dropped for him and he is priced against everyone at his
# position near his rating - which is what an agent would do anyway.
THIN_COMPS = 20

# The comp WINDOW is the years of signings that count. The agent wants only
# the last two, when the market was hottest; the team wants five, which drags
# in cheaper deals. Neither gets his way: the window is rolled between them,
# and that roll is most of where the bargaining range comes from.
WINDOW_AGENT, WINDOW_TEAM = 2, 5
UNI['contract_age'] = (2026 - UNI.signed).clip(0, 10).fillna(0)
UNI['pedigree'] = np.where(UNI.pick.notna(), 1 - np.log(UNI.pick.fillna(260)+5)/np.log(265), 0.0)

UNI['prod_f'] = UNI['prod_score'].fillna(0.5)

def _weights(c, row, use_age=True, use_prod=True):
    w = np.exp(-0.5 * ((c.ovr - row['ovr']) / BW_OVR) ** 2)
    if use_age:
        w = w * np.exp(-0.5 * ((c.age - row['age']) / BW_AGE) ** 2)
    if use_prod and 'prod_f' in c:
        pr = float(row.get('prod_f', 0.5))
        w = w * np.exp(-0.5 * ((c.prod_f.fillna(0.5) - pr) / BW_PROD) ** 2)
    # rookie deals are slotted by rule, not negotiated: never use them as comps
    return w * np.where(c.pick.notna() & (c.contract_age < 4) & (c.yrs == 4)
                        & (c.age < 25), 0.15, 1.0)


def comp_set(row, pool, window=None):
    """
    Who this man gets priced against.

    Position first, then overall, age and production as smooth weights rather
    than hard bands - so a comp fades out instead of falling off a cliff.

    `window` is how many years back a signing still counts. Narrow flatters
    the player, wide flatters the club.
    """
    c = pool[pool.grp == row['grp']]
    if len(c) < 25:
        c = pool
    if window is not None and 'contract_age' in c:
        recent = c[c.contract_age <= window]
        if len(recent) >= 20:
            c = recent

    w = _weights(c, row)
    s = w.sum()
    if s < 1e-9:
        return None
    n_eff = float(s ** 2 / (w ** 2).sum())

    # AN OUTLIER HAS NO PEERS HIS OWN AGE. Widen rather than hand back a
    # meaningless range: drop age first, then production, and price him
    # against everyone at his position near his rating.
    # Drop AGE first, then production. The rating band is never loosened:
    # widening it pulled mediocre players into an elite man's comp set and
    # took Myles Garrett from $44.8M to $24M against a real $40M. An outlier
    # is priced against everyone at his position NEAR HIS RATING, whatever
    # their age - which is exactly what an agent would argue.
    for use_age, use_prod in ((False, True), (False, False)):
        if n_eff >= THIN_COMPS:
            break
        w2 = _weights(c, row, use_age=use_age, use_prod=use_prod)
        s2 = w2.sum()
        if s2 <= 1e-9:
            continue
        n2 = float(s2 ** 2 / (w2 ** 2).sum())
        if n2 > n_eff:
            w, n_eff = w2, n2
    return c, w / w.sum()

def raw_value(row, pool, window=None):
    r = comp_set(row, pool, window)
    if r is None: return None
    c, w = r
    centre = {k: float((w * c[k].fillna(c[k].median())).sum())
              for k in ['cappct', 'yrs']}
    var = float((w * (c.cappct - centre['cappct'])**2).sum())
    n_eff = float(1.0/ (w**2).sum())
    deltas = {f: float(row[f] -
                       (w * c[f]).sum()) for f in FACTORS}
    return centre, np.sqrt(max(var, 0)), deltas, n_eff

# fit the adjustment coefficients on the league itself
rows = []
for i, row in UNI.iterrows():
    r = raw_value(row, UNI.drop(i))
    if r: rows.append((i, r[0]['cappct'], r[1], r[3], *[r[2][f] for f in FACTORS]))
F = pd.DataFrame(rows, columns=['idx','centre','spread','n_eff']+FACTORS).set_index('idx')
F['truth'] = UNI.cappct
M = np.column_stack([F[f] for f in FACTORS] + [np.ones(len(F))])
coef, *_ = np.linalg.lstsq(M, (F.truth - F.centre).values, rcond=None)
COEF = dict(zip(FACTORS + ['const'], coef))

def value(row, cap=CAP_2026, pool=UNI, window=None, rng=None):
    """
    What a deal for this man is worth.

    The comp window is ROLLED between what each side wants - the agent argues
    two years of signings, the club argues five - so the same player does not
    price identically every time he is valued. Pass `window` to pin it.
    """
    if window is None:
        r_ = rng or np.random
        window = int(round(r_.uniform(WINDOW_AGENT, WINDOW_TEAM)))
    r = raw_value(row, pool, window)
    if r is None: return None
    centre, spread, deltas, n_eff = r
    adj = sum(COEF[f]*deltas[f] for f in FACTORS) + COEF['const']
    pct = max(0.0015, centre['cappct'] + adj)
    return {
        'apy':        round(pct * cap, 2),
        'apy_low':    round(max(0.0015, pct - spread) * cap, 2),
        'apy_high':   round((pct + spread) * cap, 2),
        'years':      int(round(np.clip(centre['yrs'], 1, 6))),
        'cap_pct':    round(pct*100, 3),
        'n_comps':    round(n_eff, 1),
        'window':     window,
    }

# ---------------------------------------------------------------- validation
if __name__ == '__main__':
    print('\n=== fitted adjustments (cap % per unit vs comps) ===')
    for f in FACTORS + ['const']:
        print(f'  {f:14s} {COEF[f]*100:+7.4f} cap-% ')

    pred = F.centre + M @ coef
    truth = F.truth.values
    err = np.abs(pred - truth) * CAP_2026
    print(f'\n=== VALIDATION: predicting each player\'s real contract ===')
    print(f'  median error ${np.median(err):.2f}M   p75 ${np.percentile(err,75):.2f}M   p90 ${np.percentile(err,90):.2f}M')
    big = UNI.cappct > 0.02
    print(f'  on players earning >2% of cap (n={big.sum()}): median ${np.median(err[big.values]):.2f}M')
    print(f'  comp-set spread: median ${F.spread.median()*CAP_2026:.2f}M, n_eff median {F.n_eff.median():.0f}')

    print('\n=== SAMPLE VALUATIONS ===')
    for name in ['Ja\'Marr Chase','Pat Surtain II','Puka Nacua','Myles Garrett',
                 'Cameron Heyward','Najee Harris','Brandon Aubrey']:
        r = S[S.full_name == name]
        if not len(r): continue
        row = UNI[UNI.full_name == name]
        if not len(row): continue
        row = row.iloc[0]
        v = value(row)
        prod = f'{row.prod_f:.2f}' if not np.isnan(row.prod_score) else ' n/a'
        print(f'  {name:18s} {row.madden_position:4s} ovr {row.ovr:.0f} age {row.age:.0f} prod {prod}')
        print(f'     valued  ${v["apy"]:6.2f}M/yr over {v["years"]}yr'
              f'   range ${v["apy_low"]:.1f}-{v["apy_high"]:.1f}M  ({v["n_comps"]:.0f} comps)')
        print(f'     actual  ${row.apy:6.2f}M/yr over {int(row.yrs) if not np.isnan(row.yrs) else 0}yr')

    print('\n=== SURPLUS VALUE: biggest bargains and worst deals ===')
    UNI2 = UNI.copy()
    vals = [value(r) for _, r in UNI2.iterrows()]
    UNI2['val_apy'] = [v['apy'] if v else np.nan for v in vals]
    UNI2['surplus'] = UNI2.val_apy - UNI2.apy
    show = ['full_name','team','madden_position','ovr','age','apy','val_apy','surplus']
    print('\n  best value contracts:')
    print(UNI2.nlargest(8,'surplus')[show].round(2).to_string(index=False))
    print('\n  worst value contracts:')
    print(UNI2.nsmallest(8,'surplus')[show].round(2).to_string(index=False))

    print('\n=== POSITIONAL MARKET, straight from comps ===')
    top = UNI2.groupby('grp').apply(lambda d: d.nlargest(max(1,len(d)//12),'val_apy').val_apy.mean(),
                                    include_groups=False).sort_values(ascending=False)
    print('  top-of-market annual value by position group:')
    for g, v in top.items(): print(f'    {g:5s} ${v:6.2f}M')
    UNI2.to_csv(_p('player_valuations_2026.csv'), index=False)


# ============================================================ THE LIVE LEAGUE
# Everything above derives the DAY-ONE market from real 2026 contracts. From
# the first offseason on, the comp pool is the league's OWN signings - so
# prices drift with this league rather than with the real one.
#
# It cannot spiral, and the reason is structural rather than a cap I imposed:
# comps are stored as a SHARE OF THE CAP, and the sum of those shares is
# bounded by the cap itself. If prices rise, clubs cannot afford them, fewer
# big deals get signed, and the comp set pulls itself back down. The cap
# growing about 7.5% a year gives the whole market room to move without any
# single deal having to.

# Blocking is what a lineman does, and until the win rates existed his
# production score was snap counts - which says he played, not that he played
# well. PBWR, RBWR and the sacks he gave up are now the measure.
OL_POS = ('LT', 'LG', 'C', 'RG', 'RT')


def live_production(league, player, season=None):
    """
    Production on 0-1 for a man in THIS league, as a percentile inside his own
    position group. Returns None when he has no meaningful playing time, which
    is the honest answer rather than a made-up 0.5.
    """
    year = season or league.year
    book = league.stats.get(year, {})
    line = book.get(player.pid)
    if not line:
        return None

    def score(pid):
        s = book.get(pid) or {}
        if player.pos in OL_POS:
            pb = float(s.get('pb_snaps', 0) or 0)
            if pb < 150:
                return None
            pbwr = float(s.get('pb_wins', 0) or 0) / pb
            rb = float(s.get('rb_snaps', 0) or 0)
            rbwr = (float(s.get('rb_wins', 0) or 0) / rb) if rb else 0.0
            given = (3.0 * float(s.get('sacks_allowed', 0) or 0)
                     + float(s.get('pressures_allowed', 0) or 0)) / pb
            return 100.0 * pbwr + 45.0 * rbwr - 260.0 * given
        snaps = float(s.get('snaps', 0) or 0)
        if snaps < 120:
            return None
        return (float(s.get('pass_yds', 0) or 0) * 0.25
                + float(s.get('pass_td', 0) or 0) * 14
                - float(s.get('ints', 0) or 0) * 10
                + float(s.get('rush_yds', 0) or 0) * 0.5
                + float(s.get('rec_yds', 0) or 0) * 0.5
                + (float(s.get('rush_td', 0) or 0)
                   + float(s.get('rec_td', 0) or 0)) * 14
                + float(s.get('sacks', 0) or 0) * 12
                + float(s.get('int_def', 0) or 0) * 16
                + float(s.get('tackles', 0) or 0) * 1.2)

    mine = score(player.pid)
    if mine is None:
        return None
    peers = []
    for p in league.players.values():
        if p.retired or p.pos != player.pos:
            continue
        v = score(p.pid)
        if v is not None:
            peers.append(v)
    if len(peers) < 5:
        return 0.5
    return float(np.clip(np.mean([mine > v for v in peers]), 0.0, 1.0))


def pool_from_league(league, season=None):
    """
    The comp pool, built from THIS league's signed contracts. Everyone under
    contract counts; the market is whatever this league has actually paid.
    """
    cap = 301.2
    try:
        from cap_engine import CAP as _C
        cap = _C.get(season or league.year, cap)
    except Exception:
        pass
    rows = []
    for p in league.players.values():
        if p.retired or not p.contract or not p.team:
            continue
        apy = p.apy
        if apy <= 0:
            continue
        prod = live_production(league, p, season)
        rows.append(dict(
            full_name=p.name, grp=GRP.get(p.pos, 'LB'), madden_position=p.pos,
            ovr=p.ovr, age=p.age, apy=apy, cappct=apy / cap,
            yrs=p.contract.years,
            contract_age=max(0, (season or league.year) - p.contract.signed),
            pick=p.draft_overall,
            pedigree=(0.0 if not p.draft_overall
                      else 1 - np.log(p.draft_overall + 5) / np.log(265)),
            prod_f=(0.5 if prod is None else prod)))
    return pd.DataFrame(rows)


def value_player(league, player, side=None, rng=None, pool=None, season=None):
    """
    Value a live Player. `side` pins the comp window: 'agent' argues two years
    of signings, 'team' argues five, and None rolls between them.
    """
    cap = 301.2
    try:
        from cap_engine import CAP as _C
        cap = _C.get(season or league.year, cap)
    except Exception:
        pass
    pool = pool if pool is not None else pool_from_league(league, season)
    if not len(pool):
        return None
    prod = live_production(league, player, season)
    row = dict(grp=GRP.get(player.pos, 'LB'), ovr=player.ovr, age=player.age,
               contract_age=0.0, prod_f=(0.5 if prod is None else prod),
               pedigree=(0.0 if not player.draft_overall
                         else 1 - np.log(player.draft_overall + 5) / np.log(265)))
    window = {'agent': WINDOW_AGENT, 'team': WINDOW_TEAM}.get(side)
    return value(row, cap=cap, pool=pool, window=window, rng=rng)
