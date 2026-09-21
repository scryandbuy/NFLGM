import numpy as np
from firing import pressure, fire_chance_offseason, fire_chance_inseason, job_security

PASS = FAIL = 0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  [ok  ] {name}')
    else:    FAIL += 1; print(f'  [FAIL] {name}   {detail}')

W = lambda w, l: w / (w + l)

print('='*74); print('1. THE REAL CASES FROM THE LAST DECADE'); print('='*74)
CASES = [
 ('Carroll SEA/LV 3-14, yr 1',       dict(win_pct=W(3,14), prev_win_pct=None, tenure=0, playoff_drought=3), .45, True),
 ('Stefanski CLE 5-12, 2 playoffs',  dict(win_pct=W(5,12), prev_win_pct=W(3,14), tenure=5, playoff_drought=2), .40, False),
 ('Flores MIA 9-8, swept NE',        dict(win_pct=W(9,8),  prev_win_pct=W(10,6), tenure=2, playoff_drought=5), .45, False),
 ('Zimmer MIN 8-9',                  dict(win_pct=W(8,9),  prev_win_pct=W(7,9),  tenure=7, playoff_drought=1), .60, False),
 ('Nagy CHI 6-11',                   dict(win_pct=W(6,11), prev_win_pct=W(8,8),  tenure=3, playoff_drought=1), .45, False),
 ('Fontenot ATL 8-9, 8yr drought',   dict(win_pct=W(8,9),  prev_win_pct=W(8,9),  tenure=4, playoff_drought=8), .50, False),
 ('Harbaugh BAL, long tenure good',  dict(win_pct=W(11,6), prev_win_pct=W(12,5), tenure=17, playoff_drought=0), .80, False),
 ('yr-2 coach 3-7 off 7-9',          dict(win_pct=W(3,7),  prev_win_pct=W(7,9),  tenure=1, playoff_drought=4), .40, False),
 ('steady 8-8 guy, no fall',         dict(win_pct=W(8,9),  prev_win_pct=W(8,9),  tenure=4, playoff_drought=3), .50, False),
 ('rebuild yr1, 4-13, young QB',     dict(win_pct=W(4,13), prev_win_pct=W(3,14), tenure=0, playoff_drought=6), .25, True),
]
print(f'  {"case":36s} {"pressure":>9s} {"fire%":>7s} {"security":>9s}')
for lbl, h, rost, qb in CASES:
    print(f'  {lbl:36s} {pressure(h,rost,qb):9.2f} {fire_chance_offseason(h,rost,qb)*100:6.1f}% {job_security(h,rost,qb):9.2f}')

fired = dict(CASES[1][1]); safe = dict(CASES[6][1])
# Stefanski at 5-12 off a 3-14 season is an IMPROVEMENT, so the model reads him
# as safer than his record suggests. He was still fired, which is the drought and
# the roster talking. The bar here is that he is not comfortable, not that he is
# doomed.
check('a 5-12 coach is not comfortable',
      fire_chance_offseason(CASES[1][1], .40, False) > 0.08,
      f'{fire_chance_offseason(CASES[1][1], .40, False):.3f}')
check('a long-tenured winner is safe',
      fire_chance_offseason(CASES[6][1], .80, False) < 0.10)
check('8-9 with an 8-year drought beats 8-9 without one',
      fire_chance_offseason(CASES[5][1], .50) > fire_chance_offseason(CASES[8][1], .50))
check('a young QB developing buys real patience',
      fire_chance_offseason(CASES[9][1], .25, True) < fire_chance_offseason(CASES[9][1], .25, False))

print('\n' + '='*74); print('2. REGRESSION MATTERS MORE THAN RECORD'); print('='*74)
print(f'  {"this yr":>8s} {"last yr":>8s} {"pressure":>9s} {"fire%":>7s}')
for now, prev in [(W(6,11), W(12,5)), (W(6,11), W(6,11)), (W(6,11), W(3,14)),
                  (W(9,8),  W(14,3)), (W(9,8),  W(9,8))]:
    h = dict(win_pct=now, prev_win_pct=prev, tenure=3, playoff_drought=2)
    print(f'  {now:8.3f} {prev:8.3f} {pressure(h,.5):9.2f} {fire_chance_offseason(h,.5)*100:6.1f}%')
a = fire_chance_offseason(dict(win_pct=W(6,11), prev_win_pct=W(12,5), tenure=3, playoff_drought=2), .5)
b = fire_chance_offseason(dict(win_pct=W(6,11), prev_win_pct=W(3,14),  tenure=3, playoff_drought=2), .5)
check('the same 6-11 is far more dangerous after 12-5 than after 3-14', a > b * 1.6, f'{a:.2f} vs {b:.2f}')

