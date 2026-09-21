"""
PASSING DIAGNOSTIC.

The register reports completion, interceptions, sacks, air yards and yards
per dropback as five numbers. They are one curve seen from five angles, and
tuning any one of them blind moves the other four. This breaks the passing
game open inside REAL games - the same loop the register runs - and reports
what the chain is doing at each step: by throw depth, by man versus zone, by
coverage call, by pressure and by read.

Real figures (nflverse 2020-25, FTN 2023-24):
  completion by depth on attempts:  behind 78.4  short 71.0  medium 56.0  deep 39.4
  share of ATTEMPTS by depth:       behind 18.4  short 49.5  medium 22.4  deep  9.7
  share of COMPLETIONS by air band: behind 22.3  0-9 54.1   10-19 17.3   20+  6.3
  completion by read:               first 60.7  second 53.6  checkdown 78.1  designed 83.2
  completion vs man ~60, vs zone ~68 (FTN, all depths)
  completion under pressure 50.0 vs clean 70.6 (PFF style, pressure ~34% of dropbacks)
"""
import numpy as np, collections, sys

REAL_DEPTH_COMP = dict(behind=78.4, short=71.0, medium=56.0, deep=39.4)
REAL_DEPTH_SHARE = dict(behind=18.4, short=49.5, medium=22.4, deep=9.7)
REAL_BAND_SHARE = {'behind': 22.3, '0-9': 54.1, '10-19': 17.3, '20+': 6.3}
REAL_READ_COMP = dict(first=60.7, second=53.6, checkdown=78.1, designed=83.2,
                      scramble=29.8)


def run(weeks=6, seed=2026, verbose=True):
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league()
    teams = sorted(L)
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(
        d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(
        oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(
        adjust_skill=float(np.clip(rng.normal(.55, .18), .1, .95)),
        adjust_willingness=float(np.clip(rng.normal(.55, .2), .1, .95)),
        man_rate=float(np.clip(rng.normal(.35, .12), .12, .62)),
        blitz_rate=float(np.clip(rng.normal(.133, .05), .05, .28)),
        travel_willingness=float(np.clip(rng.normal(.5, .22), .05, .95)),
        off_script_skill=float(np.clip(rng.normal(.5, .2), .1, .9))) for t in teams}

    logs = []
    ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    ngames = 0
    for wk in range(weeks):
        o = list(teams); rng.shuffle(o)
        for i in range(0, 32, 2):
            h, a = o[i], o[i + 1]
            r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate,
                            home_state=ST[h], away_state=ST[a], week=wk + 1)
            ngames += 1
            for _, d in r['drives']:
                for l in d.log:
                    if isinstance(l, dict) and l.get('type') in (
                            'complete', 'incomplete', 'drop', 'interception', 'sack'):
                        logs.append(l)
    return summarise(logs, ngames, verbose)


def _bucket(l):
    """Depth bucket of an ATTEMPT: behind the line is its own bucket."""
    if l.get('screen'): return 'behind'
    return l.get('depth', 'short')


def _band(air):
    if air < 0: return 'behind'
    if air < 10: return '0-9'
    if air < 20: return '10-19'
    return '20+'


