import json,collections,statistics as st
from pathlib import Path
s=json.loads(Path('C:/Users/HP/Downloads/nflgm-2027-offseason-0.json').read_text())
byweek=collections.defaultdict(collections.Counter)
for key,b in s['game_stats'].items():
 if not key.startswith('2027-'):continue
 w=int(key.split('-')[1]);byweek[w]['games']+=1
 for d in b.values():
  for k in ('pass_att','pass_cmp','pass_yds','rush_att','rush_yds','sacked','pressures','pr_reps','pr_wins','rush_plays','pass_plays'):byweek[w][k]+=d.get(k,0)
print('weekly weeks,games,ppg,cmp,ypc,sack%,pressure/dropback,pass-rush win%')
for w,t in sorted(byweek.items()):
 pts=sum(g[3]+g[4] for g in s['schedule'] if g[0]==w)
 print(w,t['games'],round(pts/(2*t['games']),1),round(t['pass_cmp']/t['pass_att'],3),round(t['rush_yds']/t['rush_att'],2),round(t['sacked']/(t['pass_att']+t['sacked']),3),round(t['pressures']/(t['pass_att']+t['sacked']),3),round(t['pr_wins']/max(1,t['pr_reps']),3))
print('tendency ranges incl playoffs')
for k,den in [('passes','plays'),('pa','passes'),('motion','plays'),('blitz','def_snaps'),('two_high','def_snaps'),('fourth_go','fourth_opp')]:
 vals=sorted((round(d.get(k,0)/max(1,d.get(den,0)),3),a) for a,d in s['tendencies']['2027'].items());print(k,vals[:3],vals[-3:])
for w in (8,14,22):
 m=next(m for m in s['inbox'] if m['year']==2027 and m['week']==w and 'Assistant review:' in m['subject']);c=m['payload']['coaching_review'];print('coaching',w,str(c)[:1400])
print('unicode replacement chars',sum(m['body'].count('\ufffd')+m['subject'].count('\ufffd') for m in s['inbox']))
print('GB record',s['teams']['GB']['record'])
print('qb games',[(s['players'][pid]['name'],d.get('games'),round(d.get('pass_yds',0))) for pid,d in s['stats']['2027'].items() if d.get('pass_att',0)>450])
