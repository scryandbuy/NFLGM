"""
THE DRAFT CLASS, from EA's College Football 27 ratings.

The college file rates 10,931 players on the same attributes as the pro seed,
on a college scale: 123 men at 90+, one 99. The NFL seed has 52 at 90+ in
the whole league, and a real rookie class arrives well below that.

WHO. Seniors and juniors, the top of each position by college overall:
  30 at QB, HB, WR, TE, LEDG, REDG, DT, MIKE, WILL, SAM, CB
  20 at LT, LG, C, RG, RT, FS, SS
  10 at K, P
  every FB (there are 14)

HOW THE RATINGS COME DOWN. Not a flat cut. The pro seed already contains the
real 2026 rookie class, 323 drafted men with pro ratings, and that is the
target distribution. At each position the class is ranked by college
overall, the rookies by pro overall, and the i-th best college man is given
the i-th best rookie's overall; past the last rookie the line keeps falling
at the slope of the bottom of the rookie group, which is where the undrafted
live. Then his attributes are scaled to hit that number: skills move with
the scale, physicals move at the square root of it, because speed translates
to the league and technique does not.

WHAT THE FILE DOES NOT HAVE. Dev trait: drawn 65/22/10/3 like the league,
tilted toward the top of the class. Release (Madden-only): built from short
route running and agility for receivers and backs. Redshirt flags: absent,
so a senior is 22 and a junior 21, plus a few months.
"""
import numpy as np, pandas as pd, collections
import targets as TG

COUNTS = {'QB': 30, 'HB': 30, 'WR': 30, 'TE': 30, 'LEDG': 30, 'REDG': 30, 'DT': 30,
          'MIKE': 30, 'WILL': 30, 'SAM': 30, 'CB': 30,
          'LT': 20, 'LG': 20, 'C': 20, 'RG': 20, 'RT': 20, 'FS': 20, 'SS': 20,
          'K': 10, 'P': 10, 'FB': 30}
POS_MAP = {'LE': 'LEDG', 'RE': 'REDG', 'MLB': 'MIKE', 'ROLB': 'WILL', 'LOLB': 'SAM'}
ATTR_MAP = {
    'acceleration_rating': 'accel_rating', 'b_c_vision_rating': 'bcv_rating',
    'block_shedding_rating': 'block_shed_rating', 'carrying_rating': 'carry_rating',
    'catch_in_traffic_rating': 'cit_rating', 'catching_rating': 'catch_rating',
    'deep_route_running_rating': 'route_run_deep_rating',
    'medium_route_running_rating': 'route_run_med_rating',
    'short_route_running_rating': 'route_run_short_rating',
    'impact_blocking_rating': 'impact_block_rating', 'jumping_rating': 'jump_rating',
    'kick_accuracy_rating': 'kick_acc_rating', 'kick_return_rating': 'kick_ret_rating',
    'man_coverage_rating': 'man_cover_rating', 'zone_coverage_rating': 'zone_cover_rating',
    'play_recognition_rating': 'play_rec_rating', 'spectacular_catch_rating': 'spec_catch_rating',
    'throw_accuracy_deep_rating': 'throw_acc_deep_rating',
    'throw_accuracy_mid_rating': 'throw_acc_mid_rating',
    'throw_accuracy_short_rating': 'throw_acc_short_rating',
    'throw_on_the_run_rating': 'throw_on_run_rating', 'toughness_rating': 'tough_rating',
    'trucking_rating': 'truck_rating',
}
PHYSICAL = {'speed_rating', 'accel_rating', 'agility_rating', 'strength_rating',
            'change_of_direction_rating', 'jump_rating', 'stamina_rating', 'injury_rating',
            'tough_rating'}
NOT_RATINGS = {'overall_rating', 'running_style_rating'}
CLASS_AGE = {'Senior': 22.0, 'Junior': 21.0}
DEV_ORDER = ['normal', 'star', 'superstar', 'xfactor']
DEV_TOP, DEV_BOTTOM = [0.40, 0.32, 0.18, 0.10], [0.85, 0.12, 0.03, 0.00]


def load_college(path='cfb27_ratings.csv'):
    d = pd.read_csv(path, low_memory=False)
    d['pos'] = d.position.map(lambda p: POS_MAP.get(p, p))
    return d


def rookie_targets(seed_path='league_seed_2026.csv', year=2026):
    """{pos: sorted-desc engine overalls of the real rookie class}."""
    m = pd.read_csv(seed_path, low_memory=False)
    m = m[(m.roster == 'active') & (m.draft_year == year)]
    rc = [c for c in m.columns if c.endswith('_rating') and c != 'src_rating']
    out = collections.defaultdict(list)
    for _, r in m.iterrows():
        rat = {c: float(r[c]) for c in rc if pd.notna(r[c])}
        out[r.madden_position].append(TG.position_score(rat, r.madden_position))
    return {k: sorted(v, reverse=True) for k, v in out.items()}


