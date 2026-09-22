"""Air yards and depth mix by week across a season chunk: is there a drift?"""
import numpy as np, collections, sys
import league as LG, season as SN, game as G
def run(weeks=8, seed=2026):
    rng = np.random.default_rng(seed); L = LG.build_league(rng=rng); L.user_team = None
    r = SN.SeasonRunner(L, rng); byweek = collections.defaultdict(list); deep = collections.defaultdict(lambda: [0, 0])
    orig = G.play_game
    def hooked(*a, **k):
        res = orig(*a, **k)
        for pos, d in res['drives']:
            for l in d.log:
                if isinstance(l, dict) and l.get('type') in ('complete', 'incomplete', 'interception', 'drop'):
                    byweek[k.get('week')].append(l.get('depth')); deep[k.get('week')][0] += 1; deep[k.get('week')][1] += l.get('depth') == 'deep'
        return res
    G.play_game = hooked
    for wk in range(1, weeks + 1): r.play_week(wk)
    G.play_game = orig
    for wk in sorted(byweek):
        c = collections.Counter(byweek[wk]); n = sum(c.values())
        print(f'  week {wk}: short {c["short"]/n*100:.0f}%  medium {c["medium"]/n*100:.0f}%  deep {c["deep"]/n*100:.0f}%  (n {n})')
if __name__ == '__main__': run(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
