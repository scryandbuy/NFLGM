"""
A NEW SCHEDULE EVERY YEAR.

The league loaded the real 2026 slate on day one and never built another, so
after the first roll_year every game still carried its score and play_week
skipped all 272 of them: seasons two onward were an offseason with no
football in it. The generator (schedule_generator.py) and the week solver
(week_assign3.py) both existed as hand-run scripts against research CSVs.
This is the same logic made callable on the league itself.

Matchups follow the NFL formula: six division games, a four-game block
against a rotating division in conference (3-year cycle), a four-game block
against a rotating division out of conference (4-year cycle), two place-
based games in conference against the divisions not in the block, and the
17th place-based game out of conference with the host conference alternating.
Rotations are anchored on 2026 and derived from the 2002-2026 real slates.

Weeks: 17 games in 18 weeks, one bye each in weeks 5-14 with an even number
of clubs off, week 18 all division games, 13-16 games a week, no road trip
over three, no rematch within two weeks. Solved as min-conflicts local search
with a repair pass, as the script did.
"""
import random
from collections import Counter, defaultdict
import numpy as np

DIVS = ['AFC East', 'AFC North', 'AFC South', 'AFC West',
        'NFC East', 'NFC North', 'NFC South', 'NFC West']

INTRA = [
  {'AFC East':'AFC West','AFC West':'AFC East','AFC North':'AFC South','AFC South':'AFC North',
   'NFC East':'NFC West','NFC West':'NFC East','NFC North':'NFC South','NFC South':'NFC North'},
  {'AFC East':'AFC South','AFC South':'AFC East','AFC North':'AFC West','AFC West':'AFC North',
   'NFC East':'NFC South','NFC South':'NFC East','NFC North':'NFC West','NFC West':'NFC North'},
  {'AFC East':'AFC North','AFC North':'AFC East','AFC South':'AFC West','AFC West':'AFC South',
   'NFC East':'NFC North','NFC North':'NFC East','NFC South':'NFC West','NFC West':'NFC South'},
]
INTER = [
  {'AFC East':'NFC North','AFC North':'NFC South','AFC West':'NFC West','AFC South':'NFC East'},
  {'AFC East':'NFC East','AFC North':'NFC West','AFC West':'NFC North','AFC South':'NFC South'},
  {'AFC East':'NFC West','AFC North':'NFC East','AFC West':'NFC South','AFC South':'NFC North'},
  {'AFC East':'NFC South','AFC North':'NFC North','AFC West':'NFC East','AFC South':'NFC West'},
]
X17 = [
  {'AFC East':'NFC West','AFC North':'NFC East','AFC South':'NFC North','AFC West':'NFC South'},
  {'AFC East':'NFC South','AFC North':'NFC North','AFC South':'NFC West','AFC West':'NFC East'},
  {'AFC East':'NFC North','AFC North':'NFC South','AFC South':'NFC East','AFC West':'NFC West'},
  {'AFC East':'NFC East','AFC North':'NFC West','AFC South':'NFC South','AFC West':'NFC North'},
]

BYE_WEEKS = list(range(5, 15))
FULL_WEEKS = [1, 2, 3, 4, 15, 16, 17, 18]
MAX_AWAY_RUN, MIN_REMATCH = 3, 2


def rotation(season):
    i = INTRA[(season - 2026) % 3]
    x = INTER[(season - 2026) % 4]; x = {**x, **{v: k for k, v in x.items()}}
    s = X17[(season - 2026) % 4]; s = {**s, **{v: k for k, v in s.items()}}
    return i, x, s


def build_matchups(season, div, rank):
    """
    div: {team: division}, rank: {team: 1-4 finish in the division last year}.
    Returns [(home, away, kind)], 272 games. Deterministic; no discretion.
    """
    bydiv = defaultdict(list)
    for t, d in div.items(): bydiv[d].append(t)
    for d in bydiv: bydiv[d].sort()
    intra, inter, x17 = rotation(season)
    games = []
    for d, ts in bydiv.items():
        for a in ts:
            for b in ts:
                if a < b:
                    games.append((a, b, 'div')); games.append((b, a, 'div'))
    outer = lambda t: rank[t] in (1, 4)
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
    for conf in ['AFC', 'NFC']:
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
                b = next(x for x in bydiv[od] if rank[x] == rank[a])
                games.append((a, b, 'place_intra'))
    host_conf = 'NFC' if season % 2 == 0 else 'AFC'
    for d in [x for x in DIVS if x.startswith('AFC')]:
        od = x17[d]
        for a in bydiv[d]:
            b = next(x for x in bydiv[od] if rank[x] == rank[a])
            games.append((b, a, 'g17') if host_conf == 'NFC' else (a, b, 'g17'))
    return games


