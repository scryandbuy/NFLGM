"""How far apart the clubs are, component by component, over a full season.
Real club-season sds (nflverse 2020-25, one team-season each, so they contain
the same 17-game sampling noise as ours):
  offence: comp% 3.0  int% 0.7  yds/dropback 0.65  sack% 1.4  ypc 0.40  pts 3.9
  defence: comp% 2.5  int% 0.6  yds/dropback 0.55  sack% 1.3  ypc 0.35  pts 3.4"""
import numpy as np, collections, sys

REAL = {'off': dict(comp=3.0, int=0.7, ypd=0.65, sack=1.4, ypc=0.40, pts=3.9, to=2.0),
        'def': dict(comp=2.5, int=0.6, ypd=0.55, sack=1.3, ypc=0.35, pts=3.4, to=2.0)}

def run(weeks=17, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coach = dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    ST = {t: G.TeamState(L[t], coach=coach) for t in teams}
    C = {s: collections.defaultdict(collections.Counter) for s in ('off', 'def')}
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            h, a = o[i], o[i+1]
            r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk+1)
            C['off'][h]['pts'] += r['home']; C['off'][a]['pts'] += r['away']
            C['def'][h]['pts'] += r['away']; C['def'][a]['pts'] += r['home']
            for t in (h, a): C['off'][t]['g'] += 1; C['def'][t]['g'] += 1
            for pos, d in r['drives']:
                t, u = (h, a) if pos == 'home' else (a, h)
                for side, tm in (('off', t), ('def', u)):
                    c = C[side][tm]; c['drives'] += 1; c['to'] += d.result == 'Turnover'
                    for l in d.log:
                        if not isinstance(l, dict): continue
                        ty = l.get('type')
                        if ty in ('complete','incomplete','drop','interception','sack'):
                            c['db'] += 1; c['dby'] += l.get('yards') or 0
                            if ty == 'sack': c['sack'] += 1
                            else:
                                c['att'] += 1; c['comp'] += ty == 'complete'; c['int'] += ty == 'interception'
                        elif ty == 'run':
                            c['rush'] += 1; c['ry'] += l.get('yards') or 0
    for side in ('off', 'def'):
        rows = {}
        for t, c in C[side].items():
            rows[t] = dict(comp=c['comp']/c['att']*100, int=c['int']/c['att']*100, ypd=c['dby']/c['db'],
                           sack=c['sack']/c['db']*100, ypc=c['ry']/c['rush'], pts=c['pts']/c['g'], to=c['to']/c['drives']*100)
        print(f"\n  {side.upper():3s}   metric   club sd   real sd   ratio    min   max")
        for k in ('comp','int','ypd','sack','ypc','to','pts'):
            v = np.array([r[k] for r in rows.values()])
            print(f"        {k:6s}   {v.std():6.2f}   {REAL[side][k]:6.2f}   {v.std()/REAL[side][k]:5.2f}   {v.min():5.2f} {v.max():5.2f}")
    return C

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 17)
