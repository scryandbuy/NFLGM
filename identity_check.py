"""Does the man show up in the calls? Eight weeks on the real clubs, then each
club's measured tendencies against its identity. Hooks play_game to keep
the drive logs."""
import numpy as np, collections, sys
import league as LG, season as SN, game as G, identity_catalog as IC

def run(weeks=8, seed=2026):
    rng = np.random.default_rng(seed)
    L = LG.build_league(rng=rng); L.user_team = None
    r = SN.SeasonRunner(L, rng)
    logs = []
    orig = G.play_game
    def hooked(home, away, *a, **k):
        res = orig(home, away, *a, **k)
        logs.append((k.get('home_state'), k.get('away_state'), res))
        return res
    G.play_game = hooked
    for wk in range(1, weeks + 1): r.play_week(wk)
    G.play_game = orig
    return L, logs, r

if __name__ == '__main__':
    L, logs, r = run(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
    inv = {id(st): a for a, st in r.states.items()}
    off = collections.defaultdict(list); de = collections.defaultdict(list)
    for hs, as_, res in logs:
        h, a = inv.get(id(hs)), inv.get(id(as_))
        for pos, d in res['drives']:
            o, dd = (h, a) if pos == 'home' else (a, h)
            for l in d.log:
                if isinstance(l, dict) and l.get('type') in ('run','complete','incomplete','sack','scramble','drop','interception'):
                    off[o].append(l); de[dd].append(l)
    print(f"{'club':4s} {'coach':18s} | pass% (lean)  PA% of dropbacks (lean)  motion% (lean) | man% (lean)  blitz% (lean)  2-high% (lean)")
    rows = []
    for a in sorted(L.teams):
        e = IC.CATALOG[a]; o = off[a]; d = de[a]
        if not o or not d: continue
        pas = [l for l in o if l.get('is_pass')]
        dbs = [l for l in d if l.get('type') in ('complete','incomplete','sack','drop','interception')]
        pass_pct = np.mean([bool(l.get('is_pass')) for l in o]) * 100
        pa = np.mean([bool(l.get('play_action')) for l in pas]) * 100 if pas else 0
        mo = np.mean([bool(l.get('motion')) for l in o]) * 100
        man = np.mean([bool(l.get('in_man')) for l in dbs if l.get('type') != 'sack']) * 100 if dbs else 0
        bl = np.mean([(l.get('blitzers') or 0) > 0 for l in dbs]) * 100 if dbs else 0
        two = np.mean([str(l.get('coverage', '')) in ('cover_2','two_man','tampa_2','cover_4','cover_6') for l in dbs if l.get('type') != 'sack']) * 100 if dbs else 0
        rows.append((a, e['coach'], pass_pct, e['offence']['pass_lean'], pa, e['offence']['play_action'], mo, e['offence']['motion'], man, e['defence']['coverage'], bl, e['defence']['blitz'], two, e['defence']['shell']))
        print(f"{a:4s} {e['coach'][:18]:18s} | {pass_pct:5.1f} ({e['offence']['pass_lean']:.2f})  {pa:5.1f} ({e['offence']['play_action']:.2f})  {mo:5.1f} ({e['offence']['motion']:.2f}) | {man:5.1f} ({e['defence']['coverage']:.2f})  {bl:5.1f} ({e['defence']['blitz']:.2f})  {two:5.1f} ({e['defence']['shell']:.2f})")
    R = np.array([[x for x in r_[2:]] for r_ in rows], float)
    def corr(i, j): return np.corrcoef(R[:, i], R[:, j])[0, 1]
    print(f"\ncorrelation measured vs identity: pass {corr(0,1):+.2f}  PA {corr(2,3):+.2f}  motion {corr(4,5):+.2f}  man {corr(6,7):+.2f}  blitz {corr(8,9):+.2f}  two-high {corr(10,11):+.2f}")
    print(f"league: pass {R[:,0].mean():.1f}  PA {R[:,2].mean():.1f}  motion {R[:,4].mean():.1f}  man {R[:,6].mean():.1f}  blitz {R[:,8].mean():.1f}  (register reals: pass 57.6, PA ~17 of dropbacks, motion 36.5, man ~35 targeted, blitz 13.3)")
