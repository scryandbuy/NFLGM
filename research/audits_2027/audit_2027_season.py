import json,collections,statistics as st
from pathlib import Path
s=json.loads(Path('C:/Users/HP/Downloads/nflgm-2027-offseason-0.json').read_text())
games=[g for g in s['schedule'] if g[0]<=18];book=s['stats']['2027'];tot=collections.Counter()
for d in book.values():
 for k,v in d.items():
  if isinstance(v,(float,int)):tot[k]+=v
print('regular games',len(games),'unfinished',sum(g[3] is None for g in games),'points/team/game',sum(g[3]+g[4] for g in games)/544)
print('margins',dict(close8=sum(abs(g[3]-g[4])<=8 for g in games),blowout21=sum(abs(g[3]-g[4])>=21 for g in games),ties=sum(g[3]==g[4] for g in games)))
print('totals',dict(tot))
print('rates',dict(cmp=tot['pass_cmp']/tot['pass_att'],ypa=tot['pass_yds']/tot['pass_att'],ypc=tot['rush_yds']/tot['rush_att'],sack=tot['sacked']/(tot['pass_att']+tot['sacked']),int=tot['ints']/tot['pass_att'],fg=tot['fg_made']/tot['fg_att']))
print('inbox2027 kinds',collections.Counter(m['kind'] for m in s['inbox'] if m['year']==2027))
for k in ('pass_yds','rush_yds','rec_yds','sacks'):
 print('leaders',k,[(s['players'].get(pid,{}).get('name'),round(d.get(k,0),1)) for pid,d in sorted(book.items(),key=lambda kv:-kv[1].get(k,0))[:8]])
print('GB games')
for k,d in s['_gamedays'].items():
 if not k.startswith('2027'):continue
 g=d.get('game')
 if g: print(k,g['opp'],g['hs'],g['as_'],'env',g.get('env'), 'plays',sum(len(dr['plays']) for dr in g['drives']))
print('awards',s['awards'].keys(),'almanac',s['almanac'].keys())
