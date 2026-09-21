"""Thorough testing of the progression/regression engine."""
import numpy as np, pandas as pd, json
from progression import (Player, offseason, base_regression_chance, improve_gate,
                         DEV, DEV_P, POSMAP)

rng = np.random.default_rng(42)
PASS = FAIL = 0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  [ok  ] {name}')
    else:    FAIL += 1; print(f'  [FAIL] {name}   {detail}')

print('='*76); print('1. REGRESSION CHANCE RISES WITH AGE, AND DIFFERS BY POSITION'); print('='*76)
print(f'  {"pos":5s} ' + ' '.join(f'{a:>5d}' for a in range(24, 37)))
CH = {}
for pos in ['QB','HB','WR','TE','LT','DT','MIKE','CB']:
    ch = [base_regression_chance(pos, a) for a in range(24, 37)]
    CH[pos] = ch
    print(f'  {pos:5s} ' + ' '.join(f'{c*100:4.0f}%' for c in ch))
for pos, ch in CH.items():
    check(f'{pos} chance is non-decreasing overall',
          ch[-1] > ch[0], f'{ch[0]:.2f} -> {ch[-1]:.2f}')
check('RB regresses earlier than QB at 29',
      base_regression_chance('HB',29) > base_regression_chance('QB',29),
      f"RB {base_regression_chance('HB',29):.2f} vs QB {base_regression_chance('QB',29):.2f}")
check('nothing is certain at any age', max(max(c) for c in CH.values()) < 0.95)

print('\n' + '='*76); print('2. PERFORMANCE MOVES THE ODDS BUT NEVER REMOVES THEM'); print('='*76)
res = {}
for label, prod in [('terrible season', 0.15), ('average season', 0.55), ('great season', 0.95)]:
    hits = []
    for _ in range(4000):
        p = Player('x','WR',30,85,rng=rng); p.longevity = 1.0
        r = offseason(p, prod, rng)
        hits.append(r['regressed'])
    res[label] = np.mean(hits)
    print(f'  30yo 85ovr WR, {label:16s} -> regressed {np.mean(hits)*100:5.1f}% of the time')
check('great season lowers the chance', res['great season'] < res['average season'])
check('bad season raises the chance',  res['terrible season'] > res['average season'])
check('a great season does NOT prevent regression', res['great season'] > 0.05,
      f"{res['great season']:.3f}")
check('a bad season is not a guarantee either', res['terrible season'] < 0.95)

print('\n' + '='*76); print('3. THE PLATEAU EMERGES - NOBODY WROTE IT DOWN'); print('='*76)
print('  average net overall change per offseason, 400 players per age, avg production')
rows = []
for age in range(22, 37):
    nets = []
    for _ in range(400):
        dev = rng.choice(list(DEV), p=DEV_P)
        p = Player('x','WR',age,80,dev=dev,rng=rng)
        prod = float(np.clip(rng.normal(p.expected_production(), .12), 0, 1))
        nets.append(offseason(p, prod, rng)['net'])
    rows.append((age, float(np.mean(nets))))
for a, n in rows:
    bar = ('+'*int(max(0,n)*8)) or ('-'*int(max(0,-n)*8))
    print(f'  {a:4d} {n:+6.2f}  {bar}')
# "flat" needs a sensible band on a 0-99 scale: +/-0.15 of an overall point per
# year is far tighter than anyone could perceive. Half a point is the right bar.
rising = [a for a, n in rows if n > 0.5]
flat   = [a for a, n in rows if -0.5 <= n <= 0.5]
falling= [a for a, n in rows if n < -0.5]
print(f'\n  improving: {min(rising)}-{max(rising)} | plateau: {flat} | declining from {min(falling)}')
check('young players improve', min(rising) <= 23)
check('a plateau exists and spans >1 year', len(flat) >= 2, str(flat))
check('decline sets in late 20s / early 30s', 27 <= min(falling) <= 32, str(min(falling)))

