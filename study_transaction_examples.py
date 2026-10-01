import json
from pathlib import Path
d=json.loads(Path('../../outputs/coaching-adaptation-session-93041.json').read_text())
c=json.loads(Path('../../outputs/coaching-adaptation-session-93041.json.checkpoint').read_text())
for a in ('GB','ATL'):
    print('\nTEAM',a)
    for r in d['snapshots']:
        if r['team']!=a or r['stage'] in ('before_hire','after_hire'):continue
        print(r['year'],r['stage'],'quality',r['quality'],'fit',r['fit'])
        print('arrivals',[(p['name'],p['pos'],round(p['ovr'],1),round(p['fit'],2)) for p in r['arrivals']])
        print('departures',[(p,c['players'].get(p,{}).get('name'),c['players'].get(p,{}).get('pos')) for p in r['departures']])
    print('2028 transaction details')
    for e in d['decisions']:
        if e.get('year')==2028 and (e.get('team')==a or e.get('a')==a or e.get('b')==a) and e.get('kind') not in ('ps_sign','ps_release','udfa_sign'):
            print(e)
