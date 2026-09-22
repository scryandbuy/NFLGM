"""
THE DRAFT.

Each club sees the class through its own scouting (scouting.py). From that
read each GM builds a board the way the research says rooms do:

  - present versus ceiling: dev_belief weights the ceiling up, a hot seat
    weights the present up (career concerns bend the draft toward the near
    term)
  - position: premium spots (QB above all, then tackle, edge, receiver,
    interior DL, corner) carry a bonus inside the first hundred picks that
    fades after; backs, linebackers, safeties and interior line are
    discounted there. Need matters most at the discounted spots and least
    at the premium ones, which is the real pattern
  - need: the gap between his starters at a spot and the league's, weighted
    by how far he is from a pure best-available drafter (board_trust) and by
    how much having a need inflates a player for him (need_inflation)
  - board_trust also blends his private read toward the consensus, so a
    high-trust room drafts close to the shared board and a low-trust one
    reaches on its own grades

Picks run in the order postseason.set_draft_order wrote onto the pick
objects, seven rounds, the owner of the pick choosing. A pick has a slotted
four-year deal by selection. Whoever is left is an undrafted free agent and
goes to the pool cut-down fills from.

Not here yet: draft-day pick trades. Clubs pick in place.
"""
import numpy as np, collections
import targets as TG
import scouting as SC
from cap_engine import Contract, CAP
import min_salary as MS

ROUNDS, PER_ROUND = 7, 32
STARTERS = {'QB': 1, 'HB': 1, 'FB': 0, 'WR': 3, 'TE': 1, 'LT': 1, 'LG': 1, 'C': 1, 'RG': 1, 'RT': 1,
            'LEDG': 1, 'REDG': 1, 'DT': 2, 'MIKE': 1, 'WILL': 1, 'SAM': 1, 'CB': 3, 'FS': 1, 'SS': 1,
            'K': 1, 'P': 1}
# inside the first hundred picks; fades to 1.0 by pick 160
PREMIUM = {'QB': 1.22, 'LT': 1.10, 'RT': 1.08, 'LEDG': 1.10, 'REDG': 1.10, 'WR': 1.08, 'DT': 1.06,
           'CB': 1.05, 'TE': 0.96, 'LG': 0.96, 'RG': 0.96, 'C': 0.97, 'FS': 0.94, 'SS': 0.94,
           'MIKE': 0.92, 'WILL': 0.92, 'SAM': 0.92, 'HB': 0.90, 'FB': 0.70, 'K': 0.60, 'P': 0.60}
# a club does not draft a third quarterback in round two, or a kicker when it has one
POS_CAP_EARLY = {'QB': 1, 'K': 1, 'P': 1, 'FB': 1}

# the slotted scale, share of the cap (2026 real: pick 1 about 3.5%, pick 32
# about 1.1%, round 2 0.85 down to 0.55, round 3 about 0.4, rounds 4-7 near
# the minimum), four years, flat cap hits
def slot_apy(selection, cap):
    s = selection
    if s <= 32:   pct = 3.5 * (1.1 / 3.5) ** ((s - 1) / 31)
    elif s <= 64: pct = 0.85 - 0.30 * (s - 33) / 31
    elif s <= 96: pct = 0.45 - 0.07 * (s - 65) / 31
    else:         pct = 0.36 - 0.06 * min(1.0, (s - 97) / 128)
    return round(cap * pct / 100, 3)


def rookie_contract(selection, cap):
    apy = slot_apy(selection, cap)
    mn = MS.minimum_salary(0, cap)
    base = [mn] * 4
    sb = max(0.0, round(apy * 4 - mn * 4, 3))
    return Contract(years=4, base=base, signing_bonus=sb)


PREMIUM_SCALE = 60.0      # (PREMIUM - 1) x this, in common-scale points: QB +13, tackle +6, edge +6, back -6, LB -4.8, kicker -24


def premium(pos, selection):
    """Additive, in overall points. Multiplying an 80 by 1.22 was worth 17
    points, more than the spread of the whole first round, and put 13
    quarterbacks in it."""
    p = (PREMIUM.get(pos, 1.0) - 1.0) * PREMIUM_SCALE
    if selection <= 100: return p
    if selection >= 160: return 0.0
    return p * (160 - selection) / 60


def league_starter_level(league):
    """Average overall of the k-th best man at each spot across the league."""
    lv = collections.defaultdict(list)
    for t in league.teams.values():
        d = t.depth
        for pos, k in STARTERS.items():
            grp = d.get(pos, [])
            if k and len(grp) >= k: lv[pos].append(grp[k - 1].ovr)
    return {pos: float(np.mean(v)) for pos, v in lv.items() if v}


def position_scale(league):
    """
    {pos: (mean, sd)} of every rostered man at the spot. The engine's overall
    runs on a different scale at each position (a rookie corner class
    averages 79, a tackle class 74, a tight end class 68) and with a
    different spread, so a board has to read a prospect as a z-score within
    his position before it can compare him to a man at another.
    """
    vals = collections.defaultdict(list)
    for t in league.teams.values():
        for p in t.active():
            vals[p.pos].append(p.ovr)
    return {pos: (float(np.mean(v)), float(max(np.std(v), 3.0))) for pos, v in vals.items() if len(v) >= 8}


