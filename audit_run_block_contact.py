"""Compare conditional run opportunities; no games, saves or seasons advanced."""
import collections
import hashlib
import json
import subprocess
import types
from pathlib import Path
import numpy as np
import plays
import rosters
import offense_roles
import defense_roles


def run(n=2000):
    baseline='de36cef'
    old=types.ModuleType('baseline_plays')
    exec(compile(subprocess.check_output(['git','show',baseline+':plays.py']).decode(),
                 'baseline_plays','exec'),old.__dict__)
    teams=rosters.load_league()
    rows=[]; examples=[]
    for attack,defense in (('GB','LA'),('LA','GB'),('BAL','PIT'),('KC','BUF')):
        off=offense_roles.field(teams[attack],'11')
        deff=defense_roles.field(teams[defense],'base','4-3')
        assert len({p['pid'] for _,p in off['offensive_assignments']})==11
        assert len({a['player']['pid'] for a in deff['defensive_assignments']})==11
        for scheme,box in (('inside_zone',6),('outside_zone',5)):
            summaries=[collections.Counter(),collections.Counter()]
            samples=[[],[]]
            for seed in range(n):
                seed += 100000 * (len(rows) + 1)
                pair=[m._run_play(off,deff,dict(scheme=scheme),
                    dict(front='4-3 over',front_family='4-3',personnel='base',box=box),
                    60,np.random.default_rng(seed)) for m in (old,plays)]
                for i,p in enumerate(pair):
                    c=summaries[i];y=p['yards'];c['attempts']+=1;c['yards']+=y
                    c['losses']+=y<0;c['rounded_losses']+=round(y)<0
                    c['explosive20']+=y>=20;c['td']+=p['touchdown']
                    c['recorded_blocks']+=len(p['rb_reps']);c['recorded_wins']+=sum(w for _,w in p['rb_reps'])
                    samples[i].append(p['ybc'])
                if scheme=='inside_zone' and len([e for e in examples if e['offense']==attack])<3 and pair[0]['yards']>=0>pair[1]['yards']:
                    examples.append(dict(offense=attack,defense=defense,seed=seed,
                        runner=off['rb'].get('name',off['rb'].get('pid')),
                        blockers=[dict(pid=pid,won=bool(won)) for pid,won in pair[1]['rb_reps']],
                        old_yards=pair[0]['yards'],new_yards=pair[1]['yards']))
            for c,s in zip(summaries,samples):
                c['mean_ybc']=float(np.mean(s));c['sd_ybc']=float(np.std(s))
                c['ypc']=c['yards']/n
            rows.append(dict(offense=attack,defense=defense,scheme=scheme,box=box,
                             before=summaries[0],after=summaries[1]))
    return dict(baseline=baseline,personnel='11 offense versus base 4-3; exactly 11 selected players each',source_hashes={f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
                for f in ('plays.py','run_blocking.py','ticker.py')},samples_per_matchup=n,
                rows=rows,individual_examples=examples,
                limitations='Selected catalog players, conditional runs at 60 yards to goal. Not season calibration or the supplied saved roster. Coarse inside/outside weighting, not tracked coordinates.')


if __name__=='__main__':
    result=run()
    text=json.dumps(result,indent=2,default=lambda x:x.item())
    Path('research/run_block_contact_20261005.json').write_text(text+'\n',encoding='utf-8')
    for r in result['rows']:
        print(r['offense'],r['defense'],r['scheme'],
              {k:(round(r['before'][k],3),round(r['after'][k],3)) for k in
               ('ypc','losses','rounded_losses','explosive20','recorded_wins','mean_ybc','sd_ybc')})