# where a position's rookie group is too small or missing to shape a curve
PROXY = {'SAM': 'WILL', 'FB': None}
FALLBACK_MEAN = {'FB': 64.0}


def target_curve(rookies, n, spread_floor=4.0, tail_max=8.0):
    """
    Pro overall for class ranks 0..n-1 at one position. The i-th college man
    gets the i-th rookie's number; beyond the last rookie the line keeps
    falling at the slope of the bottom third, which is the undrafted tail.
    """
    r = list(rookies)
    if len(r) < 4:                       # K, P, FB: too few to shape; use mean and a spread
        mu = float(np.mean(r)) if len(r) >= 2 else 70.0
        return [mu + 3.0 - 8.0 * i / max(n - 1, 1) for i in range(n)]
    k = len(r)
    tail = r[int(k * 2 / 3):]
    slope = (tail[0] - tail[-1]) / max(len(tail) - 1, 1)
    slope = max(slope, spread_floor / max(k, 1))
    # the undrafted tail is a few points under the last drafted man, not a
    # cliff: a nine-man rookie group with a steep bottom third was putting
    # the 20th centre at 46
    if n > k:
        slope = min(slope, tail_max / (n - k))
    out = []
    for i in range(n):
        if i < k:
            out.append(r[i])
        else:
            out.append(r[-1] - slope * (i - k + 1))
    return out


def convert(row, pos, target):
    """His college attributes scaled so his engine overall lands on target."""
    raw = {}
    for c, v in row.items():
        if not str(c).endswith('_rating') or c in NOT_RATINGS or pd.isna(v):
            continue
        raw[ATTR_MAP.get(c, c)] = float(v)
    if pos in ('WR', 'TE', 'HB', 'FB') and 'release_rating' not in raw:
        raw['release_rating'] = 0.6 * raw.get('route_run_short_rating', 60) + 0.4 * raw.get('agility_rating', 60)
    college = TG.position_score(raw, pos)

    def scaled(k):
        return {a: float(np.clip(v * (k ** 0.5 if a in PHYSICAL else k), 20, 99)) for a, v in raw.items()}
    lo, hi = 0.4, 1.6
    for _ in range(40):
        mid = (lo + hi) / 2
        if TG.position_score(scaled(mid), pos) > target: hi = mid
        else: lo = mid
    return scaled((lo + hi) / 2), college


def draw_dev(rank_pct, rng):
    """Tilted toward the top of the class: rank_pct 0 = best, 1 = last."""
    p = np.array(DEV_TOP) * (1 - rank_pct) + np.array(DEV_BOTTOM) * rank_pct
    p = p / p.sum()
    return DEV_ORDER[int(rng.choice(4, p=p))]


def build(league, rng, path='cfb27_ratings.csv', seed_path='league_seed_2026.csv',
          draft_year=None, verbose=False):
    """
    The class as league.Player objects, unsigned and unowned, on
    league.draft_pool. Returns the list, best first by pro overall.
    """
    import league as LG
    d = load_college(path)
    d = d[d.school_year.isin(CLASS_AGE)]
    rookies = rookie_targets(seed_path)
    year = draft_year or (league.year + 1)
    out = []
    for pos, n in COUNTS.items():
        grp = d[d.pos == pos].sort_values('overall_rating', ascending=False).head(n)
        src = PROXY.get(pos, pos)
        rk = rookies.get(src, []) if src else []
        if pos in FALLBACK_MEAN: rk = [FALLBACK_MEAN[pos]] * 2
        curve = target_curve(rk, len(grp))
        for i, (_, row) in enumerate(grp.iterrows()):
            ratings, college_ovr = convert(row, pos, curve[i])
            age = CLASS_AGE[row.school_year] + float(rng.uniform(0.1, 0.9))
            p = LG.Player(f"C{int(row['id'])}", f"{row.first_name} {row.last_name}".strip(), pos,
                          age, ratings, dev=draw_dev(i / max(n - 1, 1), rng),
                          draft_year=year, entry_year=year)
            # the seed's own headroom rule, on the engine's overall
            headroom = rng.uniform(2.0, 4.5) + max(0.0, 28.0 - age) * rng.uniform(0.35, 1.15)
            pot = float(np.clip(p.ovr + headroom, p.ovr, 99.0))
            spread = rng.uniform(3.0, 11.0)
            p.potential = None
            p.potential_range = (round(max(p.ovr, pot - spread), 1), round(min(99.0, pot + spread), 1))
            p.college = row.team
            p.college_ovr = int(row.overall_rating)
            p.height, p.weight = float(row.height), float(row.weight)
            out.append(p)
    out.sort(key=lambda p: -p.ovr)
    league.draft_pool = out
    for p in out:
        league.players[p.pid] = p
    if verbose:
        print(f'{len(out)} in the class; pro overall mean {np.mean([p.ovr for p in out]):.1f}, '
              f'top {out[0].name} {out[0].pos} {out[0].ovr:.1f} (college {out[0].college_ovr})')
    import personality as PT
    for _p in out:
        PT.ensure(_p, rng)
    return out
