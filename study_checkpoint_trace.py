import json
from pathlib import Path
from collections import Counter
p=Path('../../outputs/coaching-adaptation-session-93041.json.checkpoint')
d=json.loads(p.read_text())
print('keys',list(d))
events=d.get('transactions',[])
print('hire events',json.dumps([e for e in events if e.get('kind') in ('gm_change','position_change')],default=str))
den=[(i,e) for i,e in enumerate(events) if e.get('team')=='DEN' or e.get('a')=='DEN' or e.get('b')=='DEN']
print('DEN event kinds',Counter(e.get('kind',e.get('type')) for _,e in den))
print('DEN last events',json.dumps(den[-100:],default=str))
print('DEN serialized team',json.dumps(d['teams']['DEN'],default=str)[:3000])
report=json.loads(p.with_suffix('').read_text())
for r in report['snapshots']:
    if r['stage'] in ('before_hire','after_hire','cutdown'):
        print('SNAPSHOT',r['team'],r['year'],r['stage'],'count',r['count'],'cap',round(r['cap'],2),'fit',round(r['fit'],3),'quality',r['quality'],'positions',r['positions'])
