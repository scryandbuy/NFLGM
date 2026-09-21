import pandas as pd, random, networkx as nx
from collections import defaultdict, Counter

BYE_WEEKS     = list(range(5, 15))
FULL_WEEKS    = [1, 2, 3, 4, 15, 16, 17, 18]     # every team plays; 16 games each
MAX_AWAY_RUN  = 3
MIN_REMATCH   = 2

def solve(games, DIV, seed=0, restarts=30, iters=60000):
    """
    Each team plays 17 games across 18 weeks => exactly one bye.
    So the schedule IS an 18-colouring of the game graph where every team
    misses exactly one colour. Eight colour classes must be full (16 games)
    to fill weeks 1-4, 15-17 and 18; the other ten carry the byes.
    Solved as min-conflicts local search over the whole season at once.
    """
    rng = random.Random(seed)
    n = len(games)
    teams = sorted({t for h, a, _ in games for t in (h, a)})

    for attempt in range(restarts):
        # week 18 is 16 division games covering all 32 teams: fix it up front
        G = nx.Graph()
        for i, (h, a, _) in enumerate(games):
            if DIV[h] == DIV[a]: G.add_edge(h, a, weight=rng.random(), idx=i)
        m = nx.max_weight_matching(G, maxcardinality=True)
        if len(m) != 16: continue
        fixed = {}
        for u, v in m:
            cands = [i for i, (h, a, _) in enumerate(games) if {h, a} == {u, v}]
            fixed[rng.choice(cands)] = 18

        free = [i for i in range(n) if i not in fixed]
        target = {w: 16 for w in FULL_WEEKS}
        rem = n - 16 * 8
        for k, w in enumerate(BYE_WEEKS):     # 144 games over weeks 5-14
            left = len(BYE_WEEKS) - k - 1
            lo = max(13, rem - left * 16)
            hi = min(16, rem - left * 13)
            target[w] = rng.randint(lo, hi) if lo <= hi else 13
            rem -= target[w]
        if rem: continue

        wk = dict(fixed)
        cap = Counter({18: 16})
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
            bad = [i for i in free
                   if occ[wk[i]][games[i][0]] > 1 or occ[wk[i]][games[i][1]] > 1]
            if not bad: break
            i = rng.choice(bad)
            h, a, _ = games[i]
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
        bye = {}
        bad = False
        for t in teams:
            played = {wk[i] for i in wk if t in (games[i][0], games[i][1])}
            miss = [w for w in range(1, 19) if w not in played]
            if len(miss) != 1 or miss[0] not in BYE_WEEKS: bad = True; break
            bye[t] = miss[0]
        if bad: continue
        if not all(c % 2 == 0 for c in Counter(bye.values()).values()): continue

        # ---- phase 2: violation-directed repair. Find the games actually causing a
        #      long road trip or a too-close rematch, and try to move those specifically.
        def build_sc(assign):
            sc = defaultdict(dict)
            for i, w in assign.items():
                h, a, _ = games[i]; sc[h][w] = ('H', i); sc[a][w] = ('A', i)
            return sc

        def violations(assign):
            """returns (cost, set_of_game_indices_involved)"""
            sc = build_sc(assign); cost = 0; guilty = set()
            for t in teams:
                run = []
                for w in range(1, 19):
                    e = sc[t].get(w)
                    if e and e[0] == 'A': run.append(e[1])
                    elif e and e[0] == 'H':
                        if len(run) > MAX_AWAY_RUN: cost += (len(run)-MAX_AWAY_RUN)**2; guilty |= set(run)
                        run = []
                if len(run) > MAX_AWAY_RUN: cost += (len(run)-MAX_AWAY_RUN)**2; guilty |= set(run)
            seen = defaultdict(list)
            for i, w in assign.items(): seen[tuple(sorted(games[i][:2]))].append((w, i))
            for v in seen.values():
                if len(v) == 2 and abs(v[0][0]-v[1][0]) < MIN_REMATCH:
                    cost += 10*(MIN_REMATCH - abs(v[0][0]-v[1][0])); guilty |= {v[0][1], v[1][1]}
            return cost, guilty

        occ = defaultdict(set)
        for i, w in wk.items():
            h, a, _ = games[i]; occ[w] |= {h, a}

        cur, guilty = violations(wk)
        stall = 0
        for it in range(6000):
            if cur == 0 or stall > 600: break
            pool = [i for i in guilty if i in set(free)]
            if not pool: break
            i = rng.choice(pool)
            h1, a1, _ = games[i]; w1 = wk[i]
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
        return wk, bye, attempt + 1
    return None, None, restarts