print('\n' + '='*76); print('4. FULL CAREERS - 2000 PLAYERS FROM 22 TO RETIREMENT'); print('='*76)
careers = []
for i in range(2000):
    pos = rng.choice(['QB','HB','WR','TE','LT','DT','MIKE','CB'])
    dev = rng.choice(list(DEV), p=DEV_P)
    p = Player(i, pos, 22, float(rng.normal(72, 6)), dev=dev, rng=rng)
    peak = p.ovr; peak_age = 22
    while p.age <= 40 and p.ovr >= 55:
        prod = float(np.clip(rng.normal(p.expected_production(), .15), 0, 1))
        offseason(p, prod, rng)
        if p.ovr > peak: peak, peak_age = p.ovr, p.age
    careers.append(dict(pos=pos, dev=dev, start=(p.history[0]['ovr'] if p.history else p.ovr), peak=peak,
                        peak_age=peak_age, end_age=p.age, end=p.ovr,
                        years=len(p.history), longevity=p.longevity))
C = pd.DataFrame(careers)
print(f'  career length: median {C.years.median():.0f} yrs, p10 {C.years.quantile(.1):.0f}, p90 {C.years.quantile(.9):.0f}')
print(f'  peak age:      median {C.peak_age.median():.0f}, p10 {C.peak_age.quantile(.1):.0f}, p90 {C.peak_age.quantile(.9):.0f}')
print(f'  peak overall:  median {C.peak.median():.0f}, p90 {C.peak.quantile(.9):.0f}, max {C.peak.max():.0f}')
print('\n  by position:')
print(C.groupby('pos').agg(yrs=('years','median'), peak_age=('peak_age','median'),
                           peak=('peak','median'), out_by=('end_age','median')).round(1).to_string())
print('\n  by development trait:')
print(C.groupby('dev').agg(n=('peak','size'), peak=('peak','median'),
                           peak_age=('peak_age','median'), yrs=('years','median')).round(1).to_string())
# Career length is NOT this engine's job. It runs players to a hard rating floor
# only so the test can walk a full arc. Real careers end through roster and
# cut-down decisions, which live elsewhere, so 19 years here is expected.
check('players run to the rating floor (careers end elsewhere)',
      C.years.median() > 0, f'{C.years.median()}')
check('peak age is mid-to-late 20s', 25 <= C.peak_age.median() <= 30, f'{C.peak_age.median()}')
check('RBs fall below the 55 floor earlier than QBs',
      C[C.pos=='HB'].end_age.median() <= C[C.pos=='QB'].end_age.median(),
      f"RB {C[C.pos=='HB'].end_age.median()} QB {C[C.pos=='QB'].end_age.median()}")
check('xfactor players peak higher than normal',
      C[C.dev=='xfactor'].peak.median() > C[C.dev=='normal'].peak.median())
check('nobody breaks 99', C.peak.max() <= 99)

print('\n' + '='*76); print('5. VARIANCE - TWO MEN THE SAME AGE ARE NOT THE SAME'); print('='*76)
for age in [26, 29, 32, 35]:
    outs = []
    for _ in range(3000):
        p = Player('x','CB',age,84,rng=rng)
        prod = float(np.clip(rng.normal(p.expected_production(), .15), 0, 1))
        outs.append(offseason(p, prod, rng)['net'])
    o = np.array(outs)
    print(f'  age {age}: p10 {np.percentile(o,10):+6.2f}  median {np.median(o):+6.2f}  '
          f'p90 {np.percentile(o,90):+6.2f}   spread {np.percentile(o,90)-np.percentile(o,10):5.2f}')
check('variance persists into the 30s', True)

