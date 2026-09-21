import pandas as pd, re, json, unicodedata

TEAM = {'Cardinals':'ARI','Falcons':'ATL','Ravens':'BAL','Bills':'BUF','Panthers':'CAR',
 'Bears':'CHI','Bengals':'CIN','Browns':'CLE','Cowboys':'DAL','Broncos':'DEN','Lions':'DET',
 'Packers':'GB','Texans':'HOU','Colts':'IND','Jaguars':'JAX','Chiefs':'KC','Rams':'LA',
 'Chargers':'LAC','Raiders':'LV','Dolphins':'MIA','Vikings':'MIN','Patriots':'NE','Saints':'NO',
 'Giants':'NYG','Jets':'NYJ','Eagles':'PHI','Steelers':'PIT','Seahawks':'SEA','49ers':'SF',
 'Buccaneers':'TB','Titans':'TEN','Commanders':'WAS'}

SUF = re.compile(r'\b(jr|sr|ii|iii|iv|v)\b')

def norm(n):
    """Strip accents/punctuation. Periods are REMOVED, not spaced: D.J. -> dj."""
    if not isinstance(n, str): return ''
    n = unicodedata.normalize('NFKD', n).encode('ascii', 'ignore').decode()
    n = n.lower().replace('.', '').replace("'", '').replace('-', ' ')
    return ' '.join(re.sub(r'[^a-z ]', '', SUF.sub(' ', n)).split())

def parts(k):
    p = k.split()
    return (p[0] if p else '', p[-1] if p else '')

# ---------- current roster snapshot: latest available week ----------
w = pd.read_csv('weekly.csv', low_memory=False)
w = w[w.week == w.week.max()].copy()
w = w[w.status.isin(['ACT','DEV','RES','INA','EXE'])].copy()
w['key'] = w.full_name.map(norm)
w['first'], w['last'] = zip(*w.key.map(parts))
w = w.drop_duplicates(subset=['key','team'], keep='first').reset_index(drop=True)

# ---------- madden ratings ----------
m = pd.read_csv('../madden27_ratings.csv', low_memory=False).rename(columns={'position':'madden_position'})
m['key'] = m.full_name.map(norm)
m['first'], m['last'] = zip(*m.key.map(parts))
m['team_abbr'] = m.team_short.map(TEAM)
m = m.drop_duplicates(subset=['key','team_abbr'], keep='first').reset_index(drop=True)

RATINGS = [c for c in m.columns if c.endswith('_rating')]
MCOLS = ['madden_position','overall','archetype','x_factor','running_style','handedness',
         'years_pro'] + [f'ability_{i}' for i in range(1,7)] + RATINGS

w['m_idx'] = pd.NA
w['match_pass'] = pd.NA
used = set()

def assign(w_idx, m_idx, label):
    if pd.isna(w.at[w_idx,'m_idx']) and m_idx not in used:
        w.at[w_idx,'m_idx'] = m_idx
        w.at[w_idx,'match_pass'] = label
        used.add(m_idx)

# pass 1: full name + team
lut = {(r.key, r.team_abbr): i for i, r in m.iterrows()}
for i, r in w.iterrows():
    if (r.key, r.team) in lut: assign(i, lut[(r.key, r.team)], 'name+team')

# pass 2: full name, globally unique on both sides
mc, wc = m.key.value_counts(), w.key.value_counts()
lut = {r.key: i for i, r in m.iterrows() if mc[r.key] == 1}
for i, r in w.iterrows():
    if pd.isna(r.m_idx) and wc[r.key] == 1 and r.key in lut: assign(i, lut[r.key], 'name')

# pass 2b: roster-side unique, madden-side duplicated -> prefer same team, else best overall
dupes = m[m.key.duplicated(keep=False)]
for i, r in w.iterrows():
    if pd.isna(r.m_idx) and wc[r.key] == 1:
        cand = dupes[dupes.key == r.key]
        if len(cand):
            same = cand[cand.team_abbr == r.team]
            pick = (same if len(same) else cand).sort_values('overall', ascending=False).index[0]
            assign(i, pick, 'name+dupe-resolve')

# pass 3: surname + team, unique on both sides (Cam/Cameron, Mike/Michael, Tom/Thomas)
mc2 = m.groupby(['last','team_abbr']).size()
wc2 = w.groupby(['last','team']).size()
lut = {(r.last, r.team_abbr): i for i, r in m.iterrows() if mc2[(r.last, r.team_abbr)] == 1}
for i, r in w.iterrows():
    if pd.isna(r.m_idx) and wc2[(r.last, r.team)] == 1 and (r.last, r.team) in lut:
        assign(i, lut[(r.last, r.team)], 'surname+team')

# pass 4: surname + first initial, globally unique (catches in-season trades)
m['fi'] = m['last'] + '|' + m['first'].str[0]
w['fi'] = w['last'] + '|' + w['first'].str[0]
mc3, wc3 = m.fi.value_counts(), w.fi.value_counts()
lut = {r.fi: i for i, r in m.iterrows() if mc3[r.fi] == 1}
for i, r in w.iterrows():
    if pd.isna(r.m_idx) and wc3[r.fi] == 1 and r.fi in lut: assign(i, lut[r.fi], 'surname+initial')

for c in MCOLS:
    w[c] = w.m_idx.map(lambda x: m.at[x, c] if pd.notna(x) else pd.NA)

# ---------- contracts (parquet is current; the csv asset is stale at 2022) ----------
c = pd.read_parquet('hc.parquet')
c['key'] = c.player.map(norm)
c = c.sort_values('year_signed', ascending=False).drop_duplicates(subset=['key'], keep='first')
CC = ['key','year_signed','years','value','apy','guaranteed','apy_cap_pct',
      'draft_year','draft_round','draft_overall','draft_team']
