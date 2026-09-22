"""Third down under the microscope: what is called, at what depth, and what it
gains, by distance. Real third-down conversion by distance (nflverse 2020-25):
1-2 62, 3-4 52, 5-7 42, 8-10 31, 11+ 18. Real pass rate on 3rd: 1-2 ~48%,
3-4 ~78%, 5-7 ~88%, 8+ ~92%."""
import numpy as np, collections, sys

def run(weeks=8, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5) for t in teams}
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    rows = []
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            r = G.play_game(L[o[i]], L[o[i+1]], rng, P.resolve_play, co, cd, P.rate, home_state=ST[o[i]], away_state=ST[o[i+1]], week=wk+1)
            for _, d in r['drives']:
                down, togo, ytg = 1, 10, d.start
                for l in d.log:
                    if not isinstance(l, dict): continue
                    t = l.get('type')
                    if t == 'penalty':
                        y = l['yards']
                        if l['on_offense']: togo += y; ytg += y
                        else:
                            ytg -= y
                            if l['auto_first'] or togo - y <= 0: down, togo = 1, min(10, ytg)
                            else: togo -= y
                        continue
                    if t not in ('run','complete','incomplete','sack','scramble','drop','interception'): continue
                    y = l.get('yards') or 0
                    rows.append(dict(down=down, togo=togo, ytg=ytg, **l))
                    ytg -= y; togo -= y
                    if ytg <= 0: break
                    if togo <= 0: down, togo = 1, min(10, ytg)
                    else: down += 1
    def bucket(t): return '1-2' if t <= 2 else '3-4' if t <= 4 else '5-7' if t <= 7 else '8-10' if t <= 10 else '11+'
    real_pass = {'1-2': 48, '3-4': 78, '5-7': 88, '8-10': 92, '11+': 92}
    print(f'{len(rows)} plays\n  THIRD DOWN  bucket  n   pass%(real)  depth s/m/d on passes   conv   pass conv  run conv   comp%  air on comp  yds/att')
    for b in ('1-2','3-4','5-7','8-10','11+'):
        r3 = [r for r in rows if r['down'] == 3 and bucket(r['togo']) == b]
        if not r3: continue
        ps = [r for r in r3 if r.get('is_pass')]; rn = [r for r in r3 if not r.get('is_pass')]
        dm = collections.Counter(r.get('depth') for r in ps if r.get('depth'))
        tot = sum(dm.values()) or 1
        conv = lambda rs: np.mean([(r.get('yards') or 0) >= r['togo'] for r in rs])*100 if rs else float('nan')
        att = [r for r in ps if r['type'] != 'sack']
        comp = [r for r in att if r['type'] == 'complete']
        print(f'  {b:5s} {len(r3):5d}  {len(ps)/len(r3)*100:4.0f} ({real_pass[b]})     '
              f'{dm["short"]/tot*100:3.0f}/{dm["medium"]/tot*100:3.0f}/{dm["deep"]/tot*100:3.0f}          '
              f'{conv(r3):5.1f}  {conv(ps):5.1f}     {conv(rn):5.1f}    {len(comp)/max(len(att),1)*100:5.1f}  '
              f'{np.mean([r.get("air",0) for r in comp]) if comp else 0:5.1f}       {np.mean([r.get("yards",0) or 0 for r in att]) if att else 0:4.1f}')
    # second down: what's left for third
    s2 = [r for r in rows if r['down'] == 2]
    print(f'\n  SECOND DOWN: {len(s2)} plays, pass {np.mean([bool(r.get("is_pass")) for r in s2])*100:.0f}% (real ~55), yds/play {np.mean([r.get("yards") or 0 for r in s2]):.2f} (real 5.38), mean distance {np.mean([r["togo"] for r in s2]):.2f} (real ~8.2)')
    s1 = [r for r in rows if r['down'] == 1]
    print(f'  FIRST DOWN: pass {np.mean([bool(r.get("is_pass")) for r in s1])*100:.0f}% (real ~50), yds/play {np.mean([r.get("yards") or 0 for r in s1]):.2f} (real 5.60)')
    # how often is 3rd down reached and what distance
    t3 = [r for r in rows if r['down'] == 3]
    print(f'  third downs per 100 plays {len(t3)/len(rows)*100:.1f} (real ~19.5), mean distance {np.mean([r["togo"] for r in t3]):.2f} (real ~7.2)')

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
