import json,collections
from pathlib import Path
s=json.loads(Path('C:/Users/HP/Downloads/nflgm-2027-offseason-0.json').read_text());P=s['players'];stats=s['stats']['2027'];T=collections.defaultdict(collections.Counter)
for key,b in s['game_stats'].items():
 if not key.startswith('2027-') or int(key.split('-')[1])>18:continue
 for pid,d in b.items():
  for k,v in d.items():
   if isinstance(v,(int,float)):T[d['team']][k]+=v
print('sack shares',collections.Counter({pos:sum(d.get('sacks',0) for pid,d in stats.items() if P.get(pid,{}).get('pos')==pos) for pos in set(p['pos'] for p in P.values())}))
print('QB rushing leaders',[(P[pid]['name'],d['rush_att'],round(d['rush_yds']),d.get('rush_td')) for pid,d in sorted(stats.items(),key=lambda kv:-kv[1].get('rush_yds',0)) if P[pid]['pos']=='QB'][:10])
for a in ('GB','LV','NYG','CIN'):
 t=T[a];gp=17
 print(a,'ppg',sum(g[4] if g[2]==a else g[3] for g in s['schedule'] if g[0]<=18 and a in g[1:3])/17,'rushypc',t['rush_yds']/t['rush_att'],'sacks',t['sacked'],'passatt',t['pass_att'])
print('gameday conservation')
null=0;types=collections.Counter();fg=collections.defaultdict(lambda:[0,0]);third=[0,0];short=[0,0];timeouts=[]
for key,day in s['_gamedays'].items():
 if not key.startswith('2027-') or not day.get('game'):continue
 game=day['game'];score={game['home']:0,game['away']:0}
 for dr in game['drives']:
  pts=dr['points'];a=dr['off'];opp=game['away'] if a==game['home'] else game['home'];score[a if pts>=0 else opp]+=abs(pts)
  plays=dr['plays']
  for i,p in enumerate(plays):
   types[p['type']]+=1
   if p.get('nullified'):null+=1;continue
   if p['type']=='timeout':timeouts.append((key,p['text']))
   if p.get('down')==3 and p['type'] in ('run','scramble','complete','incomplete','drop','interception','sack'):
    success=p.get('td') or (p.get('yards',0)>=p.get('togo',99) and not p.get('fumble_lost') and p['type'] in ('run','scramble','complete'))
    third[0]+=bool(success);third[1]+=1
    if p['type']=='run' and p.get('togo',99)<=2:short[0]+=bool(success);short[1]+=1
   if p['type']=='field_goal':
    import re
    m=re.search(r'(\d+)-yard',p['text'])
    if m:
     dist=int(m[1]);bucket='60+' if dist>=60 else '50-59' if dist>=50 else '40-49' if dist>=40 else '<40';fg[bucket][1]+=1;fg[bucket][0]+=bool(p.get('made'))
 if score!={game['home']:game['hs'],game['away']:game['as_']}:print('score mismatch',key,score,game['hs'],game['as_'])
print('nullified',null,'third',third,'short_run_third',short,'kicks',dict(fg),'types',dict(types))
print('dead inbox entity ids',[(m['id'],e['id']) for m in s['inbox'] for e in m.get('entities',[]) if e.get('kind')=='player' and e['id'] not in P][:10])
print('max recorded games',max(d.get('games',0) for d in stats.values()))
