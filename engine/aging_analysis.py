"""
Aging, third attempt, and the previous two were biased the same way.

Filtering to seasons that clear a playing-time floor and then measuring only
those who clear it AGAIN next year is survivorship. A running back who declines
loses carries, falls under the floor and disappears, so the backs still measured
at 30 are exactly the ones who did not decline. That is why version two said
backs hold 96% at 30, which is plainly wrong.

Fixed: every qualified season is followed forward, and losing your role or
leaving the league COUNTS as decline rather than removing you from the sample.
"""
import pandas as pd, numpy as np, glob, json

P = pd.read_csv('players.csv', low_memory=False)
bd = P.dropna(subset=['gsis_id']).drop_duplicates('gsis_id').set_index('gsis_id')

box = []
for f in sorted(glob.glob('adv/wk_*.csv')):
    d = pd.read_csv(f, low_memory=False)
    if 'season_type' in d.columns: d = d[d.season_type == 'REG']
    idc = 'player_id' if 'player_id' in d.columns else 'gsis_id'
    num = [c for c in d.select_dtypes('number').columns
           if c not in ('season','week') and not c.endswith('_id')]
    box.append(d.groupby(['season', idc])[num].sum(min_count=1).reset_index()
                .rename(columns={idc:'gsis_id'}))
BOX = pd.concat(box, ignore_index=True)

snaps = []
for f in sorted(glob.glob('adv/snap_*.csv')):
    d = pd.read_csv(f, low_memory=False); d = d[d.game_type=='REG']
    snaps.append(d.groupby(['season','pfr_player_id']).agg(
        off=('offense_snaps','sum'), dfn=('defense_snaps','sum')).reset_index()
        .rename(columns={'pfr_player_id':'pfr_id'}))
SNAP = pd.concat(snaps, ignore_index=True)
SNAP['gsis_id'] = SNAP.pfr_id.map(
    P.dropna(subset=['gsis_id','pfr_id']).drop_duplicates('pfr_id').set_index('pfr_id').gsis_id)

A = BOX.merge(SNAP.drop(columns=['pfr_id']), on=['season','gsis_id'], how='outer')
A = A[A.gsis_id.notna()].copy()
A['pos'] = A.gsis_id.map(bd.position_group)
A['age'] = ((pd.to_datetime(A.season.astype(str)+'-09-01') -
             pd.to_datetime(A.gsis_id.map(bd.birth_date), errors='coerce')).dt.days/365.25)
A = A[A.age.between(20,44) & A.pos.notna()].copy()
for c in ['attempts','carries','targets','off','dfn','passing_yards','rushing_yards',
          'receiving_yards','receptions','completions']:
    if c not in A.columns: A[c] = np.nan
    A[c] = pd.to_numeric(A[c], errors='coerce').fillna(0)

# ---- VALUE = rate x role. A man who keeps his efficiency but loses his job
#      has declined, and the old method could not see that.
def value_row(r):
    p = r['pos']
    if p == 'QB':  return (r.passing_yards / max(r.attempts,1)) * min(r.attempts/450, 1.25) if r.attempts else 0.0
    if p == 'RB':  return (r.rushing_yards / max(r.carries,1))  * min(r.carries/220, 1.25) if r.carries else 0.0
    if p in ('WR','TE'): return (r.receiving_yards / max(r.targets,1)) * min(r.targets/110, 1.25) if r.targets else 0.0
    if p == 'OL':  return min(r.off/1000, 1.25) * 8.0
    if p in ('DL','LB','DB'): return min(r.dfn/900, 1.25) * 8.0
    return np.nan
A['val'] = [value_row(r) for _, r in A.iterrows()]
A = A[A.val.notna()].copy()

# a season must be a REAL season to anchor from, but the FOLLOW-UP is measured
# whatever happens, including zero
QUAL = {'QB': lambda r: r.attempts >= 150, 'RB': lambda r: r.carries >= 80,
        'WR': lambda r: r.targets >= 40,  'TE': lambda r: r.targets >= 30,
        'OL': lambda r: r.off >= 400, 'DL': lambda r: r.dfn >= 350,
        'LB': lambda r: r.dfn >= 350, 'DB': lambda r: r.dfn >= 350}
A['qual'] = [QUAL[r['pos']](r) if r['pos'] in QUAL else False for _, r in A.iterrows()]

# index within position-season so eras are comparable
A['idx'] = A.groupby(['pos','season']).val.transform(lambda s: s / s[s > 0].median())

lookup = {(g, s): v for g, s, v in zip(A.gsis_id, A.season, A.idx)}
present = set(zip(A.gsis_id, A.season))
LAST = A.groupby('gsis_id').season.max().to_dict()
MAXSEASON = A.season.max()

rows = []
for _, r in A[A.qual].iterrows():
    nxt = r.season + 1
    if nxt > MAXSEASON: continue
    if (r.gsis_id, nxt) in present:
        nv = lookup[(r.gsis_id, nxt)]
    else:
        # not on any roster next year: he is out of the league. that is decline,
        # not a missing value.
        nv = 0.0
    if r.idx <= 0: continue
    rows.append((r.gsis_id, r['pos'], int(r.season), float(r.age), float(r.idx),
                 float(nv), float(nv / r.idx)))
D = pd.DataFrame(rows, columns=['gsis_id','pos','season','age','v','nv','ratio'])
D['ab'] = D.age.round().astype(int)
print(f'anchored qualified seasons: {len(D):,}  players: {D.gsis_id.nunique():,}')
print(f'of those, gone the next year: {(D.nv == 0).mean():.1%}\n')

