"""The shape of the final margin. Real 2020-25: mean |margin| 11.1, 10+ in
44.7% of games, 17+ in 26.1%, decided by 3 or fewer ~21%, sd of margin ~13.9,
sd across clubs of season point differential per game ~6.2, so the single-
game noise around the true gap is sd ~12.4. Ties 0.29%, overtime 6.2%."""
import numpy as np, collections, sys

def run(weeks=17, seed=2026):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(adjust_skill=float(np.clip(rng.normal(.55,.18),.1,.95)), adjust_willingness=float(np.clip(rng.normal(.55,.2),.1,.95)), man_rate=float(np.clip(rng.normal(.35,.12),.12,.62)), blitz_rate=float(np.clip(rng.normal(.133,.05),.05,.28)), travel_willingness=float(np.clip(rng.normal(.5,.22),.05,.95)), off_script_skill=float(np.clip(rng.normal(.5,.2),.1,.9))) for t in teams}
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    games = []
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            h, a = o[i], o[i+1]
            r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk+1)
            # score by quarter and at the half
            q = {1: [0,0], 2: [0,0], 3: [0,0], 4: [0,0]}
            half = [0, 0]
            for pos, d in r['drives']:
                if d.points == 0: continue
                qq = min(4, int((G.GAME - d.clock) // G.QUARTER) + 1) if d.clock >= 0 else 4
                side = 0 if pos == 'home' else 1
                pts = d.points if d.points > 0 else 0
                if d.points < 0: side = 1 - side; pts = 2
                if qq <= 4:
                    q[qq][side] += pts
                    if qq <= 2: half[side] += pts
            games.append(dict(h=h, a=a, hs=r['home'], as_=r['away'], half=half, q=q, ot=r['overtime']))
    m = np.array([g['hs'] - g['as_'] for g in games]); am = np.abs(m)
    print(f'{len(games)} games. mean |margin| {am.mean():.2f} (real 11.1)   sd {m.std():.2f} (real ~13.9)   '
          f'10+ {np.mean(am>=10)*100:.1f} (44.7)   17+ {np.mean(am>=17)*100:.1f} (26.1)   <=3 {np.mean((am<=3)&(am>0))*100:.1f} (~21)   '
          f'ties {np.mean(am==0)*100:.2f} (0.29)   OT {np.mean([g["ot"] is not None for g in games])*100:.1f} (6.2)')
    # club strength spread
    diff = collections.defaultdict(list)
    for g in games:
        diff[g['h']].append(g['hs'] - g['as_']); diff[g['a']].append(g['as_'] - g['hs'])
    club = np.array([np.mean(v) for v in diff.values()])
    print(f'  sd across clubs of point differential per game {club.std():.2f} (real ~6.2); best {club.max():+.1f} worst {club.min():+.1f} (real roughly +12 / -11)')
    # noise around the gap: margin minus the two clubs' season means
    resid = np.array([(g['hs']-g['as_']) - (np.mean(diff[g['h']]) - np.mean(diff[g['a']]))/2 for g in games])
    print(f'  single-game noise sd {resid.std():.2f} (real ~12.4)')
    # halftime and second half
    hm = np.array([g['half'][0] - g['half'][1] for g in games]); sh = m - hm
    print(f'  |margin| at the half {np.abs(hm).mean():.2f}   second-half margin sd {sh.std():.2f}   corr(half margin, 2nd-half margin) {np.corrcoef(hm, sh)[0,1]:+.3f} (real slightly negative, ~-0.1)')
    # scoring by quarter
    qs = {k: np.mean([sum(g['q'][k]) for g in games]) for k in (1,2,3,4)}
    print('  points by quarter (both clubs): ' + '  '.join(f'Q{k} {v:.1f}' for k, v in qs.items()) + '   (real ~ 9.1 / 13.9 / 9.8 / 13.0)')
    # does the team trailing at the half come back?
    trail = [g for g in games if abs(g['half'][0]-g['half'][1]) >= 10]
    cb = [g for g in trail if np.sign(g['hs']-g['as_']) != np.sign(g['half'][0]-g['half'][1]) and g['hs'] != g['as_']]
    print(f'  down 10+ at the half: {len(trail)/len(games)*100:.1f}% of games, comeback wins {len(cb)/max(len(trail),1)*100:.1f}% (real ~10-12% of those)')
    # 4th quarter: does the trailing team outscore?
    late = []
    for g in games:
        m3 = sum(g['q'][k][0] - g['q'][k][1] for k in (1,2,3))
        if abs(m3) >= 7:
            lead = 0 if m3 > 0 else 1
            late.append(g['q'][4][1-lead] - g['q'][4][lead])
    print(f'  trailing by 7+ entering Q4: Q4 net for the trailer {np.mean(late):+.2f} pts (real about +1.5 to +2)')
    return games

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 17)


def by_script(weeks=10, seed=2026):
    """Second-half drives split by the score when they started."""
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
            h, a = o[i], o[i+1]
            r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk+1)
            sc = {'home': 0, 'away': 0}
            for pos, d in r['drives']:
                other = 'away' if pos == 'home' else 'home'
                sd = sc[pos] - sc[other]
                qq = min(4, int((G.GAME - (d.clock + 0)) // G.QUARTER) + 1)
                plays = [l for l in d.log if isinstance(l, dict) and l.get('type') in ('run','complete','incomplete','sack','scramble','drop','interception')]
                rows.append(dict(sd=sd, q=qq, res=d.result, pts=d.points, plays=len(plays), start=d.start,
                                 is_pass=np.mean([bool(l.get('is_pass')) for l in plays]) if plays else np.nan,
                                 yards=d.start - max(0, d.yardline),
                                 secs=None))
                if d.points > 0: sc[pos] += d.points
                elif d.points < 0: sc[other] += 2
    def band(sd):
        return 'down 14+' if sd <= -14 else 'down 7-13' if sd <= -7 else 'down 1-6' if sd < 0 else 'tied' if sd == 0 else 'up 1-6' if sd < 7 else 'up 7-13' if sd < 14 else 'up 14+'
    print(f"\n  SECOND-HALF DRIVES by score at the start   n   pts/drive  TD%   FG%  punt%  TO%  downs%  pass%  yds/drive  start(yds to go)")
    for b in ('down 14+','down 7-13','down 1-6','tied','up 1-6','up 7-13','up 14+'):
        rs = [r for r in rows if r['q'] >= 3 and band(r['sd']) == b and r['res'] not in ('End of half','End of game')]
        if not rs: continue
        n = len(rs)
        f = lambda k: sum(r['res']==k for r in rs)/n*100
        print(f"  {b:10s} {n:5d}   {np.mean([r['pts'] for r in rs]):5.2f}   {f('Touchdown'):4.1f}  {f('Field goal'):4.1f}  {f('Punt'):5.1f}  {f('Turnover'):4.1f}  {f('Turnover on downs'):5.1f}   {np.nanmean([r['is_pass'] for r in rs])*100:4.0f}   {np.mean([r['yards'] for r in rs]):5.1f}      {np.mean([r['start'] for r in rs]):5.1f}")
    print('  (real: points per drive barely moves with score; trailing teams throw ~70% and turn it over a little more, leaders punt more)')

if __name__ == '__main__' and len(sys.argv) > 2:
    by_script(int(sys.argv[1]))
