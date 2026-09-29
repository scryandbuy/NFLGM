"""Focused catalog FG diagnostic; records attempts without extra RNG draws.
Usage: python -X utf8 check_fg_accuracy.py OUTPUT [games=64] [seeds=2026,51,87]
"""
import sys,json,time
from pathlib import Path
import numpy as np
import game as G, plays as P, calibrate as C

def run(seed,games):
    original_game,original_kick=G.play_game,G.attempt_field_goal
    collector=C.Collector(); kicks=[]; n=0
    class Finished(Exception): pass
    def kick(y,k,rng,rate):
        d=y+17; p=G.fg_probability(d,k,rate)
        env=G.ENV.kick_mult if d>=35 else 1-.3*(1-G.ENV.kick_mult)
        noise=float(k.get('st_noise',1)) if isinstance(k,dict) else 1
        actual=p*env
        if noise!=1: actual=float(np.clip(.5+(actual-.5)/noise,.02,.99))
        result=original_kick(y,k,rng,rate)
        kicks.append(dict(distance=float(d),made=bool(result['made']),neutral=p,probability=actual,
                          power=rate(k,{'kick_power_rating':1}),accuracy=rate(k,{'kick_acc_rating':.75,'awareness_rating':.25}),weather=env,noise=noise))
        return result
    def play(*a,**kw):
        nonlocal n
        if n>=games: raise Finished()
        result=original_game(*a,**kw);collector.add(result);n+=1
        if n%32==0: print(f'seed {seed}: {n} games',flush=True)
        return result
    G.play_game=play;G.attempt_field_goal=kick
    try:
        try:C.run(seed=seed,coaches='catalog',verbose=False)
        except Finished:pass
    finally:G.play_game=original_game;G.attempt_field_goal=original_kick
    def summary(rows):
        return dict(n=len(rows),made=sum(x['made'] for x in rows),actual=100*np.mean([x['made'] for x in rows]) if rows else None,
                    expected=100*np.mean([x['probability'] for x in rows]) if rows else None,
                    neutral=100*np.mean([x['neutral'] for x in rows]) if rows else None)
    out=dict(seed=seed,games=n,total=summary(kicks),metrics=collector.got(),bands={})
    for lo,hi in [(0,29),(29,39),(39,49),(49,54),(54,float('inf'))]:out['bands'][f'{lo}-{hi}']=summary([k for k in kicks if lo<k['distance']<=hi])
    out['kicks']=kicks
    return out

if __name__=='__main__':
    out=Path(sys.argv[1]); games=int(sys.argv[2]) if len(sys.argv)>2 else 64
    seeds=list(map(int,sys.argv[3].split(','))) if len(sys.argv)>3 else [2026,51,87]
    data=[]
    for seed in seeds:
        result=run(seed,games);data.append(result);out.write_text(json.dumps(data,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('kicks','metrics')}),flush=True)
