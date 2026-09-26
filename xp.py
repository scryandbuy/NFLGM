"""
XP: WHAT EVERYTHING IS WORTH.

Earning is MECHANICAL by decision - a catch is worth x, an interception is
worth y, and there is no judgement in it. What a general manager does with the
XP afterwards is where the thinking lives; this file is just the ledger.

FIVE SOURCES, which is the structure Madden uses and it holds up:

  PER EVENT      every countable thing that happens on a field
  WEEKLY         hit a line in a single game
  SEASON         hit a line across a year
  MILESTONE      career totals, which only pay once
  AWARDS         the ten that exist

Goals pay far more than the events underneath them, deliberately. A receiver
who quietly gains sixty yards a week earns steadily; one who goes for a
hundred and scores twice earns in jumps. That gap is what makes a good season
feel different from an adequate one.

EARNING IS AGE-BLIND. A thirty-four-year-old who goes for a hundred and fifty
yards earned exactly what a rookie would have. What differs is what he can DO
with it: the cost of an attribute point is priced off the real aging curve, so
the same XP buys a young man five overall and an old one barely one. Age
belongs in one place, not two.

THE EVENT VALUES ARE SET SO THE POSITIONS LAND TOGETHER. A quarterback throws
for four thousand yards and a corner never touches the ball, so paying per
yard alone would make every skill position outgrow every defender. The per-
unit numbers below are solved backwards from what a full season should be
worth at each spot, not chosen for how they read.
"""
import numpy as np

# ============================================================ PER EVENT
# XP per single unit of each stat. Negative for the things that lose games.
PER_EVENT = {
    # ---- passing ----
    'pass_yds':   2.0,
    'pass_td':    200.0,
    'pass_cmp':   12.0,
    'pass_att':   0.0,          # volume alone is not production
    'ints':      -160.0,
    'sacked':    -25.0,

    # ---- rushing ----
    'rush_yds':   6.0,
    'rush_td':    250.0,
    'rush_att':   2.0,          # a carry is a rep, and reps are worth a little

    # ---- receiving ----
    'rec_yds':    6.0,
    'rec':        40.0,
    'rec_td':     250.0,
    'tgt':        4.0,
    'drops':     -60.0,

    # ---- ball security ----
    'fum':       -60.0,
    'fum_lost':  -140.0,

    # ---- defence ----
    # A CORNER HAS ALMOST NO BOX SCORE. He is paid to be thrown at and miss,
    # and the stat that would capture him - passes defended - is not something
    # this engine records at all. Until it does, his few countable events have
    # to carry more weight or every defensive back grows at half the rate of
    # everyone else. That is a stand-in and it is marked as one.
    'tackles':    75.0,         # up from 55: linebackers and safeties record little else
    'sacks':      500.0,
    'pressures':  90.0,
    'int_def':    950.0,
    'pass_def':   150.0,        # recorded all along and paid nothing; most of a corner's box score
    'ff':         450.0,

    # ---- offensive line ----
    # Blocking has no counting stat, which is why a lineman's page is blank on
    # any real site. The win rates ARE his box score, so they are paid like one.
    'pb_wins':    12.0,
    'rb_wins':    12.0,
    'sacks_allowed':     -200.0,
    'pressures_allowed': -35.0,

    # ---- being out there ----
    # A snap is worth something on its own. It is why rotating a backup in
    # develops him, and why a man buried on a depth chart does not grow.
    'snaps':      3.0,
}

# ============================================================ WEEKLY
# (stat, threshold, xp). Hit in a single game. These are the biggest regular
# source by design - a good Sunday should be worth more than the sum of its
# parts.
WEEKLY = [
    ('pass_yds', 300, 1400), ('pass_yds', 400, 1200), ('pass_td', 3, 1300),
    ('pass_td', 5, 1500),
    ('rush_yds', 100, 1400), ('rush_yds', 150, 1100), ('rush_td', 2, 1200),
    ('rec_yds', 100, 1400), ('rec_yds', 150, 1100), ('rec_td', 2, 1200),
    ('rec', 8, 900),
    ('sacks', 2, 1400), ('sacks', 3, 1300),
    ('tackles', 10, 1100), ('int_def', 1, 1200), ('int_def', 2, 1400),
    ('ff', 1, 900),
    # A LINEMAN CLEARS THIRTY BLOCKS EVERY WEEK HE STARTS, so a threshold
    # there is not a goal, it is a salary. It has to sit where only a good
    # afternoon reaches it.
    ('pb_wins', 42, 1100),
]

