"""Summarize recorded study evidence; does not run or modify the game."""
import json
from pathlib import Path
p=Path('../../outputs/coaching-adaptation-session-93041.json')
d=json.loads(p.read_text()); checkpoint=json.loads(Path(str(p)+'.checkpoint').read_text())
d['controlled_hires']=[e for e in checkpoint['transactions'] if e.get('kind')=='gm_change' and e.get('hired','').startswith('Study ')]
d['cleanup_failures']=[{k:r[k] for k in ('year','team','count','cap')} for r in d['snapshots'] if r['stage']=='cutdown' and r['count']!=53]
d['limitations']+=' DEN2027 cutdown and later excluded from adaptation inference due to underfilled roster; conditional cap/roster gate failure, not natural incidence estimate.'
p.write_text(json.dumps(d,indent=2))
lines=[]
for r in d['snapshots']:
    if r['stage'] in ('before_hire','after_hire','cutdown'):
        lines.append(f"{r['team']} {r['year']} {r['stage']}: active={r['count']}, cap={r['cap']:.2f}, fit={r['fit']:.3f}, package offense={r['quality']['offense']:.2f}, defense={r['quality']['defense']:.2f}; positions={r['positions']}")
lines.append('Draft counts: '+str(d['draft_counts']))
lines.append('Controlled hires: '+str(d['controlled_hires']))
lines.append('Cleanup failures: '+str(d['cleanup_failures']))
Path('../../outputs/coaching-adaptation-summary.txt').write_text('\n'.join(lines))
print('\n'.join(lines))
