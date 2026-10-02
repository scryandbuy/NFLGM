"""
CUTS AND RESTRUCTURES.

The offseason step where a club gets under the cap. Nothing in it is new
machinery - cap_engine has handled proration, dead money, June 1 and the
conversion since it was written, and had never once been called.

Simple restructures preserve existing allocations. Users may add up to two
void years; their remaining bonus accelerates when the contract expires.

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


def sensible_release(player, june1=False):
    """
    Would a front office actually make this cut to save money? The release
    has to save at least as much this year as it eats in acceleration, and
    the whole bill (this year and next) cannot dwarf the saving. Without
    this the backstop released a man to save $1m at $26m dead, Seattle went
    from zero to $162m of dead money in one offseason and finished with 25
    men and no quarterback. Returns (ok, saved, dead_now, dead_next).
    """
    saved, dead_now, dead_next = savings_if_cut(player, june1)
    ok = (saved > 0 and saved >= dead_now
          and saved * 2.0 >= dead_now + dead_next)
    return ok, saved, dead_now, dead_next


def restructure_room(player, cap):
    """
    What a simple conversion would free this year, leaving the real minimum.
    Zero on a deal with one year left: there is nowhere to spread it.
    """
    c = player.contract
    if not c or c.years <= 1:
        return 0.0
    floor = max(MS.minimum_salary(player.accrued, cap),c.earned_base)
    import copy
    trial = copy.deepcopy(c)
    trial.restructure(0, min_base=floor)
    return max(0.0, c.cap_hit(0) - trial.cap_hit(0))


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


def roster_reserve(team, cap, roster_target=53):
    """Reprice the vacant roster spots after every departure, using unpaid salary."""
    remaining = max(0, 18 - team.cap.paid_week) / 18.0
    return max(0, roster_target - len(team.active())) * MS.minimum_salary(2, cap) * remaining * 1.05


def enforce(league, rng, verbose=False, target=0.5, roster_target=None):
    """
    roster_target: when given, a club must end with enough room to sign every
    body it still owes, not merely with a non-negative number. Compliance at
    zero is not enough - Baltimore finished an offseason with twenty players,
    $1.2M of space and a $1.29M minimum salary, unable to afford a
    twenty-first man and with nothing forcing it to free up the room.
    """
    """
    THE AI BACKSTOP. The user must fix his own cap before advancing.

    An AI general manager never makes a decision without the cap in it, but
    decisions still compound - a team signs three men it could each afford and
    cannot afford all three. So compliance is enforced afterwards by the same
    three levers a real front office has, in the order a real one uses them:
    rework the deals of men worth keeping, then release replaceable players
    using the calendar's current departure rules.

    It does not give up quietly any more. A club that cannot get under by any
    of those means is REPORTED, because that is a modelling failure and it
    should be visible rather than silently carried into the next season.
    """
    import min_salary as MS
    cap = CAP.get(league.year, 301.2)
    stuck = []
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None):
            continue  # The user's cap decisions are enforced by the calendar gate.
        team.sync_cap()
        need = target
        if roster_target:
            # the bodies he still owes have to be payable
            need = max(target, roster_reserve(team, cap, roster_target))
        if team.cap_space >= need:
            continue
        before = team.cap_space
        _fix_one(league, team, rng, target, roster_target=roster_target)
        team.sync_cap()
        need = max(target, roster_reserve(team, cap, roster_target)) if roster_target else target
        if team.cap_space + .0005 < need:
            stuck.append((abbr, before, team.cap_space, team.cap.dead,
                          len(team.active())))
    if stuck and verbose:
        for a, b, aft, dead, n in stuck:
            print(f'  STUCK OVER THE CAP: {a} {b:.1f} -> {aft:.1f} '
                  f'(dead {dead:.1f}, {n} players - nothing left to move)')
    return stuck


def _declining(player):
    """Is he on the down side of his position's curve? A restructure on a
    declining man pushes money into years he will not earn."""
    import regression as RG
    return RG.curve_factor(player.pos, player.age + 1) < 0.97


def _release_cap_casualty(league, team, player, rng, june1=None):
    """Called only after cleanup has selected its next release, never to rank it.

    Return True for an actual cut; a successful trade is logged by League.trade.
    """
    from trades import shop_cap_casualty
    if shop_cap_casualty(league, team, player, rng, june1=june1):
        return False
    league.release(player.pid, june1=june1)
    return True


def _fix_one(league, team, rng, target, roster_target=None):
    """
    Get one club under. Each round the GM weighs the two real moves:

    RESTRUCTURE a man worth keeping. Frees this year's room by pushing money
    into later years. The GM's restructure_depth is how far he will kick the
    can. Final roster recovery can exceed that preference on existing deals
    when the alternative is an unfunded team; no extra contract years are added.

    RELEASE a man whose contract wants to go. Ordinary cleanup prefers the
    sensible-release rule; final recovery also considers positive net-saving
    cuts with large sunk bonuses. The penalty for cutting a
    good player shrinks as the shortfall grows: a club $60m over will move a
    star it would never touch at $5m over, and sometimes one big cut of a
    great player is the better answer than a sixth restructure.

    The old version reworked one deal per pass for three passes and then
    started cutting, which is how Seattle went from $73m over to 25 men.
    """
    if team.abbr == getattr(league, 'user_team', None):
        return
    import min_salary as MS
    import roster_needs as RN
    import practice_squad as PS
    cap = CAP.get(league.year, 301.2)
    depth = getattr(team.gm, 'restructure_depth', 0.5) if team.gm else 0.5
    restructures_left = int(round(2 + 8 * depth))       # 2 to 10 deals an offseason
    # A club short of bodies that cannot pay a minimum salary keeps
    # restructuring past its own appetite: the alternative is not fielding
    # a team, and no front office chooses that over kicking the can.
    for _round in range(40):
        team.sync_cap()
        short_of_bodies = len(team.active()) < (roster_target or 53)
        reserve = roster_reserve(team, cap, roster_target) if roster_target else 0.0
        need = max(target, reserve) - team.cap_space
        if need <= .0005:
            return
        # Cutting a minimum player does not fund a replacement. Final roster
        # recovery must improve the funded roster, not only today's balance.
        replacement_cost = (MS.minimum_salary(2, cap) * max(0, 18-team.cap.paid_week)/18 * 1.05
                            if roster_target and len(team.active()) <= roster_target else 0.0)
        baseline = RN.assess(team) if roster_target else None
        market = PS.available_free_agents(league) if roster_target else []
        costs = {}

        def release_cost(p):
            if not roster_target:
                rep = replacement_level(team, p.pos)
                return max(0.0, p.ovr-rep) * 3.0 if rep > 0 else None
            if p.pid in costs: return costs[p.pid]
            if PS.locked(p, league.week): return None
            after = RN.assess(team, [q for q in team.active() if q is not p])
            from collections import Counter
            new_holes = Counter(after['uncovered']) - Counter(baseline['uncovered'])
            # Never sacrifice the only available specialist/role to fund bodies.
            for role, sources in RN.role_slots(team):
                if new_holes[role] and not any(q.pos in sources for q in market):
                    costs[p.pid] = None
                    return None
            cost = max(0.0, baseline['score']-after['score']) + RN.retention_value(team, p)
            costs[p.pid] = cost
            return cost
        # --- the restructure on the table
        rs = None
        if restructures_left > 0 or short_of_bodies or roster_target:
            for p in team.active():
                if not p.contract or (_declining(p) and not roster_target):
                    continue
                rep = replacement_level(team, p.pos)
                if p.ovr - rep <= CUTTABLE_SURPLUS and need < 30 and not roster_target:
                    continue                 # replaceable: a cut, not a rework
                freed = restructure_room(p, cap)
                if freed > 0.4 and (rs is None or freed > rs[0]):
                    rs = (freed, p)
        # --- the release on the table
        rel = None
        squeeze = float(np.clip(1.0 - need / 60.0, 0.3, 1.0))   # far over: stars come into play
        for p in team.active():
            if not p.contract:
                continue
            ok, saved, dead, _n = sensible_release(p, june1=league.post_june1())
            # At the final gate, sunk bonus alone cannot veto an otherwise
            # useful cut. Its actual charge and lost role still reduce value.
            if (not ok and not roster_target) or saved <= replacement_cost + .0005:
                continue
            cost = release_cost(p)
            if cost is None: continue
            value = saved - replacement_cost - cost * squeeze - dead * 0.35
            if rel is None or value > rel[0]:
                rel = (value, p, saved)
        # --- choose. A restructure that covers the need wins; otherwise the
        # move that closes more of the gap per point of quality given up.
        if rs is not None and (rel is None or rs[0] >= need or rs[0] >= rel[0]):
            freed, p = rs
            floor = max(MS.minimum_salary(p.accrued, cap), p.contract.earned_base)
            amount = max(0.0, p.contract.base[0]-floor) * min(1.0, (need+.001)/freed)
            before_hit = p.cap_hit(0)
            p.contract.restructure(0, amount=amount, min_base=floor)
            freed = before_hit - p.cap_hit(0)
            restructures_left -= 1
            league.log('restructure', pid=p.pid, team=team.abbr, freed=round(freed, 2),
                       enforcement=True)
            continue
        if rel is not None and rel[0] > -1e8:
            _release_cap_casualty(league, team, rel[1], rng)
            continue
        # --- June 1 on what is left
        june1 = league.post_june1()
        j = [p for p in team.active() if p.contract and sensible_release(p, june1=june1)[0]
             and savings_if_cut(p, june1)[0] > replacement_cost + .0005
             and (not roster_target or release_cost(p) is not None)]
        # A legacy already-collapsed roster may have only bonus-heavy veterans
        # left. A positive net-saving release is still preferable to an illegal
        # minimum roster; use it only after usable conversions are exhausted.
        if not j and roster_target:
            j = [p for p in team.active() if p.contract
                 and savings_if_cut(p, june1)[0] > replacement_cost + .0005
                 and release_cost(p) is not None]
        if j:
            j.sort(key=lambda p: -(savings_if_cut(p, june1)[0]
                                  - (release_cost(p) * squeeze if roster_target else 0)))
            _release_cap_casualty(league, team, j[0], rng, june1=june1)
            continue
        return


def run(league, rng, verbose=False):
    """
    Get AI clubs under the cap. Restructure keepers, select replaceable cuts,
    then try June 1 releases if still stuck. Shop each decided cut last.
    """
    cap = CAP.get(league.year, 301.2)
    import financial_plan as FP
    cuts, restructures = [], []

    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None):
            continue
        team.sync_cap()
        need = FP.roster_funding_target(league, team) - team.cap_space
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
            # Fund identified roster/draft obligations only, not a generic
            # cushion that the market immediately treats as spending money.
            amount = max(0.,p.contract.base[0]-floor) * min(1.,(need+.001)/freed)
            import copy
            preview = copy.deepcopy(p.contract)
            preview.restructure(0, amount=amount, min_base=floor)
            if not FP.evaluate(league, team, additions=[(p, preview)],
                               essential=True, action='fund_roster_restructure')['approved']:
                continue
            conv, _spread = p.contract.restructure(0, amount=amount, min_base=floor)
            if conv <= 0:
                continue
            team.sync_cap()
            got = before_hit - p.cap_hit(0)
            restructures.append((abbr, p, got, conv))
            league.log('restructure', pid=p.pid, team=abbr,
                       converted=round(conv, 2), freed=round(got, 2),
                       dead_now=round(p.dead_if_cut(0), 2))
            need = FP.roster_funding_target(league, team) - team.cap_space

        # ---- 2. cut the bad contracts -----------------------------------
        cands = []
        for p in team.active():
            if not p.contract:
                continue
            ok, saved, dead, _n = sensible_release(p, june1=league.post_june1())
            if not ok:
                continue                 # costs more to release than it saves
            # a man the club cannot replace does not get cut to save money
            rep = replacement_level(team, p.pos)
            if rep <= 0:
                continue
            cands.append((cut_score(p, team, rep), p, saved))
        cands.sort(key=lambda x: -x[0])

        for score, p, saved in cands:
            if need <= 0:
                break
            if score <= 0:
                break                    # everyone left is worth his money
            if _release_cap_casualty(league, team, p, rng):
                cuts.append((abbr, p, saved))
            team.sync_cap()
            need = FP.roster_funding_target(league, team) - team.cap_space

        # ---- 3. still stuck: take the June 1 route -----------------------
        if need > 0:
            for p in sorted(team.active(), key=lambda x: -x.cap_hit(0)):
                if need <= 0:
                    break
                if not p.contract:
                    continue
                ok, saved, dead, dead_next = sensible_release(p, june1=True)
                if not ok:
                    continue
                rep = replacement_level(team, p.pos)
                if rep <= 0 or p.ovr - rep > 6:
                    continue
                if _release_cap_casualty(league, team, p, rng, june1=True):
                    cuts.append((abbr, p, saved))
                    league.log('june1_cut', pid=p.pid, team=abbr,
                               saved=round(saved, 2), dead_next=round(dead_next, 2))
                team.sync_cap()
                need = FP.roster_funding_target(league, team) - team.cap_space

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


# ============================================================ THE USER'S RESTRUCTURE
def restructure_preview(league, pid, amount=None, void_years=0):
    """
    What converting base salary into signing bonus does to the books, before
    it is done: this year's saving, the added hit in every later year, and
    the dead money if he is cut or the deal voids afterwards. Up to two void
    years may be added to spread it further. No consent step: the player
    gets his money sooner and always says yes.
    """
    import copy, min_salary as MS
    from cap_engine import CAP, MAX_PRORATION_YEARS
    p = league.player(pid)
    c = p.contract
    if c is None:
        return dict(ok=False, why='no contract')
    from cap_accounting import pre_roll
    index = 1 if pre_roll(league) else 0
    if c.years <= index: return dict(ok=False, why='No remaining salary to restructure')
    cap = CAP.get(league.year+index, CAP.get(league.year,301.2)*1.055**index)
    floor = max(MS.minimum_salary(p.accrued or 0, cap), c.earned_base if index==0 else 0.0)
    max_conv = max(0.0, c.base[index] - floor)
    conv = max_conv if amount is None else float(min(max(0.0, amount), max_conv))
    if conv <= 0:
        return dict(ok=False, why='nothing above the minimum to convert')
    void_years = int(max(0, min(2, void_years)))
    before = [round(c.cap_hit(i), 2) for i in range(c.years)]
    trial = copy.deepcopy(c)
    trial.void = max(trial.void, void_years)
    trial.restructure(index, amount=conv, min_base=floor)
    after = [round(trial.cap_hit(i), 2) for i in range(trial.years)]
    return dict(ok=True, convert=conv, max_convert=round(max_conv, 3), void_years=trial.void,
                year_index=index, cap_year=league.year+index, min_base=floor,
                saves_now=round(before[index] - after[index], 2),
                added_later=[round(after[i] - before[i], 2) for i in range(index+1, c.years)],
                proration_years=trial.proration_years,
                dead_if_cut_next_year=round(trial.remaining_proration(index+1), 2),
                dead_at_void=round(trial.remaining_proration(trial.years), 2),
                hits_before=before, hits_after=after)


def restructure_user(league, pid, amount=None, void_years=0):
    """Do it, as previewed."""
    import min_salary as MS
    from cap_engine import CAP
    pv = restructure_preview(league, pid, amount, void_years)
    if not pv['ok']:
        return pv
    p = league.player(pid); c = p.contract
    c.void = max(c.void, pv['void_years'])
    c.restructure(pv['year_index'], amount=pv['convert'], min_base=pv['min_base'])
    league.teams[p.team].sync_cap()
    league.log('restructure', pid=pid, team=p.team, converted=pv['convert'], void_years=c.void, user=True)
    return dict(pv, done=True)
