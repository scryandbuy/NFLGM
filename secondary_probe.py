"""PD concentration, block win rates, CB3 snap share and corner travel, from
a bank of games between real clubs. Reals: PD leader ~24 over 17 games (top
corner ~1.4/game); PBWR 91%, RBWR 71%; third corner ~57% of snaps; travel
15-25% of snaps for clubs that travel."""
import numpy as np, collections, sys
import rosters as R, game as G, plays as P, schemes as S

def run(n=40, seed=3):
    rng = np.random.default_rng(seed); L = R.load_league()
    teams = list(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coach = dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    pd = collections.Counter(); games = collections.Counter(); role = {}
    pb = [0, 0]; rb = [0, 0]; travel = [0, 0]; cb_snaps = collections.defaultdict(lambda: [0, 0])
    for g in range(n):
        a, b = rng.choice(teams, 2, replace=False)
        A, B = L[a], L[b]
        SA, SB = G.TeamState(A, coach=coach), G.TeamState(B, coach=coach)
        r = G.play_game(A, B, rng, P.resolve_play, co, cd, P.rate, home_state=SA, away_state=SB, week=1 + g % 17)
        for side, st, ros in (('home', SA, A), ('away', SB, B)):
            import targets as TG
            cbs = [x for x in ros['db'] if x.get('pos') == 'CB']
            cbs = sorted(cbs, key=lambda x: -TG.position_score(x, 'CB'))
            for i, x in enumerate(cbs[:4]): role[x['pid']] = f'CB{i+1}'
            for x in ros['db']:
                if x.get('pos') in ('FS', 'SS'): role[x['pid']] = x['pos']
            for x in ros['lb']: role[x['pid']] = 'LB'
            games[side + str(g)] += 1
            for pid, nsn in (st.last_snaps or st.snaps or {}).items():
                if pid in role and role[pid].startswith('CB'):
                    cb_snaps[role[pid]][0] += nsn
            for k, v in st.book.players.items() if hasattr(st, 'book') and hasattr(st.book, 'players') else []:
                pass
        for pos, d in r['drives']:
            for l in d.log:
                if not isinstance(l, dict): continue
                if l.get('pass_def'): pd[l['pass_def']] += 1
                if l.get('type') in ('complete', 'incomplete', 'sack', 'interception', 'drop'):
                    reps = l.get('pb_reps') or []
                    for w in reps: pb[0] += 1; pb[1] += bool(w[1] if isinstance(w, (tuple, list)) else w)
                    if 'travelled' in l: travel[0] += 1; travel[1] += bool(l['travelled'])
                if l.get('type') == 'run' and l.get('rb_reps'):
                    for w in l['rb_reps']: rb[0] += 1; rb[1] += bool(w[1] if isinstance(w, (tuple, list)) else w)
    top = pd.most_common(8)
    print(f'{n} games. PD: total {sum(pd.values())} ({sum(pd.values())/(2*n):.1f} per team-game, real ~2.9); leader {top[0][1]} in {n} games -> {top[0][1]/n*17:.0f} per 17 (real ~24)')
    print('  leaders by role:', [(role.get(pid, '?'), c) for pid, c in top])
    byrole = collections.Counter()
    for pid, c in pd.items(): byrole[role.get(pid, '?')] += c
    print('  PD by role:', dict(byrole.most_common()))
    print(f'PBWR {pb[1]/max(1,pb[0])*100:.1f}% (real 91) on {pb[0]} reps; RBWR {rb[1]/max(1,rb[0])*100:.1f}% (real 71) on {rb[0]} reps')
    tot = sum(v[0] for v in cb_snaps.values())
    print('  CB snap share:', {k: f'{v[0]/max(1,tot)*100:.0f}%' for k, v in sorted(cb_snaps.items())}, '(real CB3 ~57% of team snaps)')
    print(f'  travel flagged on {travel[1]} of {travel[0]} pass plays with the flag ({travel[1]/max(1,travel[0])*100:.1f}%)')

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