def assign_weeks(games, div, seed=0, restarts=30, iters=60000):
    """{game index: week}, {team: bye week}. None, None if no solution."""
    import networkx as nx
    rng = random.Random(seed)
    n = len(games)
    teams = sorted({t for h, a, _ in games for t in (h, a)})
    for attempt in range(restarts):
        G = nx.Graph()
        for i, (h, a, _) in enumerate(games):
            if div[h] == div[a]: G.add_edge(h, a, weight=rng.random(), idx=i)
        m = nx.max_weight_matching(G, maxcardinality=True)
        if len(m) != 16: continue
        fixed = {}
        for u, v in m:
            cands = [i for i, (h, a, _) in enumerate(games) if {h, a} == {u, v}]
            fixed[rng.choice(cands)] = 18
        free = [i for i in range(n) if i not in fixed]
        target = {w: 16 for w in FULL_WEEKS}
        rem = n - 16 * 8
        for k, w in enumerate(BYE_WEEKS):
            left = len(BYE_WEEKS) - k - 1
            lo = max(13, rem - left * 16); hi = min(16, rem - left * 13)
            target[w] = rng.randint(lo, hi) if lo <= hi else 13
            rem -= target[w]
        if rem: continue
        wk = dict(fixed); cap = Counter({18: 16})
        for i in free:
            w = rng.choice([x for x in target if cap[x] < target[x]])
            wk[i] = w; cap[w] += 1

        def conflicts(assign):
            occ = defaultdict(Counter)
            for i, w in assign.items():
                h, a, _ = games[i]; occ[w][h] += 1; occ[w][a] += 1
            return sum(v - 1 for w in occ for v in occ[w].values() if v > 1)

        cost = conflicts(wk)
        for it in range(iters):
            if cost == 0: break
            occ = defaultdict(Counter)
            for i, w in wk.items():
                h, a, _ = games[i]; occ[w][h] += 1; occ[w][a] += 1
            bad = [i for i in free if occ[wk[i]][games[i][0]] > 1 or occ[wk[i]][games[i][1]] > 1]
            if not bad: break
            i = rng.choice(bad); h, a, _ = games[i]
            best, bestc = None, 1e9
            for j in free:
                if j == i: continue
                w1, w2 = wk[i], wk[j]
                if w1 == w2: continue
                h2, a2, _ = games[j]
                d = 0
                d -= (occ[w1][h] > 1) + (occ[w1][a] > 1) + (occ[w2][h2] > 1) + (occ[w2][a2] > 1)
                d += (occ[w2][h] >= 1) + (occ[w2][a] >= 1) + (occ[w1][h2] >= 1) + (occ[w1][a2] >= 1)
                if d < bestc: bestc, best = d, j
                if d <= -2: break
            if best is None: break
            wk[i], wk[best] = wk[best], wk[i]
            cost = conflicts(wk)
        if cost: continue
        bye = {}; bad = False
        for t in teams:
            played = {wk[i] for i in wk if t in (games[i][0], games[i][1])}
            miss = [w for w in range(1, 19) if w not in played]
            if len(miss) != 1 or miss[0] not in BYE_WEEKS: bad = True; break
            bye[t] = miss[0]
        if bad: continue
        if not all(c % 2 == 0 for c in Counter(bye.values()).values()): continue

        def build_sc(assign):
            sc = defaultdict(dict)
            for i, w in assign.items():
                h, a, _ = games[i]; sc[h][w] = ('H', i); sc[a][w] = ('A', i)
            return sc

        def violations(assign):
            sc = build_sc(assign); cost = 0; guilty = set()
            for t in teams:
                run = []
                for w in range(1, 19):
                    e = sc[t].get(w)
                    if e and e[0] == 'A': run.append(e[1])
                    elif e and e[0] == 'H':
                        if len(run) > MAX_AWAY_RUN: cost += (len(run) - MAX_AWAY_RUN) ** 2; guilty |= set(run)
                        run = []
                if len(run) > MAX_AWAY_RUN: cost += (len(run) - MAX_AWAY_RUN) ** 2; guilty |= set(run)
            seen = defaultdict(list)
            for i, w in assign.items(): seen[tuple(sorted(games[i][:2]))].append((w, i))
            for v in seen.values():
                if len(v) == 2 and abs(v[0][0] - v[1][0]) < MIN_REMATCH:
                    cost += 10 * (MIN_REMATCH - abs(v[0][0] - v[1][0])); guilty |= {v[0][1], v[1][1]}
            return cost, guilty

        occ = defaultdict(set)
        for i, w in wk.items():
            h, a, _ = games[i]; occ[w] |= {h, a}
        cur, guilty = violations(wk)
        stall = 0; freeset = set(free)
        for it in range(6000):
            if cur == 0 or stall > 600: break
            pool = [i for i in guilty if i in freeset]
            if not pool: break
            i = rng.choice(pool); h1, a1, _ = games[i]; w1 = wk[i]
            moved = False
            order = free[:]; rng.shuffle(order)
            for j in order[:220]:
                w2 = wk[j]
                if w2 == w1: continue
                h2, a2, _ = games[j]
                if {h1, a1} & (occ[w2] - {h2, a2}): continue
                if {h2, a2} & (occ[w1] - {h1, a1}): continue
                wk[i], wk[j] = w2, w1
                new, ng = violations(wk)
                if new < cur:
                    cur, guilty = new, ng
                    occ[w1] = (occ[w1] - {h1, a1}) | {h2, a2}
                    occ[w2] = (occ[w2] - {h2, a2}) | {h1, a1}
                    moved = True; stall = 0
                    break
                wk[i], wk[j] = w1, w2
            if not moved: stall += 1
        return wk, bye
    return None, None