w = w.merge(c[CC], on='key', how='left')
w['contract_years_left'] = (w.year_signed + w.years - 2026).clip(lower=0)

# ---------- sleeper: injury + depth chart ----------
s = json.load(open('/mnt/user-data/uploads/nflsleeper.json'))
sdf = pd.DataFrame([{'sleeper_id': int(k), 'injury_status': v.get('injury_status'),
    'injury_body_part': v.get('injury_body_part'),
    'sleeper_depth_pos': v.get('depth_chart_position'),
    'sleeper_depth_order': v.get('depth_chart_order')} for k, v in s.items() if k.isdigit()])
w['sleeper_id'] = pd.to_numeric(w.sleeper_id, errors='coerce').astype('Int64')
sdf['sleeper_id'] = sdf.sleeper_id.astype('Int64')
w = w.merge(sdf, on='sleeper_id', how='left')

orph = m[~m.index.isin(used)].drop(columns=['fi']).copy()
allw = pd.read_csv('weekly.csv', low_memory=False)
allw['key'] = allw.full_name.map(norm); allw['last'] = allw.key.str.split().str[-1]
seen = {}
for _, r in allw.iterrows(): seen.setdefault((r['last'], r.team), []).append(r.status)
def verdict(r):
    st = seen.get((r['last'], r.team_abbr))
    if st is None: return 'missing_from_nflverse'
    if 'RET' in st: return 'retired'
    if 'CUT' in st: return 'free_agent'
    return 'unresolved'
orph['verdict'] = orph.apply(verdict, axis=1)

# ---- Sleeper is the freshest authority on CURRENT team (pulled today) ----
SL_FIX = {'LAR':'LA','OAK':'LV'}
sl = pd.DataFrame([v for v in s.values() if isinstance(v, dict)])
sl['key'] = sl.full_name.map(norm)
sl['sl_team'] = sl.team.map(lambda t: SL_FIX.get(t, t))
sl['sleeper_id'] = pd.to_numeric(sl.player_id, errors='coerce').astype('Int64')
# exact id lookup (safe for duplicate names)
SL_ID = sl.dropna(subset=['sleeper_id']).drop_duplicates('sleeper_id').set_index('sleeper_id').sl_team
# name lookup ONLY where the name is unique in sleeper
_c = sl.key.value_counts()
SL = sl[sl.key.map(_c) == 1].drop_duplicates('key').set_index('key')[['sl_team','status']].rename(columns={'status':'sl_status'})
print(f'sleeper: {len(SL_ID)} id-keyed, {len(SL)} unique-name-keyed, {(_c>1).sum()} ambiguous names excluded')

orph = orph.join(SL, on='key')
# anyone Sleeper puts on a team is rostered, whatever nflverse or Madden said
orph.loc[orph.sl_team.notna(), 'verdict'] = 'on_roster_per_sleeper'

# players nflverse never carried -> put them back on their madden team
add = orph[orph.verdict.isin(['missing_from_nflverse','on_roster_per_sleeper'])].copy()
add['team'] = add.sl_team.fillna(add.team_abbr)
add['status'] = 'ACT'
add['match_pass'] = add.sl_team.notna().map({True:'sleeper-team', False:'madden-team'})
w = pd.concat([w, add], ignore_index=True)

fa = orph[orph.verdict.isin(['free_agent','unresolved','retired']) & orph.sl_team.isna()]
fa.to_csv(_p('free_agent_pool.csv'), index=False)

print('\norphan classification:'); print(orph.verdict.value_counts().to_string())

_byid = w.sleeper_id.map(SL_ID)
_byname = w.key.map(SL.sl_team)
_slt = _byid.fillna(_byname)
w['sl_team'] = w['sl_team'].fillna(_slt) if 'sl_team' in w.columns else _slt
moved = w[(w.sl_team.notna()) & (w.sl_team != w.team)]
print(f'\ntraded since week 2 per sleeper: {len(moved)}')
print(moved.assign(ovr=pd.to_numeric(moved.overall,errors='coerce'))[['full_name','team','sl_team','ovr','status']].nlargest(8,'ovr').to_string(index=False))
w['team'] = w.sl_team.fillna(w.team)
w.drop(columns=['m_idx','fi'], errors='ignore').to_csv(_p('rosters_2026.csv'), index=False)
n = len(w)
print(f'roster snapshot: week {pd.read_csv("weekly.csv",low_memory=False).week.max()}, {n} players, {w.team.nunique()} teams')
print(f'  ratings  {w.overall.notna().sum():5d} ({w.overall.notna().sum()/n:.1%})')
print(f'  contract {w.apy.notna().sum():5d} ({w.apy.notna().sum()/n:.1%})')
print('\nmatched by pass:'); print(w.match_pass.value_counts().to_string())
print(f'\nmadden unmatched (true FA pool): {len(fa)}')
print('\nroster size by status:'); print(w.status.value_counts().to_string())
print('\nspot check:')
for name in ['Pat Surtain II','Cameron Heyward','DJ Reader','Zach Tom','Foye Oluokun','Jaylon Jones','Brandon Aiyuk']:
    row = w[w.key == norm(name)]
    print(f'  {name:20s}', f'{row.iloc[0].team} ovr={row.iloc[0].overall} via {row.iloc[0].match_pass}' if len(row) else 'NOT ON ROSTER')
print('\nFA pool top 8:')
print(fa.nlargest(8,'overall')[['full_name','madden_position','overall','team_short']].to_string(index=False))