# ============================================================ SEASON
# Second tiers pay half the first: the first tier is the big year, the second
# was the same season being paid again, and the stack was a third of what
# carried a star receiver to four times the ledger line.
SEASON = [
    ('pass_yds', 4000, 6000), ('pass_yds', 5000, 2500), ('pass_td', 30, 5500),
    ('pass_td', 40, 2500),
    ('rush_yds', 1000, 6000), ('rush_yds', 1500, 2750), ('rush_td', 10, 4500),
    ('rec_yds', 1000, 6000), ('rec_yds', 1400, 2750), ('rec_td', 10, 4500),
    ('rec', 80, 4000), ('rec', 100, 2000),
    ('sacks', 10, 6000), ('sacks', 15, 2750),
    ('tackles', 100, 6000), ('tackles', 140, 2250),
    ('int_def', 4, 6500), ('int_def', 7, 2750),
    ('pb_wins', 500, 5000),
]

# ============================================================ MILESTONE
# Career totals. Each pays ONCE, ever - the whole point of a milestone is that
# it cannot be farmed.
MILESTONE = [
    ('pass_yds', 10000, 4000), ('pass_yds', 25000, 8000),
    ('pass_yds', 50000, 15000), ('pass_td', 100, 6000), ('pass_td', 300, 14000),
    ('rush_yds', 5000, 5000), ('rush_yds', 10000, 12000),
    ('rush_td', 50, 6000), ('rush_td', 100, 14000),
    ('rec_yds', 5000, 5000), ('rec_yds', 10000, 12000),
    ('rec', 500, 6000), ('rec', 800, 12000),
    ('sacks', 50, 6000), ('sacks', 100, 14000),
    ('tackles', 500, 5000), ('tackles', 1000, 11000),
    ('int_def', 20, 6000), ('int_def', 40, 13000),
]

# ============================================================ AWARDS
# The five that carry a guaranteed development tier are also the five that pay
# most - they are the season a career is built on.
# Halved. The five major awards already carry a guaranteed development tier,
# which is the real prize; 31k of XP on top is what turned a 93 into a 99 in
# one year.
AWARDS = {
    'mvp': 12000, 'opoy': 9000, 'dpoy': 9000,
    'oroy': 7500, 'droy': 7500,
    'protector': 6000, 'sb_mvp': 6000,
    'all_pro_1': 4500, 'all_pro_2': 2500,
    'coty': 0,                      # a coach award, not a player one
}

# ============================================================ MODIFIERS
# Only the DEVELOPMENT TRAIT touches what a man earns. Age used to sit here
# too and it does not any more, because age now sets what a point COSTS - and
# carrying it in both places counted it twice.
# Cut from 1.00 / 1.25 / 1.55 / 1.90. A star already out-earns everyone by
# producing more, so a large multiplier counted him twice: an xfactor
# receiver's season came to six times the ledger's own big-year line.
DEV_MULT = {'normal': 1.00, 'star': 1.05, 'superstar': 1.10, 'xfactor': 1.15}


def modifier(player):
    dev = getattr(player, 'dev', None) or 'normal'
    return DEV_MULT.get(dev, 1.0)


# ============================================================ WHAT IT COSTS
# THREE THINGS SET THE PRICE OF A POINT, and all three compound.
#
# 1. EVERY POINT BOUGHT RAISES THE PRICE OF THE NEXT ONE, whatever it goes
#    into. Buying catching makes speed dearer too. This is what stops a league
#    filling with 99s: the first points of a career are cheap and the fortieth
#    is not, and a man who has already been built up pays for having been.
# 2. AGE, every year of it. Not a step at 25: each year of age adds to the
#    price, and the position's real aging curve steepens it once his curve is
#    falling (a back's from 26, a quarterback's barely at all). The §5 growth
#    table is the guardrail this is solved against - what a big year should buy
#    at 22, 25, 28, 31 and 34.
# 3. THE ATTRIBUTE. Speed, acceleration, agility, strength, change of
#    direction and jumping help every man on the field whatever his position,
#    so they cost a multiple of what a position skill costs. Catching, block
#    shed and the like help one kind of player and are priced at the base.
#
# The overall wall stays alongside these (a 90 improving is harder than a 70
# improving), so a man who arrived at 95 pays more than one who was built up.
BASE_COST = 600.0            # a rookie's first point into a position skill
PHYSICAL_BASE = 2500.0       # a 21-year-old's first point of speed; see the wall in cost_per_point
PHYS_ATTR_ESCALATOR = 1.25   # per point already bought into the same physical

