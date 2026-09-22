"""Several seasons of earning and best-case spending, to see how men develop.

Every offseason each player spends everything he earned the best way he can
(most overall per XP), then the real offseason runs: regression, retirement,
contracts, market, cut-down. There is no draft yet, so the league thins each
year; the point here is the trajectory of the men who are in it.
Best-case spending is the ceiling, not the AI's behaviour, which is not built."""
import numpy as np, collections, sys, copy
import league as LG, franchise as FR, xp as XP, xp_cost_solve as CS, targets as TG

GROUP = {'QB': 'QB', 'HB': 'HB', 'WR': 'WR', 'TE': 'TE', 'LT': 'OL', 'RT': 'OL', 'LG': 'OL', 'RG': 'OL', 'C': 'OL',
         'LEDG': 'EDGE', 'REDG': 'EDGE', 'DT': 'DT', 'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'CB', 'FS': 'S', 'SS': 'S'}

def spend_all(L):
    n = 0; gains = []
    for p in L.players.values():
        if p.retired or p.xp <= 0: continue
        g = CS.best_spend_inplace(p)
        if g: gains.append(g); n += 1
    return n, gains

if __name__ == '__main__':
    years = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    F = FR.Franchise(seed=2026)
    L = F.L
    # snapshot everyone at the start
    start = {p.pid: (p.ovr, p.age, p.pos, p.dev) for p in L.players.values()}
    track = collections.defaultdict(list)     # pid -> [ovr by year]
    dist = []
    for pid, (o, a, pos, dev) in start.items(): track[pid].append(o)
    for yr in range(years):
        log = F.play_year(report=False)
        # spend BEFORE regression would be the natural order, but play_year
        # runs regression inside; so spend here, after the offseason, on the
        # XP earned this season (regression has already taken its share)
        n, gains = spend_all(L)
        alive = [p for p in L.players.values() if not p.retired]
        ov = np.array([p.ovr for p in alive])
        dist.append(dict(year=L.year, n=len(alive), mean=ov.mean(), p90=np.mean(ov >= 90) * 100, p95=np.mean(ov >= 95) * 100, p99=np.mean(ov >= 98.5) * 100, spent=n, gain=np.mean(gains) if gains else 0))
        for p in alive: track[p.pid].append(p.ovr)
        d = dist[-1]
        print(f"  {d['year']}: {d['n']} players, mean ovr {d['mean']:.1f}, 90+ {d['p90']:.1f}%, 95+ {d['p95']:.1f}%, 99 {d['p99']:.2f}%, {d['spent']} spent (mean gain {d['gain']:.2f})")
    # trajectories by group and starting age
    print(f'\n  NET CHANGE IN OVERALL over {years} seasons (spend minus regression), men still in the league, by group and starting age')
    bands = [(20, 24, '20-23'), (24, 27, '24-26'), (27, 30, '27-29'), (30, 33, '30-32'), (33, 40, '33+')]
    print(f'  {"group":5s}' + ''.join(f'{b[2]:>14s}' for b in bands) + '    (mean / top quarter, n)')
    for grp in ('QB', 'HB', 'WR', 'TE', 'OL', 'EDGE', 'DT', 'LB', 'CB', 'S'):
        row = ''
        for lo, hi, lab in bands:
            ch = sorted(track[pid][-1] - track[pid][0] for pid, (o, a, pos, dev) in start.items()
                        if GROUP.get(pos) == grp and lo <= a < hi and len(track[pid]) == years + 1 and o >= 70)
            if len(ch) < 3: row += f'{"-":>14s}'; continue
            row += f'{np.mean(ch):+5.1f}/{ch[int(len(ch)*0.75)]:+5.1f}({len(ch):3d})'
        print(f'  {grp:5s}{row}')
    # who reached the top
    top = sorted([p for p in L.players.values() if not p.retired], key=lambda p: -p.ovr)[:8]
    print('\n  top of the league now:')
    for p in top:
        o0 = start.get(p.pid, (None,))[0]
        print(f'    {p.name:22s} {p.pos:4s} age {p.age:.0f} ovr {p.ovr:.1f} (was {o0:.1f}) dev {p.dev} bought {XP.points_bought(p)} pts')
    # dev tier split
    print('\n  net change by dev tier (all groups, started 70+): ' + ', '.join(
        f'{dev} {np.mean([track[pid][-1]-track[pid][0] for pid,(o,a,pos,d) in start.items() if d==dev and len(track[pid])==years+1 and o>=70]):+.1f}'
        for dev in ('normal', 'star', 'superstar', 'xfactor')))
