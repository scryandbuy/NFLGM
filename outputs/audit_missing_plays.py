import json
from pathlib import Path
from collections import Counter
from session import Session
import gameday,ticker
s=Session.load(Path('C:/Users/HP/Downloads/nflgm-2032-week-5.json').read_text(encoding='utf-8'))
r=s.runner;r.last_games=[];r.open_live('GB','DET',5,playoffs=True)
previous=[];hidden=Counter();replaced=[];losses=[];steps=0
while not r.live['done']:
    r.live_step('resume' if r.live['halftime_open'] else 'play');steps+=1
    raw=r.live['res'] if r.live['done'] else r.live_partial()
    data=gameday.capture(s.L,[('GB','DET',raw,r.live['book'])],'GB',states=r.states)['game']
    rows=[(d['n'],p['type'],p['head'],p['text']) for d in data['drives'] for p in d['plays'] if p['text']]
    # Stable event order should only extend (quarter metadata aside).
    if rows[:len(previous)]!=previous:losses.append(steps)
    new=rows[len(previous):]
    main=[p for p in new if p[1] in ('run','scramble','complete','incomplete','drop','interception','sack','punt','field_goal','kickoff','kneel','spike')]
    if main and new[-1]!=main[-1]:replaced.append(dict(step=steps,events=[p[1] for p in new],actual=main[-1][3],latest=new[-1][3]))
    previous=rows
for pos,dr in raw['drives']:
    for p in dr.log:
        if not ticker.play_line(s.L,p,'GB' if pos=='home' else 'DET','DET' if pos=='home' else 'GB'):hidden[p.get('type')]+=1
print(json.dumps(dict(steps=steps,visible_events=len(previous),shrinking_or_reordered=losses,unwritten_types=dict(hidden),latest_replaced_count=len(replaced),examples=replaced[:8]),indent=2))
Path('outputs/broadcast/missing_play_audit.json').write_text(json.dumps(dict(steps=steps,visible_events=len(previous),lost=losses,unwritten=dict(hidden),replaced=replaced),indent=2),encoding='utf-8')
