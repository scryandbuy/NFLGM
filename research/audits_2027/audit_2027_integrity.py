import json,collections,statistics as st
from pathlib import Path
s=json.loads(Path('C:/Users/HP/Downloads/nflgm-2027-offseason-0.json').read_text())
# Accounting per game and season
ks=['pass_att','pass_cmp','pass_yds','pass_td','ints','sacked','rush_att','rush_yds','rush_td','rec','rec_yds','rec_td','sacks','int_def','fg_att','fg_made']
agg=collections.defaultdict(collections.Counter);bad=[];aff=[]
for key,b in s['game_stats'].items():
 if not key.startswith('2027-'):continue
 week=int(key.split('-')[1]);t=collections.Counter()
 for pid,d in b.items():
  for k in ks:t[k]+=d.get(k,0);agg[(week<=18,pid)][k]+=d.get(k,0)
 if any(abs(t[a]-t[b])>.01 for a,b in [('pass_cmp','rec'),('pass_yds','rec_yds'),('pass_td','rec_td'),('sacked','sacks'),('ints','int_def')]):bad.append((key,dict(t)))
 aff.append((week,sum('team' in d for d in b.values()),len(b)))
mismatch=[]
for (reg,pid),d in agg.items():
 target=s['stats' if reg else 'post_stats'].get('2027',{}).get(pid,{})
 for k,v in d.items():
  if abs(v-target.get(k,0))>.02:mismatch.append((reg,pid,k,round(v-target.get(k,0),2)))
print('game conservation failures',len(bad),bad[:2]);print('season rollup mismatches',len(mismatch),mismatch[:15]);print('attribution by week',[(w,sum(n for ww,n,z in aff if w==ww),sum(z for ww,n,z in aff if w==ww)) for w in range(1,23)])
msgs=[m for m in s['inbox'] if m['year']==2027]
for m in msgs:
 if m['kind'] in ('practice','roster_report') or 'Player of the Week' in m['subject']:print('msg',m['week'],m['kind'],m['subject'],str(m.get('payload',{}))[:100])
print('dupes',[(k,len(v)) for k,v in __import__('itertools').groupby([])])
c=collections.Counter((m['week'],m['subject']) for m in msgs);print('exact subject dupes',[(k,n) for k,n in c.items() if n>1][:20])
print('review email kinds',[(m['week'],m['kind'],m['subject'],list(m.get('payload',{}))) for m in msgs if 'review:' in m['subject'].lower() or 'snap counts' in m['subject'].lower()])
print('plan keys',s['user_week_plan'].keys());print('gamedaykeys',s['_gamedays']['2027-22']['game'].keys())
