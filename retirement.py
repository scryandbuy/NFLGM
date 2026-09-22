"""
RETIREMENT.

Measured, not assumed. Fifteen seasons of real player-seasons (2011-2025),
joined to birth dates, with each man's final season identified - and 2025
excluded as censored, since a 2025 final season may only mean he is still
playing.

WHAT THE DATA SAID, AND WHY THE OBVIOUS APPROACH IS WRONG:

  aging_curves.json already carried a per-position "retention" curve, and it
  is NOT a retirement rate. It measures a player leaving the dataset, which
  conflates retiring, being cut, and simply not accumulating stats. Applied
  directly it would have retired 35-50% of the league every year.

  The true figure: 18.7% of all player-seasons are a final season. But that
  number is useless on its own, because it is dominated by fringe players
  washing out rather than starters retiring.

  PLAYING TIME IS THE STRONGEST PREDICTOR IN THE REAL WORLD, and it is
  deliberately NOT used here. Measured hazard:

                  22-25    26-29    30-32     33+
      starter      1.9%     4.5%    12.7%   18.5%
      rotation    10.3%    18.9%    31.4%   47.7%
      fringe      28.2%    34.8%    42.9%   46.4%

  That is a real 15x spread, and it is real because snaps predict getting
  CUT - which is a different event here. A buried 23-year-old goes to free
  agency and signs somewhere; he does not stop playing football. Using the
  table directly retired three hundred men an offseason, most of them young
  and most of them merely stuck behind someone better. So snaps are out and
  almost nobody under 27 goes, by design.

  POSITION MATTERS TOO, and in the direction you would expect. Running backs
  fall off a cliff: hazard 0.32 at 29 and 0.52 at 32, against 0.21 and 0.29
  for a defensive lineman at the same ages. Median final age is 25.3 for a
  receiver and 25.8 for a back, against 27.3 for a lineman and 28.5 for a
  quarterback. Specialists last longest of all - median final age 28.5, still
  going at 38.

THE ONE THING THIS MODEL DOES THAT THE DATA CANNOT: in the real league, "never
plays again" covers both a man who retires and a man nobody signs. Here those
are different events - an unsigned player sits in free agency and may be
picked up. So the hazard below is applied as RETIREMENT, and the quality
gradient is what keeps a useful player in the league: a starter almost never
walks away young, and a fringe 33-year-old usually does.
"""
import json
import os

import numpy as np

_D = os.path.dirname(os.path.abspath(__file__))

# P(final season | playing at this age), by position group, from 2011-2024
# completed careers. Ages outside the measured range fall back to the nearest.
HAZARD = {
    'QB':  {22: .029, 23: .130, 24: .145, 25: .142, 26: .131, 27: .133,
            28: .151, 29: .193, 30: .159, 31: .070, 32: .155, 33: .170,
            34: .231, 35: .206, 36: .214},
    'RB':  {22: .120, 23: .120, 24: .200, 25: .170, 26: .220, 27: .220,
            28: .280, 29: .320, 30: .300, 31: .380, 32: .520},
    'WR':  {22: .100, 23: .170, 24: .210, 25: .200, 26: .200, 27: .220,
            28: .200, 29: .250, 30: .290, 31: .240, 32: .380, 33: .290,
            34: .480},
    'TE':  {22: .030, 23: .120, 24: .130, 25: .190, 26: .200, 27: .180,
            28: .200, 29: .190, 30: .230, 31: .330, 32: .380, 33: .390},
    'OL':  {22: .020, 23: .130, 24: .110, 25: .160, 26: .160, 27: .160,
            28: .170, 29: .180, 30: .240, 31: .360, 32: .380, 33: .530,
            34: .340, 35: .390},
    'DL':  {22: .040, 23: .090, 24: .140, 25: .140, 26: .170, 27: .180,
            28: .180, 29: .210, 30: .210, 31: .230, 32: .290, 33: .340,
            34: .410, 35: .530},
    'LB':  {22: .070, 23: .110, 24: .150, 25: .180, 26: .170, 27: .170,
            28: .210, 29: .250, 30: .280, 31: .380, 32: .360, 33: .370,
            34: .380},
    'DB':  {22: .070, 23: .120, 24: .160, 25: .160, 26: .190, 27: .180,
            28: .190, 29: .190, 30: .310, 31: .370, 32: .350, 33: .470,
            34: .400},
    'SPEC': {23: .100, 24: .130, 25: .090, 26: .140, 27: .120, 28: .160,
             29: .080, 30: .090, 31: .130, 32: .110, 33: .160, 34: .160,
             35: .210, 36: .130, 37: .280, 38: .190},
}

