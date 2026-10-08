import copy,json,time
from pathlib import Path
from session import Session
import views
start=time.perf_counter()
s=Session.load(Path('C:/Users/HP/Downloads/nflgm-2032-week-5.json').read_text(encoding='utf-8'))
out=Path('outputs/broadcast')
def write(name,v):
    (out/(name+'.json')).write_text(json.dumps(v),encoding='utf-8')
write('legacy',s.gameday_view(week=4))
print('loaded',round(time.perf_counter()-start,2),flush=True)
r=s.runner
if r is None:
    from season import SeasonRunner
    r=s.runner=SeasonRunner(s.L,s.rng)
r.last_games=[]
h,a='GB','DET'
r.open_live(h,a,5,playoffs=True)
s.played=True
for i in range(8):
    r.live_step('play')
state=copy.deepcopy(s.rng.bit_generator.state);book=copy.deepcopy(r.live['book'].p)
v=s.gameday_view();write('live',v)
assert state==s.rng.bit_generator.state and book==r.live['book'].p
assert v['game']['box_version']==2
r.live_step('finish');write('halftime',s.gameday_view())
assert r.live['halftime_open']
r.live_step('resume');r.live_step('finish')
while not r.live['done']:
    r.live_step('resume' if r.live['halftime_open'] else 'finish')
s._capture_gameday(5);write('final',views.gameday(s,s.L,s.user_team,gd=s.gameday))
print('finished',round(time.perf_counter()-start,2), 'score',s.gameday['game']['hs'],s.gameday['game']['as_'],flush=True)
print({k:len(v) for k,v in s.gameday['game']['box'].items()},flush=True)

