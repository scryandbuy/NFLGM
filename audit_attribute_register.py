"""Fixed-seed full-game slice for attribute wiring; no outcome mutations."""
import argparse, json
from pathlib import Path
from collections import Counter
import numpy as np
import league, season, plays
from calibrate import Collector, TARGETS


def run(output, seeds=(100141,100142)):
    c=Collector(); games=[]; signals=Counter()
    for seed in seeds:
        lg=league.build_league(rng=np.random.default_rng(seed))
        runner=season.SeasonRunner(lg,np.random.default_rng(seed+1000))
        teams=sorted(lg.teams);np.random.default_rng(seed).shuffle(teams)
        for home,away in zip(teams[::2],teams[1::2]):
            trace=[];previous_trace=plays.PASS_TRACE;plays.PASS_TRACE=trace
            try:r=runner.play(home,away,1)
            finally:plays.PASS_TRACE=previous_trace
            c.add(r)
            signals['moving_throws']+=sum(bool(p.get('on_run')) for p in trace)
            tally=dict(home=0,away=0)
            for side,dr in r['drives']:
                tally[side if dr.points>=0 else ('away' if side=='home' else 'home')]+=abs(dr.points)
                for p in dr.log:
                    if p.get('nullified'):continue
                    signals['fumbles']+=bool(p.get('fumble'))
                    signals['lost_fumbles']+=bool(p.get('fumble_lost'))
                    if p.get('type')=='run':
                        signals['run_support_blocks']+=len(p.get('run_support',()))
                        ids=[pid for pid,_ in p.get('rb_reps',())]
                        assert len(ids)==len(set(ids)),('duplicate_blocker',p)
            assert tally=={s:r[s] for s in tally},('score',home,away,tally)
            games.append(dict(seed=seed,home=home,away=away,home_score=r['home'],away_score=r['away']))
            print(f'{len(games)}/{16*len(seeds)} {home} {r["home"]}-{r["away"]} {away}',flush=True)
    got=c.report('Attribute wiring register')
    result=dict(seeds=list(seeds),games=games,register=got,signals=dict(signals),
        misses=[dict(metric=n,value=float(got[n]),target=t,tolerance=tol) for n,t,tol,_ in TARGETS if abs(got[n]-t)>tol],
        denominators=dict(games=c.ngames,drives=c.drives_total,offensive_plays=c.n_off,
                          passes=sum(len(c.ypp[k]) for k in ('complete','incomplete','drop','interception')),
                          runs=len(c.ypp['run']),fg=len(c.fg)),
        scope='Fresh 2026 rosters, each team once per seed; no season development')
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    parser.add_argument('--seeds',nargs='+',type=int,default=[100141,100142])
    args=parser.parse_args();run(args.out,args.seeds)
