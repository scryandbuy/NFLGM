"""Which link of the completion chain carries the club-to-club spread.
Wraps the resolver so every attempt's trace rides on its own outcome, then
groups by offensive and defending club."""
import numpy as np, collections, sys

def run(weeks=10, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coach = dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    ST = {t: G.TeamState(L[t], coach=coach) for t in teams}
    P.PASS_TRACE = []
    def resolve(*a, **k):
        n0 = len(P.PASS_TRACE)
        out = P.resolve_play(*a, **k)
        new = [t for t in P.PASS_TRACE[n0:] if t['path'] in ('man', 'zone')]
        if new: out['trace'] = new[-1]
        del P.PASS_TRACE[:]
        return out
    per_def = collections.defaultdict(list); per_off = collections.defaultdict(list)
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            h, a = o[i], o[i+1]
            r = G.play_game(L[h], L[a], rng, resolve, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk+1)
            for pos, d in r['drives']:
                off, deff = (h, a) if pos == 'home' else (a, h)
                for l in d.log:
                    if isinstance(l, dict) and l.get('trace'):
                        row = dict(l['trace'], comp=l['type'] == 'complete')
                        per_def[deff].append(row); per_off[off].append(row)
    P.PASS_TRACE = None
    def summar(per, label):
        print(f'\n  by {label} club: sd across clubs of the per-attempt mean  (n per club ~{np.mean([len(v) for v in per.values()]):.0f})')
        for k in ('p', 'comp', 'acc', 'pressure', 'dis', 'cmult', 'rmod'):
            v = np.array([np.mean([r[k] for r in rows]) for rows in per.values()])
            print(f'    {k:9s} mean {v.mean():.3f}  sd {v.std():.3f}  min {v.min():.3f} max {v.max():.3f}')
        for k, path in (('window', 'zone'), ('sep', 'man')):
            v = np.array([np.mean([r[k] for r in rows if r['path'] == path]) for rows in per.values()])
            print(f'    {k:9s} mean {v.mean():.3f}  sd {v.std():.3f}  min {v.min():.3f} max {v.max():.3f}   ({path})')
        v = np.array([np.mean([r['path'] == 'man' for r in rows]) for rows in per.values()])
        print(f'    man share mean {v.mean():.3f}  sd {v.std():.3f}')
    summar(per_def, 'DEFENDING'); summar(per_off, 'OFFENSIVE')

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
