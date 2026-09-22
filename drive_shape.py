"""Where drives die. Reach-the-20 rate, scoring once there, TD once there, and
pass outcomes inside the 20 - the rows the register folds into one TD number."""
import numpy as np, collections, sys

def run(weeks=8, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(adjust_skill=float(np.clip(rng.normal(.55, .18), .1, .95)),
        adjust_willingness=float(np.clip(rng.normal(.55, .2), .1, .95)),
        man_rate=float(np.clip(rng.normal(.35, .12), .12, .62)),
        blitz_rate=float(np.clip(rng.normal(.133, .05), .05, .28)),
        travel_willingness=float(np.clip(rng.normal(.5, .22), .05, .95)),
        off_script_skill=float(np.clip(rng.normal(.5, .2), .1, .9))) for t in teams}
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    drives = []
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            r = G.play_game(L[o[i]], L[o[i+1]], rng, P.resolve_play, co, cd, P.rate,
                            home_state=ST[o[i]], away_state=ST[o[i+1]], week=wk+1)
            drives += [d for _, d in r['drives']]
    n = len(drives)
    rz = [d for d in drives if d.best <= 20]
    print(f'{n} drives; reach the 20: {len(rz)/n*100:.1f}% (real 35.5)')
    print(f'  once there: TD {sum(d.result=="Touchdown" for d in rz)/len(rz)*100:.1f} (real ~61 TD+FG total 61.0 score)  '
          f'FG {sum(d.result=="Field goal" for d in rz)/len(rz)*100:.1f}  '
          f'score {sum(d.result in ("Touchdown","Field goal") for d in rz)/len(rz)*100:.1f}')
    def td_from(d):
        last = [l for l in d.log if isinstance(l, dict) and l.get('touchdown')]
        return (last[-1].get('yards') or 0) if last else 0
    long_td = sum(1 for d in drives if d.result == 'Touchdown' and td_from(d) > 20)
    print(f'  TD scored from beyond the 20: {long_td/n*100:.2f}% of all drives (real ~2.4)')
    print(f'  drive start mean {np.mean([d.start for d in drives]):.1f} (yards to go)   result mix: ' +
          ', '.join(f'{k} {v/n*100:.1f}' for k, v in collections.Counter(d.result for d in drives).most_common()))
    # punting: where the ball comes down
    punts = [l for d in drives for l in d.log if isinstance(l, dict) and l.get('type') == 'punt' and not l.get('blocked')]
    tb = [l for l in punts if l.get('touchback')]
    live = [l for l in punts if not l.get('touchback')]
    print(f'\n  PUNTS {len(punts)}: net {np.mean([l["net"] for l in punts if l.get("net") is not None]):.1f} (real 41.6), gross {np.mean([l["gross"] for l in punts if l.get("gross")]):.1f} (real 47.2), '
          f'touchback {len(tb)/len(punts)*100:.1f}% (real ~7.5), pooch {np.mean([bool(l.get("pooch")) for l in punts])*100:.1f}%, '
          f'inside 20: {np.mean([l.get("land", 50) < 20 for l in live])*100:.1f}% (real ~38), returned {np.mean([l.get("how")=="return" for l in punts])*100:.1f}% (real ~45)')
    print(f'  drive starts inside own 10: {np.mean([d.start >= 91 for d in drives])*100:.1f}% (real a few %), mean yards to go {np.mean([d.start for d in drives]):.1f} (real ~70.5)')
    # backed up: what the coach does with the ball inside his own 10
    bp = bs = bd = 0; bruns = 0
    for d in drives:
        ytg = d.start
        for l in d.log:
            if not isinstance(l, dict): continue
            t = l.get('type')
            if t in ('run','complete','incomplete','sack','scramble','drop','interception'):
                if ytg >= 91:
                    if t == 'run': bruns += 1
                    else:
                        bd += 1
                        if t == 'sack': bs += 1
                ytg -= (l.get('yards') or 0)
    tot = bruns + bd
    print(f'\n  BACKED UP inside own 10: {tot} snaps, pass {bd/max(tot,1)*100:.1f}% (real 52.2), '
          f'sack {bs/max(bd,1)*100:.2f}% of dropbacks (real 3.9), '
          f'safeties {sum(d.result=="Safety" for d in drives)/n*100:.2f}% of drives (real 0.28)')
    # pass outcomes by field zone
    zones = [(0, 10, 'inside 10'), (10, 20, '11-20'), (20, 50, '21-50'), (50, 101, 'own half')]
    print('\n  passing by field zone: att  comp%  int%  sack%  ypa')
    for lo, hi, lab in zones:
        rows = []
        for d in drives:
            ytg = d.start
            for l in d.log:
                if not isinstance(l, dict): continue
                t = l.get('type')
                if t in ('complete','incomplete','drop','interception','sack'):
                    if lo < ytg <= hi: rows.append(l)
                if t in ('run','complete','incomplete','sack','scramble','drop','interception'):
                    ytg -= (l.get('yards') or 0)
        att = [l for l in rows if l['type'] != 'sack']
        if not att: continue
        c = sum(l['type']=='complete' for l in att)/len(att)*100
        it = sum(l['type']=='interception' for l in att)/len(att)*100
        sk = (len(rows)-len(att))/max(len(rows),1)*100
        ypa = sum(l.get('yards',0) for l in att if l['type']=='complete')/len(att)
        print(f'  {lab:10s} {len(att):5d}  {c:5.1f}  {it:4.2f}  {sk:5.2f}  {ypa:4.2f}')

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
