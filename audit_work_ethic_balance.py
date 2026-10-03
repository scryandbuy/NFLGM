"""Paired practice/XP audit. Practice-only growth is not full-season calibration."""
import argparse
import copy
import json
import subprocess
import types
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as N

import numpy as np
import league as LG
import practice as P
import personality as PT
import targets as TG
import xp as XP
import xp_spend as XS


def baseline_award(ref):
    source = subprocess.check_output(['git', 'show', f'{ref}:practice.py']).decode('utf-8')
    module = types.ModuleType('baseline_practice')
    exec(compile(source, f'{ref}:practice.py', 'exec'), module.__dict__)
    return module._xp_award


def summary(values):
    return dict(n=len(values), mean=float(np.mean(values)), min=float(min(values)),
                max=float(max(values)), p10=float(np.quantile(values, .1)),
                p90=float(np.quantile(values, .9)))


def roster_comparison(old, seeds):
    results = []
    for seed in seeds:
        league = LG.build_league(rng=np.random.default_rng(seed))
        teams, people, ratios, ethics, cohort = [], [], [], [], {}
        for abbr, team in league.teams.items():
            before = after = 0.
            for p in P._roster(league, abbr):
                previous = old(league, team, p, 1., 1., False, 0)['xp']
                current = P._xp_award(league, team, p, 1., 1., False, 0)['xp']
                factor = PT.xp_mult(p)
                assert abs(current - min(P._xp_award(league, team, p, 1., 1., False, 0)['xp_ceiling'], previous*factor)) < 1e-8
                before += previous; after += current
                ratio = current/previous if previous else 1.
                ratios.append(ratio); ethics.append(p.traits['work_ethic'])
                people.append((p.pid, current-previous))
                label = 'low' if p.traits['work_ethic'] < 42 else 'high' if p.traits['work_ethic'] >= 58 else 'middle'
                cohort.setdefault(label, []).append(ratio)
            teams.append(dict(team=abbr, before=before, after=after, pct=100*(after/before-1)))
        results.append(dict(seed=seed, players=len(people), work_ethic=summary(ethics),
            individual_ratio=summary(ratios), groups={k:summary(v) for k,v in cohort.items()},
            league_pct=100*(sum(t['after'] for t in teams)/sum(t['before'] for t in teams)-1),
            teams=teams))
    return results


def growth_comparison(old):
    rows=[]
    for pos in ('QB','HB','WR','TE','LT','REDG','DT','CB','K','LS'):
        for exp in (0,3,9):
            for dev in ('normal','star','superstar','xfactor'):
                for ethic in (15,50,85):
                    outcomes=[]
                    for mode, award_fn in (('before',old),('after',P._xp_award)):
                        p=LG.Player(f'{pos}-{exp}-{dev}-{ethic}', 'Audit player', pos,22+exp,
                            {key:70. for key in TG.DEPTH_WEIGHTS[pos]},dev=dev,potential=90,
                            entry_year=2026-exp)
                        p.traits={'work_ethic':ethic,'discipline':50}
                        league=N(year=2026); team=N(record=(0,0,0))
                        gm=N(dev_belief=.5,patience=.5)
                        before=p.ovr; total=0.;rng=np.random.default_rng(229)
                        with patch('staff.xp_mult',return_value=1.):
                            for week in range(1,19):
                                award=award_fn(league,team,p,1.,1.,False,0)['xp']
                                # Same real credit path as practice.resolve, no double effect.
                                paid=XP.credit(p,award/PT.xp_mult(p),'practice')
                                assert abs(paid-award)<1e-8
                                p.xp+=paid;total+=paid
                                if week % XS.CPU_SPEND_INTERVAL == 0:
                                    XS.spend_player(p,gm,team,week,rng,year=2026)
                        assert p.ovr <= p.potential+.01
                        outcomes.append(dict(mode=mode,xp=total,ovr_gain=p.ovr-before,
                                             bought=XP.points_bought(p),unspent=p.xp))
                    rows.append(dict(pos=pos,experience=exp,dev=dev,ethic=ethic,**{r.pop('mode'):r for r in outcomes}))
    assert all(abs(r['before']['xp']-r['after']['xp'])<1e-8 and r['before']==r['after'] for r in rows if r['ethic']==50)
    return rows


def workload_parity(old):
    from test_practice_engine import setup, plan
    snapshots=[]
    for mode,award_fn in (('before',old),('after',P._xp_award)):
        league,runner,players=setup(seed=77)
        for i,p in enumerate(players):
            p.traits={'work_ethic':(15,50,85)[i%3],'discipline':50}
        rng=copy.deepcopy(runner.rng.bit_generator.state)
        with patch.object(P,'_xp_award',award_fn),patch('staff.xp_mult',return_value=1.):
            for week in range(1,19):
                P.resolve(league,runner,'A',week,plan('standard'),bye=(week==8))
        snapshots.append(dict(mode=mode,health=league.practice_state['players'],
                              rng=copy.deepcopy(runner.rng.bit_generator.state),
                              xp=sum(p.xp for p in players)))
    assert snapshots[0]['health']==snapshots[1]['health']
    assert snapshots[0]['rng']==snapshots[1]['rng']
    return dict(players=66,weeks=18,health_equal=True,rng_equal=True,
                before_xp=snapshots[0]['xp'],after_xp=snapshots[1]['xp'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',default='c14c945')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    old=baseline_award(args.baseline)
    result=dict(baseline=args.baseline,revision=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
                scope='Static standard/balanced 32-team previews and practice-only 18-week cohorts; no games, regression, awards, or season rewards.',
                rosters=roster_comparison(old,(71,229,991)),growth=growth_comparison(old),
                workload=workload_parity(old))
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(rosters=[dict(seed=r['seed'],players=r['players'],league_pct=r['league_pct'],
        team_pct=summary([t['pct'] for t in r['teams']])) for r in result['rosters']],
        growth_cases=len(result['growth']),workload=result['workload']),indent=2))
