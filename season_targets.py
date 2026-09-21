"""
Season-total production by POSITION RANK, six seasons (2020-2025).

The per-play distributions tell you a snap looks right. They do not tell you a
SEASON looks right. If the sim hands every receiver 700 yards the per-play
numbers can still be perfect while the league is nonsense.

So: what does the WR1 in the league produce, versus WR15, WR30, WR60? And the
same for every position. These are the shape targets a season has to land on.
"""
import pandas as pd, numpy as np, json, glob

SEASONS = [2020, 2021, 2022, 2023, 2024, 2025]
box = []
for y in SEASONS:
    d = pd.read_csv(f'adv/wk_{y}.csv', low_memory=False)
    if 'season_type' in d.columns: d = d[d.season_type == 'REG']
    idc = 'player_id' if 'player_id' in d.columns else 'gsis_id'
    num = [c for c in d.select_dtypes('number').columns
           if c not in ('season','week') and not c.endswith('_id')]
    g = d.groupby(['season', idc])[num].sum(min_count=1).reset_index()
    box.append(g.rename(columns={idc: 'gsis_id'}))
B = pd.concat(box, ignore_index=True)

P = pd.read_csv('players.csv', low_memory=False)
bd = P.dropna(subset=['gsis_id']).drop_duplicates('gsis_id').set_index('gsis_id')
B['pos'] = B.gsis_id.map(bd.position)
B['grp'] = B.gsis_id.map(bd.position_group)
for c in ['passing_yards','passing_tds','interceptions','attempts','completions',
          'rushing_yards','rushing_tds','carries','receiving_yards','receiving_tds',
          'receptions','targets','sacks','sack_yards']:
    if c not in B.columns: B[c] = np.nan
    B[c] = pd.to_numeric(B[c], errors='coerce').fillna(0)

print(f'player-seasons: {len(B):,}   seasons {SEASONS[0]}-{SEASONS[-1]}')

RANKS = [1, 3, 5, 10, 15, 20, 25, 30, 40, 50, 64, 80, 100]
OUT = {}

def rank_table(df, metric, label, ranks=RANKS, top=120):
    """For each season take the top N at this metric, then average across seasons."""
    rows = {}
    for y in SEASONS:
        d = df[df.season == y].nlargest(top, metric)[metric].values
        for r in ranks:
            if r <= len(d): rows.setdefault(r, []).append(d[r-1])
    return {r: round(float(np.mean(v)), 1) for r, v in rows.items() if v}

def show(title, df, metrics, ranks=RANKS):
    print(f'\n=== {title} ===')
    hdr = f'  {"metric":22s} ' + ' '.join(f'{r:>6d}' for r in ranks)
    print(hdr)
    block = {}
    for m, lbl in metrics:
        t = rank_table(df, m, lbl, ranks)
        block[lbl] = t
        print(f'  {lbl:22s} ' + ' '.join(f'{t.get(r, float("nan")):6.0f}' if r in t else '     .'
                                         for r in ranks))
    return block

QB = B[B.pos == 'QB']
_pbi = []
for y in SEASONS:
    d = pd.read_csv(f'pbp{y}.csv', low_memory=False,
                    usecols=lambda c: c in ['season','season_type','passer_player_id','interception'])
    d = d[(d.season_type == 'REG') & d.passer_player_id.notna()]
    _pbi.append(d.groupby(['season','passer_player_id']).interception.sum().reset_index())
INTT = pd.concat(_pbi)
print('\n=== QB INTERCEPTIONS THROWN (from play-by-play) ===')
_r = [1,3,5,10,15,20,25,30]
_rows = {}
for y in SEASONS:
    v = INTT[INTT.season == y].nlargest(40, 'interception').interception.values
    for r in _r:
        if r <= len(v): _rows.setdefault(r, []).append(v[r-1])
print('  ' + ' '.join(f'{r:>6d}' for r in _r))
print('  ' + ' '.join(f'{np.mean(_rows[r]):6.1f}' if r in _rows else '     .' for r in _r))
# 'interceptions' in the weekly file is a DEFENSIVE column - picks recorded, not
# thrown - so ranking quarterbacks on it returned zeros. INTs thrown come from
# the play-by-play instead.
OUT['QB'] = show('QUARTERBACKS (by season rank)', QB, [
    ('passing_yards','pass yards'), ('passing_tds','pass TD'),
    ('attempts','attempts'), ('completions','completions'),
    ('rushing_yards','rush yards')],
    ranks=[1,3,5,10,15,20,25,30,40])

RB = B[B.grp == 'RB']
OUT['RB'] = show('RUNNING BACKS', RB, [
    ('rushing_yards','rush yards'), ('carries','carries'),
    ('rushing_tds','rush TD'), ('receptions','receptions'),
    ('receiving_yards','rec yards')])