def summarise(logs, ngames, verbose=True):
    att = [l for l in logs if l['type'] != 'sack']
    comp = [l for l in att if l['type'] == 'complete']
    out = {}

    def rate(rows):
        n = len(rows)
        return (sum(1 for x in rows if x['type'] == 'complete') / n * 100) if n else float('nan'), n

    # by depth
    by_depth = {}
    for b in ('behind', 'short', 'medium', 'deep'):
        rows = [l for l in att if _bucket(l) == b]
        c, n = rate(rows)
        by_depth[b] = dict(comp=c, share=n / max(len(att), 1) * 100, n=n,
                           int=sum(1 for x in rows if x['type'] == 'interception') / max(n, 1) * 100,
                           drop=sum(1 for x in rows if x['type'] == 'drop') / max(n, 1) * 100)
    out['by_depth'] = by_depth

    # completion air-yard bands
    bands = collections.Counter(_band(l.get('air', 0)) for l in comp)
    out['bands'] = {k: bands[k] / max(len(comp), 1) * 100 for k in REAL_BAND_SHARE}

    # man vs zone by depth
    mz = {}
    for m in (True, False):
        for b in ('short', 'medium', 'deep'):
            rows = [l for l in att if l.get('in_man') is m and _bucket(l) == b]
            mz[('man' if m else 'zone', b)] = rate(rows)
    out['man_zone'] = mz

    # by read
    by_read = {}
    for k in REAL_READ_COMP:
        rows = [l for l in att if l.get('read') == k]
        by_read[k] = rate(rows)
    out['by_read'] = by_read

    # pressure
    pr = [l for l in att if l.get('pressured')]
    cl = [l for l in att if not l.get('pressured')]
    out['pressure'] = dict(pressured=rate(pr), clean=rate(cl),
                           share=len(pr) / max(len(att), 1) * 100)

    # by coverage call
    by_cov = {}
    for cv in sorted({l.get('coverage') for l in att}):
        rows = [l for l in att if l.get('coverage') == cv]
        by_cov[cv] = rate(rows) + (len(rows) / max(len(att), 1) * 100,)
    out['by_coverage'] = by_cov

    # headline
    sacks = sum(1 for l in logs if l['type'] == 'sack')
    out['headline'] = dict(
        attempts=len(att), completion=len(comp) / max(len(att), 1) * 100,
        int=sum(1 for l in att if l['type'] == 'interception') / max(len(att), 1) * 100,
        drop=sum(1 for l in att if l['type'] == 'drop') / max(len(att), 1) * 100,
        sack=sacks / max(len(logs), 1) * 100,
        air=np.mean([l.get('air', 0) for l in comp]) if comp else 0,
        yac=np.mean([l.get('yac', 0) for l in comp]) if comp else 0,
        ypd=(sum(l.get('yards', 0) for l in comp) + sum(l.get('yards', 0) for l in logs if l['type'] == 'sack')) / max(len(logs), 1))

    if verbose:
        h = out['headline']
        print(f"{ngames} games, {h['attempts']} attempts")
        print(f"  completion {h['completion']:.1f} (real 65.0)   int {h['int']:.2f} (2.10)   "
              f"drop {h['drop']:.2f} (~2.4 of att)   sack {h['sack']:.2f} (6.60)")
        print(f"  air {h['air']:.2f} (5.72)   yac {h['yac']:.2f} (5.19)   ypd {h['ypd']:.2f} (6.18)\n")

        print("  BY THROW DEPTH (attempts)")
        print(f"  {'bucket':8s} {'share':>7s} {'real':>6s}   {'comp':>6s} {'real':>6s}   {'int%':>5s} {'drop%':>5s}")
        for b, d in by_depth.items():
            print(f"  {b:8s} {d['share']:7.1f} {REAL_DEPTH_SHARE[b]:6.1f}   "
                  f"{d['comp']:6.1f} {REAL_DEPTH_COMP[b]:6.1f}   {d['int']:5.2f} {d['drop']:5.2f}")

        print("\n  COMPLETIONS BY AIR-YARD BAND")
        for k, v in out['bands'].items():
            print(f"  {k:8s} {v:6.1f}  real {REAL_BAND_SHARE[k]:5.1f}")

        print("\n  MAN vs ZONE, completion by depth (n)")
        for b in ('short', 'medium', 'deep'):
            m, mn = mz[('man', b)]; z, zn = mz[('zone', b)]
            print(f"  {b:8s} man {m:5.1f} ({mn:4d})   zone {z:5.1f} ({zn:4d})")
        man_all = rate([l for l in att if l.get('in_man')])
        zone_all = rate([l for l in att if not l.get('in_man')])
        print(f"  all      man {man_all[0]:5.1f} ({man_all[1]:4d}, real ~60)   "
              f"zone {zone_all[0]:5.1f} ({zone_all[1]:4d}, real ~68)")

        print("\n  BY READ")
        for k, (c, n) in by_read.items():
            print(f"  {k:10s} {c:5.1f}  real {REAL_READ_COMP[k]:5.1f}  ({n})")

        p = out['pressure']
        print(f"\n  PRESSURE  pressured {p['pressured'][0]:.1f} (real 50.0) on {p['share']:.1f}% of att (real ~34)"
              f"   clean {p['clean'][0]:.1f} (real 70.6)")

        print("\n  BY COVERAGE CALL   comp  (n)  share")
        for cv, (c, n, sh) in by_cov.items():
            print(f"  {str(cv):16s} {c:5.1f} ({n:4d}) {sh:5.1f}%")
    return out


if __name__ == '__main__':
    run(weeks=int(sys.argv[1]) if len(sys.argv) > 1 else 6)
