"""
Calibration targets for the sim, from six full seasons of real play-by-play
(2020-2025). 2026 is excluded: it is a partial season in progress.

Every number here is computed, not recalled. These are what the engine has to
reproduce before it is worth anything.
"""
import pandas as pd, numpy as np, json

SEASONS = [2020, 2021, 2022, 2023, 2024, 2025]
COLS = ['game_id','season','play_type','yards_gained','down','ydstogo','complete_pass',
        'sack','interception','fumble_lost','touchdown','air_yards','yards_after_catch',
        'field_goal_result','fixed_drive_result','drive','season_type','first_down',
        'home_score','away_score','qtr','posteam','epa','penalty','play_id',
        'rush_attempt','pass_attempt','yardline_100','score_differential']

frames = []
for y in SEASONS:
    d = pd.read_csv(f'pbp{y}.csv', low_memory=False,
                    usecols=lambda c: c in COLS)
    d = d[d.season_type == 'REG']
    frames.append(d)
P = pd.concat(frames, ignore_index=True)
print(f'seasons {SEASONS[0]}-{SEASONS[-1]}   plays {len(P):,}   games {P.game_id.nunique():,}')

S = P[P.play_type.isin(['pass','run'])].copy()
OUT = {}

def band(x, lo=.25, hi=.75):
    return dict(mean=round(float(np.mean(x)),3), sd=round(float(np.std(x)),3),
                p25=round(float(np.quantile(x, lo)),3), p75=round(float(np.quantile(x, hi)),3))

# ---------------- per game ----------------
per_game = P.groupby(['season','game_id']).agg(
    plays=('play_id','size'),
    tds=('touchdown','sum'),
    turnovers=('interception', lambda s: s.sum()),
).reset_index()
scr = P.groupby(['season','game_id'])[['home_score','away_score']].max().reset_index()
scr['total'] = scr.home_score + scr.away_score
snaps = S.groupby(['season','game_id']).size()

print('\n=== PER GAME (by season, to show the year-to-year band) ===')
print(f'  {"season":>7s} {"games":>6s} {"snaps":>7s} {"points/team":>12s} {"total":>7s} {"drives":>7s}')
drv = P[P.drive.notna()].groupby(['season','game_id','drive']).size().groupby(level=[0,1]).size()
rows = []
for y in SEASONS:
    sn = snaps.loc[y]; sc = scr[scr.season == y]; dv = drv.loc[y]
    rows.append((y, len(sc), sn.mean(), (sc.home_score.mean()+sc.away_score.mean())/2,
                 sc.total.mean(), dv.mean()))
    print(f'  {y:7d} {len(sc):6d} {sn.mean():7.1f} {(sc.home_score.mean()+sc.away_score.mean())/2:12.1f} '
          f'{sc.total.mean():7.1f} {dv.mean():7.1f}')
R = pd.DataFrame(rows, columns=['season','games','snaps','ppt','total','drives'])
OUT['per_game'] = dict(
    offensive_snaps=band(snaps.values), points_per_team=round(float(R.ppt.mean()),2),
    points_per_team_sd_between_seasons=round(float(R.ppt.std()),2),
    total_points=round(float(R.total.mean()),2),
    drives=round(float(R.drives.mean()),2),
    points_sd_between_teams=round(float(scr.home_score.std()),2))

# ---------------- play mix ----------------
mix = (P[P.play_type.notna() & (P.play_type != 'no_play')]
       .groupby('season').play_type.value_counts(normalize=True).unstack().mean()*100)
OUT['play_mix_pct'] = {k: round(float(v),2) for k, v in mix.sort_values(ascending=False).items() if v > 0.05}
print('\n=== PLAY MIX (% of all plays, 6-season mean) ===')
print('  ' + '  '.join(f'{k} {v:.1f}' for k, v in OUT['play_mix_pct'].items()))