def common_scale(ovr, pos, scale):
    mu, sd = scale.get(pos, (75.0, 5.0))
    return 75.0 + float(np.clip((ovr - mu) / sd, -2.5, 2.5)) * 5.0


def needs(team, level):
    """{pos: gap}: how far this club's starters sit below the league at each spot."""
    d = team.depth; out = {}
    for pos, k in STARTERS.items():
        if not k or pos not in level: continue
        grp = d.get(pos, [])
        have = grp[k - 1].ovr if len(grp) >= k else 45.0
        # a need is being CLEARLY below the league at the spot, not merely
        # below average - by definition half the league is below average
        # everywhere, and that had every club drafting quarterbacks
        out[pos] = float(min(12.0, max(0.0, (level[pos] - 2.5) - have)))
    return out


# ============================================================ THE SLOT CURVES
# Where the k-th best man at each position typically goes, 2020-25 averages.
# Real boards work off slot expectation, not overall: the top quarterback
# goes top three, the third around 20, the top back around 15, the fifth
# back in round three, the first kicker in round five. A board built on
# overall put positions on in blocks (16 edges in one first round, then 22
# backs when the premium moved a notch); this makes the mix right by
# construction and leaves the reaches to scouting, need and personality.
SLOT = {
    'QB':   [3, 7, 15, 35, 65, 100, 150, 200, 240],
    'HB':   [18, 38, 55, 75, 95, 120, 150, 180, 210, 240],
    'WR':   [8, 15, 22, 30, 40, 52, 65, 80, 95, 110, 130, 150, 175, 200, 225, 250],
    'TE':   [12, 42, 65, 90, 115, 140, 170, 200, 230],
    'T':    [6, 11, 18, 26, 34, 45, 58, 75, 95, 120, 150, 180, 210, 240],
    'IOL':  [20, 35, 48, 62, 78, 95, 115, 140, 165, 190, 215, 240],
    'EDGE': [4, 9, 14, 20, 27, 35, 44, 55, 68, 85, 105, 130, 160, 190, 220, 250],
    'DT':   [10, 20, 32, 45, 60, 78, 98, 120, 145, 175, 205, 235],
    'LB':   [22, 40, 60, 80, 100, 125, 150, 175, 200, 225, 250],
    'S':    [25, 45, 65, 85, 105, 130, 155, 180, 205, 230],
    'CB':   [7, 14, 22, 32, 44, 56, 70, 85, 100, 120, 140, 165, 190, 215, 240],
    'K':    [150, 200, 240], 'P': [160, 210, 245], 'FB': [230, 250],
}
SLOT_GROUP = {'LT': 'T', 'RT': 'T', 'LG': 'IOL', 'RG': 'IOL', 'C': 'IOL',
              'LEDG': 'EDGE', 'REDG': 'EDGE', 'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB',
              'FS': 'S', 'SS': 'S'}


def expected_slot(pos, rank):
    """Slot for the rank-th best (0-based) at the position; past the table it
    keeps sliding into the undrafted range."""
    curve = SLOT[SLOT_GROUP.get(pos, pos)]
    if rank <= len(curve) - 1:
        return float(np.interp(rank, range(len(curve)), curve))   # ranks are blended, so fractional
    step = max(12.0, curve[-1] - curve[-2]) if len(curve) > 1 else 25.0
    return curve[-1] + step * (rank - len(curve) + 1)


def slot_value(slot):
    """The pick chart's outcome value at a slot; the same chart the trade
    engine prices picks with."""
    import json, functools
    return _chart()(slot)


@__import__('functools').lru_cache(maxsize=None)
def _chart():
    import json
    ch = json.load(open('pick_values.json'))['outcome']
    xs = sorted(int(k) for k in ch); ys = [ch[str(x)] for x in xs]
    def f(slot):
        if slot <= xs[-1]:
            return float(np.interp(max(1.0, slot), xs, ys))
        # past the chart the value keeps falling instead of going flat, so
        # late boards still have an order and a second kicker stays behind
        # every position player left
        return float(ys[-1] * 0.97 ** (slot - xs[-1]))
    return f


