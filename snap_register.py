import sys
import numpy as np, collections, rosters as R, game as G, plays as P, schemes as S, league as LG, season as SN, gm_engine as GE, targets as TG, defense_roles as DR
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 51
rng = np.random.default_rng(seed)
LL = LG.build_league(rng=np.random.default_rng(seed))
schemes = {t: GE.scheme_of(team.gm) for t, team in LL.teams.items()}
rigidity = {t: float(getattr(team.gm, 'scheme_rigidity', 0.5)) for t, team in LL.teams.items()}
L = R.load_league(scheme=schemes, rigidity=rigidity); teams = sorted(L)
coaches = {t: SN.make_coach(LL.teams[t].gm) for t in teams}
co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
ST = {t: G.TeamState(L[t], coach=coaches[t], scheme=schemes[t]) for t in teams}
# per game: each man's snaps as a share of his team's offensive or defensive plays, by depth slot at his position group
share = collections.defaultdict(list); tgt_share = collections.defaultdict(list)
back_share = collections.defaultdict(list); pooled_third = collections.defaultdict(list)
front_share = collections.defaultdict(list)
OFF = {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT']}
DEF = {'EDGE': ['LEDG', 'REDG'], 'IDL': ['DT'], 'LB': ['MIKE', 'WILL', 'SAM'],
       'CB': ['CB'], 'FS': ['FS'], 'SS': ['SS']}
def by_depth(units, poss, scheme):
    # The engine's roster dictionaries have ratings and position-specific depth,
    # but no 'ovr' key. Use the same depth order used to field players.
    men = [(rank, TG.position_score(m, pos, scheme), m)
           for pos in poss for rank, m in enumerate(units['depth'].get(pos, []))]
    return [m for _, _, m in sorted(men, key=lambda row: (row[0], -row[1]))]
def is_play(pl):
    # State records a player's physical snap even when a penalty voids the
    # official play, so the denominator must include those snaps too.
    return (isinstance(pl, dict) and
            pl.get('type') in ('run', 'complete', 'incomplete', 'sack',
                               'scramble', 'drop', 'interception'))
n = 0
for wk in range(4):
    o = list(teams); rng.shuffle(o)
    for i in range(0, 32, 2):
        h, a = o[i], o[i + 1]
        r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk + 1); n += 1
        for abbr in (h, a):
            units = L[abbr]; snaps = ST[abbr].last_snaps
            off_plays = sum(1 for pos, d in r['drives'] if (pos == 'home') == (abbr == h) for pl in d.log if is_play(pl))
            def_plays = sum(1 for pos, d in r['drives'] if (pos == 'home') != (abbr == h) for pl in d.log if is_play(pl))
            tg = collections.Counter(pl.get('target') for pos, d in r['drives'] if (pos == 'home') == (abbr == h) for pl in d.log if is_play(pl) and pl.get('type') in ('complete', 'incomplete', 'drop', 'interception')); team_tgts = sum(tg.values())
            own_back_rank = {man['pid']: f'{pos}{rank}'
                             for pos in ('HB', 'FB')
                             for rank, man in enumerate(units['depth'].get(pos, ()), 1)}
            for gname, poss in list(OFF.items()) + list(DEF.items()):
                men = by_depth(units, poss, schemes[abbr])
                denom = off_plays if gname in OFF else def_plays
                for k, m in enumerate(men[:6], 1):
                    sn = snaps.get(m['pid'], 0)
                    share[(gname, k)].append(sn / max(1, denom))
                    if gname in ('WR', 'TE', 'RB'): tgt_share[(gname, k)].append(tg.get(m['pid'], 0) / max(1, team_tgts))
                    if gname == 'RB' and k == 3:
                        pooled_third[own_back_rank.get(m['pid'], '?')].append(sn / max(1, denom))
            package = str(getattr(LL.teams[abbr].gm, 'off_personnel', '11'))
            for pos in ('HB', 'FB'):
                for rank, man in enumerate(units['depth'].get(pos, ())[:4], 1):
                    value = snaps.get(man['pid'], 0) / max(1, off_plays)
                    back_share[(pos, rank, 'all')].append(value)
                    back_share[(pos, rank, 'two-back' if package in ('21', '22') else 'other')].append(value)
            role_counts = collections.Counter()
            for row in DR.assign(units['depth'], units['front_family'], 'base'):
                role = DR.role_label(row['role'])
                role_counts[role] += 1
                label = f'{role}{role_counts[role]}' if DR.shape(units['front_family'], 'base')[row['group']].count(row['role']) > 1 else role
                player = row['player']
                if player:
                    front_share[(units['front_family'], label)].append(
                        snaps.get(player['pid'], 0) / max(1, def_plays))
