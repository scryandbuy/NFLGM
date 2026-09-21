import pandas as pd, numpy as np
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n), re, unicodedata


# Data-prep script. Reads source files that are not part of the runtime,
# so it runs by hand only.
if __name__ == '__main__':
    SUF = re.compile(r'\b(jr|sr|ii|iii|iv|v)\b')
    def norm(n):
        if not isinstance(n, str): return ''
        n = unicodedata.normalize('NFKD', n).encode('ascii','ignore').decode()
        n = n.lower().replace('.', '').replace("'", '').replace('-', ' ')
        return ' '.join(re.sub(r'[^a-z ]', '', SUF.sub(' ', n)).split())

    w = pd.read_csv(_p('rosters_2026.csv'), low_memory=False)
    c = pd.read_parquet('hc.parquet').copy()

    OLD = w[['full_name','team','apy','draft_overall']].copy()

    CC = ['year_signed','years','value','apy','guaranteed','apy_cap_pct',
          'draft_year','draft_round','draft_overall','draft_team']
    for col in CC + ['contract_years_left']:
        if col in w.columns: w = w.drop(columns=[col])

    c['key'] = c.player.map(norm)
    c['last'] = c.key.str.split().str[-1]
    c['gsis'] = c.gsis_id.astype(str).str.strip()
    w['gsis'] = w.gsis_id.astype(str).str.strip()
    w['key']  = w.full_name.map(norm)
    w['last'] = w.key.str.split().str[-1]
    w['dob']  = pd.to_datetime(w.birth_date, errors='coerce').dt.date.astype(str)
    c['dob']  = pd.to_datetime(c.date_of_birth, errors='coerce').dt.date.astype(str)

    # Current deal = the ACTIVE contract, not merely the most recent year_signed.
    # A player franchise-tagged and then extended in the same year has two 2023 rows;
    # the tag is marked Renegotiated and the extension Active. Sorting on year alone
    # picks arbitrarily between them (this put Lamar Jackson on a $32.4M tag instead
    # of his $52M extension). Rank on is_active first, then recency, then size.
    c['_act'] = (c.is_active == True).astype(int)
    c = c.sort_values(['_act','year_signed','value'], ascending=[False, False, False])

    w['c_idx'] = pd.NA
    w['contract_pass'] = pd.NA
    def take(mask_rows, lut, label):
        for i in w.index[w.c_idx.isna()]:
            k = mask_rows(w.loc[i])
            if k is not None and k in lut:
                w.at[i,'c_idx'] = lut[k]; w.at[i,'contract_pass'] = label

    # pass 1: gsis_id. exact, immune to duplicate names.
    lut = c[c.gsis.notna() & (c.gsis != 'nan')].drop_duplicates('gsis').set_index('gsis').index
    lut = {g: idx for g, idx in zip(c.drop_duplicates('gsis').gsis, c.drop_duplicates('gsis').index)
           if isinstance(g, str) and g not in ('nan','')}
    take(lambda r: r.gsis if isinstance(r.gsis, str) and r.gsis not in ('nan','') else None, lut, 'gsis_id')

    # pass 2: date of birth + surname. separates two players who share a name.
    cd = c.dropna(subset=['dob']); cd = cd[cd.dob != 'NaT']
    key2 = cd.last + '|' + cd.dob
    lut = {k: i for k, i in zip(key2, cd.index) if (key2 == k).sum() >= 1}
    lut = {k: cd.index[key2 == k][0] for k in key2.unique() if (key2 == k).sum() > 0}
    take(lambda r: (str(r['last']) + '|' + str(r.dob)) if isinstance(r.dob,str) and r.dob not in ('NaT','nan') else None, lut, 'dob+surname')

    # pass 3: full name, only where that name is unique in BOTH files
    cn, wn = c.key.value_counts(), w.key.value_counts()
    lut = {k: c.index[c.key == k][0] for k in cn[cn.index.map(lambda x: True)].index
           if c[c.key == k].draft_year.nunique() <= 1}
    take(lambda r: r.key if isinstance(r.key,str) and wn.get(r.key, 0) == 1 else None, lut, 'unique name')

    # pass 4: surname + draft year (catches Matt/Matthew, Mike/Michael)
    w['dy'] = pd.to_numeric(w.entry_year, errors='coerce')
    cg = c.dropna(subset=['draft_year'])
    k4 = cg['last'] + '|' + cg.draft_year.astype(int).astype(str)
    lut = {k: cg.index[k4 == k][0] for k in k4.unique() if (k4 == k).sum() == 1}
    take(lambda r: f"{r['last']}|{int(r.dy)}" if pd.notna(r.dy) and isinstance(r['last'],str) else None, lut, 'surname+draftyear')

    for col in CC:
        w[col] = w.c_idx.map(lambda x: c.at[x, col] if pd.notna(x) else np.nan)
    w['contract_years_left'] = (w.year_signed + w.years - 2026).clip(lower=0)
    w = w.drop(columns=['c_idx','gsis','last','dob','dy'])
    w.to_csv(_p('rosters_2026.csv'), index=False)

    # ================= report =================
    n = len(w)
    print(f'contract coverage: {w.apy.notna().sum()}/{n} ({w.apy.notna().mean():.1%})   '
          f'was {OLD.apy.notna().mean():.1%}')
    print(f'draft data:        {w.draft_overall.notna().sum()}/{n} ({w.draft_overall.notna().mean():.1%})   '
          f'was {OLD.draft_overall.notna().mean():.1%}')
    print('\nmatched by pass:'); print(w.contract_pass.value_counts().to_string())

    w['ovr'] = pd.to_numeric(w.overall, errors='coerce')
    el = w[w.ovr >= 85]
    bad = el[(el.apy.isna()) | (el.apy < 3)]
    print(f'\nplayers 85+ with missing/implausible contract: {len(bad)}/{len(el)} ({len(bad)/len(el):.0%})   was 23/190 (12%)')

    print('\nthe players that were wrong before:')
    for nm in ['Matt Stafford','Matthew Stafford','Lamar Jackson','Justin Jefferson',
               'DeVonta Smith','Puka Nacua','Pat Surtain II','Sauce Gardner']:
        h = w[(w.full_name == nm)]
        if len(h):
            x = h.sort_values('ovr', ascending=False).iloc[0]
            was = OLD[(OLD.full_name == nm)].apy.max()
            print(f'  {nm:20s} {str(x.team):4s} ovr {x.ovr:.0f}  apy ${x.apy:6.1f}M  pick {x.draft_overall if pd.notna(x.draft_overall) else "UDFA"}   (was ${was:.2f}M)'
                  if pd.notna(x.apy) else f'  {nm:20s} STILL MISSING')

    print('\nteam cap totals (sum of APY, $M) -- sanity vs ~$280M cap:')
    t = w[w.status != 'DEV'].groupby('team').apy.sum().sort_values()
    print(f'  min {t.min():.0f}  median {t.median():.0f}  max {t.max():.0f}')
    print(' ', t.head(3).round(0).to_dict(), '...', t.tail(3).round(0).to_dict())
