"""Do the leans change OUTCOMES? A club against its own mirror; one side gets an
identity lean, the other the neutral man. Points and results over n games."""
import numpy as np, copy, collections, sys
import rosters as R, game as G, plays as P, schemes as S, season as SN, gm_engine as GE

def run(n=40, team='KC', seed=3):
    rng = np.random.default_rng(seed); L = R.load_league(); A = L[team]; B = copy.deepcopy(A)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    base = GE.GM(name='neutral', board_trust=.5, aggression=.5, patience=.5)
    configs = {
        'neutral vs neutral': {},
        'pass-heavy (.85)': dict(pass_lean=.85), 'run-heavy (.15)': dict(pass_lean=.15),
        'play-action .9': dict(play_action=.9), 'deep ball .9': dict(deep=.9),
        'blitz 1.0 (Flores)': dict(blitz=1.0), 'blitz .05 (Graham)': dict(blitz=.05),
        'man .9 (Anarumo)': dict(coverage=.9), 'zone .02 (Macdonald)': dict(coverage=.02),
        'two-high .9': dict(shell=.9), 'fourth-down .95': dict(fourth_down=.95),
    }
    rows = []
    for name, over in configs.items():
        gm = copy.deepcopy(base)
        for k, v in over.items(): setattr(gm, k, v)
        ca, cb = SN.make_coach(gm), SN.make_coach(base)
        pts = []; wins = 0; sacks_for = 0; sacks_against = 0; plays = 0; passes = 0; ints_forced = 0
        for g in range(n):
            SA, SB = G.TeamState(A, coach=ca), G.TeamState(B, coach=cb)
            home = g % 2 == 0
            r = G.play_game(A if home else B, B if home else A, rng, P.resolve_play, co, cd, P.rate,
                            home_state=SA if home else SB, away_state=SB if home else SA, week=1)
            mine, theirs = (r['home'], r['away']) if home else (r['away'], r['home'])
            pts.append((mine, theirs)); wins += mine > theirs
            for pos, d in r['drives']:
                is_mine = (pos == 'home') == home
                for l in d.log:
                    if not isinstance(l, dict): continue
                    t = l.get('type')
                    if is_mine and t in ('run','complete','incomplete','sack','scramble','drop','interception'):
                        plays += 1; passes += bool(l.get('is_pass'))
                    if t == 'sack': (sacks_against if is_mine else 0); 
                    if t == 'sack' and not is_mine: sacks_for += 1
                    if t == 'sack' and is_mine: sacks_against += 1
                    if t == 'interception' and not is_mine: ints_forced += 1
        pf, pa = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
        rows.append((name, pf, pa, wins / n, passes / max(1, plays), sacks_for / n, ints_forced / n))
        print(f"  {name:22s}  for {pf:5.1f}  against {pa:5.1f}  net {pf-pa:+5.1f}  win {wins/n*100:3.0f}%  pass rate {passes/max(1,plays)*100:3.0f}%  sacks made {sacks_for/n:.1f}  INTs {ints_forced/n:.1f}", flush=True)
    return rows

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
