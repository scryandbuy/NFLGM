import numpy as np, schemes as S, plays as P, gm as G

rng = np.random.default_rng(21)
PASS = FAIL = 0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  [ok  ] {name}')
    else:    FAIL += 1; print(f'  [FAIL] {name}   {detail}')

def avg(): return {}
def roster():
    return dict(qb=avg(), rb=avg(), ol=[avg()]*5, wr=[avg()]*5,
                extra_blockers=[avg()]*3)
def defense():
    return dict(dl=[avg()]*5, lb=[avg()]*4, db=[avg()]*6)

print('='*72); print('1. PLAY CALLING vs REAL RATES'); print('='*72)
N = 60000
calls = []
for _ in range(N):
    dn = int(rng.integers(1, 5)); dist = int(rng.integers(1, 16))
    sd = int(rng.normal(0, 10)); ytg = int(rng.integers(3, 95))
    calls.append((dn, dist, S.call_offense(dn, dist, sd, ytg, rng)))

print('  pass rate by down and distance (sim vs real):')
print(f'  {"":5s} ' + ' '.join(f'{b:>11s}' for b in ['1-2','3-4','5-7','8-10','11+']))
maxerr = 0
for dn in [1, 2, 3, 4]:
    row = f'  {dn:<5d} '
    for b in ['1-2','3-4','5-7','8-10','11+']:
        g = [c for d, di, c in calls if d == dn and S.dist_band(di) == b]
        if len(g) < 60: row += f'{"":>11s} '; continue
        sim = np.mean([c['is_pass'] for c in g]) * 100
        real = S.PASS_RATE[dn][b] * 100
        maxerr = max(maxerr, abs(sim - real))
        row += f'{sim:5.1f}/{real:5.1f} '
    print(row)
check('play calling tracks the real down-and-distance table', maxerr < 14, f'max err {maxerr:.1f}')

allc = [c for _, _, c in calls]
for lbl, key, real in [('play action', 'play_action', 10.2), ('screen', 'screen', 4.4),
                       ('RPO', 'rpo', 3.3), ('motion', 'motion', 36.5),
                       ('no huddle', 'no_huddle', 8.5)]:
    sim = np.mean([c.get(key, False) for c in allc]) * 100
    print(f'  {lbl:12s} sim {sim:5.2f}%   real {real:5.2f}%')
check('play action rate is realistic',
      abs(np.mean([c.get('play_action', False) for c in allc])*100 - 10.2) < 4.0)
check('motion rate is realistic',
      abs(np.mean([c['motion'] for c in allc])*100 - 36.5) < 3.0)

print('\n' + '='*72); print('2. DEFENSIVE CALLING vs REAL RATES'); print('='*72)
dcalls = [S.call_defense(c, d, di, rng) for d, di, c in calls[:40000]]
ru = np.array([d['rushers'] for d in dcalls])
bl = np.array([d['blitzers'] for d in dcalls])
print('  pass rushers (sim vs real share of pass plays):')
real_r = {3: 1.77/46.99*100, 4: 33.17/46.99*100, 5: 9.37/46.99*100,
          6: 2.60/46.99*100, 7: 0.46/46.99*100}
for n in [3, 4, 5, 6, 7]:
    print(f'    {n} rushers  sim {(ru==n).mean()*100:5.2f}%   real {real_r[n]:5.2f}%')
print('  blitzers:')
for n, real in [(0, 86.7), (1, 9.7), (2, 3.1), (3, 0.47)]:
    print(f'    {n}  sim {(bl==n).mean()*100:5.2f}%   real {real:5.2f}%')
check('blitz rate is realistic', abs((bl>0).mean()*100 - 13.3) < 5.0,
      f'{(bl>0).mean()*100:.1f}%')

