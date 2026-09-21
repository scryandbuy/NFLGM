import numpy as np, collections, json, rosters as R, game as G, plays as P, schemes as S
rng = np.random.default_rng(2026)
L = R.load_league(); teams = sorted(L)
co = lambda d,di,sd,ytg,r: S.call_offense(d,di,sd,ytg,r)
cd = lambda oc,d,di,r,ytg=50: S.call_defense(oc,d,di,r,yards_to_endzone=ytg)
coaches = {t: dict(
    adjust_skill=float(np.clip(rng.normal(.55,.18),.1,.95)),
    adjust_willingness=float(np.clip(rng.normal(.55,.2),.1,.95)),
    man_rate=float(np.clip(rng.normal(.35,.12),.12,.62)),
    blitz_rate=float(np.clip(rng.normal(.133,.05),.05,.28)),
    travel_willingness=float(np.clip(rng.normal(.5,.22),.05,.95)),
    off_script_skill=float(np.clip(rng.normal(.5,.2),.1,.9))) for t in teams}
pts=[]; byteam=collections.defaultdict(list); fgatt=0; fgmade=0; res=collections.Counter()
for s in range(2):
    ST={t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
    for wk in range(17):
        o=list(teams); rng.shuffle(o)
        for i in range(0,32,2):
            h,a=o[i],o[i+1]
            r=G.play_game(L[h],L[a],rng,P.resolve_play,co,cd,P.rate,
                          home_state=ST[h],away_state=ST[a],week=wk+1)
            pts += [r['home'], r['away']]
            byteam[h].append(r['home']); byteam[a].append(r['away'])
            for _,d in r['drives']:
                res[d.result]+=1
                for l in d.log:
                    if isinstance(l,dict) and l.get('type')=='field_goal':
                        fgatt+=1; fgmade+= 1 if l.get('made') else 0
tm = {t: round(float(np.mean(v)),2) for t,v in byteam.items()}
out=dict(pts_mean=round(float(np.mean(pts)),3), pts_sd=round(float(np.std(pts)),3),
         team_mean_sd=round(float(np.std(list(tm.values()))),3),
         best=max(tm.values()), worst=min(tm.values()),
         fg_att_per_game=round(fgatt/544,3), fg_pct=round(100*fgmade/max(fgatt,1),2),
         results={k:v for k,v in res.most_common()})
json.dump(out, open('/tmp/diag_py.json','w'))
print(json.dumps(out, indent=1))