POS_GROUP = {
    'QB': 'QB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE',
    'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
    'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL',
    'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB',
    'CB': 'DB', 'FS': 'DB', 'SS': 'DB',
    'K': 'SPEC', 'P': 'SPEC', 'LS': 'SPEC',
}

# AGE DECIDES. BY DESIGN, NOT BY THE DATA.
#
# The measurement says a 22-25 fringe player ends his career 28.2% of the
# time, and that is true of the real NFL - but it is not RETIREMENT. It is a
# man getting cut who never catches on anywhere. In this league he goes to
# free agency and someone signs him, so applying that number retired three
# hundred men an offseason and most of them were 23-year-olds who had simply
# been buried on a depth chart.
#
# So two deliberate departures from the measured data:
#
#   SNAPS DO NOT COUNT. Playing time was the strongest predictor in the real
#   world precisely because it predicts getting cut, and getting cut is not
#   the same event here. A good player stuck behind a better one asks for a
#   trade; he does not quit at 26.
#
#   ALMOST NOBODY UNDER 27 GOES, whatever his role. Careers end young in the
#   real league because rosters churn, not because men that age stop wanting
#   to play.
#
# What is kept from the data is the SHAPE - the climb through the thirties,
# and the fact that a back ages faster than a lineman.
AGE_HAZARD = {
    21: .004, 22: .004, 23: .005, 24: .005, 25: .006, 26: .008,
    27: .030, 28: .055, 29: .090,
    30: .140, 31: .175, 32: .215,
    33: .300, 34: .380, 35: .460,
    36: .540, 37: .600, 38: .660, 39: .720, 40: .780,
}


def age_hazard(age):
    a = int(round(age))
    if a < min(AGE_HAZARD): return AGE_HAZARD[min(AGE_HAZARD)]
    if a > max(AGE_HAZARD): return 0.85
    return AGE_HAZARD[a]


def pos_factor(pos, age):
    """
    How this position ages against the league. Kept from the real curves: a
    back at 29 sits at .32 where the league mean is near .21, so he carries a
    factor above one; a specialist sits well below.
    """
    a = int(round(age))
    mine = base_hazard(pos, a)
    vals = []
    for g in HAZARD:
        if g == 'SPEC':
            continue                    # specialists would drag the mean down
        tbl = HAZARD[g]
        k = min(max(a, min(tbl)), max(tbl))
        vals.append(tbl[k])
    mean = float(np.mean(vals)) if vals else mine
    return float(np.clip(mine / max(mean, 1e-6), 0.45, 1.9))


def base_hazard(pos, age):
    """Position-and-age hazard, with the ends of the curve held flat."""
    tbl = HAZARD.get(POS_GROUP.get(pos, 'LB'), HAZARD['LB'])
    a = int(round(age))
    if a in tbl:
        return tbl[a]
    lo, hi = min(tbl), max(tbl)
    return tbl[lo] if a < lo else tbl[hi]


def chance(player, games=0, ovr=None, league_avg_ovr=72.0, snaps=None):
    """
    Probability this man retires after the season just played.

    Age and position set it; quality moves it. Playing time deliberately does
    NOT enter - see the note on AGE_HAZARD above. games and snaps are kept in
    the signature so callers do not have to change, and so injury history can
    be added here later without another signature churn.
    """
    h = age_hazard(player.age) * pos_factor(player.pos, player.age)
    if ovr is not None:
        # A good player keeps getting paid, and the reasons to stop arrive
        # later for him. Steeper before thirty, shallower after, so an aging
        # star can still go while a young one effectively cannot.
        gap = ovr - league_avg_ovr
        if player.age < 30:
            h *= float(np.clip(1.0 - 0.090 * gap, 0.015, 2.2))
        else:
            h *= float(np.clip(1.0 - 0.045 * gap, 0.15, 2.2))
    # hidden, drawn at creation: some men are finished at 28 and some play to
    # 38, and nothing on their rating sheet says which
    h /= max(0.45, player.longevity)
    if player.age >= 39:
        h = max(h, 0.45)
    return float(np.clip(h, 0.0, 0.95))


