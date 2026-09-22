"""A club against itself. With identical rosters any pull-away or comeback is
MECHANISM, not the better team being better. Real second-half margin is
roughly independent of the first half (corr ~ -0.1, the trailer presses)."""
import numpy as np, copy, sys, collections

def run(n=160, seed=3, team='KC'):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league()
    A = L[team]; B = copy.deepcopy(A)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coach = dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    hm, sh, fin = [], [], []; rows = []
    for g in range(n):
        SA, SB = G.TeamState(A, coach=coach), G.TeamState(B, coach=coach)
        r = G.play_game(A, B, rng, P.resolve_play, co, cd, P.rate, home_state=SA, away_state=SB, week=1 + g % 17)
        half = [0, 0]; sc = {'home': 0, 'away': 0}
        for pos, d in r['drives']:
            other = 'away' if pos == 'home' else 'home'
            qq = min(4, int((G.GAME - d.clock) // G.QUARTER) + 1)
            sd = sc[pos] - sc[other]
            if qq >= 3 and d.result not in ('End of half', 'End of game'):
                plays = [l for l in d.log if isinstance(l, dict) and l.get('type') in ('run','complete','incomplete','sack','scramble','drop','interception')]
                rows.append(dict(sd=sd, res=d.result, pts=d.points, yards=d.start - max(0, d.yardline), plays=plays, start=d.start, clock=d.clock))
            if d.points > 0:
                sc[pos] += d.points
                if qq <= 2: half[0 if pos == 'home' else 1] += d.points
            elif d.points < 0:
                sc[other] += 2
                if qq <= 2: half[1 if pos == 'home' else 0] += 2
        hm.append(half[0] - half[1]); fin.append(r['home'] - r['away'])
    hm = np.array(hm); fin = np.array(fin); sh = fin - hm
    print(f'{n} mirror games ({team} v {team}). home wins {np.mean(fin>0)*100:.0f}%  mean |margin| {np.abs(fin).mean():.1f}  10+ {np.mean(np.abs(fin)>=10)*100:.0f}%')
    print(f'  corr(half margin, second-half margin) {np.corrcoef(hm, sh)[0,1]:+.3f}  (real ~ -0.1; a positive number is the leader pulling away by mechanism)')
    lead = np.abs(hm) >= 7
    print(f'  when one side leads by 7+ at the half ({lead.mean()*100:.0f}% of games): second half net for the LEADER {np.mean(np.sign(hm[lead]) * sh[lead]):+.2f} pts')
    def band(sd):
        return 'down 14+' if sd <= -14 else 'down 7-13' if sd <= -7 else 'down 1-6' if sd < 0 else 'tied' if sd == 0 else 'up 1-6' if sd < 7 else 'up 7-13' if sd < 14 else 'up 14+'
    print(f"\n  2nd-half drives     n   pts/dr  TD%   punt%  TO%  downs%  pass%  yds/dr  run ypc  pass y/db  comp%  int%")
    for b in ('down 14+','down 7-13','down 1-6','tied','up 1-6','up 7-13','up 14+'):
        rs = [r for r in rows if band(r['sd']) == b]
        if len(rs) < 20: continue
        n_ = len(rs); f = lambda k: sum(r['res']==k for r in rs)/n_*100
        pl = [l for r in rs for l in r['plays']]
        runs = [l for l in pl if l['type']=='run']; dbs = [l for l in pl if l['type'] in ('complete','incomplete','sack','drop','interception')]
        att = [l for l in dbs if l['type']!='sack']
        print(f"  {b:10s} {n_:5d}   {np.mean([r['pts'] for r in rs]):4.2f}  {f('Touchdown'):4.1f}  {f('Punt'):5.1f}  {f('Turnover'):4.1f}  {f('Turnover on downs'):5.1f}   {np.mean([bool(l.get('is_pass')) for l in pl])*100:3.0f}   {np.mean([r['yards'] for r in rs]):5.1f}   {np.mean([l['yards'] for l in runs]) if runs else 0:5.2f}    {np.mean([l.get('yards') or 0 for l in dbs]) if dbs else 0:5.2f}   {np.mean([l['type']=='complete' for l in att])*100 if att else 0:4.1f}  {np.mean([l['type']=='interception' for l in att])*100 if att else 0:4.2f}")

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 160)