box = np.array([d['box'] for d in dcalls])
print('  defenders in box (sim vs real):')
for n, real in [(5, 10.5), (6, 37.6), (7, 18.3), (8, 4.7)]:
    print(f'    {n}  sim {(box==n).mean()*100:5.2f}%   real {real:5.2f}%')
print(f'  nickel {np.mean([d["personnel"]=="nickel" for d in dcalls])*100:.1f}%  '
      f'base {np.mean([d["personnel"]=="base" for d in dcalls])*100:.1f}%  '
      f'dime {np.mean([d["personnel"]=="dime" for d in dcalls])*100:.1f}%')
print(f'  disguised {np.mean([d["fooled"] for d in dcalls])*100:.1f}%   '
      f'simulated pressure {np.mean([d["sim_pressure"] for d in dcalls])*100:.1f}%')

print('\n' + '='*72); print('3. BOX COUNT DRIVES THE RUN (real: 5.92/4.76/4.16/3.77/2.41)'); print('='*72)
O, D = roster(), defense()
for b in [5, 6, 7, 8, 9]:
    oc = dict(personnel='11', shotgun=False, is_pass=False, scheme='inside_zone', motion=False)
    dc = dict(personnel='nickel', front='4-3 over', rushers=4, blitzers=0,
              shell='cover_3', shown_shell='cover_3', fooled=False, box=b,
              sim_pressure=False, protection_error=0.0, man=False)
    y = [P.resolve_play(O, D, oc, dc, 60, rng)['yards'] for _ in range(6000)]
    print(f'  box {b}: ypc {np.mean(y):5.2f}   real {S.BOX_YPC[b]:5.2f}')
b6 = np.mean([P.resolve_play(O, D, dict(personnel='11',shotgun=False,is_pass=False,scheme='inside_zone',motion=False),
     dict(personnel='nickel',front='4-3 over',rushers=4,blitzers=0,shell='cover_3',shown_shell='cover_3',
          fooled=False,box=6,sim_pressure=False,protection_error=0.0,man=False), 60, rng)['yards'] for _ in range(8000)])
b8 = np.mean([P.resolve_play(O, D, dict(personnel='11',shotgun=False,is_pass=False,scheme='inside_zone',motion=False),
     dict(personnel='nickel',front='4-3 over',rushers=4,blitzers=0,shell='cover_3',shown_shell='cover_3',
          fooled=False,box=8,sim_pressure=False,protection_error=0.0,man=False), 60, rng)['yards'] for _ in range(8000)])
check('a heavier box suppresses the run', b8 < b6 * 0.90, f'{b8:.2f} vs {b6:.2f}')

print('\n' + '='*72); print('4. RUN SCHEME vs FRONT'); print('='*72)
print(f'  {"front":10s} ' + ' '.join(f'{s:>13s}' for s in ['inside_zone','power']))
for fr in ['4-3 over', 'tite', 'bear', 'wide 9']:
    row = f'  {fr:10s} '
    for sc in ['inside_zone', 'power']:
        oc = dict(personnel='11', shotgun=False, is_pass=False, scheme=sc, motion=False)
        dc = dict(personnel='nickel', front=fr, rushers=4, blitzers=0, shell='cover_3',
                  shown_shell='cover_3', fooled=False, box=6, sim_pressure=False,
                  protection_error=0.0, man=False)
        y = np.mean([P.resolve_play(O, D, oc, dc, 60, rng)['yards'] for _ in range(4000)])
        row += f'{y:13.2f} '
    print(row)
def ypc(sc, fr):
    oc = dict(personnel='11', shotgun=False, is_pass=False, scheme=sc, motion=False)
    dc = dict(personnel='nickel', front=fr, rushers=4, blitzers=0, shell='cover_3',
              shown_shell='cover_3', fooled=False, box=6, sim_pressure=False,
              protection_error=0.0, man=False)
    return np.mean([P.resolve_play(O, D, oc, dc, 60, rng)['yards'] for _ in range(5000)])