st = pd.read_csv('standings.csv', low_memory=False)
DIV = st[st.season == 2026].set_index('team').division.to_dict()
real = pd.read_csv('sched.csv', low_memory=False)
real = real[(real.season == 2026) & (real.game_type == 'REG')]
games = [(r.home_team, r.away_team, '') for _, r in real.iterrows()]

wk, bye, tries = solve(games, DIV, seed=5)
print('FAILED' if not wk else f'solved in {tries} restart(s)')
if not wk: raise SystemExit

out = pd.DataFrame([{'week': wk[i], 'home_team': h, 'away_team': a,
                     'div_game': DIV[h] == DIV[a]} for i, (h, a, _) in enumerate(games)]
                   ).sort_values(['week','home_team']).reset_index(drop=True)
out.to_csv(_p('schedule_generated_weeks.csv'), index=False)

f = lambda c: 'ok  ' if c else 'FAIL'
print('\n=== VALIDATION against rules derived from real schedules ===')
pg = Counter()
for _, r in out.iterrows(): pg[r.home_team] += 1; pg[r.away_team] += 1
print(f'  [{f(set(pg.values())=={17})}] every team plays 17 games')
bw = Counter(bye.values())
print(f'  [{f(all(w in BYE_WEEKS for w in bw))}] byes only in weeks 5-14: {dict(sorted(bw.items()))}')
print(f'  [{f(all(c%2==0 for c in bw.values()))}] even number of teams on bye each week')
w18 = out[out.week == 18]
print(f'  [{f(len(w18)==16 and w18.div_game.all())}] week 18 is 16 division games')
gpw = out.groupby('week').size()
print(f'  [{f(gpw.between(13,16).all())}] games per week 13-16: min {gpw.min()} max {gpw.max()}')
sched = defaultdict(dict)
for _, r in out.iterrows():
    sched[r.home_team][r.week] = 'H'; sched[r.away_team][r.week] = 'A'
runs = Counter()
for t in DIV:
    run = best = 0
    for w in range(1, 19):
        ha = sched[t].get(w)
        if ha == 'A': run += 1; best = max(best, run)
        elif ha == 'H': run = 0
    runs[best] += 1
print(f'  [{f(max(runs)<=MAX_AWAY_RUN)}] longest away streak {dict(sorted(runs.items()))}   real 2026 {{2:29, 3:3}}')
seen = defaultdict(list)
for _, r in out.iterrows(): seen[tuple(sorted([r.home_team, r.away_team]))].append(r.week)
gaps = [abs(v[0]-v[1]) for v in seen.values() if len(v) == 2]
print(f'  [{f(min(gaps)>=MIN_REMATCH)}] rematch gap min {min(gaps)} median {sorted(gaps)[len(gaps)//2]} max {max(gaps)}   real 2 / 9 / 16')
share = out.groupby(pd.cut(out.week,[0,6,12,18],labels=['w1-6','w7-12','w13-18'])).div_game.mean()
print(f'  division weighting ' + ', '.join(f'{k} {v:.0%}' for k,v in share.items()) + '   real 30% / 35% / 41%')
print('\n  games per week: ' + ' '.join(f'{w}:{n}' for w, n in gpw.items()))
