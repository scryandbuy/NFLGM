"""Read what the clubs bought. Decision-driven: ten men across ages, positions,
ceilings and club situations, then the league-wide split of XP by attribute
type and by age."""
import numpy as np, collections, sys
import league as LG, season as SN, xp as XP, xp_spend as XS, targets as TG

rng = np.random.default_rng(2026)
L = LG.build_league(rng=rng)
L.user_team = None
start = {p.pid: (p.ovr, dict(p.ratings), p.potential) for p in L.players.values()}
runner = SN.run_season(L, rng)
year = L.year; stats = L.stats.get(year, {})

ps = [p for p in L.players.values() if not p.retired and XP.points_bought(p) > 0]
print(f'{len(ps)} men bought something during the season')
# league-wide split
spent = collections.Counter(); byage = collections.defaultdict(lambda: [0.0, 0])
for p in L.players.values():
    for k, v in p.xp_spent.items():
        if k.startswith('_'): continue
        kind = 'physical' if k in XP.PHYSICAL else 'awareness' if k == 'awareness_rating' else 'skill'
        spent[kind] += v
    n = XP.points_bought(p)
    if n: byage[int(p.age // 3 * 3)][0] += p.ovr - start[p.pid][0]; byage[int(p.age // 3 * 3)][1] += 1
tot = sum(spent.values())
print('  points bought: ' + ', '.join(f'{k} {v} ({v/tot*100:.0f}%)' for k, v in spent.most_common()))
print('  unlocks bought: ' + str(sum(p.xp_spent.get('_unlocks', 0) for p in L.players.values())) + f'   men at their ceiling now: {sum(1 for p in L.players.values() if not p.retired and XP.at_ceiling(p))}')
print('  mean overall gain among buyers by age: ' + ', '.join(f'{a}-{a+2}: {s/n:+.2f} ({n})' for a, (s, n) in sorted(byage.items()) if n >= 5))
# how spread: for buyers with 8+ points, share of points in their single biggest attribute
conc = [max(v for k, v in p.xp_spent.items() if not k.startswith('_')) / XP.points_bought(p) for p in ps if XP.points_bought(p) >= 8]
print(f'  concentration: among men who bought 8+ points, the biggest single attribute took {np.mean(conc)*100:.0f}% of them on average (pure argmax would be ~100)')
unspent = [p.xp for p in L.players.values() if not p.retired and p.team]
print(f'  unspent XP league-wide: mean {np.mean(unspent):.0f}, men holding 5k+: {sum(1 for x in unspent if x >= 5000)}')

def show(p, why):
    o0, r0, pot0 = start[p.pid]
    t = L.teams.get(p.team); gm = t.gm if t else None
    bought = {k: v for k, v in p.xp_spent.items() if not k.startswith('_')}
    print(f"\n  {p.name} {p.pos} age {p.age:.0f}  {p.team} {t.record if t else ''}  {why}")
    print(f"    ovr {o0:.1f} -> {p.ovr:.1f}   ceiling {pot0} -> {p.potential}   unlocks {p.xp_spent.get('_unlocks', 0)}   unspent {p.xp:.0f}")
    print(f"    GM dev_belief {gm.dev_belief:.2f} patience {gm.patience:.2f}" if gm else '')
    print('    bought: ' + ', '.join(f'{k.replace("_rating","")} +{v}' for k, v in sorted(bought.items(), key=lambda kv: -kv[1])))

def pick(cond, key, why):
    c = [p for p in L.players.values() if not p.retired and p.team and cond(p)]
    if c: show(max(c, key=key), why)
pick(lambda p: p.age <= 23 and p.pos == 'WR' and XP.points_bought(p) > 0, lambda p: p.xp_spent.get('_earned', {}).get('game', 0), 'young receiver, top earner')
pick(lambda p: p.age <= 24 and p.pos in ('LEDG','REDG') and XP.points_bought(p) > 0, lambda p: XP.points_bought(p), 'young edge, most points bought')
pick(lambda p: 27 <= p.age <= 29 and p.pos == 'QB' and XP.points_bought(p) > 0, lambda p: p.ovr, 'prime quarterback')
pick(lambda p: p.age >= 32 and XP.points_bought(p) > 0, lambda p: p.ovr, 'veteran, best overall who bought')
pick(lambda p: p.xp_spent.get('_unlocks', 0) > 0, lambda p: p.xp_spent.get('_unlocks', 0), 'most unlocks')
pick(lambda p: XP.at_ceiling(p) and p.xp > 3000, lambda p: p.xp, 'at his ceiling, holding the most XP (saving)')
pick(lambda p: any(k in XP.PHYSICAL for k in p.xp_spent if not k.startswith('_')), lambda p: sum(v for k, v in p.xp_spent.items() if k in XP.PHYSICAL), 'bought the most physical points')
pick(lambda p: p.pos == 'C' and XP.points_bought(p) > 0, lambda p: p.xp_spent.get('awareness_rating', 0), 'centre, most awareness bought')
lo = min((t for t in L.teams.values()), key=lambda t: t.record[0]); hi = max((t for t in L.teams.values()), key=lambda t: t.record[0])
pick(lambda p: p.team == lo.abbr and p.age <= 24 and XP.points_bought(p) > 0, lambda p: XP.points_bought(p), f'young man on the worst club ({lo.abbr})')
pick(lambda p: p.team == hi.abbr and p.age >= 29 and XP.points_bought(p) > 0, lambda p: XP.points_bought(p), f'veteran on the best club ({hi.abbr})')
