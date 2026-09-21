"""
CUT-DOWN TO 53.

roster_construction was built and never called once, and almost every open
roster problem traced back to that: clubs finished an offseason with 47 men
and a minimum of 14, one club a year ended over the cap with nothing left to
move, and a team with seventeen players had no mechanism forcing it to go and
find thirty-six more.

WHAT THE ENGINE ALREADY DOES, and why it is worth using rather than writing a
simpler version:

  POSITIONAL MINIMUMS ARE NOT NEGOTIABLE. You cannot dress two offensive
  linemen because they happened to grade out below a fourth tight end.

  GROUP MINIMUMS BIND TOO. The per-position floors sum to five offensive
  linemen and no club in football carries fewer than nine, because five means
  one injury ends your game.

  EVERY OTHER SPOT COMPETES ON MARGINAL VALUE. A fourth receiver on a team
  with three good ones is worth less than a second corner on a team with one,
  and slot_value prices that directly - so the 53rd man is chosen against
  what the roster already has rather than by rating.

The output is a real shape: 2 QB, 3 HB, 7 WR, 4 TE, 9 OL, 11 DL, 4 LB, 10 DB
and 3 specialists.

CUTS COST MONEY, and that is the point of doing this after free agency rather
than before. Releasing a man accelerates his remaining signing bonus onto this
year's cap, so a club that overspent in March pays for it in August - which is
exactly when real teams discover the same thing.
"""
import numpy as np

import roster_construction as RC
import contracts as CT

ROSTER_LIMIT = 53

# How deep a real 53 goes at each spot, from what roster_construction itself
# produces: 2 QB, 3 HB, 7 WR, 4 TE, 9 OL, 11 DL, 4 LB, 10 DB, 3 specialists.
POS_CAP = {'QB': 3, 'HB': 4, 'FB': 2, 'WR': 7, 'TE': 4,
           'LT': 3, 'LG': 3, 'C': 3, 'RG': 3, 'RT': 3,
           'LEDG': 4, 'REDG': 4, 'DT': 5,
           'MIKE': 3, 'WILL': 3, 'SAM': 3,
           'CB': 6, 'FS': 3, 'SS': 3, 'K': 1, 'P': 1, 'LS': 1}


def rows_for(team):
    """The shape roster_construction wants."""
    return [dict(pos=p.pos, ovr=p.ovr, pid=p.pid, name=p.name)
            for p in team.active()]


def run(league, rng, verbose=False):
    """
    Every club to 53. Surplus players are released and reach the market.
    """
    cuts, short = [], []
    for abbr, team in league.teams.items():
        pool = rows_for(team)
        if len(pool) <= ROSTER_LIMIT:
            # Not a cut-down problem - he is SHORT, which free agency should
            # have solved and could not afford to.
            if len(pool) < ROSTER_LIMIT:
                short.append((abbr, len(pool)))
            continue
        keep, counts = RC.allocate(pool, team.ctx(), team.gm,
                                   limit=ROSTER_LIMIT)
        kept = {p['pid'] for p in keep}
        for p in list(team.active()):
            if p.pid in kept:
                continue
            league.release(p.pid)
            cuts.append((abbr, p))
        team.sync_cap()

    # Cutting accelerates signing bonus, so a club can go over doing it - and
    # it must end with room for the men it still owes, not merely a positive
    # number.
    CT.enforce(league, rng, verbose, roster_target=ROSTER_LIMIT)

    if verbose:
        sizes = np.array([len(t.active()) for t in league.teams.values()])
        sp = np.array([t.cap_space for t in league.teams.values()])
        print(f'  {len(cuts)} cut to the limit | rosters min {sizes.min()} '
              f'mean {sizes.mean():.0f} max {sizes.max()} | '
              f'{len(short)} clubs short of 53 | over the cap {(sp < 0).sum()}')
    return cuts, short


