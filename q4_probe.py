"""Which mechanism makes the better club better in the fourth quarter?
Runs the league with one system switched off at a time and reports how much
of the strength gap shows up in each quarter."""
import numpy as np, collections, sys

def season(weeks, seed, patch=None):
    import rosters as R, game as G, plays as P, schemes as S, health as H
    if patch: patch(G, P, S, H)
    rng = np.random.default_rng(seed)
    L = R.load_league(); teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(adjust_skill=.55, adjust_willingness=.55, man_rate=.35, blitz_rate=.133, travel_willingness=.5, off_script_skill=.5) for t in teams}
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    games = []
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            h, a = o[i], o[i+1]
            r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate, home_state=ST[h], away_state=ST[a], week=wk+1)
            q = [0, 0, 0, 0]
            for pos, d in r['drives']:
                qq = min(4, int((G.GAME - d.clock) // G.QUARTER) + 1) - 1
                if d.points > 0: q[qq] += d.points if pos == 'home' else -d.points
                elif d.points < 0: q[qq] += -2 if pos == 'home' else 2
            games.append((h, a, q, r['home'] - r['away']))
    diff = collections.defaultdict(list)
    for h, a, q, m in games: diff[h].append(m); diff[a].append(-m)
    s = {t: np.mean(v) for t, v in diff.items()}
    x = np.array([s[h] - s[a] for h, a, q, m in games])
    slopes = [np.polyfit(x, np.array([q[k] for h, a, q, m in games]), 1)[0] for k in range(4)]
    m = np.array([g[3] for g in games])
    return slopes, np.mean(np.abs(m) >= 10) * 100, np.std(list(s.values())), np.abs(m).mean()

def no_fatigue(G, P, S, H):
    H.apply_state = lambda player, condition=100.0: dict(player)
    H.Condition.needs_rest = lambda self, *a, **k: False

def no_adjust(G, P, S, H):
    import adjust as AD
    for name in dir(AD):
        pass
    AD._DISABLED = True
    orig = G.TeamState.__init__
    def init(self, roster, policy=0.5, plan=None, coach=None, scheme=None):
        coach = dict(coach or {}); coach['adjust_willingness'] = 0.0; coach['adjust_skill'] = 0.0
        orig(self, roster, policy, plan, coach, scheme)
    G.TeamState.__init__ = init

def no_clock_script(G, P, S, H):
    import decisions as DEC
    DEC.pass_rate = lambda sd, secs: S.NEUTRAL_SCRIPT

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'base'
    patch = {'base': None, 'nofatigue': no_fatigue, 'noadjust': no_adjust, 'noclock': no_clock_script}[which]
    sl, b10, spread, am = season(10, 2026, patch)
    print(f'{which:10s} slopes Q1-Q4 ' + ' '.join(f'{v:+.3f}' for v in sl) + f'   Q4/mean(Q1-3) {sl[3]/np.mean(sl[:3]):.2f}   10+ {b10:.1f}%   |m| {am:.1f}   spread {spread:.2f}')
