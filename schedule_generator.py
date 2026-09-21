import pandas as pd
from collections import Counter, defaultdict

st = pd.read_csv('standings.csv', low_memory=False)
g  = pd.read_csv('sched.csv', low_memory=False)

DIVS = ['AFC East','AFC North','AFC South','AFC West','NFC East','NFC North','NFC South','NFC West']

# ---- rotations, derived from 2002-2026 real schedules (see derive_rotation.py) ----
# intra-conference: 3-year cycle. anchor 2026.
INTRA = [
  {'AFC East':'AFC West','AFC West':'AFC East','AFC North':'AFC South','AFC South':'AFC North',
   'NFC East':'NFC West','NFC West':'NFC East','NFC North':'NFC South','NFC South':'NFC North'},   # 2026
  {'AFC East':'AFC South','AFC South':'AFC East','AFC North':'AFC West','AFC West':'AFC North',
   'NFC East':'NFC South','NFC South':'NFC East','NFC North':'NFC West','NFC West':'NFC North'},   # 2027
  {'AFC East':'AFC North','AFC North':'AFC East','AFC South':'AFC West','AFC West':'AFC South',
   'NFC East':'NFC North','NFC North':'NFC East','NFC South':'NFC West','NFC West':'NFC South'},   # 2028
]
# inter-conference 4-game block: 4-year cycle. anchor 2026.
INTER = [
  {'AFC East':'NFC North','AFC North':'NFC South','AFC West':'NFC West','AFC South':'NFC East'},   # 2026
  {'AFC East':'NFC East','AFC North':'NFC West','AFC West':'NFC North','AFC South':'NFC South'},   # 2027
  {'AFC East':'NFC West','AFC North':'NFC East','AFC West':'NFC South','AFC South':'NFC North'},   # 2028
  {'AFC East':'NFC South','AFC North':'NFC North','AFC West':'NFC East','AFC South':'NFC West'},   # 2029
]
# 17th game division pairing: its own 4-year cycle. anchor 2026.
X17 = [
  {'AFC East':'NFC West','AFC North':'NFC East','AFC South':'NFC North','AFC West':'NFC South'},   # 2026
  {'AFC East':'NFC South','AFC North':'NFC North','AFC South':'NFC West','AFC West':'NFC East'},   # 2027
  {'AFC East':'NFC North','AFC North':'NFC South','AFC South':'NFC East','AFC West':'NFC West'},   # 2028
  {'AFC East':'NFC East','AFC North':'NFC West','AFC South':'NFC South','AFC West':'NFC North'},   # 2029
]

def rot(season):
    i = INTRA[(season - 2026) % 3]
    x = INTER[(season - 2026) % 4]
    x = {**x, **{v: k for k, v in x.items()}}
    s = X17[(season - 2026) % 4]
    s = {**s, **{v: k for k, v in s.items()}}
    return i, x, s

