"""Read existing season records and probe current resolvers; no new game sims."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import numpy as np
import plays as P
import events as E
from test_run_support_attributes import offense
from test_defensive_rush import unit, call


def add_run(c, p):
    y = p.get('yards', 0) or 0
    c['attempts'] += 1
    c['yards'] += y
    c['raw_losses'] += y < 0
    c['displayed_losses'] += round(y) < 0
    c['fractional_losses_shown_zero'] += y < 0 and round(y) == 0
    c['zero_or_loss'] += round(y) <= 0


def saved_samples(root):
    groups = collections.defaultdict(collections.Counter)
    games = 0
    for seed in (93031, 93032):
        source = root / f'coordinated-20261005-seed{seed}' / 'games.jsonl'
        with source.open(encoding='utf-8') as stream:
            for line in stream:
                g = json.loads(line)
                if g.get('playoffs') or not 1 <= g['week'] <= 18: continue
                games += 1
                for d in g['drives']:
                    for p in d['log']:
                        if p.get('nullified') or p.get('type') != 'run' or p.get('sneak'): continue
                        for key in ('all_designed', 'qb' if p.get('qb_run') else 'non_qb',
                                    f"box_{p.get('box', 'missing')}"):
                            add_run(groups[key], p)
    return dict(games=games, groups=groups,
                caveat='Frozen 0b4c49c gameplay, not the supplied game or a rerun of the latest build.')


def controls(n):
    runs = []
    block_attrs = {k for weights in P.RUN_BLOCK['blocker'].values() for k in weights}
    defense_attrs = {k for weights in P.RUN_BLOCK['defender'].values() for k in weights}
    for label, attack, defense in (('neutral',70,70), ('better_blocking',85,70), ('better_front',70,85)):
        for box in (4,6,8):
            off, deff = offense(), unit('4-3')
            for p in off['ol'] + off['extra_blockers'] + off['wr']:
                p.update({k:attack for k in block_attrs})
            for group in ('dl','lb','db'):
                for p in deff[group]:p.update({k:defense for k in defense_attrs})
            c = collections.Counter()
            for seed in range(n):
                p = P._run_play(off,deff,dict(scheme='inside_zone'),
                    dict(call('4-3'),front='4-3 over',box=box),60,np.random.default_rng(seed))
                add_run(c,p)
            runs.append(dict(matchup=label,box=box,**c))
    scrambles = []
    for mobility in (70,90):
        qb=dict(pid='qb',pos='QB',speed_rating=mobility,accel_rating=mobility,agility_rating=mobility)
        for pursuit in (70,90):
            defenders=[dict(pid=f'd{i}',pos=pos,pursuit_rating=pursuit,speed_rating=pursuit,tackle_rating=pursuit)
                       for i,pos in enumerate(('LEDG','DT','DT','REDG','MIKE','WILL','CB','CB','CB','SS','FS'))]
            for goal in (6,16,40):
                c=collections.Counter()
                for seed in range(n):
                    p=E.resolve_scramble(qb,defenders,goal,np.random.default_rng(seed),P.rate)
                    c['opportunities']+=1;c['touchdowns']+=p['touchdown'];c['yards']+=p['yards']
                    c['td_without_individual_contact']+=p['touchdown'] and 'pre_goal_contact_yards' not in p
                scrambles.append(dict(mobility=mobility,pursuit=pursuit,goal=goal,**c))
    # Hold contact-depth noise and all tackle/chase draws fixed. Only the
    # separately recorded block-win draws change.
    class BlockDraws:
        def __init__(self, sign):self.sign=sign;self.rng=np.random.default_rng(3)
        def normal(self,loc,scale):
            if scale==P.BE.RUN_SIGMA:return self.sign*10
            return self.rng.normal(loc,scale)
        def __getattr__(self,key):return getattr(self.rng,key)
    block_reps=[]
    for sign in (-1,1):
        p=P._run_play(offense(),unit('4-3'),dict(scheme='inside_zone'),
            dict(call('4-3'),front='4-3 over',box=6),60,BlockDraws(sign))
        block_reps.append(dict(recorded_wins=sum(w for _,w in p['rb_reps']),
            blockers=len(p['rb_reps']),yards=p['yards'],ybc=p['ybc']))
    return dict(samples_per_cell=n,runs=runs,scrambles=scrambles,block_rep_controls=block_reps,
        caveat='Synthetic conditional opportunities. No frequency calibration, QB-contact avoidance, or full-game claim.')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--outputs',type=Path,required=True)
    ap.add_argument('--save',type=Path,required=True);ap.add_argument('--samples',type=int,default=1000)
    args=ap.parse_args()
    result=dict(source_hashes={f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
        for f in ('game.py','plays.py','events.py','schemes.py')},
        existing_sample=saved_samples(args.outputs),controls=controls(args.samples))
    text=json.dumps(result,indent=2,default=lambda x:x.item())
    args.save.write_text(text+'\n',encoding='utf-8')
    print(text)
