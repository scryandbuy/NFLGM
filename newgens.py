"""
NEWGENS: the draft class after the real one.

Built onto the same template the College Football 27 class was mapped to:
your position counts, the real rookie curve at each position for the pro
overall, the seed's headroom rule for the ceiling, dev drawn 65/22/10/3
tilted to the top of the class.

WHAT VARIES. Class strength. Each year every position's curve moves up or
down a little (sd 1.5 overall points), and the whole class moves a little
on top (sd 0.8), so there are strong quarterback years and thin tackle
years and drafts that are just weak.

WHERE A MAN'S SHAPE COMES FROM. A real attribute profile. The college file
holds 10,931 real profiles by position; a newgen takes one at his position
as his template and is scaled to his pro overall the way the class builder
does it, physicals moving at the square root of the scale. Nothing is
invented about how a corner's ratings hang together. Height and weight ride
along.

NAMES. Drawn from a pool of 7,000 first names and 8,000 surnames built from
both seeds, first and last drawn independently, so they read like a real
class and no name belongs to a real man.

WHEN. The class for NEXT year's draft is generated in the offseason right
after this year's draft, and scouted then, so it is on the scouting tab
through the preseason and the season that follows.
"""
import numpy as np, pandas as pd, collections
import targets as TG
import draft_class as DC

STRENGTH_SD_POS, STRENGTH_SD_CLASS = 1.5, 0.8


def _name_pools(cfb_path='cfb27_ratings.csv', seed_path='league_seed_2026.csv'):
    c = pd.read_csv(cfb_path, low_memory=False, usecols=['first_name', 'last_name'])
    m = pd.read_csv(seed_path, low_memory=False)
    col = next((c for c in ('name', 'player_name', 'full_name', 'display_name') if c in m.columns), None)
    first = list(c.first_name.dropna()); last = list(c.last_name.dropna())
    if col:
        for n in m[col].dropna():
            parts = str(n).split()
            if len(parts) >= 2:
                first.append(parts[0]); last.append(' '.join(parts[1:]))
    # keep the frequency of the real pools so common names stay common and
    # the rare ones stay rare, then dedupe the suffix junk
    first = [f for f in first if len(f) > 1 and not f.endswith('.')]
    last = [l for l in last if len(l) > 1 and l not in ('Jr.', 'Sr.', 'II', 'III', 'IV')]
    return first, last


_POOLS = None


_REAL = None


def name(rng):
    """An invented name that is not any real man's in either seed."""
    global _POOLS, _REAL
    if _POOLS is None:
        _POOLS = _name_pools()
        c = pd.read_csv('cfb27_ratings.csv', low_memory=False, usecols=['first_name', 'last_name'])
        _REAL = set((c.first_name + ' ' + c.last_name).dropna())
    first, last = _POOLS
    for _ in range(20):
        n = f"{first[int(rng.integers(len(first)))]} {last[int(rng.integers(len(last)))]}"
        if n not in _REAL:
            return n
    return n


def build(league, rng, draft_year, cfb_path='cfb27_ratings.csv', verbose=False):
    """The class for draft_year, on league.next_class and in league.players."""
    import league as LG
    college = DC.load_college(cfb_path)
    college = college[college.school_year.isin(DC.CLASS_AGE)]
    rookies = DC.rookie_targets()
    class_shift = float(rng.normal(0.0, STRENGTH_SD_CLASS))
    out = []; strength = {}
    for pos, n in DC.COUNTS.items():
        templates = college[college.pos == pos]
        if templates.empty:
            continue
        n = min(n, len(templates))
        src = DC.PROXY.get(pos, pos)
        rk = rookies.get(src, []) if src else []
        if pos in DC.FALLBACK_MEAN: rk = [DC.FALLBACK_MEAN[pos]] * 2
        pos_shift = float(rng.normal(0.0, STRENGTH_SD_POS))
        strength[pos] = round(class_shift + pos_shift, 1)
        curve = [c + class_shift + pos_shift for c in DC.target_curve(rk, n)]
        # a random real profile at the spot for each slot; the top of the class
        # leans on the better college profiles so shapes stay plausible
        ranked = templates.sort_values('overall_rating', ascending=False)
        for i in range(n):
            lo = int(len(ranked) * max(0.0, i / n - 0.25)); hi = int(len(ranked) * min(1.0, i / n + 0.35))
            row = ranked.iloc[int(rng.integers(lo, max(lo + 1, hi)))]
            ratings, _ = DC.convert(row, pos, curve[i])
            age = (22.0 if rng.random() < 0.68 else 21.0) + float(rng.uniform(0.1, 0.9))
            p = LG.Player(f"N{draft_year}{pos}{i:03d}", name(rng), pos, age, ratings,
                          dev=DC.draw_dev(i / max(n - 1, 1), rng),
                          draft_year=draft_year, entry_year=draft_year)
            headroom = rng.uniform(2.0, 4.5) + max(0.0, 28.0 - age) * rng.uniform(0.35, 1.15)
            pot = float(np.clip(p.ovr + headroom, p.ovr, 99.0)); spread = rng.uniform(3.0, 11.0)
            p.potential = None
            p.potential_range = (round(max(p.ovr, pot - spread), 1), round(min(99.0, pot + spread), 1))
            p.college = str(row.team); p.college_ovr = None
            p.height, p.weight = float(row.height), float(row.weight)
            out.append(p)
    out.sort(key=lambda p: -p.ovr)
    league.next_class = out
    league.class_strength = strength
    for p in out:
        league.players[p.pid] = p
    if verbose:
        strong = sorted(strength.items(), key=lambda kv: -kv[1])
        print(f'{len(out)} newgens for {draft_year}; class shift {class_shift:+.1f}; strongest {strong[:3]}, weakest {strong[-3:]}')
    import personality as PT
    for _p in out:
        PT.ensure(_p, rng)
    return out
