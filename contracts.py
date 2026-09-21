"""
CUTS AND RESTRUCTURES.

The offseason step where a club gets under the cap. Nothing in it is new
machinery - cap_engine has handled proration, dead money, June 1 and the
conversion since it was written, and had never once been called.

SIMPLE RESTRUCTURES ONLY, by decision. A simple restructure converts base
salary into signing bonus and spreads it over the years ALREADY on the deal.
A team can do it unilaterally; the player's consent is not required, and he
generally wants it anyway - money that might never have been guaranteed gets
paid immediately. The maximum restructure, which bolts void years onto the
end, is deliberately not in the game.

That choice removes a real hazard. Void years are placeholders that exist only
to widen proration, and when the deal voids every remaining prorated dollar
slams onto that year's cap. Contract still carries a `void` field and nothing
in the game ever sets it above zero, so no club can quietly borrow against a
year that never arrives.

AVAILABLE TO EVERY GENERAL MANAGER. Restructuring is a mechanic the rules
allow any club to use, not a personality trait, so nothing here reads a GM
rating to decide whether it is permitted. What separates front offices is how
often need drives them to it - and what they are holding afterwards.

THE ONLY LIMIT IS THE MINIMUM. A club must leave at least the player's minimum
base salary for the year, and that minimum scales with his accrued seasons:
0.971 for a rookie against 1.561 for a ten-year veteran at a 301.2 cap. The
engine used to leave a flat 1.2 regardless, which overcharged young players
and undercharged old ones.

ORDER OF OPERATIONS matters and is not arbitrary. Rework the deals of men the
club wants to keep, THEN release the ones it can replace. Real teams
restructure far more often than they cut, because the conversion costs nothing
this year and keeps the player. Running cuts first released an 88-overall
receiver to save twenty million, which is not a thing a front office does -
it reworks him and lets go of somebody the roster can absorb losing.
"""
import numpy as np

import gm_engine as GM
import min_salary as MS
from cap_engine import CAP

# A club must be under the cap before the league year opens. Real teams do not
# sit at exactly zero, they leave room to sign a draft class and fill a roster.
TARGET_ROOM = 12.0

# Below this, cutting a man costs almost as much as keeping him - the trap a
# club builds for itself with repeated restructures.
TRAP_RATIO = 0.80


def savings_if_cut(player, june1=False):
    """(cap saved this year, dead money now, dead money next year)."""
    if not player.contract:
        return 0.0, 0.0, 0.0
    dead_now, dead_next, saved = player.contract.release(0, june1)
    return saved, dead_now, dead_next


def restructure_room(player, cap):
    """
    What a simple conversion would free this year, leaving the real minimum.
    Zero on a deal with one year left: there is nowhere to spread it.
    """
    c = player.contract
    if not c or c.years <= 1:
        return 0.0
    floor = MS.minimum_salary(player.accrued, cap)
    room, _conv = GM.simple_restructure_room(c.base[0], c.years, floor)
    return room


# A club does not release a star to make room; it reworks his deal. The gate
# is how far he sits above the next man at his spot - not his rating, which
# says nothing about whether the team can replace him.
CUTTABLE_SURPLUS = 4.0


def cut_score(player, team, replacement):
    """
    How badly this man's contract wants to go.

    Not a rating question - a rating-per-dollar question. An expensive
    thirty-two-year-old just below his replacement is a cut; the same player on
    a minimum deal is not.

    The surplus term has to be steep. At a gentle weight this cut an
    88-overall receiver to save twenty million, which no front office does -
    they restructure him instead and cut somebody they can actually replace.
    """
    saved, dead, _n = savings_if_cut(player)
    if saved <= 0:
        return -1e9
    surplus = player.ovr - replacement
    if surplus > CUTTABLE_SURPLUS:
        return -1e9                      # he is the answer, not the problem
    return saved - max(0.0, surplus) * 3.0 - dead * 0.35


def replacement_level(team, pos):
    """The next man at this spot. Cutting is always relative to him."""
    grp = team.by_pos(pos)
    if len(grp) < 2:
        return 0.0                       # no cover: he is not going anywhere
    return grp[1].ovr