def run(league, rng, verbose=False):
    """
    Retire the league. Called FIRST in the offseason, before any roster or
    contract decision, because a man who retires frees his cap hit and opens
    a hole his club then has to fill.
    """
    year = league.year
    ovrs = [p.ovr for p in league.players.values() if not p.retired]
    avg = float(np.mean(ovrs)) if ovrs else 72.0
    stats = league.stats.get(year, {})

    # ONLY MEN WHO WERE ACTUALLY IN THE LEAGUE.
    # The seed carries 66 players a club, well past a 53-man limit, and
    # cut-down is not built yet - so roughly a dozen men per team never take a
    # snap all year. Those are CUTS, not retirements, and running the hazard
    # over them retired 37% of the league against a real 18.7%. They are left
    # alone here and belong to the cut-down step when it exists.
    ACTIVE = 53
    eligible = set()
    for t in league.teams.values():
        ranked = sorted(t.active(), key=lambda p: -p.ovr)[:ACTIVE]
        eligible.update(p.pid for p in ranked)
    eligible.update(pid for pid in league.free_agents)

    retired = []
    for p in list(league.players.values()):
        if p.retired or p.pid not in eligible:
            continue
        line = stats.get(p.pid, {})
        games = float(line.get('games', 0) or 0)
        snaps = float(line.get('snaps', 0) or 0)
        # Both are passed through unused - see the note on AGE_HAZARD. They
        # stay on the call so injury history can join them here later without
        # another signature change.
        if rng.random() < chance(p, games, p.ovr, avg, snaps):
            p.retired = True
            t = league.teams.get(p.team)
            if t and p in t.roster:
                t.roster.remove(p)
                if p.contract:
                    # A retirement is not a release. The signing bonus still
                    # accelerates, but the club keeps no salary obligation.
                    # He retires after the season and before the year rolls,
                    # so the year just played is already charged; what is
                    # left of his bonus accelerates onto NEXT year's books.
                    # Charging release(0) here put it on the finished year,
                    # where the roll then erased it.
                    dead = p.contract.remaining_proration(1)
                    t.cap.dead_next += dead
            if p.pid in league.free_agents:
                league.free_agents.remove(p.pid)
            p.team, p.contract = None, None
            retired.append(p)
            league.log('retire', pid=p.pid, name=p.name, pos=p.pos,
                       age=round(p.age, 1), ovr=round(p.ovr, 1))
    if verbose:
        print(f'  {len(retired)} retired '
              f'({100.0 * len(retired) / max(len(ovrs), 1):.1f}% of the league)')
    return retired


if __name__ == '__main__':
    import collections
    import league as LG, season as SN
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    before = len([p for p in L.players.values() if not p.retired])
    got = run(L, rng, verbose=True)
    by = collections.Counter(POS_GROUP.get(p.pos, '?') for p in got)
    tot = collections.Counter(POS_GROUP.get(p.pos, '?')
                              for p in L.players.values())
    print('\n%-5s %6s %6s   real median final age' % ('pos', 'ret', 'rate'))
    REAL = {'QB': 27.2, 'RB': 25.8, 'WR': 25.3, 'TE': 26.4, 'OL': 26.4,
            'DL': 26.4, 'LB': 26.1, 'DB': 26.0, 'SPEC': 28.5}
    for g in sorted(by):
        print('%-5s %6d %5.1f%%   %.1f' % (g, by[g], 100 * by[g] / tot[g],
                                           REAL.get(g, 0)))
    ages = [p.age for p in got]
    print('\nmean age of a retiring player: %.1f' % np.mean(ages))
    old = [p for p in got if p.age >= 33]
    print('33 and over: %d of %d' % (len(old), len(got)))