print('\n' + '='*74); print('3. TENURE'); print('='*74)
print(f'  {"tenure":>7s} {"fire% at 5-12 off 9-8":>24s}')
for t in [0, 1, 2, 3, 5, 8, 12]:
    h = dict(win_pct=W(5,12), prev_win_pct=W(9,8), tenure=t, playoff_drought=2)
    print(f'  {t:7d} {fire_chance_offseason(h,.5)*100:23.1f}%')

print('\n' + '='*74); print('4. IN-SEASON FIRINGS CLUSTER AT WEEK 10'); print('='*74)
h = dict(win_pct=W(2,8), prev_win_pct=W(9,8), tenure=2, playoff_drought=4)
print(f'  a 2-8 team, off a 9-8 season:')
for wk in range(4, 18, 2):
    print(f'    week {wk:2d}: {fire_chance_inseason(h, wk, .5)*100:5.2f}%')
peak = max(range(4,18), key=lambda w: fire_chance_inseason(h,w,.5))
check('in-season firing peaks around week 10-11', 9 <= peak <= 12, str(peak))
check('nobody is fired before week 5', fire_chance_inseason(h, 3, .5) == 0.0)
ok = dict(win_pct=W(5,5), prev_win_pct=W(8,9), tenure=3, playoff_drought=2)
check('a merely disappointing team is not fired mid-season',
      fire_chance_inseason(ok, 10, .5) < 0.02)

print('\n' + '='*74); print('5. DOES THE REAL BASE RATE EMERGE? (validation, not a quota)'); print('='*74)
rng = np.random.default_rng(4)
teams = []
for i in range(32):
    teams.append(dict(win_pct=float(np.clip(rng.normal(.5,.16),.06,.94)),
                      prev_win_pct=float(np.clip(rng.normal(.5,.16),.06,.94)),
                      tenure=int(rng.integers(0,9)),
                      playoff_drought=int(rng.integers(0,10)),
                      roster=float(np.clip(rng.normal(.5,.18),.1,.9))))
SEASONS = 400
tot_off = tot_in = 0
for s in range(SEASONS):
    for t in teams:
        t['win_pct'] = float(np.clip(rng.normal(.5,.16),.06,.94))
        t['prev_win_pct'] = float(np.clip(rng.normal(.5,.16),.06,.94))
        t['tenure'] = int(rng.integers(0,9))
        t['playoff_drought'] = int(rng.integers(0,10))
        h = {k: t[k] for k in ('win_pct','prev_win_pct','tenure','playoff_drought')}
        gone = False
        for wk in range(5, 18):
            if rng.random() < fire_chance_inseason(h, wk, t['roster']):
                tot_in += 1; gone = True; break
        if not gone and rng.random() < fire_chance_offseason(h, t['roster']):
            tot_off += 1
per_season = (tot_off + tot_in) / SEASONS
print(f'  over {SEASONS} simulated seasons of 32 teams:')
print(f'    changes per season: {per_season:.2f}  ({per_season/32*100:.1f}% of teams)')
print(f'    of those, in-season: {tot_in/(tot_in+tot_off)*100:.1f}%')
print(f'  real NFL: 6.5 per season (20.3%), in-season roughly 3 of 6.5 in recent years')
check('base rate lands near the real 6.5 per season', 4.0 <= per_season <= 9.5, f'{per_season:.2f}')
check('in-season is a real but minority path', 0.05 < tot_in/(tot_in+tot_off) < 0.55,
      f'{tot_in/(tot_in+tot_off):.2f}')

print('\n' + '='*74); print('6. JOB SECURITY FEEDS THE GM ENGINE'); print('='*74)
import gm as G
rng2 = np.random.default_rng(3)
team = dict(win_pct=.30, depth={'QB':[74,62]}, expiring={}, top_apy={})
qb = dict(now=5.0, later=24.0, cost=6.0, dead=0, age=22, pos='QB', pedigree=.95,
          ours=False, availability=1.0)
for lbl, h, rost in [('safe: long tenure, winning', dict(win_pct=W(12,5), prev_win_pct=W(11,6), tenure=7, playoff_drought=0), .7),
                     ('hot seat: 3-7 off 9-8',      dict(win_pct=W(3,7),  prev_win_pct=W(9,8),  tenure=2, playoff_drought=4), .5)]:
    g = G.make_gm(rng2, 'balanced')
    g.job_security = job_security(h, rost)
    v = G.value(qb, g, team, 'draft', ctx=dict(round=1, scheme_fit=1.0))
    print(f'  {lbl:30s} security {g.job_security:.2f} -> need-filling QB valued {v["total"]:6.2f}')

print('\n' + '='*74)
print(f'RESULT: {PASS} passed, {FAIL} failed')
print('='*74)