# ---------------- yards per play ----------------
print('\n=== YARDS PER PLAY ===')
print(f'  {"type":6s} {"mean":>6s} {"sd":>6s} {"p10":>5s} {"med":>5s} {"p90":>5s} {"20+%":>6s} {"neg%":>6s}')
OUT['yards'] = {}
for t in ['pass','run']:
    d = S[S.play_type == t].yards_gained.dropna()
    OUT['yards'][t] = dict(mean=round(float(d.mean()),3), sd=round(float(d.std()),3),
                           p10=float(d.quantile(.1)), p50=float(d.median()), p90=float(d.quantile(.9)),
                           explosive_pct=round(float((d>=20).mean()*100),2),
                           negative_pct=round(float((d<0).mean()*100),2))
    o = OUT['yards'][t]
    print(f'  {t:6s} {o["mean"]:6.2f} {o["sd"]:6.2f} {o["p10"]:5.1f} {o["p50"]:5.1f} {o["p90"]:5.1f} '
          f'{o["explosive_pct"]:6.2f} {o["negative_pct"]:6.2f}')

# ---------------- pass outcomes ----------------
PA = P[P.play_type == 'pass']
OUT['pass'] = dict(
    completion_pct=round(float(PA.complete_pass.mean()*100),2),
    sack_pct=round(float(PA.sack.mean()*100),2),
    int_pct=round(float(PA.interception.mean()*100),2),
    air_yards=round(float(PA.air_yards.mean()),2),
    yac=round(float(PA.yards_after_catch.mean()),2))
print('\n=== PASS OUTCOMES ===')
print('  ' + '  '.join(f'{k}: {v}' for k, v in OUT['pass'].items()))

# ---------------- down and distance ----------------
print('\n=== BY DOWN AND DISTANCE ===')
S['dist'] = pd.cut(S.ydstogo, [0,3,6,10,99], labels=['1-3','4-6','7-10','11+'])
dd = S.groupby(['down','dist'], observed=True).agg(n=('yards_gained','size'),
        ypp=('yards_gained','mean'), conv=('first_down','mean')).reset_index()
dd = dd[dd.n >= 500]
print(f'  {"down":>4s} {"dist":>5s} {"n":>7s} {"ypp":>6s} {"1st-dn%":>8s}')
OUT['down_distance'] = []
for _, r in dd.iterrows():
    print(f'  {int(r.down):4d} {r.dist:>5s} {int(r.n):7d} {r.ypp:6.2f} {r.conv*100:7.1f}%')
    OUT['down_distance'].append(dict(down=int(r.down), dist=str(r.dist), n=int(r.n),
                                     ypp=round(float(r.ypp),3), conv_pct=round(float(r.conv*100),2)))

# ---------------- drive outcomes ----------------
D = P[P.drive.notna()].groupby(['season','game_id','drive']).fixed_drive_result.first()
dr = (D.groupby(level=0).value_counts(normalize=True).unstack().mean()*100).sort_values(ascending=False)
OUT['drive_outcomes_pct'] = {k: round(float(v),2) for k, v in dr.items() if v > 0.05}
print('\n=== DRIVE OUTCOMES (6-season mean) ===')
for k, v in OUT['drive_outcomes_pct'].items(): print(f'  {k:20s} {v:5.2f}%')

# ---------------- scoring and turnovers ----------------
ng = P.game_id.nunique()
FG = P[P.play_type == 'field_goal']
OUT['scoring'] = dict(
    td_per_game=round(float(P.touchdown.sum()/ng),3),
    fga_per_game=round(float(len(FG)/ng),3),
    fg_pct=round(float(FG.field_goal_result.eq('made').mean()*100),2),
    turnovers_per_game=round(float((P.interception.sum()+P.fumble_lost.sum())/ng),3))
print('\n=== SCORING & TURNOVERS (per game) ===')
print('  ' + '  '.join(f'{k}: {v}' for k, v in OUT['scoring'].items()))

# ---------------- field position ----------------
print('\n=== YARDS PER PLAY BY FIELD POSITION ===')
S['fz'] = pd.cut(S.yardline_100, [0,20,50,80,100],
                 labels=['opp 1-20','opp 21-50','own 21-50','own 1-20'])
fz = S.groupby('fz', observed=True).agg(n=('yards_gained','size'), ypp=('yards_gained','mean'),
                                        td=('touchdown','mean'))
OUT['field_zone'] = {str(k): dict(ypp=round(float(v.ypp),3), td_pct=round(float(v.td*100),2))
                     for k, v in fz.iterrows()}
for k, v in fz.iterrows():
    print(f'  {str(k):12s} n={int(v.n):7d}  ypp {v.ypp:5.2f}  TD rate {v.td*100:5.2f}%')

json.dump(OUT, open('sim_targets.json','w'), indent=1)
print('\nsaved sim_targets.json')