PHYSICAL = {'speed_rating', 'accel_rating', 'agility_rating', 'strength_rating',
            'change_of_direction_rating', 'jump_rating'}
PHYSICAL_MULT = 2.5
# Awareness carries the biggest weight for a quarterback, a centre and a
# safety and is not a physical; it is buyable by anyone at a premium.
AWARENESS_MULT = 1.75

ESCALATOR = 1.030            # per point ever bought, into anything
# and the same skill again costs more than a new one: learning has diminishing
# returns per skill. Without this a corner put nearly every point into man
# coverage and the league's corners gained +3.5 a year in it at 21-24 and +2.3
# at 25-27 (CB1 average 84 to 86 in three seasons) while receivers, whose
# points spread across routes, catching and release, grew a point a year.
ATTR_ESCALATOR = 1.060       # per point already bought into this attribute

AGE_FROM, AGE_SLOPE = 21.0, 0.15     # per year of age past a rookie's
# A quarterback's production curve is flat into his late thirties, so the
# curve term never bites for him and a 38-year-old off a big year was adding
# two overall. Learning still slows. The first version started the brake at
# 30 at 12% a year; three franchise seasons showed QBs aged 25-27 gaining
# +0.9 a year in accuracy and 28-30 gaining +1.4, and the league's QB1
# average rose 85.7 to 88.3. Real quarterbacks plateau at 27-28. The brake now
# starts at 27 and is steeper: at 0.30 one franchise season still had 28-to-30-
# year-olds gaining +0.6 a year in accuracy (from +1.4), so it is 0.40, which
# puts a 30-year-old at about 2.2x a 26-year-old's price and a 34-year-old
# at about 3.8x.
LATE_SLOPE = {'QB': (27.0, 0.40)}
OVR_PIVOT, OVR_SLOPE = 70.0, 0.030


def points_bought(player):
    """Every attribute point this man has ever bought."""
    return sum(v for k, v in player.xp_spent.items()
               if not k.startswith('_') and isinstance(v, (int, float)))


def cost_per_point(player, attr=None):
    """XP for one more attribute point, for this man right now."""
    import regression as RG
    f = RG.curve_factor(player.pos, player.age)
    curve = 1.0 if f >= 1.0 else (1.0 / max(f, 0.30)) ** 1.5
    years = max(0.0, float(player.age) - AGE_FROM)
    ovr_scale = 1.0 + OVR_SLOPE * max(0.0, float(player.ovr) - OVR_PIVOT)
    phys = (PHYSICAL_MULT if attr in PHYSICAL else
            AWARENESS_MULT if attr == 'awareness_rating' else 1.0)
    late_from, late_slope = LATE_SLOPE.get(player.pos, (99.0, 0.0))
    late = 1.0 + late_slope * max(0.0, float(player.age) - late_from)
    same = float(player.xp_spent.get(attr, 0) or 0) if attr else 0.0
    if attr in PHYSICAL:
        # PHYSICALS ARE NOT LEARNED. Speed, burst, agility, jumping and strength grow only while a
        # young man's body is still finishing, and by a little. They price off their own base and
        # climb a wall with age: x1 at 21 and 22, x2 at 23, x3.5 at 24, x6 at 25, x10 at 26, doubling
        # each year after; strength grows a little longer, so its wall is softer. Repeats climb 25%
        # a point, so speed goes up in ones. A 22-year-old starter can add a point of speed once or
        # twice a season if he spends nothing else; a 26-year-old is looking at three seasons of XP.
        age = float(player.age)
        wall = 1.0 if age < 23 else 2.0 if age < 24 else 3.5 if age < 25 else 6.0 if age < 26 else 10.0 * (2.0 ** max(0.0, age - 26.0))
        if attr == 'strength_rating': wall = wall ** 0.7
        return (PHYSICAL_BASE * wall * ovr_scale * ESCALATOR ** points_bought(player) * PHYS_ATTR_ESCALATOR ** same)
    return (BASE_COST * curve * (1.0 + AGE_SLOPE * years) * ovr_scale * late
            * ESCALATOR ** points_bought(player) * ATTR_ESCALATOR ** same * phys)


