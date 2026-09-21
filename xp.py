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

THE MODIFIERS ARE ON WHAT IS EARNED, not on what a point costs. Madden does
the opposite - everyone earns the same and a young star upgrades cheaper -
and the two are close to equivalent, but this way the number on the page is
the number that matters, and a 23-year-old with a superstar trait visibly
outgrains a 33-year-old having the same afternoon.

THE EVENT VALUES ARE SET SO THE POSITIONS LAND TOGETHER. A quarterback throws
for four thousand yards and a corner never touches the ball, so paying per
yard alone would make every skill position outgrow every defender. The per-
unit numbers below are solved backwards from what a full season should be
worth at each spot, not chosen for how they read.
"""

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
    'tackles':    55.0,
    'sacks':      500.0,
    'pressures':  90.0,
    'int_def':    950.0,
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
SEASON = [
    ('pass_yds', 4000, 6000), ('pass_yds', 5000, 5000), ('pass_td', 30, 5500),
    ('pass_td', 40, 5000),
    ('rush_yds', 1000, 6000), ('rush_yds', 1500, 5500), ('rush_td', 10, 4500),
    ('rec_yds', 1000, 6000), ('rec_yds', 1400, 5500), ('rec_td', 10, 4500),
    ('rec', 80, 4000), ('rec', 100, 4000),
    ('sacks', 10, 6000), ('sacks', 15, 5500),
    ('tackles', 100, 6000), ('tackles', 140, 4500),
    ('int_def', 4, 6500), ('int_def', 7, 5500),
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
AWARDS = {
    'mvp': 25000, 'opoy': 18000, 'dpoy': 18000,
    'oroy': 15000, 'droy': 15000,
    'protector': 12000, 'sb_mvp': 12000,
    'all_pro_1': 9000, 'all_pro_2': 5000,
    'coty': 0,                      # a coach award, not a player one
}

# ============================================================ MODIFIERS
# Applied to what is EARNED. A trait is how fast a man turns work into
# ability; age is how much of that is still ahead of him.
DEV_MULT = {'normal': 1.00, 'star': 1.25, 'superstar': 1.55, 'xfactor': 1.90}

AGE_MULT = [(23, 1.40), (26, 1.20), (29, 1.00), (32, 0.70), (99, 0.45)]


def age_mult(age):
    for cap, m in AGE_MULT:
        if age <= cap:
            return m
    return AGE_MULT[-1][1]


def modifier(player):
    dev = getattr(player, 'dev', None) or 'normal'
    return DEV_MULT.get(dev, 1.0) * age_mult(float(getattr(player, 'age', 27)))


# ============================================================ EARNING
def event_xp(line):
    """Raw XP from one stat line - a game, or a season."""
    return sum(PER_EVENT.get(k, 0.0) * float(v or 0)
               for k, v in line.items() if isinstance(v, (int, float)))


def goal_xp(line, table):
    """Every threshold this line clears."""
    return sum(xp for stat, need, xp in table
               if float(line.get(stat, 0) or 0) >= need)


def game_xp(player, line):
    """One game: the events plus whatever weekly lines he crossed."""
    return (event_xp(line) + goal_xp(line, WEEKLY)) * modifier(player)


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