def board(league, abbr, selection, level, taken, scale=None):
    """
    This club's board right now: [(value, player)], best first.

    Each position's prospects are ranked by the club's own read (present and
    ceiling blended by dev_belief and the seat), pooled across the two
    tackle spots, the three interior spots, the two edges, the three
    linebackers and the two safeties the way boards actually group them.
    The rank becomes a slot off the position's curve and the slot a value
    off the pick chart. Then the leans: need pulls a man up the board,
    hardest for the low-trust, need-inflating GM; board_trust also blends
    his private ranking toward the consensus one; a hot seat wants the
    older, readier man; a quarterback goes early only to a real hole.
    """
    team = league.teams[abbr]; gm = team.gm
    trust = float(getattr(gm, 'board_trust', 0.5)); belief = float(getattr(gm, 'dev_belief', 0.5))
    inflate = float(getattr(gm, 'need_inflation', 0.5)); heat = 1.0 - float(getattr(gm, 'job_security', 0.6))
    need = needs(team, level)
    mine = league.scouting[abbr]; cons = league.consensus
    d = team.depth
    w_pot = 0.40 + 0.35 * belief * (1.0 - 0.8 * heat)
    # my grade and the room's grade on every man left
    left = [p for p in league.draft_pool if p.pid not in taken]
    def grade(p, v):
        return (1 - w_pot) * v['ovr'] + w_pot * (v['pot_lo'] + v['pot_hi']) / 2
    my_grade = {p.pid: grade(p, mine[p.pid]) for p in left}
    cons_grade = {p.pid: 0.6 * cons[p.pid]['ovr'] + 0.4 * cons[p.pid]['pot'] for p in left}
    # rank within position group, mine and the room's, then blend the ranks
    groups = collections.defaultdict(list)
    for p in left: groups[SLOT_GROUP.get(p.pos, p.pos)].append(p)
    rows = []
    for g, ps in groups.items():
        mine_order = sorted(ps, key=lambda p: -my_grade[p.pid])
        cons_order = sorted(ps, key=lambda p: -cons_grade[p.pid])
        my_rank = {p.pid: i for i, p in enumerate(mine_order)}
        cons_rank = {p.pid: i for i, p in enumerate(cons_order)}
        # the men already gone from this group shift the whole group down
        # the curve: the fourth tackle left is still the fourth tackle left,
        # but the curve position is by how many at the spot have been taken
        gone = sum(1 for pid in taken if SLOT_GROUP.get(league.players[pid].pos, league.players[pid].pos) == g)
        for p in ps:
            r = trust * my_rank[p.pid] + (1 - trust) * cons_rank[p.pid]
            slot = expected_slot(p.pos, gone + r)
            # NEED pulls him up the board: a 12-point hole is worth about 30
            # slots to a pure-need drafter, a few to a board man
            gap = need.get(p.pos, 0.0)
            slot -= gap * (0.6 + 2.0 * (1 - trust)) * (0.5 + inflate)
            # a hot seat wants the older, readier man
            slot -= heat * (p.age - 21.5) * 6.0
            if p.pos in POS_CAP_EARLY and len(d.get(p.pos, [])) >= POS_CAP_EARLY[p.pos]:
                # a quarterback hole: a starter four or more under the
                # league's, or one who is 34 and past it, or none at all
                if p.pos == 'QB':
                    starter = d.get('QB', [None])[0]
                    hole = gap >= 4.0 or (starter is not None and starter.age >= 34)
                else:
                    hole = gap > 0
                if not hole:
                    # no club drafts a second kicker, a second punter or a
                    # backup quarterback on day one or two; late, a cheap
                    # developmental arm is fine
                    slot += 60.0 if selection <= 96 else (200.0 if p.pos in ('K', 'P') else 0.0)
            # and never two of them in one draft
            if p.pos in POS_CAP_EARLY and any(league.players[pid].pos == p.pos and league.players[pid].team == abbr for pid in taken):
                slot += 200.0
            rows.append((slot_value(max(1.0, slot)), p))
    rows.sort(key=lambda r: -r[0])
    return rows


def run(league, rng, year=None, verbose=False):
    """The whole draft. Returns [(selection, team, player)]."""
    year = year or league.year
    if not getattr(league, 'scouting', None):
        SC.scout(league, rng)
    cap = CAP.get(year, 301.2)
    picks = sorted((pk for t in league.teams.values() for pk in t.picks
                    if pk.year == year and pk.selection and not pk.used_on),
                   key=lambda pk: pk.selection)
    level = league_starter_level(league); scale = position_scale(league)
    taken = set(); results = []
    for pk in picks:
        owner = pk.owner
        rows = board(league, owner, pk.selection, level, taken, scale)
        if not rows: break
        val, p = rows[0]
        taken.add(p.pid)
        pk.used_on = p.pid
        p.draft_round, p.draft_overall = pk.round, pk.selection
        p.potential = None                     # resolved when the ceiling first matters
        league.sign(p.pid, owner, rookie_contract(pk.selection, cap))
        league.log('draft', pid=p.pid, team=owner, round=pk.round, selection=pk.selection,
                   pos=p.pos, consensus_rank=league.consensus[p.pid]['rank'])
        results.append((pk.selection, owner, p))
        if verbose and pk.round == 1:
            print(f"  {pk.selection:3d} {owner} {p.name:22s} {p.pos:4s} true {p.ovr:.1f}  seen {league.scouting[owner][p.pid]['ovr']}  consensus #{league.consensus[p.pid]['rank']}")
    # the rest are undrafted free agents
    for p in league.draft_pool:
        if p.pid not in taken:
            p.draft_round, p.draft_overall = None, None
            if p.pid not in league.free_agents:
                league.free_agents.append(p.pid)
    league.draft_pool = []
    return results