WR = B[B.pos == 'WR']
OUT['WR'] = show('WIDE RECEIVERS', WR, [
    ('receiving_yards','rec yards'), ('receptions','receptions'),
    ('targets','targets'), ('receiving_tds','rec TD')])

TE = B[B.pos == 'TE']
OUT['TE'] = show('TIGHT ENDS', TE, [
    ('receiving_yards','rec yards'), ('receptions','receptions'),
    ('targets','targets'), ('receiving_tds','rec TD')],
    ranks=[1,3,5,10,15,20,25,30,40,50])

# ---------------- defence: from PFR advanced, which has the real columns ----
adv = pd.read_csv('adv/advstats_season_def.csv', low_memory=False)
adv = adv[adv.season.isin(SEASONS)]
for c in ['sk','prss','comb','int','hrry','qbkd','tgt','yds']:
    if c in adv.columns: adv[c] = pd.to_numeric(adv[c], errors='coerce').fillna(0)
print(f'\ndefensive player-seasons: {len(adv):,}')

def rank_table_adv(df, metric, ranks=RANKS, top=120):
    rows = {}
    for y in SEASONS:
        d = df[df.season == y].nlargest(top, metric)[metric].values
        for r in ranks:
            if r <= len(d): rows.setdefault(r, []).append(d[r-1])
    return {r: round(float(np.mean(v)), 1) for r, v in rows.items() if v}

print('\n=== PASS RUSHERS (all defenders, by season rank) ===')
print(f'  {"metric":22s} ' + ' '.join(f'{r:>6d}' for r in RANKS))
OUT['pass_rush'] = {}
for m, lbl in [('sk','sacks'), ('prss','pressures'), ('hrry','hurries'), ('qbkd','QB knockdowns')]:
    if m not in adv.columns: continue
    t = rank_table_adv(adv, m)
    OUT['pass_rush'][lbl] = t
    print(f'  {lbl:22s} ' + ' '.join(f'{t.get(r, float("nan")):6.1f}' if r in t else '     .'
                                     for r in RANKS))

print('\n=== TACKLERS AND COVERAGE ===')
print(f'  {"metric":22s} ' + ' '.join(f'{r:>6d}' for r in RANKS))
OUT['defense'] = {}
for m, lbl in [('comb','combined tackles'), ('int','interceptions'), ('tgt','targets faced')]:
    if m not in adv.columns: continue
    t = rank_table_adv(adv, m)
    OUT['defense'][lbl] = t
    print(f'  {lbl:22s} ' + ' '.join(f'{t.get(r, float("nan")):6.1f}' if r in t else '     .'
                                     for r in RANKS))

# ---------------- team totals ----------------
print('\n=== TEAM SEASON TOTALS (rank 1 / 8 / 16 / 24 / 32) ===')
pbp = []
for y in SEASONS:
    d = pd.read_csv(f'pbp{y}.csv', low_memory=False,
                    usecols=lambda c: c in ['season','season_type','posteam','play_type',
                                            'yards_gained','touchdown','pass_attempt',
                                            'rush_attempt','interception','fumble_lost'])
    pbp.append(d[d.season_type == 'REG'])
PB = pd.concat(pbp, ignore_index=True)
PB = PB[PB.posteam.notna()]
tm = PB.groupby(['season','posteam']).agg(
    yards=('yards_gained','sum'), tds=('touchdown','sum'),
    pass_att=('pass_attempt','sum'), rush_att=('rush_attempt','sum'),
    ints=('interception','sum'), fum=('fumble_lost','sum')).reset_index()
TEAM_RANKS = [1,4,8,16,24,28,32]
print(f'  {"metric":22s} ' + ' '.join(f'{r:>7d}' for r in TEAM_RANKS))
OUT['team'] = {}
for m, lbl in [('yards','total yards'), ('tds','touchdowns'),
               ('pass_att','pass attempts'), ('rush_att','rush attempts'),
               ('ints','INTs thrown')]:
    rows = {}
    for y in SEASONS:
        d = tm[tm.season == y].nlargest(32, m)[m].values
        for r in TEAM_RANKS:
            if r <= len(d): rows.setdefault(r, []).append(d[r-1])
    t = {r: round(float(np.mean(v)), 1) for r, v in rows.items()}
    OUT['team'][lbl] = t
    print(f'  {lbl:22s} ' + ' '.join(f'{t.get(r, float("nan")):7.0f}' for r in TEAM_RANKS))

json.dump(OUT, open('season_targets.json','w'), indent=1)
print('\nsaved season_targets.json')
