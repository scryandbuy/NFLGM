"""One season of XP as actually earned, then what it BUYS.

Two questions. Do the season totals land where the ledger was solved to put
them (39k for a 4,500-yard QB, 32k for a 1,200-yard back, 28k for a twelve-sack
edge, 21k for a tackle, 21k for a corner)? And when every man spends what he
earned the best way he can, does the league inflate?

Spending here is the greedy best case: each attribute point goes where it
moves the position score most, priced by xp.cost_per_point as he goes (the
price climbs with his overall). That is the ceiling a strong year can buy,
which is what the §5 growth table describes."""
import numpy as np, collections, sys, pickle, os

def run_season(seed=2026):
    import league as LG, season as SN, awards as AW, postseason as PS, xp as XP
    rng = np.random.default_rng(seed)
    L = LG.build_league(rng=rng)
    runner = SN.run_season(L, rng)
    post, order, fired = PS.close_season(L, runner, rng)
    votes = AW.vote(L, post)
    XP.close_season(L, votes)
    return L

def best_spend(p, xp_budget):
    """Greedy: buy the attribute with the highest weight for his position,
    one point at a time, repricing as his overall rises. Returns ovr gain."""
    import targets as TG, xp as XP
    w = TG.DEPTH_WEIGHTS.get(p.pos)
    if not w:
        return 0.0, 0
    ovr0 = p.ovr; ratings = dict(p.ratings); spent = 0; budget = xp_budget
    order = sorted(w.items(), key=lambda kv: -kv[1])
    class Tmp: pass
    t = Tmp(); t.pos, t.age = p.pos, p.age
    while True:
        t.ovr = TG.position_score(ratings, p.pos)
        cost = XP.cost_per_point(t)
        if cost > budget: break
        # highest-weight attribute that is not capped
        for k, _ in order:
            if ratings.get(k, 70) < 99:
                ratings[k] = ratings.get(k, 70) + 1; break
        else: break
        budget -= cost; spent += 1
    return TG.position_score(ratings, p.pos) - ovr0, spent

if __name__ == '__main__':
    import targets as TG, xp as XP
    L = run_season(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
    year = L.year
    ps = [p for p in L.players.values() if not p.retired and p.xp > 0]
    print(f'{len(ps)} players earned XP')
    # by source
    src = collections.Counter()
    for p in ps:
        for k, v in p.xp_spent.get('_earned', {}).items(): src[k] += v
    tot = sum(src.values())
    print('  by source: ' + ', '.join(f'{k} {v/tot*100:.0f}%' for k, v in src.most_common()))
    # top earners by position vs the ledger's solved lines
    print('\n  POSITION   starters(n)  median XP   top-5 mean   ledger target for a big year')
    targets = {'QB': 39000, 'HB': 32000, 'WR': 28000, 'TE': 20000, 'LEDG': 28000, 'REDG': 28000, 'LT': 21000, 'RT': 21000, 'CB': 21000, 'MIKE': 24000, 'FS': 20000, 'SS': 20000, 'DT': 22000, 'LG': 21000, 'RG': 21000, 'C': 21000}
    stats = L.stats.get(year, {})
    for pos in ('QB','HB','WR','TE','LT','LG','C','RG','RT','LEDG','REDG','DT','MIKE','WILL','CB','FS','SS'):
        grp = sorted([p for p in ps if p.pos == pos], key=lambda p: -p.xp)
        starters = [p for p in grp if stats.get(p.pid, {}).get('snaps', 0) >= 500]
        if not grp: continue
        top5 = np.mean([p.xp for p in grp[:5]])
        print(f'  {pos:6s}     {len(starters):3d}        {np.median([p.xp for p in starters]) if starters else 0:7.0f}    {top5:8.0f}      {targets.get(pos, "-")}')
    # what it buys: best-case spend, by age band and position group
    print('\n  BEST-CASE OVERALL GAIN from this season alone (greedy spend), starters only')
    print('  §5 table: WR 4.9/4.3/2.6/1.8/0.7  QB 5.2/4.3/3.2/2.5/2.0  HB 4.2/3.7/2.3/1.4/1.1  EDGE 3.8/3.3/1.8/1.2/1.0 at 22/25/28/31/34')
    bands = [(20, 23.5, '~22'), (23.5, 26.5, '~25'), (26.5, 29.5, '~28'), (29.5, 32.5, '~31'), (32.5, 40, '~34')]
    groups = {'QB': ['QB'], 'WR': ['WR'], 'HB': ['HB'], 'EDGE': ['LEDG', 'REDG'], 'OL': ['LT','LG','C','RG','RT'], 'CB': ['CB'], 'LB': ['MIKE','WILL','SAM'], 'S': ['FS','SS'], 'DT': ['DT'], 'TE': ['TE']}
    gains_all = []
    print(f'  {"group":5s} ' + ' '.join(f'{b[2]:>10s}' for b in bands) + '    (mean gain / top-quarter gain, n)')
    for g, poss in groups.items():
        row = []
        for lo, hi, lab in bands:
            grp = [p for p in ps if p.pos in poss and lo <= p.age < hi and stats.get(p.pid, {}).get('snaps', 0) >= 500]
            if not grp: row.append(f'{"-":>10s}'); continue
            gains = sorted(best_spend(p, p.xp)[0] for p in grp)
            gains_all += [(p.age, gn) for p, gn in zip(grp, gains)]
            q = gains[int(len(gains) * 0.75)] if len(gains) > 3 else gains[-1]
            row.append(f'{np.mean(gains):4.1f}/{q:4.1f}({len(grp):2d})')
        print(f'  {g:5s} ' + ' '.join(row))
    # inflation check: league overall distribution before and after everyone spends
    ovr_before = np.array([p.ovr for p in ps if stats.get(p.pid, {}).get('snaps', 0) >= 200])
    after = []
    for p in ps:
        if stats.get(p.pid, {}).get('snaps', 0) >= 200:
            after.append(p.ovr + best_spend(p, p.xp)[0])
    after = np.array(after)
    print(f'\n  INFLATION, men with 200+ snaps: mean ovr {ovr_before.mean():.1f} -> {after.mean():.1f}  '
          f'90+ {np.mean(ovr_before>=90)*100:.1f}% -> {np.mean(after>=90)*100:.1f}%   95+ {np.mean(ovr_before>=95)*100:.1f}% -> {np.mean(after>=95)*100:.1f}%   '
          f'(before regression takes its share back)')

def top_lines(L, n=6):
    import xp as XP
    year = L.year; stats = L.stats.get(year, {})
    ps = sorted([p for p in L.players.values() if p.xp > 0], key=lambda p: -p.xp)[:n]
    for p in ps:
        l = stats.get(p.pid, {}); e = p.xp_spent.get('_earned', {})
        keys = [k for k in ('pass_yds','pass_td','rush_yds','rush_td','rec','rec_yds','rec_td','tackles','sacks','int_def','pb_wins','snaps','games') if l.get(k)]
        print(f"  {p.name:22s} {p.pos:4s} age {p.age:4.1f} ovr {p.ovr:4.1f} dev {p.dev:9s} xp {p.xp:8.0f}  " + ' '.join(f'{k}={l[k]:.0f}' for k in keys))
        print('      ' + ', '.join(f'{k} {v:.0f}' for k, v in e.items()) + f'   cost/pt now {XP.cost_per_point(p):.0f}  -> best gain {best_spend(p, p.xp)[0]:.1f} ovr')
