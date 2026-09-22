"""Where drives die, and what extends them. Real: 3-and-out ~22% of drives,
3rd down conversion 39%, first downs by penalty ~1.7 a team a game, accepted
penalties ~11.9 a game (both clubs), yards per drive ~31."""
import numpy as np, collections, sys

def run(weeks=8, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5) for t in teams}
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    drives = []; ng = 0
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            r = G.play_game(L[o[i]], L[o[i+1]], rng, P.resolve_play, co, cd, P.rate, home_state=ST[o[i]], away_state=ST[o[i+1]], week=wk+1)
            drives += [d for _, d in r['drives']]; ng += 1
    n = len(drives)
    real_ends = [d for d in drives if d.result not in ('End of half', 'End of game')]
    three_out = sum(1 for d in real_ends if d.plays <= 3 and d.first_downs == 0 and d.result == 'Punt')
    print(f'{n} drives, {ng} games')
    print(f'  3-and-out (punt, no first down, <=3 plays): {three_out/len(real_ends)*100:.1f}% (real ~22)')
    print(f'  yards per drive {np.mean([d.start - max(0, d.yardline) for d in drives]):.1f} (real ~31)   plays {np.mean([d.plays for d in drives]):.2f}   first downs {np.mean([d.first_downs + (d.result=="Touchdown") for d in drives]):.2f}')
    # penalties
    pens = [l for d in drives for l in d.log if isinstance(l, dict) and l.get('type') == 'penalty']
    c = collections.Counter(l['penalty'] for l in pens)
    print(f'  penalties applied {len(pens)/ng:.2f} a game (real 11.9 accepted), on offence {np.mean([l["on_offense"] for l in pens])*100:.0f}%, auto first {sum(l["auto_first"] and not l["on_offense"] for l in pens)/ng:.2f} a game (real ~3.4 first downs by penalty)')
    print('   ', ', '.join(f'{k} {v/ng:.2f}' for k, v in c.most_common(8)))
    # third down by distance: replay downs from the log
    conv = collections.defaultdict(lambda: [0, 0]); third_togo = []
    ypd = collections.defaultdict(list)
    for d in drives:
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
            ypd[down].append(y)
            if down == 3:
                b = '1-2' if togo <= 2 else '3-4' if togo <= 4 else '5-7' if togo <= 7 else '8-10' if togo <= 10 else '11+'
                third_togo.append(togo)
                conv[b][1] += 1
                if y >= togo: conv[b][0] += 1
            ytg -= y; togo -= y
            if ytg <= 0: break
            if togo <= 0: down, togo = 1, min(10, ytg)
            else: down += 1
    real3 = {'1-2': 62, '3-4': 52, '5-7': 42, '8-10': 31, '11+': 18}
    tot = sum(v[1] for v in conv.values()); made = sum(v[0] for v in conv.values())
    print(f'  3rd down conversion {made/max(tot,1)*100:.1f}% (real ~39), mean 3rd-down distance {np.mean(third_togo):.2f} (real ~7.2)')
    for b in ('1-2','3-4','5-7','8-10','11+'):
        m, k = conv[b]
        print(f'    3rd & {b:5s} {k/max(tot,1)*100:5.1f}% of 3rd downs (real {[16,16,21,22,25][["1-2","3-4","5-7","8-10","11+"].index(b)]})   conv {m/max(k,1)*100:5.1f} (real {real3[b]})')
    print('  yards per play by down: ' + ', '.join(f'{d} {np.mean(v):.2f}' for d, v in sorted(ypd.items())) + '   (real 5.60 / 5.38 / 5.37)')

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