# ============================================================ THE CEILING
# Potential is a hard ceiling on overall, set on day one. At the ceiling a
# man keeps earning and can BUY the ceiling up, one overall at a time, then
# goes back to buying attributes. Under-23s arrive with a range rather than a
# point; the point is drawn from it the first time it matters, so the same
# prospect turns out differently in different saves.
UNLOCK_BASE, UNLOCK_FROM, UNLOCK_GROWTH = 5000.0, 80.0, 1.10


def ceiling(player, rng=None):
    """His hard ceiling, resolving a range on first use. None means uncapped."""
    if player.potential is None and player.potential_range:
        lo, hi = player.potential_range
        r = rng or np.random.default_rng()
        player.potential = float(round(r.uniform(lo, hi), 1))
    return player.potential


def unlock_cost(player):
    """XP to raise the ceiling by one overall, for this man right now."""
    pot = ceiling(player)
    if pot is None:
        return None
    years = max(0.0, float(player.age) - AGE_FROM)
    return (UNLOCK_BASE * UNLOCK_GROWTH ** max(0.0, pot - UNLOCK_FROM)
            * (1.0 + AGE_SLOPE * years))


def unlock(player):
    """Raise the ceiling one point. Returns the cost, or None."""
    pot = ceiling(player)
    if pot is None or pot >= 99.0:
        return None
    cost = unlock_cost(player)
    if player.xp < cost:
        return None
    player.xp -= cost
    player.potential = min(99.0, pot + 1.0)
    player.xp_spent['_unlocks'] = player.xp_spent.get('_unlocks', 0) + 1
    return cost


def at_ceiling(player, attr=None):
    """Would one more point (into attr, or the heaviest skill) breach it?"""
    import targets as TG
    pot = ceiling(player)
    if pot is None:
        return False
    if attr is None:
        w = TG.DEPTH_WEIGHTS.get(player.pos, {})
        attr = max(w, key=w.get) if w else 'awareness_rating'
    trial = dict(player.ratings); trial[attr] = trial.get(attr, 70.0) + 1.0
    return TG.position_score(trial, player.pos) > pot + 1e-6


def buy(player, attr):
    """
    Spend: one point into one attribute. Returns the cost paid, or None if he
    cannot afford it, the attribute is at 99, or the point would take him
    past his ceiling. This is the only way a rating goes up through XP, so
    the ledger of purchases is always exact.
    """
    cur = player.ratings.get(attr, 70.0)
    if cur >= 99.0 or at_ceiling(player, attr):
        return None
    cost = cost_per_point(player, attr)
    if player.xp < cost:
        return None
    player.xp -= cost
    player.ratings[attr] = cur + 1.0
    player.xp_spent[attr] = player.xp_spent.get(attr, 0) + 1
    player.xp_spent['_bought_season'] = player.xp_spent.get('_bought_season', 0) + 1
    return cost


# ============================================================ EARNING
def event_xp(line):
    """Raw XP from one stat line - a game, or a season."""
    return sum(PER_EVENT.get(k, 0.0) * float(v or 0)
               for k, v in line.items() if isinstance(v, (int, float)))


def goal_xp(line, table):
    """Every threshold this line clears."""
    return sum(xp for stat, need, xp in table
               if float(line.get(stat, 0) or 0) >= need)


# A weekly line hit again in the same season pays this share of the last
# time. Eleven 100-yard games were paying eleven full bonuses; a fourth
# 100-yard afternoon is a good day, not a milestone.
WEEKLY_REPEAT = 0.80


def weekly_xp(player, line, season=None):
    """The weekly lines crossed in this game, each paid less every time he has
    already crossed it this season."""
    hits = player.xp_spent.setdefault('_weekly', {})
    total = 0.0
    for stat, need, xp in WEEKLY:
        if float(line.get(stat, 0) or 0) >= need:
            key = f'{season}:{stat}:{need}'
            n = hits.get(key, 0)
            total += xp * WEEKLY_REPEAT ** n
            hits[key] = n + 1
    return total


def game_xp(player, line, season=None):
    """One game: the events plus whatever weekly lines he crossed."""
    return (event_xp(line) + weekly_xp(player, line, season)) * modifier(player)


def season_xp(player, line):
    """End of year: the season goals only - events were paid week by week."""
    return goal_xp(line, SEASON) * modifier(player)


def milestone_xp(player, career_before, career_after):
    """
    Career lines crossed THIS season and never before. Paid once, ever.
    """
    total = 0.0
    for stat, need, xp in MILESTONE:
        if (float(career_after.get(stat, 0) or 0) >= need
                > float(career_before.get(stat, 0) or 0)):
            total += xp
    return total * modifier(player)


