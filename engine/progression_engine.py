"""
Progression and regression: two opposing forces.

This engine changes RATINGS and TRAITS. Nothing else. It does not cut players,
does not end careers and does not touch rosters: those are GM and depth-chart
decisions and they live elsewhere.

Every offseason a player gets TWO independent rolls and what you see is the net.

  UPWARD   earned from production relative to what his position and role should
           produce, multiplied by a hidden development trait, then gated by age
           so improvement gets progressively more expensive. A backup who never
           plays earns nothing, which is the flaw in Madden's XP model.

  DOWNWARD a PROBABILITY, not a certainty, from the aging curves we derived.
           Performance moves the odds but never removes them: a great year at 30
           cuts the chance, a bad one raises it, and he can still regress after
           a career season.

The plateau is not written anywhere. It emerges: at 23 the upward force is large
and the regression chance tiny; by 27 they roughly cancel; by 32 decline wins.
"""
import numpy as np, json

CURVES = json.load(open('aging_v3.json'))

# ---------------------------------------------------------------- age gates
# Madden uses hard cutoffs at 25 and 28. Ours are smooth but land in the same
# places, and the cost of improving rises rather than ability simply falling.
def improve_gate(age):
    if age <= 22: return 1.00
    if age <= 24: return 0.85
    if age <= 27: return 0.55
    if age <= 29: return 0.30
    if age <= 31: return 0.15
    if age <= 33: return 0.06
    return 0.02

# ---------------------------------------------------------------- dev traits
# Hidden. They multiply the upward force. Normal is the floor: there is no
# below-normal tier.
DEV = {'normal': 1.00, 'star': 1.55, 'superstar': 2.20, 'xfactor': 3.00}
DEV_ORDER = ['normal', 'star', 'superstar', 'xfactor']
DEV_P = [0.65, 0.22, 0.10, 0.03]

# Traits themselves move, on the same logic as attributes: a scale of odds, not
# a set rule. Production, age and awards all shift the probability of climbing
# or falling a tier, and nothing is ever certain.
AWARD_WEIGHT = {'mvp': 0.40, 'opoy': 0.30, 'dpoy': 0.30, 'all_pro_1': 0.22,
                'all_pro_2': 0.12, 'pro_bowl': 0.07, 'oroy': 0.20, 'droy': 0.20}

# The major individual honours are not a nudge to the odds, they are a certainty.
# Win one of these and the trait goes up a tier, full stop - unless you are
# already at the top, where it instead locks the trait against demotion.
GUARANTEED_UPGRADE = {'mvp', 'oroy', 'droy', 'opoy', 'dpoy'}

def trait_move_chances(dev, age, production, expected, awards=()):
    """
    Returns (chance_up, chance_down) for this offseason.
    Rising is driven by beating your own level and by honours; falling is driven
    by age and by underperforming what your tier implies.
    """
    over = production - expected
    tier = DEV_ORDER.index(dev)
    award = sum(AWARD_WEIGHT.get(a, 0.05) for a in awards)

    # MVP / OROY / DROY / OPOY / DPOY: guaranteed tier up, no roll.
    if GUARANTEED_UPGRADE & set(awards):
        return (1.0, 0.0) if tier < len(DEV_ORDER)-1 else (0.0, 0.0)

    # UP: harder the higher you already are, and much harder with age
    up = (max(0.0, over) * 1.5 + award) * (0.85 ** tier)
    if age >= 27: up *= 0.55
    if age >= 30: up *= 0.35
    up = float(np.clip(up, 0.0, 0.55))

    # DOWN: only possible if you are above normal. Underperforming the tier you
    # hold is the main driver; age adds to it; honours suppress it.
    if tier == 0:
        down = 0.0
    else:
        shortfall = max(0.0, -over)
        down = 0.05 + shortfall * 1.6 + max(0.0, (age - 28)) * 0.045
        down *= (1.0 + 0.25 * tier)          # higher tiers have further to fall
        down *= max(0.25, 1.0 - award * 1.8)  # a big year protects the trait
        down = float(np.clip(down, 0.01, 0.70))
    return up, down

# ---------------------------------------------------------------- regression odds
POSMAP = {'QB':'QB','HB':'RB','FB':'RB','WR':'WR','TE':'TE','LT':'OL','RT':'OL',
          'LG':'OL','RG':'OL','C':'OL','LEDG':'DL','REDG':'DL','DT':'DL',
          'MIKE':'LB','WILL':'LB','SAM':'LB','CB':'DB','FS':'DB','SS':'DB',
          'K':'OL','P':'OL','LS':'OL'}

