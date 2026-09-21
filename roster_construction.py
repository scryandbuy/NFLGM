"""
Roster construction.

Two layers, and they are different in kind.

  MINIMUMS are hard. Observed as the FLOOR across all 32 real 2026 rosters, not
  an average. A roster below these cannot take the field.

  EVERYTHING ABOVE is a GM decision, and it is a portfolio problem under a hard
  53-slot budget: an extra body at a strong position competes directly against
  one at a weak position. The NFL cannot stockpile the way baseball does - the
  hard cap and the 53 make it unfeasible to carry men you do not use.

Surplus IS a trade asset ("Denver would benefit more from getting an asset for
its sixth pass-rusher over keeping him in case of injury"), but the value decays
to zero at cutdown, because once you release him you get nothing.
"""
import numpy as np

ROSTER_LIMIT = 53
GAMEDAY_ACTIVE = 48          # 47 unless the club dresses eight offensive linemen

# ---------------------------------------------------------------- minimums
# Floors observed across all 32 clubs in the real 2026 data. FB and SAM bottom
# out at 0, so neither is required.
MINIMUMS = {
    'QB': 2, 'HB': 2, 'FB': 0, 'WR': 5, 'TE': 3,
    'LT': 1, 'LG': 1, 'C': 1, 'RG': 1, 'RT': 1,
    'LEDG': 1, 'REDG': 1, 'DT': 4,
    'MIKE': 1, 'WILL': 1, 'SAM': 0,
    'CB': 4, 'FS': 1, 'SS': 1,
    'K': 1, 'P': 1, 'LS': 1,
}
GROUP_MINIMUMS = {'OL': 9, 'DL': 10, 'LB': 4, 'DB': 10, 'ST': 3}

def meets_minimums(counts):
    """Hard gate. Returns (ok, list of shortfalls)."""
    short = [(p, counts.get(p, 0), m) for p, m in MINIMUMS.items()
             if counts.get(p, 0) < m]
    return (len(short) == 0), short

# ---------------------------------------------------------------- drivers
# How often a club deploys a personnel group drives how deep it needs to be.
# Green Bay ran 2+ TE on 35.6% of snaps, which is why their TE depth matters
# more than another club's. Usage rate, not position label.
DEFAULT_USAGE = {'QB': .06, 'HB': .35, 'FB': .04, 'WR': .60, 'TE': .30,
                 'LT': .06, 'LG': .06, 'C': .06, 'RG': .06, 'RT': .06,
                 'LEDG': .22, 'REDG': .22, 'DT': .32, 'MIKE': .18,
                 'WILL': .18, 'SAM': .08, 'CB': .45, 'FS': .16, 'SS': .16,
                 'K': .02, 'P': .02, 'LS': .02}

# The market's willingness to refill a spot. High = the waiver wire will bail
# you out, so carry fewer. OL and TE are the positions personnel men say keep
# them awake, because they are hard to find on the street.
from gm_engine import REPLACEABILITY  # one source of truth  (module was renamed)

# Injury exposure by position: you cannot win with your fourth corner but you
# can certainly lose with him.
INJURY_EXPOSURE = {'HB': .85, 'WR': .70, 'CB': .75, 'LEDG': .70, 'REDG': .70,
                   'DT': .65, 'LT': .55, 'RT': .55, 'LG': .55, 'RG': .55,
                   'C': .50, 'TE': .60, 'MIKE': .60, 'WILL': .60, 'SAM': .45,
                   'FS': .55, 'SS': .55, 'QB': .40, 'FB': .30,
                   'K': .10, 'P': .10, 'LS': .10}

# Bottom-of-roster spots are decided on coverage value, not position rank.
ST_VALUE = {'WILL': .85, 'SAM': .90, 'MIKE': .70, 'SS': .85, 'FS': .80,
            'CB': .65, 'TE': .70, 'HB': .60, 'FB': .75, 'WR': .55,
            'LEDG': .45, 'REDG': .45, 'DT': .25, 'LT': .15, 'RT': .15,
            'LG': .15, 'RG': .15, 'C': .15, 'QB': .05, 'K': 1.0, 'P': 1.0,
            'LS': 1.0}

# ---------------------------------------------------------------- allocation
def slot_value(pos, depth_rank, team, gm, usage=None, waiver_priority=0.5):
    """
    What is the NEXT body at this position worth?
    depth_rank: 1 = starter, 2 = first backup, etc.
    waiver_priority: 0 = last claim, 1 = first. A club picking first on waivers
        does not need to carry its own insurance - New Orleans was described as
        sitting high in the claim order and therefore not compelled to trade
        for depth.
    """
    g = gm.shift(team)
    usage = (usage or DEFAULT_USAGE).get(pos, .2)
    mn = MINIMUMS.get(pos, 1)

    if depth_rank <= mn:
        return 99.0                                   # required; not a choice

    over = depth_rank - mn
    # each body past the minimum is worth less than the last
    decay = 0.62 ** (over - 1)
    injury = INJURY_EXPOSURE.get(pos, .5) * usage
    scarce = 1.0 - REPLACEABILITY.get(pos, .6)        # the wire will not save you
    st = ST_VALUE.get(pos, .4) * 0.5                  # coverage keeps marginal men

    # Scarcity protects the STARTER, not the fourth man. A quarterback is
    # irreplaceable, which is why you cannot lose QB1 - it is not a reason to
    # carry four of them. The first build had scarcity apply flat at every depth
    # and produced four-QB rosters.
    playable = {'QB': 2, 'K': 1, 'P': 1, 'LS': 1}.get(pos, mn + 3)
    scarce_eff = scarce * (0.25 if depth_rank > playable else 1.0)

    # GM parameters must modulate the COMPONENTS, not the total. A uniform
    # multiplier scales every position equally and leaves the ranking - and so
    # the roster - identical, which is exactly what the first build produced.
    w_injury = 2.4 * (1.45 - 0.85 * g.risk)           # risk-averse men buy insurance
    w_scarce = 1.8 * (0.55 + 0.95 * g.patience)       # patient men hoard scarce spots
    w_st = 1.0 * (1.30 - 0.60 * g.aggression)         # coverage value for the bottom
    dev_bonus = 1.0 + max(0.0, g.youth - 0.5) * 0.9 * (1.0 - REPLACEABILITY.get(pos, .6))

    v = (injury * w_injury + scarce_eff * w_scarce + st * w_st) * decay * dev_bonus
    v *= (1.0 - 0.45 * waiver_priority)               # first call replaces insurance
    return round(float(v), 3)