def fill_short(league, rng, verbose=False):
    """
    A club under the limit signs minimum bodies until it is whole.

    This is the other half of cut-down and it has to run AFTER it, because the
    men one club releases are exactly who another club is short of. Free
    agency leaves 500-600 players unsigned; nobody should be fielding 40.
    """
    import min_salary as MS
    from cap_engine import CAP, Contract
    import contract_structure as CS
    cap = CAP.get(league.year, 301.2)
    signed = 0
    pool = [league.player(pid) for pid in list(league.free_agents)]
    pool = [p for p in pool if p and not p.retired]
    pool.sort(key=lambda p: -p.ovr)

    for abbr, team in league.teams.items():
        need = ROSTER_LIMIT - len(team.active())
        while need > 0 and pool:
            floor = None
            pick = None
            for p in pool:
                f = MS.minimum_salary(p.accrued, cap)
                if team.cap_space < f * 1.05:
                    break
                # Take the best man who fills a hole rather than simply the
                # best man. The depth cap has to be the REAL one: a 53-man
                # roster carries eleven defensive linemen and ten defensive
                # backs, so capping every position at five left clubs unable
                # to fill and stuck at twenty players.
                if len(team.by_pos(p.pos)) >= POS_CAP.get(p.pos, 4):
                    continue
                pick, floor = p, f
                break
            if pick is None:
                break
            st = CS.structure(floor, 1, pick.pos, cap, team.gm)
            c = Contract(years=1, base=st['base'],
                         signing_bonus=st['signing_bonus'], signed=league.year)
            league.sign(pick.pid, abbr, c)
            pool.remove(pick)
            team.sync_cap()
            need -= 1
            signed += 1
    if verbose:
        sizes = np.array([len(t.active()) for t in league.teams.values()])
        print(f'  {signed} signed to fill out | rosters min {sizes.min()} '
              f'mean {sizes.mean():.0f}')
    return signed


def finalize(league, rng, verbose=False, passes=3):
    """
    Cut, free up room, fill, repeat.

    One pass is not enough and the reason is circular: a club cannot sign its
    52nd man until it has cut somebody, and it cannot know who to cut until it
    has seen who it can sign. Cutting also accelerates dead money, which can
    take away the room the signing needed. Three passes settles it.
    """
    total_cut, total_signed = [], 0
    for i in range(passes):
        CT.enforce(league, rng, roster_target=ROSTER_LIMIT)
        cuts, short = run(league, rng)
        total_cut += cuts
        total_signed += fill_short(league, rng)
        # Filling out costs money too, and nothing was re-checking after it -
        # two clubs a year finished over the cap on the last signing.
        CT.enforce(league, rng)
        sizes = [len(t.active()) for t in league.teams.values()]
        if min(sizes) >= ROSTER_LIMIT and max(sizes) <= ROSTER_LIMIT:
            break
    if verbose:
        import numpy as _np
        sizes = _np.array([len(t.active()) for t in league.teams.values()])
        sp = _np.array([t.cap_space for t in league.teams.values()])
        print(f'  {len(total_cut)} cut, {total_signed} signed | rosters min '
              f'{sizes.min()} mean {sizes.mean():.0f} max {sizes.max()} | '
              f'{(sizes < ROSTER_LIMIT).sum()} short | over the cap '
              f'{(sp < 0).sum()}')
    return total_cut, total_signed


if __name__ == '__main__':
    import league as LG, season as SN, retirement as RT
    import regression as RG, tags as TG, market as MK
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)
    L.roll_year(rng)
    L.advance_contracts()
    CT.run(L, rng)
    CT.enforce(L, rng)
    TG.run(L, rng)
    CT.enforce(L, rng)
    MK.run(L, rng)
    sizes = np.array([len(t.active()) for t in L.teams.values()])
    print(f'before cut-down: rosters min {sizes.min()} mean {sizes.mean():.0f} '
          f'max {sizes.max()}')
    finalize(L, rng, verbose=True)
    import collections
    t = L.teams['KC']
    GRP = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
           'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL', 'MIKE': 'LB', 'WILL': 'LB',
           'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'K': 'ST',
           'P': 'ST', 'LS': 'ST'}
    print('\nKC final roster:',
          dict(collections.Counter(GRP.get(p.pos, p.pos) for p in t.active())))