def enforce(league, rng, verbose=False, target=0.5, roster_target=None):
    """
    roster_target: when given, a club must end with enough room to sign every
    body it still owes, not merely with a non-negative number. Compliance at
    zero is not enough - Baltimore finished an offseason with twenty players,
    $1.2M of space and a $1.29M minimum salary, unable to afford a
    twenty-first man and with nothing forcing it to free up the room.
    """
    """
    THE BACKSTOP. No club ends a phase over the cap.

    An AI general manager never makes a decision without the cap in it, but
    decisions still compound - a team signs three men it could each afford and
    cannot afford all three. So compliance is enforced afterwards by the same
    three levers a real front office has, in the order a real one uses them:
    rework the deals of men worth keeping, release the ones you can replace,
    and take the June 1 route on what is left.

    It does not give up quietly any more. A club that cannot get under by any
    of those means is REPORTED, because that is a modelling failure and it
    should be visible rather than silently carried into the next season.
    """
    import min_salary as MS
    cap = CAP.get(league.year, 301.2)
    floor = MS.minimum_salary(2, cap)
    stuck = []
    for abbr, team in league.teams.items():
        team.sync_cap()
        need = target
        if roster_target:
            # the bodies he still owes have to be payable
            need = max(target,
                       (roster_target - len(team.active())) * floor * 1.05)
        if team.cap_space >= need:
            continue
        before = team.cap_space
        _fix_one(league, team, rng, need)
        team.sync_cap()
        if team.cap_space < min(0.0, need):
            stuck.append((abbr, before, team.cap_space, team.cap.dead,
                          len(team.active())))
    if stuck and verbose:
        for a, b, aft, dead, n in stuck:
            print(f'  STUCK OVER THE CAP: {a} {b:.1f} -> {aft:.1f} '
                  f'(dead {dead:.1f}, {n} players - nothing left to move)')
    return stuck


def _fix_one(league, team, rng, target):
    cap = CAP.get(league.year, 301.2)
    for _pass in range(3):
        if team.cap_space >= target:
            return
        # 1. rework whoever frees the most, keeping the player
        best = None
        for p in team.active():
            if not p.contract:
                continue
            freed = restructure_room(p, cap)
            if freed > 0.4 and (best is None or freed > best[0]):
                best = (freed, p)
        if best is not None:
            p = best[1]
            floor = MS.minimum_salary(p.accrued, cap)
            p.contract.restructure(0, min_base=floor)
            team.sync_cap()
            continue
        # 2. release the most expensive man the roster can absorb losing
        cands = []
        for p in team.active():
            if not p.contract:
                continue
            saved, dead, _n = savings_if_cut(p)
            if saved <= 0:
                continue
            rep = replacement_level(team, p.pos)
            cands.append((saved - max(0.0, p.ovr - rep) * 1.5, p))
        if cands:
            cands.sort(key=lambda x: -x[0])
            league.release(cands[0][1].pid)
            team.sync_cap()
            continue
        # 3. June 1, which splits the dead money across two years
        j = [p for p in team.active() if p.contract
             and savings_if_cut(p, june1=True)[0] > 0]
        if j:
            j.sort(key=lambda p: -savings_if_cut(p, june1=True)[0])
            league.release(j[0].pid, june1=True)
            team.sync_cap()
            continue
        return


