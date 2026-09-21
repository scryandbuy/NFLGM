"""
Progression and regression.

Cross-sectional age averages are biased by survivorship: the only 34-year-olds
still playing are the good ones, so the curve looks flat when it is not. So we
use the delta method instead: compare the SAME player at age t to himself at
t+1, which controls for quality entirely. This is how aging curves are done
properly in baseball research and it is the right tool here.
"""
import pandas as pd, numpy as np
import os

# Derivation script. The body reads source data that is not part of the
# runtime, so it runs ONLY by hand - importing this module used to fail
# outright, which is how several engines ended up uncallable.
if __name__ == '__main__':
    _D = os.path.dirname(os.path.abspath(__file__))
    def _p(n): return os.path.join(_D, n)

    A = pd.read_csv(_p('advanced_stats_by_season.csv'), low_memory=False)
    P = pd.read_csv('players.csv', low_memory=False)

    bd = P.dropna(subset=['gsis_id']).drop_duplicates('gsis_id').set_index('gsis_id')
    A['dob'] = A.gsis_id.map(bd.birth_date)
    A['pos_grp'] = A.gsis_id.map(bd.position_group)
    A['age'] = ((pd.to_datetime(A.season.astype(str) + '-09-01') -
                 pd.to_datetime(A.dob, errors='coerce')).dt.days / 365.25)
    A = A[A.age.between(20, 42)].copy()
    print(f'player-seasons with a valid age: {len(A):,}  players: {A.gsis_id.nunique():,}')

    GRP = {'QB':'QB','RB':'RB','FB':'RB','WR':'WR','TE':'TE','OL':'OL','DL':'DL',
           'LB':'LB','DB':'DB','SPEC':'SPEC'}
    A['grp'] = A.pos_grp.map(GRP)

    # ---- one production number per player-season, ranked inside position and year ----
    METRICS = {
     'QB': ['qbr_total','ngs_pass_completion_percentage_above_expectation','passing_yards','passing_epa'],
     'RB': ['ngs_rush_rush_yards_over_expected_per_att','rushing_yards','pfr_rush_brk_tkl','rushing_epa'],
     'WR': ['ngs_rece_avg_separation','receiving_yards','ngs_rece_avg_yac_above_expectation','receiving_epa'],
     'TE': ['receiving_yards','ngs_rece_avg_separation','pfr_rec_brk_tkl'],
     'OL': ['snap_off_pct','snap_off_snaps'],
     'DL': ['pfr_def_prss','pfr_def_sk','pfr_def_comb','snap_def_pct'],
     'LB': ['pfr_def_comb','pfr_def_prss','snap_def_pct'],
     'DB': ['pfr_def_comb','snap_def_pct','pfr_def_int'],
    }
    rows = []
    for (grp, season), d in A.groupby(['grp','season']):
        cols = [c for c in METRICS.get(grp, []) if c in d.columns and d[c].notna().sum() >= 8]
        if not cols: continue
        sc = pd.concat([d[c].rank(pct=True) for c in cols], axis=1).mean(axis=1)
        for gid, age, v, snaps in zip(d.gsis_id, d.age, sc,
                                      d.get('snap_off_snaps', pd.Series(index=d.index)).fillna(0) +
                                      d.get('snap_def_snaps', pd.Series(index=d.index)).fillna(0)):
            if not np.isnan(v): rows.append((gid, grp, season, age, float(v), float(snaps)))
    S = pd.DataFrame(rows, columns=['gsis_id','grp','season','age','pscore','snaps'])
    print(f'scored player-seasons: {len(S):,}')

    # ---- delta method: the same man, this year vs next ----
    S = S.sort_values(['gsis_id','season'])
    S['next_prod'] = S.groupby('gsis_id')['pscore'].shift(-1)
    S['next_season'] = S.groupby('gsis_id')['season'].shift(-1)
    D = S[(S.next_season == S.season + 1) & S.next_prod.notna()].copy()
    D['delta'] = D.next_prod - D.pscore
    D['age_bin'] = D.age.round().astype(int)
    print(f'consecutive-season pairs: {len(D):,}')

    print('\n=== AGING CURVE: change in production percentile, same player year over year ===')
    print(f'  {"age":>4s} {"n":>5s} {"delta":>8s}   curve')
    overall = D.groupby('age_bin').agg(n=('delta','size'), d=('delta','mean'))
    overall = overall[overall.n >= 30]
    for a, r in overall.iterrows():
        bar = '+' * int(max(0, r.d)*200) or ('-' * int(max(0, -r.d)*200))
        print(f'  {a:4d} {int(r.n):5d} {r.d:+8.4f}   {bar}')

    print('\n=== PEAK AND DECLINE BY POSITION ===')
    print(f'  {"pos":5s} {"peak age":>9s} {"decline starts":>15s} {"annual decline after 30":>25s}')
    CURVES = {}
    for grp, d in D.groupby('grp'):
        g = d.groupby('age_bin').agg(n=('delta','size'), dl=('delta','mean'))
        g = g[g.n >= 15]
        if len(g) < 5: continue
        cum = g.dl.cumsum()
        peak = int(cum.idxmax())
        neg = [a for a in g.index if a > 23 and g.dl[a] < 0]
        onset = min(neg) if neg else None
        late = g[g.index >= 30].dl.mean() if (g.index >= 30).any() else np.nan
        CURVES[grp] = dict(peak=peak, onset=onset, late=float(late) if late == late else None,
                           by_age={int(a): float(v) for a, v in g.dl.items()})
        print(f'  {grp:5s} {peak:9d} {str(onset):>15s} {late:+25.4f}')

    # ---- how much of a year-over-year change is real vs noise? ----
    print('\n=== HOW STICKY IS PRODUCTION? (does a career year repeat?) ===')
    S['prev_prod'] = S.groupby('gsis_id')['pscore'].shift(1)
    S['prev_season'] = S.groupby('gsis_id')['season'].shift(1)
    E = S[(S.prev_season == S.season - 1) & S.prev_prod.notna()]
    for grp, d in E.groupby('grp'):
        if len(d) < 80: continue
        r = np.corrcoef(d.prev_prod, d.pscore)[0,1]
        print(f'  {grp:5s} year-to-year correlation {r:+.3f}   n={len(d):,}')

    import json
    json.dump(CURVES, open('aging_curves.json','w'), indent=1)
    print('\nsaved aging_curves.json')