# Reading the odds off raw year-over-year drops gave a jagged, non-monotonic
# curve (quarterbacks at 14% at 24 and 4% at 30). The chance a player declines
# must never fall as he ages, so build it once per position and force it up.
from sklearn.isotonic import IsotonicRegression
_CHANCE = {}
def _build_chance(grp):
    c = CURVES.get(grp, {}).get('curve', {})
    if not c: return {a: 0.10 for a in range(20, 45)}
    ks = sorted(int(k) for k in c)
    raw = []
    for a in range(min(ks), max(ks)+1):
        here = float(c.get(str(a), c.get(a)))
        before = float(c.get(str(a-1), c.get(a-1, here)))
        drop = max(0.0, before - here)
        level = max(0.0, 1.0 - here)
        raw.append(0.035 + drop*3.0 + level*0.60)
    ages = np.array(range(min(ks), max(ks)+1), float)
    fit = IsotonicRegression(increasing=True, out_of_bounds='clip').fit_transform(ages, raw)
    fit = np.clip(fit, 0.02, 0.90)
    out = {int(a): float(v) for a, v in zip(ages, fit)}
    # A MINIMUM SLOPE past 30. The quarterback curve was flattened by the no-rise
    # constraint, so it showed no year-over-year drop and produced a flat 5% at
    # every age - effectively immortal quarterbacks. Nobody ages at zero. This
    # floor is a design decision, not something the data showed.
    for a in sorted(out):
        if a > 30:
            out[a] = max(out[a], out[a-1] + 0.025)
    # An absolute age floor on top. Even the position whose data shows no decline
    # must face real risk in its mid-30s: an elite 33-year-old QB was holding up
    # 99.7% of the time, which is immortality rather than resilience.
    for a in sorted(out):
        out[a] = max(out[a], (a - 28) * 0.065 if a > 28 else out[a])
        out[a] = float(min(out[a], 0.92))
    for a in range(20, int(min(ks))): out[a] = out[int(min(ks))]
    for a in range(int(max(ks))+1, 45):
        out[a] = float(min(0.92, out[a-1] + 0.05))    # keeps climbing past the data
    return out

def base_regression_chance(pos, age):
    grp = POSMAP.get(pos, 'LB')
    if grp not in _CHANCE: _CHANCE[grp] = _build_chance(grp)
    return _CHANCE[grp][int(np.clip(round(age), 20, 44))]

# ---------------------------------------------------------------- the engine
ATTR_PHYSICAL = ['speed_rating','accel_rating','agility_rating','strength_rating',
                 'jump_rating','stamina_rating','change_of_direction_rating']
ATTR_MENTAL   = ['awareness_rating','play_rec_rating','throw_acc_short_rating',
                 'route_run_short_rating','zone_cover_rating','pass_block_rating']

class Player:
    def __init__(self, pid, pos, age, ovr, dev='normal', longevity=None, rng=None):
        rng = rng or np.random.default_rng()
        self.pid, self.pos, self.age, self.ovr = pid, pos, float(age), float(ovr)
        self.dev = dev
        # hidden: carries the variance we measured (at 29 the 10th pct held 74%
        # of his baseline and the 90th held 125%). Some men are done at 28.
        self.longevity = longevity if longevity is not None else float(np.clip(rng.normal(1.0, .22), .45, 1.7))
        self.history = []

    def expected_production(self):
        """what a player of his rating should produce, 0-1"""
        return float(np.clip((self.ovr - 58) / 42.0, 0.05, 0.98))

def offseason(p, production, rng, played=True, awards=()):
    """
    production: 0-1, what he actually did this season.
    awards: any of mvp, opoy, dpoy, all_pro_1, all_pro_2, pro_bowl, roty.
    Returns a dict describing what happened and mutates the player.
    """
    exp = p.expected_production()
    over = production - exp                      # did he beat his own level?

    # ---- UPWARD: earned, then gated by age, then multiplied by dev ----
    if played:
        earned = max(0.0, production * 0.55 + max(0.0, over) * 1.8)
    else:
        earned = 0.08                            # practice reps only
    up = earned * improve_gate(p.age) * DEV[p.dev]
    up_pts = up * rng.normal(3.1, 0.9)
    up_pts = max(0.0, up_pts)

    # ---- DOWNWARD: a probability, shifted by performance, never removed ----
    base = base_regression_chance(p.pos, p.age)
    perf_shift = np.clip(-over * 0.85, -0.30, 0.34)   # good year lowers, bad raises
    chance = (base + perf_shift) / p.longevity
    # A great season makes regression LESS LIKELY, never impossible. Without this
    # floor an elite 30-year-old regressed 1.6% of the time, which is effectively
    # immunity. He keeps at least 40% of his age-based risk no matter what he did.
    chance = max(chance, base * 0.40)
    chance = float(np.clip(chance, 0.02, 0.95))
    if not played: chance = min(0.95, chance + 0.12)

    regressed = rng.random() < chance
    down_pts = 0.0
    severity = None
    if regressed:
        r = rng.random()
        if r < 0.55:   severity, down_pts = 'slip',  rng.uniform(1, 2)
        elif r < 0.88: severity, down_pts = 'drop',  rng.uniform(2, 5)
        else:          severity, down_pts = 'cliff', rng.uniform(5, 11)
        down_pts *= (2.0 - p.longevity) ** 0.5

    net = up_pts - down_pts
    p.ovr = float(np.clip(p.ovr + net, 40, 99))

    # ---- the TRAIT itself moves, on the same odds-not-rules logic ----
    trait_change = None
    if played:
        c_up, c_down = trait_move_chances(p.dev, p.age, production, exp, awards)
        r = rng.random()
        if r < c_up and p.dev != DEV_ORDER[-1]:
            p.dev = DEV_ORDER[DEV_ORDER.index(p.dev) + 1]; trait_change = 'up'
        elif r > 1 - c_down and p.dev != DEV_ORDER[0]:
            p.dev = DEV_ORDER[DEV_ORDER.index(p.dev) - 1]; trait_change = 'down'
    p.age += 1

    rec = dict(age=round(p.age-1,0), ovr=round(p.ovr,1), up=round(up_pts,2),
               chance=round(chance,3), regressed=regressed, severity=severity,
               down=round(down_pts,2), net=round(net,2),
               dev=p.dev, trait_change=trait_change, awards=list(awards))
    p.history.append(rec)
    return rec
