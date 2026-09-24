import numpy as np, collections, rosters as R, game as G, plays as P, schemes as S, league as LG, season as SN
rng = np.random.default_rng(51); L = R.load_league(); teams = sorted(L)
LL = LG.build_league(rng=np.random.default_rng(51)); coaches = {t: SN.make_coach(LL.teams[t].gm) for t in teams}
co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
# per game: each man's snaps as a share of his team's offensive or defensive plays, by depth slot at his position group
share = collections.defaultdict(list); tgt_share = collections.defaultdict(list); rows_by_slot = collections.defaultdict(list)
OFF = {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT']}
DEF = {'EDGE': ['LEDG', 'REDG'], 'IDL': ['DT'], 'LB': ['MIKE', 'WILL', 'SAM'], 'CB': ['CB'], 'S': ['FS', 'SS']}
def by_ovr(units, poss):
    men = [m for grp in ('qb', 'rb', 'backs', 'wr', 'te', 'ol', 'dl', 'lb', 'db') for m in (units.get(grp) or []) if isinstance(m, dict) and m.get('pos') in poss]
    seen = set(); out = []
    for m in sorted(men, key=lambda m: -float(m.get('ovr', 0) or 0)):
        if m['pid'] in seen: continue
        seen.add(m['pid']); out.append(m)
    return out
n = 0
for wk in range(4):
    o = list(teams); rng.shuffle(o)
    for i in range(0, 32, 2):
        h, a = o[i], o[i + 1]
        r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk + 1); n += 1
        for abbr in (h, a):
            units = L[abbr]; snaps = ST[abbr].last_snaps
            off_plays = sum(1 for pos, d in r['drives'] if (pos == 'home') == (abbr == h) for pl in d.log if isinstance(pl, dict) and pl.get('type') in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'))
            def_plays = sum(1 for pos, d in r['drives'] if (pos == 'home') != (abbr == h) for pl in d.log if isinstance(pl, dict) and pl.get('type') in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'))
            tg = collections.Counter(pl.get('target') for pos, d in r['drives'] if (pos == 'home') == (abbr == h) for pl in d.log if isinstance(pl, dict) and pl.get('type') in ('complete', 'incomplete', 'drop', 'interception')); team_tgts = sum(tg.values())
            for gname, poss in list(OFF.items()) + list(DEF.items()):
                men = by_ovr(units, poss)
                denom = off_plays if gname in OFF else def_plays
                for k, m in enumerate(men[:6], 1):
                    sn = snaps.get(m['pid'], 0)
                    share[(gname, k)].append(sn / max(1, denom))
                    if gname in ('WR', 'TE', 'RB'): tgt_share[(gname, k)].append(tg.get(m['pid'], 0) / max(1, team_tgts))
REAL = {('QB', 1): '100', ('RB', 1): '55-65', ('RB', 2): '25-35', ('RB', 3): '5-12', ('WR', 1): '85-92', ('WR', 2): '75-85', ('WR', 3): '55-65', ('WR', 4): '20-30', ('WR', 5): '5-12', ('TE', 1): '75-90', ('TE', 2): '30-45', ('TE', 3): '5-12', ('OL', 5): '~100',
        ('EDGE', 1): '70-80', ('EDGE', 2): '60-75', ('EDGE', 3): '30-45', ('EDGE', 4): '10-20', ('IDL', 1): '60-70', ('IDL', 2): '50-65', ('IDL', 3): '30-45', ('IDL', 4): '15-30', ('LB', 1): '90-100', ('LB', 2): '65-85', ('LB', 3): '20-35', ('CB', 1): '90-100', ('CB', 2): '85-100', ('CB', 3): '60-75', ('CB', 4): '10-20', ('S', 1): '95-100', ('S', 2): '90-100', ('S', 3): '15-30'}
print(f"{n} games. snap share of team plays by depth slot (ordered by overall), sim mean vs real range")
for g in list(OFF) + list(DEF):
    line = []
    for k in range(1, 7):
        v = share.get((g, k))
        if not v: break
        line.append(f"{g}{k} {np.mean(v)*100:4.0f}%{(' [' + REAL[(g, k)] + ']') if (g, k) in REAL else ''}")
    print('  ' + ' | '.join(line))
print('target share of team targets:', ' | '.join(f"{g}{k} {np.mean(v)*100:.0f}%" for (g, k), v in sorted(tgt_share.items()) if k <= 5))
