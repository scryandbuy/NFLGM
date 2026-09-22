"""One season at a time, state pickled between runs so nothing is lost to a
response limit. Each run: play a year, every man spends what he earned the
best way he can (best-case ceiling, not the AI), print the season and the
trajectory so far, save."""
import numpy as np, collections, sys, pickle, os
import franchise as FR, xp as XP, xp_cost_solve as CS

STATE = '/home/claude/xp_state.pkl'
GROUP = {'QB': 'QB', 'HB': 'HB', 'WR': 'WR', 'TE': 'TE', 'LT': 'OL', 'RT': 'OL', 'LG': 'OL', 'RG': 'OL', 'C': 'OL',
         'LEDG': 'EDGE', 'REDG': 'EDGE', 'DT': 'DT', 'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'CB', 'FS': 'S', 'SS': 'S'}

if os.path.exists(STATE):
    S = pickle.load(open(STATE, 'rb'))
else:
    F = FR.Franchise(seed=2026)
    S = dict(F=F, start={p.pid: (p.ovr, p.age, p.pos, p.dev) for p in F.L.players.values()},
             track={p.pid: [p.ovr] for p in F.L.players.values()}, years=0, dist=[])
F, L = S['F'], S['F'].L
F.play_year(report=False)
n = 0; gains = []
for p in L.players.values():
    if p.retired or p.xp <= 0: continue
    g = CS.best_spend_inplace(p)
    if g: gains.append(g); n += 1
S['years'] += 1
alive = [p for p in L.players.values() if not p.retired]
ov = np.array([p.ovr for p in alive])
for p in alive: S['track'].setdefault(p.pid, []).append(p.ovr)
line = f"season {S['years']} ({L.year}): {len(alive)} players, mean ovr {ov.mean():.1f}, 90+ {np.mean(ov>=90)*100:.1f}%, 95+ {np.mean(ov>=95)*100:.1f}%, 99 {np.mean(ov>=98.5)*100:.2f}%, {n} spent, mean gain {np.mean(gains) if gains else 0:.2f}, top gain {max(gains) if gains else 0:.1f}"
S['dist'].append(line)
print('\n'.join(S['dist']))
yrs = S['years']; start, track = S['start'], S['track']
print(f'\n  NET CHANGE IN OVERALL over {yrs} season(s), spend minus regression, men still in the league who started 70+')
bands = [(20, 24, '20-23'), (24, 27, '24-26'), (27, 30, '27-29'), (30, 33, '30-32'), (33, 40, '33+')]
print(f'  {"":5s}' + ''.join(f'{b[2]:>15s}' for b in bands) + '    mean/top-quarter(n)')
for grp in ('QB', 'HB', 'WR', 'TE', 'OL', 'EDGE', 'DT', 'LB', 'CB', 'S'):
    row = ''
    for lo, hi, lab in bands:
        ch = sorted(track[pid][-1] - track[pid][0] for pid, (o, a, pos, dev) in start.items()
                    if GROUP.get(pos) == grp and lo <= a < hi and len(track[pid]) == yrs + 1 and o >= 70)
        row += f'{"-":>15s}' if len(ch) < 3 else f'{np.mean(ch):+5.1f}/{ch[int(len(ch)*0.75)]:+5.1f}({len(ch):3d})'
    print(f'  {grp:5s}{row}')
print('\n  by dev tier: ' + ', '.join(f'{dev} {np.mean([track[pid][-1]-track[pid][0] for pid,(o,a,pos,d) in start.items() if d==dev and len(track[pid])==yrs+1 and o>=70]):+.1f}' for dev in ('normal','star','superstar','xfactor')))
top = sorted(alive, key=lambda p: -p.ovr)[:6]
print('\n  top of the league now:')
for p in top:
    o0 = start.get(p.pid, (p.ovr,))[0]
    print(f'    {p.name:22s} {p.pos:4s} age {p.age:.0f} ovr {p.ovr:.1f} (was {o0:.1f}) {p.dev}, bought {XP.points_bought(p)} pts')
pickle.dump(S, open(STATE, 'wb'))