REAL = {('QB', 1): '100', ('RB', 1): '55-65', ('RB', 2): '25-35', ('RB', 3): '5-12', ('WR', 1): '85-92', ('WR', 2): '75-85', ('WR', 3): '55-65', ('WR', 4): '20-30', ('WR', 5): '5-12', ('TE', 1): '75-90', ('TE', 2): '30-45', ('TE', 3): '5-12', ('OL', 5): '~100',
        ('CB', 1): '90-100', ('CB', 2): '85-100', ('CB', 3): '60-75', ('CB', 4): '10-20', ('FS', 1): '95-100', ('SS', 1): '90-100'}
print(f"{n} games, seed {seed}. snap share of physical team plays by depth slot, sim mean vs real range")
print('EDGE/IDL/LB are pooled roster positions across fronts; compare actual front roles below.')
for g in list(OFF) + list(DEF):
    line = []
    for k in range(1, 7):
        v = share.get((g, k))
        if not v: break
        # The pooled RB order interleaves HB and FB depth. Compare the
        # reference backfield shares with HB ranks in the split below.
        reference = '' if g == 'RB' else (' [' + REAL[(g, k)] + ']' if (g, k) in REAL else '')
        line.append(f'{g}{k} {np.mean(v)*100:4.0f}%{reference}')
    print('  ' + ' | '.join(line))
print('target share of team targets:', ' | '.join(f"{g}{k} {np.mean(v)*100:.0f}%" for (g, k), v in sorted(tgt_share.items()) if k <= 5))
print('Back snaps separated by saved position and coach base package (mean share of team offensive plays):')
for category in ('all', 'two-back', 'other'):
    parts = []
    for pos in ('HB', 'FB'):
        for rank in range(1, 5):
            values = back_share.get((pos, rank, category))
            if values:
                parts.append(f'{pos}{rank} {np.mean(values)*100:.1f}% (n={len(values)})')
    print(f'  {category}: ' + ' | '.join(parts))
print('Reference RB depth bands: RB1 55-65%, RB2 25-35%, RB3 5-12%; compare only after matching HB/FB ranking rules.')
print('Pooled RB3 saved positions:', ' | '.join(
    f'{pos} {np.mean(values)*100:.1f}% (n={len(values)})'
    for pos, values in sorted(pooled_third.items())))
print('Base-chart defensive starters by front (share of all defensive plays; no front-specific reference ranges):')
for front in ('4-3', '3-4'):
    roles = (('LEDG', 'DT1', 'DT2', 'REDG', 'MLB', 'WILL', 'SAM', 'CB1', 'CB2', 'FS', 'SS')
             if front == '4-3' else
             ('LE', 'NT', 'RE', 'LOLB', 'LILB', 'RILB', 'ROLB', 'CB1', 'CB2', 'FS', 'SS'))
    for start in (0, 4, 7):
        segment = roles[start:(4 if start == 0 else 7 if start == 4 else 11)]
        line = [f'{role} {np.mean(front_share[(front, role)])*100:.0f}%'
                for role in segment if front_share.get((front, role))]
        print(f"  {front} " + ' | '.join(line))
