import numpy as np, collections, sys
import rosters as R, game as G, plays as P, schemes as S
def run(n=20, seed=3):
    rng = np.random.default_rng(seed); L = R.load_league(); teams = list(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coach = dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    pos_of = {}
    for t in L.values():
        for k, v in t.items():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and 'pid' in x: pos_of[x['pid']] = x.get('pos')
            elif isinstance(v, dict) and 'pid' in v: pos_of[v['pid']] = v.get('pos')
    pdrole = collections.Counter(); byd = collections.defaultdict(lambda: [0, 0]); deep_zone = [0, 0]
    for g in range(n):
        a, b = rng.choice(teams, 2, replace=False)
        r = G.play_game(L[a], L[b], rng, P.resolve_play, co, cd, P.rate, home_state=G.TeamState(L[a], coach=coach), away_state=G.TeamState(L[b], coach=coach), week=1)
        for pos, d in r['drives']:
            for l in d.log:
                if not isinstance(l, dict) or l.get('type') not in ('complete','incomplete','interception','drop'): continue
                if l.get('pass_def'): pdrole[{'FS': 'S', 'SS': 'S', 'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB'}.get(pos_of.get(l['pass_def'], '?'), pos_of.get(l['pass_def'], '?'))] += 1
                c = l['type'] == 'complete'; byd[l.get('depth')][0] += 1; byd[l.get('depth')][1] += c
                if l.get('depth') == 'deep' and not l.get('in_man'): deep_zone[0] += 1; deep_zone[1] += c
    tot = sum(pdrole.values())
    print('PD by role:', {k: f'{v/tot*100:.0f}%' for k, v in pdrole.most_common()}, '(real CB 55-60, S 20-25, LB 12-15)')
    print('completion by depth:', {k: f'{v[1]/max(1,v[0])*100:.0f}% ({v[0]})' for k, v in byd.items()}, f'| deep in zone {deep_zone[1]/max(1,deep_zone[0])*100:.0f}% ({deep_zone[0]}) (real 71/56/39)')
if __name__ == '__main__': run(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