def run(league, rng, verbose=False):
    """
    Get every club under the cap. Cuts first, then restructures, then June 1
    designations if a team is still stuck.
    """
    cap = CAP.get(league.year, 301.2)
    cuts, restructures = [], []

    for abbr, team in league.teams.items():
        team.sync_cap()
        need = TARGET_ROOM - team.cap_space
        if need <= 0:
            continue

        # ---- 1. rework the deals of men worth keeping -------------------
        # Real clubs restructure far more often than they release. The
        # conversion costs nothing this year and keeps the player, so it comes
        # first for anyone clearly above his replacement; the axe is for the
        # men the roster can actually absorb losing.
        room = []
        for p in team.active():
            if not p.contract:
                continue
            rep = replacement_level(team, p.pos)
            if p.ovr - rep <= CUTTABLE_SURPLUS:
                continue                 # replaceable: he belongs to the cuts
            freed = restructure_room(p, cap)
            if freed > 0.5:
                room.append((freed, p))
        room.sort(key=lambda x: -x[0])
        for freed, p in room:
            if need <= 0:
                break
            floor = MS.minimum_salary(p.accrued, cap)
            before_hit = p.cap_hit(0)
            conv, _spread = p.contract.restructure(0, min_base=floor)
            if conv <= 0:
                continue
            team.sync_cap()
            got = before_hit - p.cap_hit(0)
            restructures.append((abbr, p, got, conv))
            league.log('restructure', pid=p.pid, team=abbr,
                       converted=round(conv, 2), freed=round(got, 2),
                       dead_now=round(p.dead_if_cut(0), 2))
            need = TARGET_ROOM - team.cap_space

        # ---- 2. cut the bad contracts -----------------------------------
        cands = []
        for p in team.active():
            if not p.contract:
                continue
            saved, dead, _n = savings_if_cut(p)
            if saved <= 0:
                continue
            # a man the club cannot replace does not get cut to save money
            rep = replacement_level(team, p.pos)
            if rep <= 0:
                continue
            if GM.is_uncuttable(p.cap_hit(0), dead):
                continue                 # costs more to release than to keep
            cands.append((cut_score(p, team, rep), p, saved))
        cands.sort(key=lambda x: -x[0])

        for score, p, saved in cands:
            if need <= 0:
                break
            if score <= 0:
                break                    # everyone left is worth his money
            league.release(p.pid)
            cuts.append((abbr, p, saved))
            team.sync_cap()
            need = TARGET_ROOM - team.cap_space

        # ---- 3. still stuck: take the June 1 route -----------------------
        if need > 0:
            for p in sorted(team.active(), key=lambda x: -x.cap_hit(0)):
                if need <= 0:
                    break
                if not p.contract:
                    continue
                saved, dead, dead_next = savings_if_cut(p, june1=True)
                if saved <= 0:
                    continue
                rep = replacement_level(team, p.pos)
                if rep <= 0 or p.ovr - rep > 6:
                    continue
                league.release(p.pid, june1=True)
                cuts.append((abbr, p, saved))
                league.log('june1_cut', pid=p.pid, team=abbr,
                           saved=round(saved, 2), dead_next=round(dead_next, 2))
                team.sync_cap()
                need = TARGET_ROOM - team.cap_space

    if verbose:
        over = sum(1 for t in league.teams.values() if t.cap_space < 0)
        print(f'  {len(cuts)} cut, {len(restructures)} restructured, '
              f'{over} of 32 still over the cap')
    return cuts, restructures


if __name__ == '__main__':
    import collections
    import league as LG, season as SN, retirement as RT, regression as RG
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)

    before = {a: t.cap_space for a, t in L.teams.items()}
    cuts, res = run(L, rng, verbose=True)

    print('\n%-4s %9s %9s  %s' % ('team', 'before', 'after', 'moves'))
    for a in sorted(L.teams)[:10]:
        nc = sum(1 for x in cuts if x[0] == a)
        nr = sum(1 for x in res if x[0] == a)
        print('%-4s %9.1f %9.1f  %d cut, %d restructured'
              % (a, before[a], L.teams[a].cap_space, nc, nr))

    print('\nbiggest cuts:')
    for a, p, s in sorted(cuts, key=lambda x: -x[2])[:6]:
        print('  %-4s %-22s %-5s age %2.0f ovr %.0f  saves %.1f, dead %.1f'
              % (a, p.name, p.pos, p.age, p.ovr, s, 0.0))
    print('\nbiggest restructures:')
    for a, p, got, conv in sorted(res, key=lambda x: -x[2])[:6]:
        print('  %-4s %-22s %-5s freed %.1f (converted %.1f), dead if cut now %.1f'
              % (a, p.name, p.pos, got, conv, p.dead_if_cut(0)))