check('Tite suppresses zone more than gap', ypc('inside_zone','tite') < ypc('power','tite'))
check('Wide 9 is softer against zone than Tite', ypc('inside_zone','wide 9') > ypc('inside_zone','tite'))

print('\n' + '='*72); print('5. BLITZ TRADEOFF (real: 4-man 6.61% sack/61.9% comp, blitz 8.35%/56.1%)'); print('='*72)
for r in [4, 5, 6]:
    oc = dict(personnel='11', shotgun=True, is_pass=True, concept='curl_flat',
              depth='medium', play_action=False, screen=False, rpo=False, motion=False)
    dc = dict(personnel='nickel', front='4-3 over', rushers=r, blitzers=max(0, r-4),
              shell='cover_1' if r >= 5 else 'cover_3', shown_shell='cover_3',
              fooled=False, box=6, sim_pressure=False, protection_error=0.0,
              man=r >= 5)
    out = [P.resolve_play(O, D, oc, dc, 60, rng) for _ in range(9000)]
    sk = np.mean([o['type'] == 'sack' for o in out]) * 100
    att = [o for o in out if o['type'] != 'sack']
    cp = np.mean([o['type'] == 'complete' for o in att]) * 100
    yp = np.mean([o['yards'] for o in out])
    print(f'  {r} rushers: sack {sk:5.2f}%   completion {cp:5.1f}%   ypp {yp:5.2f}')

print('\n' + '='*72); print('6. CONCEPT vs COVERAGE'); print('='*72)
print(f'  {"concept":12s} ' + ' '.join(f'{s:>9s}' for s in ['cover_2','cover_3','cover_4','man']))
for c in ['mesh', 'four_verts', 'scissors', 'flood', 'smash']:
    row = f'  {c:12s} '
    for sh in ['cover_2', 'cover_3', 'cover_4', 'cover_1']:
        row += f'{S.concept_multiplier(c, sh):9.2f} '
    print(row)
check('four verticals is worst against Cover 4', 
      S.concept_multiplier('four_verts','cover_4') < S.concept_multiplier('four_verts','cover_2'))
check('scissors is a quarters beater',
      S.concept_multiplier('scissors','cover_4') > S.concept_multiplier('scissors','cover_2'))
check('mesh is a man beater',
      S.concept_multiplier('mesh','cover_1') > S.concept_multiplier('mesh','cover_3'))

print('\n' + '='*72); print('7. PROTECTION MATH AND HOT ROUTES'); print('='*72)
for pr in ['five', 'half_slide', 'seven', 'max']:
    for r in [4, 6]:
        m = S.protection_math(pr, r)
        print(f'  {pr:11s} vs {r} rushers: {m["blockers"]} blockers, '
              f'{m["free_rushers"]} free, routes lost {m["routes_lost"]}, hot={m["hot"]}')
check('five-man protection is hot against a six-man rush',
      S.protection_math('five', 6)['hot'])
check('max protect blocks a six-man rush', not S.protection_math('max', 6)['hot'])

print('\n' + '='*72); print('8. DISGUISE PUNISHES POOR PROCESSORS'); print('='*72)
eq = dict(awareness_rating=96, play_action_rating=92, throw_under_pressure_rating=93)
bq = dict(awareness_rating=55, play_action_rating=58, throw_under_pressure_rating=50)
for q, lbl in [(eq, 'elite processor'), ({}, 'average'), (bq, 'poor processor')]:
    print(f'  {lbl:17s} penalty when fooled: {S.disguise_penalty(q, True, P.rate):.3f}')
check('an elite processor is barely fooled',
      S.disguise_penalty(eq, True, P.rate) < S.disguise_penalty(bq, True, P.rate) * 0.5)
check('no penalty when not fooled', S.disguise_penalty(bq, False, P.rate) == 0.0)

print('\n' + '='*72)
print(f'RESULT: {PASS} passed, {FAIL} failed')
print('='*72)