print('=== RETENTION: share still holding a real role the following season ===')
print(f'  {"age":>4s} ' + ' '.join(f'{p:>6s}' for p in ['QB','RB','WR','TE','OL','DL','LB','DB']))
for a in range(23, 37):
    line = f'  {a:4d} '
    for p in ['QB','RB','WR','TE','OL','DL','LB','DB']:
        d = D[(D.pos == p) & (D.ab == a)]
        line += f'{(d.nv > 0.5*d.v).mean()*100:5.0f}%' if len(d) >= 12 else '     .'
        line += ' '
    print(line)

print('\n=== VALUE HELD NEXT SEASON (rate x role, dropouts counted as zero) ===')
print(f'  {"age":>4s} ' + ' '.join(f'{p:>6s}' for p in ['QB','RB','WR','TE','OL','DL','LB','DB']))
CURVES = {}
for a in range(23, 37):
    line = f'  {a:4d} '
    for p in ['QB','RB','WR','TE','OL','DL','LB','DB']:
        d = D[(D.pos == p) & (D.ab == a)]
        if len(d) >= 12:
            m = d.ratio.mean()
            CURVES.setdefault(p, {})[a] = round(float(m), 4)
            line += f'{m*100:5.0f}%'
        else: line += '     .'
        line += ' '
    print(line)

# Smooth, then enforce that the curve cannot RISE once decline has begun.
# Small age-position cells plus the dropout-as-zero rule make single years swing
# hard, which had quarterbacks going 93% at 28 and back up to 107% at 30. A
# player does not get better at 30 than he was at 28; that is thin-sample noise
# and only the survivors being measured. Ability is allowed to hold flat, never
# to climb back.
from sklearn.isotonic import IsotonicRegression
for p in CURVES:
    ser = pd.Series(CURVES[p]).sort_index()
    sm = ser.rolling(3, center=True, min_periods=2).mean()
    ages = sm.index.values.astype(float)
    # anchor at the end of prime, not at argmax: for quarterbacks the noisy tail
    # WAS the argmax, so the constraint applied from 35 and the 28->30 rise stood
    after = ages >= 27
    if after.sum() >= 3:
        fixed = IsotonicRegression(increasing=False, out_of_bounds='clip'
                 ).fit_transform(ages[after], sm.values[after])
        sm = pd.Series(np.concatenate([sm.values[~after], fixed]), index=sm.index)
    CURVES[p] = {int(a): float(v) for a, v in sm.items()}

print('\n=== NORMALISED TO EACH POSITION PRIME (25-27 = 100) ===')
NORM = {}
print(f'  {"pos":5s} ' + ' '.join(f'{a:>5d}' for a in range(24, 36)))
for p, c in CURVES.items():
    prime = [c[a] for a in (25,26,27) if a in c]
    if not prime: continue
    f = np.mean(prime)
    NORM[p] = {a: round(v/f, 4) for a, v in c.items()}
    print(f'  {p:5s} ' + ' '.join(f'{NORM[p][a]*100:4.0f}%' if a in NORM[p] else '    .'
                                  for a in range(24, 36)))

print('\n=== WHERE EACH POSITION FALLS OFF ===')
print(f'  {"pos":5s} {"last age >=97%":>15s} {"drops below 90%":>17s} {"below 75%":>11s}')
SUM = {}
for p, c in NORM.items():
    ages = sorted(c)
    hold = [a for a in ages if a >= 24 and c[a] >= 0.97]
    b90 = next((a for a in ages if a >= 26 and c[a] < 0.90), None)
    b75 = next((a for a in ages if a >= 26 and c[a] < 0.75), None)
    SUM[p] = dict(plateau_end=max(hold) if hold else None, below90=b90, below75=b75,
                  curve=c)
    print(f'  {p:5s} {str(max(hold) if hold else "-"):>15s} {str(b90):>17s} {str(b75):>11s}')

# retention is the cleanest signal in the data: it is monotonic, it has large
# cells, and it captures the thing that actually ends careers - losing the job.
RET = {}
for p in ['QB','RB','WR','TE','OL','DL','LB','DB']:
    r = {}
    for a in range(23, 38):
        d = D[(D.pos == p) & (D.ab == a)]
        if len(d) >= 12: r[a] = round(float((d.nv > 0.5*d.v).mean()), 3)
    if r:
        ser = pd.Series(r).sort_index().rolling(3, center=True, min_periods=2).mean()
        RET[p] = {int(a): round(float(v), 3) for a, v in ser.items()}
for p in SUM: SUM[p]['retention'] = RET.get(p, {})

print('\n=== SMOOTHED RETENTION: chance he still has a real role next year ===')
print(f'  {"pos":5s} ' + ' '.join(f'{a:>5d}' for a in range(24, 36)))
for p, r in RET.items():
    print(f'  {p:5s} ' + ' '.join(f'{r[a]*100:4.0f}%' if a in r else '    .' for a in range(24, 36)))

print('\n=== WHEN DOES A POSITION START LOSING PLAYERS? ===')
print(f'  {"pos":5s} {"peak retention":>15s} {"first big drop":>15s} {"halved by":>11s}')
for p, r in RET.items():
    ages = sorted(r); top = max(r.values()); topa = [a for a in ages if r[a] == top][0]
    drop = next((a for a in ages if a > topa and r[a] < top*0.88), None)
    half = next((a for a in ages if a > topa and r[a] < top*0.65), None)
    print(f'  {p:5s} {f"{top*100:.0f}% at {topa}":>15s} {str(drop):>15s} {str(half):>11s}')

json.dump(SUM, open('aging_v3.json','w'), indent=1, default=str)
print('\nsaved aging_v3.json')