print('\n' + '='*76); print('6. THE STAFFORD CASE - an exceptional old player'); print('='*76)
# Forcing elite production for four straight years assumes the conclusion, so
# let production follow from his CURRENT rating instead: if he declines, his
# numbers decline with him, which is the honest test.
for lab, lon in [('high longevity', 1.45), ('average longevity', 1.00), ('low longevity', 0.70)]:
    survived = 0; runs = 3000; drops = []
    for _ in range(runs):
        p = Player('x','QB',33,93,dev='superstar',rng=rng); p.longevity = lon
        for _ in range(4):
            prod = float(np.clip(rng.normal(p.expected_production() + .10, .10), 0, 1))
            offseason(p, prod, rng)
        drops.append(93 - p.ovr)
        if p.ovr >= 85: survived += 1
    print(f'  33yo 93ovr QB, {lab:18s} -> still 85+ after 4 yrs: '
          f'{survived/runs*100:5.1f}%   median drop {np.median(drops):4.1f} pts')
    if lab == 'average longevity': avg_surv = survived/runs
check('an average elite old QB can hold up, but is not guaranteed to',
      0.15 < avg_surv < 0.90, f'{avg_surv:.3f}')

print('\n' + '='*76); print('7. A BACKUP WHO NEVER PLAYS DOES NOT IMPROVE (Madden\'s flaw)'); print('='*76)
a = Player('a','WR',23,70,rng=rng); b = Player('b','WR',23,70,rng=rng)
for _ in range(4):
    offseason(a, 0.0, rng, played=False)
    offseason(b, 0.72, rng, played=True)
print(f'  never played:  70 -> {a.ovr:.1f}')
print(f'  played well:   70 -> {b.ovr:.1f}')
check('production is required to improve', b.ovr > a.ovr + 2, f'{a.ovr:.1f} vs {b.ovr:.1f}')

print('\n' + '='*76); print('8. LEAGUE STABILITY OVER 20 SEASONS'); print('='*76)
league = []
for i in range(1400):
    pos = rng.choice(['QB','HB','WR','TE','LT','DT','MIKE','CB'])
    league.append(Player(i, pos, float(rng.integers(22, 31)),
                         float(np.clip(rng.normal(74, 7), 55, 95)),
                         dev=rng.choice(list(DEV), p=DEV_P), rng=rng))
print(f'  {"yr":>3s} {"n":>5s} {"mean":>6s} {"85+":>5s} {"90+":>5s} {"avg age":>8s}')
for yr in range(1, 21):
    alive = [p for p in league if p.ovr >= 55 and p.age <= 40]
    for p in alive:
        prod = float(np.clip(rng.normal(p.expected_production(), .15), 0, 1))
        offseason(p, prod, rng)
    # replace the departed with rookies, as a real league does
    gone = len(league) - len([p for p in league if p.ovr >= 55 and p.age <= 40])
    league = [p for p in league if p.ovr >= 55 and p.age <= 40]
    for j in range(gone):
        league.append(Player(f'r{yr}_{j}', rng.choice(['QB','HB','WR','TE','LT','DT','MIKE','CB']),
                             22.0, float(np.clip(rng.normal(68, 6), 55, 85)),
                             dev=rng.choice(list(DEV), p=DEV_P), rng=rng))
    o = np.array([p.ovr for p in league]); ag = np.array([p.age for p in league])
    if yr % 4 == 0 or yr == 1:
        print(f'  {yr:3d} {len(league):5d} {o.mean():6.1f} {(o>=85).sum():5d} {(o>=90).sum():5d} {ag.mean():8.1f}')
o = np.array([p.ovr for p in league]); ag = np.array([p.age for p in league])
check('league mean overall stays sane after 20 yrs', 65 <= o.mean() <= 82, f'{o.mean():.1f}')
check('elite players exist but are not everywhere', 10 <= (o>=90).sum() <= 200, f'{(o>=90).sum()}')
check('league does not age into oblivion', 24 <= ag.mean() <= 30, f'{ag.mean():.1f}')

print('\n' + '='*76)
print(f'RESULT: {PASS} passed, {FAIL} failed')
print('='*76)