def allocate(pool, team, gm, usage=None, waiver_priority=0.5, limit=ROSTER_LIMIT):
    """
    Fill the 53. Minimums first, then the highest marginal slot value, where
    every extra body at a strong position competes against one at a weak one.
    pool: list of dicts with pos and ovr.
    """
    by_pos = {}
    for p in pool: by_pos.setdefault(p['pos'], []).append(p)
    for k in by_pos: by_pos[k].sort(key=lambda x: -x['ovr'])

    GRP = {'LT':'OL','LG':'OL','C':'OL','RG':'OL','RT':'OL',
           'LEDG':'DL','REDG':'DL','DT':'DL','MIKE':'LB','WILL':'LB','SAM':'LB',
           'CB':'DB','FS':'DB','SS':'DB','K':'ST','P':'ST','LS':'ST'}
    roster, counts = [], {}
    taken = {p: 0 for p in by_pos}
    # 1. per-position minimums are not negotiable
    for pos, m in MINIMUMS.items():
        for i in range(m):
            if len(by_pos.get(pos, [])) > i:
                roster.append(by_pos[pos][i]); counts[pos] = counts.get(pos, 0) + 1
                taken[pos] = taken.get(pos, 0) + 1
    # 2. GROUP minimums also bind. Per-position floors sum to only 5 offensive
    #    linemen, but no club carries fewer than 9 - you cannot survive a game
    #    with five. The first build shipped 7-man lines.
    for grp, need in GROUP_MINIMUMS.items():
        have = sum(counts.get(p, 0) for p, gg in GRP.items() if gg == grp)
        while have < need:
            best = None
            for pos, gg in GRP.items():
                if gg != grp: continue
                i = taken.get(pos, 0)
                if i < len(by_pos.get(pos, [])):
                    cand = by_pos[pos][i]
                    if best is None or cand['ovr'] > best[0]['ovr']: best = (cand, pos)
            if best is None: break
            roster.append(best[0]); counts[best[1]] = counts.get(best[1], 0) + 1
            taken[best[1]] = taken.get(best[1], 0) + 1; have += 1
    # 2. everything else competes on marginal value x player quality
    cands = []
    for pos, men in by_pos.items():
        for i, m in enumerate(men):
            rank = i + 1
            if rank <= taken.get(pos, 0): continue
            sv = slot_value(pos, rank, team, gm, usage, waiver_priority)
            cands.append((sv * (0.4 + m['ovr'] / 90.0), pos, m, rank))
    cands.sort(key=lambda x: -x[0])
    for score, pos, m, rank in cands:
        if len(roster) >= limit: break
        roster.append(m); counts[pos] = counts.get(pos, 0) + 1
    return roster, counts

# ---------------------------------------------------------------- surplus
def surplus_players(counts, by_pos, team, gm, usage=None, waiver_priority=0.5):
    """
    Who is genuinely spare. A man is surplus when the NEXT body at his spot is
    worth less than an ordinary body elsewhere - not merely when the room looks
    crowded.
    """
    out = []
    for pos, men in by_pos.items():
        n = counts.get(pos, 0)
        for rank in range(MINIMUMS.get(pos, 1) + 1, n + 1):
            sv = slot_value(pos, rank, team, gm, usage, waiver_priority)
            if sv < 0.45 and rank <= len(men):
                out.append(dict(player=men[rank-1], pos=pos, rank=rank, slot_value=sv))
    return sorted(out, key=lambda x: x['slot_value'])

def surplus_trade_window(weeks_to_cutdown, gm, team):
    """
    Surplus converts to an asset ONLY before cutdown. Once you release him you
    get nothing, so his trade value decays to zero at the deadline. That is a
    real decision window, not a standing option.
    """
    g = gm.shift(team)
    if weeks_to_cutdown <= 0: return 0.0
    urgency = float(np.clip(1.0 - weeks_to_cutdown / 6.0, 0.0, 1.0))
    # a patient GM sits on depth longer; an aggressive one converts early
    return round(float(0.35 + 0.65 * urgency * (1.4 - g.patience)), 3)

def hoard_tolerance(gm):
    """How long this GM sits on surplus rather than converting it."""
    g = gm
    return round(float(0.5 * g.own_bias + 0.5 * g.patience), 3)
