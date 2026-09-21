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

  PLAYING TIME IS THE STRONGEST PREDICTOR, far stronger than age. Measured
  hazard, P(this is his last season):

                  22-25    26-29    30-32     33+
      starter      1.9%     4.5%    12.7%   18.5%
      rotation    10.3%    18.9%    31.4%   47.7%
      fringe      28.2%    34.8%    42.9%   46.4%

  A 15x spread between a young starter and an old fringe player. A man who
  plays is a man who keeps his job, at every single age.

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

# The measured role multipliers, relative to the 18.7% league-wide base. These
# are what turn one hazard curve into the 15x spread the data actually shows.
ROLE_MULT = {'starter': 0.28, 'rotation': 1.05, 'fringe': 2.05}

# Games played is what separated them in the measurement. Snaps are the better
# signal where we have them - a lineman plays every down of a game he dresses
# for, and a backup dresses for all seventeen and plays none of it, so games
# alone would call them the same man. Roughly 1,000 snaps is a full season for
# a starter on either side of the ball.
STARTER_GAMES = 13
ROTATION_GAMES = 6
STARTER_SNAPS = 600
ROTATION_SNAPS = 220


def base_hazard(pos, age):
    """Position-and-age hazard, with the ends of the curve held flat."""
    tbl = HAZARD.get(POS_GROUP.get(pos, 'LB'), HAZARD['LB'])
    a = int(round(age))
    if a in tbl:
        return tbl[a]
    lo, hi = min(tbl), max(tbl)
    return tbl[lo] if a < lo else tbl[hi]


def role_of(games, snaps=None):
    if snaps is not None and snaps > 0:
        if snaps >= STARTER_SNAPS:
            return 'starter'
        if snaps >= ROTATION_SNAPS:
            return 'rotation'
        return 'fringe'
    if games >= STARTER_GAMES:
        return 'starter'
    if games >= ROTATION_GAMES:
        return 'rotation'
    return 'fringe'


def chance(player, games, ovr=None, league_avg_ovr=72.0, snaps=None):
    """
    Probability this man retires after the season just played.

    Age and position set the base; the role he actually held moves it by up to
    15x, because that is what the data shows. Quality is a second, gentler
    nudge on top - a man well above replacement finds another job, and a man
    well below does not, independent of how many games he happened to play on
    a thin roster.
    """
    h = base_hazard(player.pos, player.age) * ROLE_MULT[role_of(games, snaps)]
    if ovr is not None:
        # Quality has to bite harder than a linear nudge. At 0.030 with a
        # floor of 0.25, a 92-overall starter still walked away at about 3% a
        # year - which across two thousand players retired twenty-eight men
        # rated 85 or better in a single offseason. Elite players do not
        # quietly retire at 27; they are the ones who play until their body
        # stops them.
        gap = ovr - league_avg_ovr
        h *= float(np.clip(1.0 - 0.055 * gap, 0.06, 2.4))
    # nobody is legally required to keep playing, and nobody retires at 22
    # off a single good year
    if player.age < 24:
        h *= 0.6
    if player.age >= 38:
        h = max(h, 0.35)
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
        # SPECIALISTS. StatBook records nothing for a kicker or punter and
        # field_units never puts him on the field, so every one of them read
        # as a man who had not played - and a 23-year-old kicker rated 90 was
        # retiring at the fringe rate. He is his club's only kicker; he played
        # every week. Until kicking stats exist this stands in for them.
        if p.pos in ('K', 'P', 'LS'):
            t = league.teams.get(p.team)
            if t is not None and t.starter(p.pos) is p:
                snaps, games = STARTER_SNAPS, 17.0
        if rng.random() < chance(p, games, p.ovr, avg, snaps):
            p.retired = True
            t = league.teams.get(p.team)
            if t and p in t.roster:
                t.roster.remove(p)
                if p.contract:
                    # A retirement is not a release. The signing bonus still
                    # accelerates, but the club keeps no salary obligation.
                    dead, _n, _s = p.contract.release(0)
                    t.cap.dead += dead
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