def award_xp(player, awards):
    return sum(AWARDS.get(a, 0) for a in awards) * modifier(player)


# ============================================================ THE BOOK
# Where each man's XP came from, kept beside the balance so the earning can
# be audited by source: game events, snaps, season lines, milestones, awards.
def credit(player, amount, source):
    """Record the source and return the amount, so `p.xp += credit(...)`.
    Work ethic scales everything a man earns, 0.8x to 1.2x (personality.py)."""
    import personality as PT, staff as ST
    amount = float(amount or 0.0) * PT.xp_mult(player)
    team = getattr(player, '_team_ref', None)
    if team is not None:
        amount *= ST.xp_mult(team, player)
    if amount:
        led = player.xp_spent.setdefault('_earned', {})
        led[source] = led.get(source, 0.0) + float(amount)
    return float(amount)


def close_season(league, votes, season=None):
    """
    End of the regular season: the season lines, the career milestones
    crossed this year, and the awards. Events and weekly lines were paid week
    by week. Returns {pid: xp paid here}.
    """
    year = season or league.year
    lines = league.stats.get(year, {})
    paid = {}
    for pid, line in lines.items():
        p = league.player(pid)
        if p is None: continue
        got = credit(p, season_xp(p, line), 'season')
        before, after = {}, {}
        for yr, sl in p.career.items():
            for k, v in sl.items():
                if not isinstance(v, (int, float)): continue
                after[k] = after.get(k, 0) + v
                if yr != year: before[k] = before.get(k, 0) + v
        got += credit(p, milestone_xp(p, before, after), 'milestone')
        p.xp += got; paid[pid] = got
    # awards: a pid, or a list of pids for the All-Pro teams
    for award, who in (votes or {}).items():
        if award not in AWARDS or not AWARDS[award]: continue
        for w in (who if isinstance(who, list) else [who]):
            pid = getattr(w, 'pid', w)
            p = league.player(pid) if isinstance(pid, str) else None
            if p is None: continue
            got = credit(p, award_xp(p, [award]), 'award')
            p.xp += got; paid[pid] = paid.get(pid, 0.0) + got
    return paid


if __name__ == '__main__':
    class P:
        def __init__(s, age, dev): s.age, s.dev = age, dev

    print('A FULL SEASON, by position - events + weekly + season goals\n')
    seasons = {
        'QB  4500yd 32td 10int': dict(pass_yds=4500, pass_td=32, ints=10,
                                      pass_cmp=390, sacked=30, snaps=1050),
        'RB  1200yd 11td':       dict(rush_yds=1200, rush_td=11, rush_att=260,
                                      rec=40, rec_yds=300, snaps=700),
        'WR  1150yd 9td':        dict(rec_yds=1150, rec=88, rec_td=9, tgt=135,
                                      drops=5, snaps=1000),
        'EDGE 12sk 55tk':        dict(sacks=12, tackles=55, pressures=48,
                                      ff=3, snaps=900),
        'CB  4int 70tk':         dict(int_def=4, tackles=70, snaps=1000),
        'LT  94% pbwr':          dict(pb_snaps=600, pb_wins=555, rb_wins=380,
                                      sacks_allowed=4, pressures_allowed=22,
                                      snaps=1080),
    }
    base = P(26, 'normal')
    for lab, line in seasons.items():
        # weekly goals are hit game by game, so approximate at a seventeenth
        wk = {k: v / 17.0 for k, v in line.items()}
        weekly = goal_xp(wk, WEEKLY) * 17
        tot = (event_xp(line) + weekly + goal_xp(line, SEASON)) * modifier(base)
        print('  %-24s %8.0f XP   (events %6.0f | weekly %5.0f | season %5.0f)'
              % (lab, tot, event_xp(line), weekly, goal_xp(line, SEASON)))
    print('\nthe same receiver, aged and by trait:')
    for age in (22, 26, 30, 34):
        for dev in ('normal', 'superstar'):
            p = P(age, dev)
            l = seasons['WR  1150yd 9td']
            wk = {k: v / 17.0 for k, v in l.items()}
            tot = (event_xp(l) + goal_xp(wk, WEEKLY) * 17
                   + goal_xp(l, SEASON)) * modifier(p)
            print('  age %2d %-10s %8.0f XP  (x%.2f)' % (age, dev, tot,
                                                         modifier(p)))
    print('\nawards on top: MVP %s, All-Pro 1st %s'
          % (AWARDS['mvp'], AWARDS['all_pro_1']))
