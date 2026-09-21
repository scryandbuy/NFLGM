import json, numpy as np, collections, rosters as R, game as G

L = R.load_league(); teams = sorted(L)
A = L[teams[0]]

def slim(p):
    if p is None: return None
    return {k: (float(v) if isinstance(v,(int,float)) else v)
            for k,v in p.items() if k in ('pid','pos') or k.endswith('_rating')}

rost = {}
for k in ('qb','rb','k','p','kr'):
    rost[k] = slim(A.get(k))
for k in ('qbs','backs','wr','extra_blockers','ol','dl','lb','db'):
    rost[k] = [slim(x) for x in (A.get(k) or [])]
json.dump(rost, open('/tmp/roster_fixture.json','w'))

out = {}
# ---- packageUnits: fully deterministic ----
import targets as TG
pk = []
for pkg in sorted(TG.OFF_PACKAGES):
    r = G.package_units(A, None, None, True, pkg)
    pk.append(['off', pkg, None if r is None else {k:[p['pid'] for p in v] for k,v in r.items()}])
for pkg in sorted(TG.DEF_PACKAGES):
    r = G.package_units(A, None, None, False, pkg)
    pk.append(['def', pkg, None if r is None else {k:[p['pid'] for p in v] for k,v in r.items()}])
pk.append(['off','nonsense', G.package_units(A, None, None, True, 'nonsense')])
out['package'] = pk

# ---- sideline_recovery arithmetic ----
import health as H
sr = []
for snaps in (0, 3, 6, 11, 12, 30, 47, 60):
    st = G.TeamState(A)
    for i, pid in enumerate(['a','b','c']):
        st.cond.cond[pid] = [20.0, 55.0, 99.0][i]
    st.sideline_recovery(snaps)
    sr.append([snaps, {k: round(v,10) for k,v in sorted(st.cond.cond.items())}])
out['sideline'] = sr

# ---- end_game arithmetic ----
eg = []
for snaps in (10, 45, 80):
    st = G.TeamState(A)
    st.snaps = {'a': snaps, 'b': snaps//2}
    st.sharp = {'a': 88.0}
    st.jaded = {'b': 0.3}
    st.end_game(None, 45.0, False)
    eg.append([snaps, {k: round(v,10) for k,v in sorted(st.sharp.items())},
               {k: round(v,10) for k,v in sorted(st.jaded.items())}])
out['endgame'] = eg

# ---- available() with men ruled out ----
av = []
st = G.TeamState(A)
ol = A['ol']
st.out = {ol[0]['pid'], ol[2]['pid']}
av.append([[p['pid'] for p in st.available(ol, 'LT')]])
st.out = {p['pid'] for p in ol}
av.append([[p['pid'] for p in st.available(ol, 'LT')]])
out['available'] = av

# ---- fieldUnits: statistical snap share ----
rng = np.random.default_rng(31)
st = G.TeamState(A, coach={})
N = 12000
snapshare = collections.Counter()
for i in range(N):
    pkg = ['11','12','10','21','13'][i % 5]
    f, pos = G.field_units(A, st, rng, True, pkg)
    if i % 2 == 0:
        st.sideline_recovery(6)
share = {k: round(v/N,4) for k,v in st.snaps.items()}
out['snapshare_off'] = dict(n=N, top=sorted(share.items(), key=lambda kv:-kv[1])[:14],
                            distinct=len(share),
                            mean_cond=round(float(np.mean(list(st.cond.cond.values()))),3))

rng = np.random.default_rng(31)
st2 = G.TeamState(A, coach={})
for i in range(N):
    pkg = ['base','nickel','dime'][i % 3]
    f, pos = G.field_units(A, st2, rng, False, pkg)
    if i % 2 == 0:
        st2.sideline_recovery(6)
share2 = {k: round(v/N,4) for k,v in st2.snaps.items()}
out['snapshare_def'] = dict(n=N, top=sorted(share2.items(), key=lambda kv:-kv[1])[:14],
                            distinct=len(share2),
                            mean_cond=round(float(np.mean(list(st2.cond.cond.values()))),3))

json.dump(out, open('/tmp/state_py.json','w'))
print('package:', len(pk), 'sideline:', len(sr), 'endgame:', len(eg))
print('off distinct:', out['snapshare_off']['distinct'], 'mean cond', out['snapshare_off']['mean_cond'])
print('def distinct:', out['snapshare_def']['distinct'], 'mean cond', out['snapshare_def']['mean_cond'])
