"""Fit distance distributions on 2021-24 nflverse REG; hold out 2025.

Input: the selected-column CSVs retained in outputs/margin-real-pbp.
Fumble recovery spots come from the final credited RECOVERED-by location in
the description; rows without an unambiguous defensive recovery are excluded.
Positive distances use a censored two-exponential likelihood: a touchdown
observes distance >= distance to goal, not an artificial touchdown draw.
"""
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd


def reference(root, kind):
    df = pd.concat(pd.read_csv(f) for f in Path(root).glob('20*.csv'))
    df = df[(df.season_type == 'REG') & (df.play_type != 'no_play') &
            (df.kickoff_attempt != 1) & (df.punt_attempt != 1)]
    t = df[df.interception == 1 if kind == 'int' else
           (df.fumble_lost == 1) & (df.interception != 1)].copy()
    t['td'] = (t.td_team == t.defteam) & (t.touchdown == 1)
    if kind == 'int':
        t['spot'] = t.yardline_100 - t.air_yards.fillna(0)
        t['ret'] = t.return_yards
    else:
        spots = []
        for _, r in t.iterrows():
            hits = [h for h in re.findall(r'RECOVERED by ([A-Z]+)-.*? at ([A-Z]+) (-?\d+)', r['desc'])
                    if h[0] == r.defteam and h[1] in (r.posteam, r.defteam)]
            h = hits[-1] if hits else None
            spots.append((100 - float(h[2]) if h[1] == r.posteam else float(h[2])) if h else np.nan)
        t['spot'] = spots
        t['ret'] = t.fumble_recovery_1_yards.where(t.fumble_recovery_1_team == t.defteam,
                   t.fumble_recovery_2_yards.where(t.fumble_recovery_2_team == t.defteam, 0)).fillna(0)
    return t[t.spot.notna()].copy()


def fit(t):
    tr = t[(t.season < 2025) & (t.spot < 100)]
    bins = [-20, 0, 20, 40, 60, 80, 100]
    stops = []
    for lo, hi in zip(bins, bins[1:]):
        a = tr[(tr.spot > lo) & (tr.spot <= hi)]
        stops.append(float(((a.ret <= 0) & ~a.td).mean()))
    a = tr[(tr.ret > 0) | tr.td]
    x, d, td = a.ret.to_numpy(), (100 - a.spot).to_numpy(), a.td.to_numpy()
    def loss(v):
        # Censoring cannot identify an infinite breakaway scale. Bound the
        # latent distance scale at one field rather than fit a forced-TD mass.
        if np.any(v[1:] < np.log(.5)) or np.any(v[1:] > np.log(100)):
            return 1e12
        p = 1 / (1 + np.exp(-v[0])); s1, s2 = np.exp(v[1:])
        density = (1-p)/s1*np.exp(-x/s1) + p/s2*np.exp(-x/s2)
        tail = (1-p)*np.exp(-d/s1) + p*np.exp(-d/s2)
        return -float(np.log(np.maximum(np.where(td, tail, density), 1e-12)).sum())
    v = np.array([0.0, np.log(5), np.log(35)])
    step = 1.0
    while step > .0001:
        old = loss(v)
        trials = [v + np.eye(3)[i] * step * direction for i in range(3) for direction in (-1, 1)]
        best = min(trials, key=loss)
        if loss(best) < old: v = best
        else: step *= .5
    p = 1/(1+np.exp(-v[0])); s1, s2 = np.exp(v[1:])
    return dict(stop=stops, tail=float(p), scales=[float(s1), float(s2)])


def expected(z, model):
    stop = np.array(model['stop'])[np.clip(np.digitize(z.spot, [0,20,40,60,80], right=True), 0, 5)]
    dist = np.maximum(0, 100-z.spot.to_numpy())
    p = model['tail']; s1, s2 = model['scales']
    ptd = np.where(dist == 0, 1, (1-stop)*((1-p)*np.exp(-dist/s1)+p*np.exp(-dist/s2)))
    mean = (1-stop)*((1-p)*s1*(1-np.exp(-dist/s1))+p*s2*(1-np.exp(-dist/s2)))
    return dict(n=len(z), real_td_rate=float(z.td.mean()), model_td_rate=float(ptd.mean()),
                real_mean_return=float(z.ret.mean()), model_mean_return=float(mean.mean()))


def sampled(z, kind):
    import plays
    rng = np.random.default_rng(930306)
    count = td = 0
    yards = 0.0
    for _ in range(20):
        for spot in z.spot:
            result = plays.defensive_return(spot, kind, dict(pid='neutral'), [], rng)
            count += 1; td += bool(result['defensive_td']); yards += result['ret']
    return dict(returns=count, td_rate=td/count, mean_return=yards/count)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('reference_dir')
    args = parser.parse_args()
    report = {}
    for kind in ('int', 'fumble'):
        t = reference(args.reference_dir, kind); model = fit(t)
        report[kind] = dict(model=model, train=expected(t[t.season<2025],model),
                           holdout=expected(t[t.season==2025],model), all=expected(t,model),
                           runtime_sample=sampled(t,kind))
    print(json.dumps(report, indent=2))
