"""
Player valuation.

Same machinery as the rating engine, pointed the other way. There we asked
"what rating does a player on this contract usually have"; here we ask
"what contract does a player like this usually get".

No regression, no invented numbers: every valuation resolves to a weighted set
of real players on real contracts, plus adjustments fitted from those same
contracts. Output is a structure (years / annual value / guarantee share) with
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
S['gpct'] = (pd.to_numeric(S.guaranteed, errors='coerce') /
             pd.to_numeric(S.value, errors='coerce').replace(0, np.nan)).clip(0, 1)
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

BW_OVR, BW_AGE = 4.0, 2.0
FACTORS = ['prod_f', 'contract_age', 'pedigree']
UNI['contract_age'] = (2026 - UNI.signed).clip(0, 10).fillna(0)
UNI['pedigree'] = np.where(UNI.pick.notna(), 1 - np.log(UNI.pick.fillna(260)+5)/np.log(265), 0.0)

UNI['prod_f'] = UNI['prod_score'].fillna(0.5)

def comp_set(row, pool):
    c = pool[pool.grp == row['grp']]
    if len(c) < 25: c = pool
    w = np.exp(-0.5*((c.ovr - row['ovr'])/BW_OVR)**2) * np.exp(-0.5*((c.age - row['age'])/BW_AGE)**2)
    # rookie deals are slotted by rule, not negotiated: never use them as comps
    w = w * np.where(c.pick.notna() & (c.contract_age < 4) & (c.yrs == 4) & (c.age < 25), 0.15, 1.0)
    s = w.sum()
    if s < 1e-9: return None
    w = w / s
    return c, w

def raw_value(row, pool):
    r = comp_set(row, pool)
    if r is None: return None
    c, w = r
    centre = {k: float((w * c[k].fillna(c[k].median())).sum())
              for k in ['cappct', 'yrs', 'gpct']}
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

def value(row, cap=CAP_2026, pool=UNI):
    r = raw_value(row, pool)
    if r is None: return None
    centre, spread, deltas, n_eff = r
    adj = sum(COEF[f]*deltas[f] for f in FACTORS) + COEF['const']
    pct = max(0.0015, centre['cappct'] + adj)
    return {
        'apy':        round(pct * cap, 2),
        'apy_low':    round(max(0.0015, pct - spread) * cap, 2),
        'apy_high':   round((pct + spread) * cap, 2),
        'years':      int(round(np.clip(centre['yrs'], 1, 6))),
        'gtd_share':  round(float(np.clip(centre['gpct'], 0, 1)), 2),
        'cap_pct':    round(pct*100, 3),
        'n_comps':    round(n_eff, 1),
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
        print(f'     valued  ${v["apy"]:6.2f}M/yr over {v["years"]}yr, {v["gtd_share"]*100:.0f}% gtd'
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