def division_ranks(league, standings):
    """1-4 finish within each division from the season runner's standings."""
    return {abbr: int(s['div_rank'] or 4) for abbr, s in standings.items()}


def new_season(league, rank, rng):
    """
    Build next year's slate onto the league: 272 (week, away, home, None,
    None) rows in league.schedule, byes in league.byes. rank: {team: 1-4}.
    """
    div = {a: t.division for a, t in league.teams.items()}
    games = build_matchups(league.year, div, rank)
    seed = int(rng.integers(1 << 30)) if rng is not None else 0
    wk, bye = assign_weeks(games, div, seed=seed)
    if wk is None:
        raise RuntimeError('schedule: no week assignment found')
    league.schedule = sorted([(wk[i], a, h, None, None) for i, (h, a, _) in enumerate(games)])
    league.byes = bye
    return league.schedule


def validate(league):
    """The rules the real slates obey. Returns a list of failures."""
    fails = []
    sched = league.schedule
    div = {a: t.division for a, t in league.teams.items()}
    pg = Counter()
    for wk, a, h, _, _ in sched: pg[h] += 1; pg[a] += 1
    if set(pg.values()) != {17}: fails.append('not every team plays 17')
    w18 = [(a, h) for wk, a, h, _, _ in sched if wk == 18]
    if len(w18) != 16 or not all(div[a] == div[h] for a, h in w18): fails.append('week 18 not all division')
    gpw = Counter(wk for wk, *_ in sched)
    if min(gpw.values()) < 13 or max(gpw.values()) > 16: fails.append(f'games per week {dict(gpw)}')
    byes = Counter(getattr(league, 'byes', {}).values())
    if any(w not in BYE_WEEKS for w in byes) or any(c % 2 for c in byes.values()): fails.append(f'byes {dict(byes)}')
    hg = Counter(h for _, _, h, _, _ in sched)
    if not all(v in (8, 9) for v in hg.values()): fails.append('home games not 8 or 9 each')
    return fails
