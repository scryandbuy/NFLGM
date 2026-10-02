"""Measurement only: ownership probabilities and decision thresholds."""
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import game as G
import decisions as D
from test_week3_engine import rates

out = {'commit': 'cf70245', 'fourth_down': {}, 'penalty_probabilities': {}}
for aggression in (0., .5, 1.):
    for label, y, need, lead, secs, half, intent in [
        ('half_protect',46,4,3,1811,11,'protect'),
        ('half_attack',46,4,3,1811,11,'attack'),
        ('late_goal',2,2,7,108,None,None)]:
        out['fourth_down'][f'{label}_{aggression}'] = dict(Counter(
            G.fourth_down_decision(y,need,lead,secs,NS(random=lambda v=v:v),
                aggression=aggression,half_seconds_left=half,half_intent=intent,
                is_home=0,timeout_edge=2)
            for v in np.linspace(.0005,.9995,1000)))
for label, kwargs in [
    ('def_low',dict(offense_discipline=.7,defense_discipline=.5)),
    ('def_high',dict(offense_discipline=.7,defense_discipline=.9)),
    ('off_low',dict(offense_discipline=.5,defense_discipline=.7)),
    ('off_high',dict(offense_discipline=.9,defense_discipline=.7)),
    ('hurry',dict(hurry=True))]:
    measured=rates(**kwargs)
    out['penalty_probabilities'][label]={k:measured[k] for k in ('Delay of Game','False Start','Offensive Holding','Defensive Holding')}
out['late_goal_values']=D.fourth_down(7,108,2,2,fg_prob=G.fg_probability(19),is_home=0,timeout_edge=2)
out['limitations']='1000 evenly spaced decision thresholds per scenario; exact penalty probability probes, not sampled game rates. Neutral context, not a reconstruction of the user save.'
Path('week3_fixed_probes.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
