import numpy as np, collections, rosters as R, game as G, plays as P, schemes as S
rng=np.random.default_rng(5); L=R.load_league(); teams=sorted(L)
co=lambda d,di,sd,ytg,r: S.call_offense(d,di,sd,ytg,r)
cd=lambda oc,d,di,r,ytg=50: S.call_defense(oc,d,di,r,yards_to_endzone=ytg)
coach=dict(adjust_skill=.55,adjust_willingness=.55,man_rate=.35,blitz_rate=.133,travel_willingness=.5,off_script_skill=.5)
ST={t:G.TeamState(L[t],coach=coach) for t in teams}
bands=[(1,2),(3,5),(6,10),(11,15),(16,20),(21,30),(31,50),(51,99)]
td=collections.Counter(); n=collections.Counter(); drives=0; rz=0; rztd=0; alltd=0
o=list(teams); rng.shuffle(o)
for wk in range(3):
  for i in range(0,32,2):
    r=G.play_game(L[o[i]],L[o[i+1]],rng,P.resolve_play,co,cd,P.rate,home_state=ST[o[i]],away_state=ST[o[i+1]],week=wk+1)
    for _s,d in r['drives']:
        drives+=1; y=d.start
        for l in d.log:
            if not isinstance(l,dict) or l.get('type') not in ('run','complete','incomplete','sack','scramble','drop','interception'): continue
            for lo,hi in bands:
                if lo<=y<=hi: n[(lo,hi)]+=1; td[(lo,hi)]+= 1 if l.get('touchdown') else 0
            y=max(1,y-(l.get('yards') or 0))
        if d.best<=20: rz+=1
        if d.result=='Touchdown':
            alltd+=1
            if d.best<=20: rztd+=1
REAL={(1,2):51.6,(3,5):34.3,(6,10):19.5,(11,15):10.1,(16,20):7.1,(21,30):3.8,(31,50):1.7,(51,99):0.6}
print('PER-PLAY TD RATE   sim    real')
for b in bands:
    if n[b]>=60: print('  %-7s %6.1f%% %6.1f%%  %+.1f' % ('%d-%d'%b,100*td[b]/n[b],REAL[b],100*td[b]/n[b]-REAL[b]))
print()
print('reaching the 20: %.1f%%  (real 35.5)' % (100*rz/drives))
print('scoring once there: %.1f%%  (real 61.0)' % (100*rztd/max(rz,1)))
print('all drives TD: %.1f%%  (real 21.8)' % (100*alltd/drives))
