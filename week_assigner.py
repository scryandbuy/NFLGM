import pandas as pd, random
from collections import defaultdict, Counter
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n)
from ortools.sat.python import cp_model

BYE_WEEKS    = list(range(5, 15))
FULL_WEEKS   = [1, 2, 3, 4, 15, 16, 17, 18]
MAX_AWAY_RUN = 3
MIN_REMATCH  = 2
W = list(range(1, 19))

def schedule(games, DIV, seed=0, time_limit=180):
    teams = sorted({t for h, a, _ in games for t in (h, a)})
    n = len(games)
    m = cp_model.CpModel()
    x = {(i, w): m.NewBoolVar(f'x{i}_{w}') for i in range(n) for w in W}

    # every game lands in exactly one week
    for i in range(n): m.AddExactlyOne(x[i, w] for w in W)

    # a team plays at most once per week
    tg = defaultdict(list)
    for i, (h, a, _) in enumerate(games): tg[h].append(i); tg[a].append(i)
    play = {}
    for t in teams:
        for w in W:
            p = m.NewBoolVar(f'p{t}_{w}')
            m.Add(sum(x[i, w] for i in tg[t]) == p)
            play[t, w] = p
        # exactly one bye, and it must fall in weeks 5-14
        m.Add(sum(play[t, w] for w in W) == 17)
        for w in FULL_WEEKS: m.Add(play[t, w] == 1)

    # week 18 is all division games; weeks are 13-16 games
    for w in W:
        lo, hi = (16, 16) if w in FULL_WEEKS else (13, 16)
        m.Add(sum(x[i, w] for i in range(n)) >= lo)
        m.Add(sum(x[i, w] for i in range(n)) <= hi)
    for i, (h, a, _) in enumerate(games):
        if DIV[h] != DIV[a]: m.Add(x[i, 18] == 0)

    # an even number of teams on bye each week
    for w in BYE_WEEKS:
        half = m.NewIntVar(0, 16, f'h{w}')
        m.Add(sum(x[i, w] for i in range(n)) == half)

    # the two meetings between a pair are >= MIN_REMATCH weeks apart
    pairs = defaultdict(list)
    for i, (h, a, _) in enumerate(games): pairs[tuple(sorted([h, a]))].append(i)
    for ids in pairs.values():
        if len(ids) == 2:
            i, j = ids
            for w in W:
                for v in W:
                    if abs(w - v) < MIN_REMATCH:
                        m.Add(x[i, w] + x[j, v] <= 1)

    # no more than MAX_AWAY_RUN consecutive road games
    away = {}
    for t in teams:
        for w in W:
            av = m.NewBoolVar(f'a{t}_{w}')
            m.Add(sum(x[i, w] for i in tg[t] if games[i][1] == t) == av)
            away[t, w] = av
        home = {}
        for w in W:
            hv = m.NewBoolVar(f'hm{t}_{w}')
            m.Add(sum(x[i, w] for i in tg[t] if games[i][0] == t) == hv)
            home[t, w] = hv
        for L in (MAX_AWAY_RUN + 1, MAX_AWAY_RUN + 2):
            for s0 in range(1, 20 - L):
                win = range(s0, s0 + L)
                # away games in this window <= 3, unless a home game breaks it up
                m.Add(sum(away[t, k] for k in win) <= MAX_AWAY_RUN + L * sum(home[t, k] for k in win))

    # division games are weighted late in reality but not stacked there:
    # real 2026 runs ~30% / 35% / 41% across weeks 1-6, 7-12, 13-18.
    divs = [i for i, (h, a, _) in enumerate(games) if DIV[h] == DIV[a]]
    bands = {'early': range(1, 7), 'mid': range(7, 13), 'late': range(13, 19)}
    counts = {}
    for name, rng_ in bands.items():
        c = m.NewIntVar(0, 96, f'dc_{name}')
        m.Add(c == sum(x[i, w] for i in divs for w in rng_))
        counts[name] = c
    m.Add(counts['early'] >= 24); m.Add(counts['early'] <= 32)
    m.Add(counts['mid']   >= 26); m.Add(counts['mid']   <= 34)
    m.Add(counts['late']  >= 34); m.Add(counts['late']  <= 42)

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.num_search_workers = 8
    s.parameters.random_seed = seed
    r = s.Solve(m)
    if r not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None, s.StatusName(r)
    return {i: next(w for w in W if s.Value(x[i, w])) for i in range(n)}, s.StatusName(r)

st = pd.read_csv('standings.csv', low_memory=False)
DIV = st[st.season == 2026].set_index('team').division.to_dict()
real = pd.read_csv('sched.csv', low_memory=False)
real = real[(real.season == 2026) & (real.game_type == 'REG')]
games = [(r.home_team, r.away_team, '') for _, r in real.iterrows()]

wk, status = schedule(games, DIV, seed=1, time_limit=240)
print('solver status:', status)
if not wk: raise SystemExit

out = pd.DataFrame([{'week': wk[i], 'home_team': h, 'away_team': a,
                     'div_game': DIV[h] == DIV[a]} for i, (h, a, _) in enumerate(games)]
                   ).sort_values(['week','home_team']).reset_index(drop=True)
out.to_csv(_p('schedule_generated_weeks.csv'), index=False)

sched_t = defaultdict(dict)
for _, r in out.iterrows():
    sched_t[r.home_team][r.week] = 'H'; sched_t[r.away_team][r.week] = 'A'
bye = {t: [w for w in W if w not in sched_t[t]][0] for t in DIV}

f = lambda c: 'ok  ' if c else 'FAIL'
print('\n=== VALIDATION ===')
pg = Counter()
for _, r in out.iterrows(): pg[r.home_team] += 1; pg[r.away_team] += 1
print(f'  [{f(set(pg.values())=={17})}] every team plays 17 games')
bw = Counter(bye.values())
print(f'  [{f(all(w in BYE_WEEKS for w in bw))}] byes only in weeks 5-14: {dict(sorted(bw.items()))}')
print(f'  [{f(all(c%2==0 for c in bw.values()))}] even teams on bye each week')
w18 = out[out.week == 18]
print(f'  [{f(len(w18)==16 and w18.div_game.all())}] week 18 = 16 division games')
gpw = out.groupby('week').size()
print(f'  [{f(gpw.between(13,16).all())}] games per week 13-16')
runs = Counter()
for t in DIV:
    run = best = 0
    for w in W:
        ha = sched_t[t].get(w)
        if ha == 'A': run += 1; best = max(best, run)
        elif ha == 'H': run = 0
    runs[best] += 1
print(f'  [{f(max(runs)<=MAX_AWAY_RUN)}] longest away streak {dict(sorted(runs.items()))}   real 2026 {{2:29, 3:3}}')
seen = defaultdict(list)
for _, r in out.iterrows(): seen[tuple(sorted([r.home_team, r.away_team]))].append(r.week)
gaps = [abs(v[0]-v[1]) for v in seen.values() if len(v) == 2]
print(f'  [{f(min(gaps)>=MIN_REMATCH)}] rematch gap min {min(gaps)} median {sorted(gaps)[len(gaps)//2]} max {max(gaps)}   real 2 / 9 / 16')
share = out.groupby(pd.cut(out.week,[0,6,12,18],labels=['w1-6','w7-12','w13-18'])).div_game.mean()
print('  division weighting ' + ', '.join(f'{k} {v:.0%}' for k,v in share.items()) + '   real 30% / 35% / 41%')
print('\n  games per week: ' + ' '.join(f'{w}:{n}' for w, n in gpw.items()))