def build(season, prev_standings):
    """Returns the full matchup set for a season. Deterministic; no discretion."""
    teams = prev_standings.team.tolist()
    DIV  = prev_standings.set_index('team').division.to_dict()
    CONF = prev_standings.set_index('team').conf.to_dict()
    RANK = prev_standings.set_index('team').div_rank.to_dict()
    bydiv = defaultdict(list)
    for t in teams: bydiv[DIV[t]].append(t)
    intra, inter, x17 = rot(season)
    games = []           # (home, away, kind)

    # 1. division: home and away vs each rival
    for d, ts in bydiv.items():
        for a in ts:
            for b in ts:
                if a < b:
                    games.append((a, b, 'div')); games.append((b, a, 'div'))

    # 2 & 3. the two 4-game blocks.
    # NFL constraint: every team gets exactly 2 home and 2 away inside each block.
    # The league's specific choice is not derivable from the data, so we use the
    # outer/inner rank pattern (ranks 1&4 vs 2&3) which satisfies it by construction,
    # with polarity alternating across pairs so league-wide home totals stay balanced.
    outer = lambda t: RANK[t] in (1, 4)
    for rotmap, kind in [(intra, 'intra_block'), (inter, 'inter_block')]:
        done, flip = set(), 0
        for d in sorted(rotmap):
            od = rotmap[d]
            if (od, d) in done: continue
            done.add((d, od))
            pol = (flip % 2 == 0); flip += 1
            for a in bydiv[d]:
                for b in bydiv[od]:
                    home_a = (outer(a) == outer(b)) == pol
                    games.append((a, b, kind) if home_a else (b, a, kind))

    # 4. two place-based intra-conference games vs the divisions not in the block.
    # The four divisions of a conference form a 4-cycle under "not my block partner".
    # Orient the cycle: each division hosts the next and visits the previous,
    # which gives every team exactly 1 home and 1 away here.
    for conf in ['AFC','NFC']:
        cds = sorted(d for d in DIVS if d.startswith(conf))
        cycle = [cds[0]]
        while len(cycle) < 4:
            cur = cycle[-1]
            nxt = [o for o in cds if o != cur and o != intra[cur] and o not in cycle]
            if not nxt: break
            cycle.append(nxt[0])
        for i, d in enumerate(cycle):
            od = cycle[(i + 1) % 4]
            for a in bydiv[d]:
                b = next(x for x in bydiv[od] if RANK[x] == RANK[a])
                games.append((a, b, 'place_intra'))     # d hosts od

    # 5. the 17th game: place-based, cross-conference, host conference alternates
    host_conf = 'NFC' if season % 2 == 0 else 'AFC'
    for d in [x for x in DIVS if x.startswith('AFC')]:
        od = x17[d]
        for a in bydiv[d]:
            b = next(x for x in bydiv[od] if RANK[x] == RANK[a])
            games.append((b, a, 'g17') if host_conf == 'NFC' else (a, b, 'g17'))

    return games

# ================= VALIDATE against real schedules =================
def real_matchups(season):
    gs = g[(g.season == season) & (g.game_type == 'REG')]
    return Counter(tuple(sorted([r.home_team, r.away_team])) for _, r in gs.iterrows()), \
           Counter((r.home_team, r.away_team) for _, r in gs.iterrows())

print('=== VALIDATION: generated vs the real NFL schedule ===\n')
for season in [2024, 2025, 2026]:
    prev = st[st.season == season - 1]
    if len(prev) != 32: continue
    gen = build(season, prev)
    gen_un = Counter(tuple(sorted([h, a])) for h, a, _ in gen)
    gen_dir = Counter((h, a) for h, a, _ in gen)
    real_un, real_dir = real_matchups(season)

    tot = sum(real_un.values())
    match_un = sum((gen_un & real_un).values())
    match_dir = sum((gen_dir & real_dir).values())
    print(f'{season}:  games {sum(gen_un.values())} vs real {tot}')
    print(f'   matchups (who plays whom):  {match_un}/{tot}  ({match_un/tot:.1%})')
    print(f'   with home/away correct:     {match_dir}/{tot}  ({match_dir/tot:.1%})')
    miss = (real_un - gen_un)
    if miss: print(f'   missing: {list(miss.elements())[:6]}')
    per = Counter()
    for h, a, _ in gen: per[h] += 1; per[a] += 1
    print(f'   games per team: {dict(Counter(per.values()))}')
    hs = Counter(h for h, a, _ in gen)
    print(f'   home splits: {dict(Counter(hs.values()))}')
    print(f'   by kind: {dict(Counter(k for _,_,k in gen))}')
    perblock = Counter()
    for t in prev.team:
        for kind in ['intra_block','inter_block','place_intra']:
            h = sum(1 for x,a,k in gen if k==kind and x==t)
            n = sum(1 for x,a,k in gen if k==kind and (x==t or a==t))
            perblock[(kind,h,n)] += 1
    print('   per-team home/total inside each block:')
    for (k,h,n),c in sorted(perblock.items()): print(f'      {k:12s} {h}H of {n}: {c} teams')
    print()
