"""One read-only offseason roster plan for drafting, scouting and pick trades.

Reuse the coach's role assignments and GM future-needs model. A roster-depth
shortage is not a vacant starting job, and an IR designation is not a departure.
Scores are on the draft board's existing 0..12 need scale.
"""
from cap_engine import forecast_cap
from collections import defaultdict
from math import ceil
import gm_engine as GM
import roster_needs as RN
from cap_engine import CAP


def projected_players(team, players=None):
    """Retained roster, including IR returnees; never assume a squad promotion.

    Explicit players replace the roster for evaluating a proposed transaction.
    Lightweight tools without contract fields retain their existing behavior.
    """
    source = players if players is not None else getattr(team, 'roster', team.active())
    return [p for p in source if not getattr(p, 'retired', False)
            and (not hasattr(p, 'contract') or
                 (p.contract is not None and p.contract.years > 0))]


class _Roster:
    def __init__(self, team, players):
        self.abbr = getattr(team, 'abbr', None)
        self.gm = getattr(team, 'gm', None)
        self.scheme = getattr(team, 'scheme', None)
        self.roster = players

    def active(self):
        return self.roster

    @property
    def depth(self):
        groups = defaultdict(list)
        for p in self.roster:
            groups[p.pos].append(p)
        return {pos: sorted(men, key=lambda p: -RN._grade(p, self))
                for pos, men in groups.items()}


def _reserve_grade(player, team, belief):
    """Conservative, visible growth credit, shared by depth and succession."""
    grade = RN._grade(player, team)
    from ceiling_knowledge import observed_range
    pr = observed_range(player)
    if getattr(player, 'age', 25) <= 26 and pr:
        grade += min(6.0, max(0.0, sum(pr) / 2 - player.ovr)) * (.5 + .5 * belief)
    from development_value import player_credit
    return grade + 2.0 * player_credit(player)


def _family_reserve_grade(player, team, belief, family):
    if len(family) == 1:
        return _reserve_grade(player, team, belief)
    # Read either eligible side without changing the saved player/transition.
    # A native label must not decide whether the same reserve occupies a job.
    from copy import copy
    grades = []
    for pos in family:
        view = copy(player)
        view.pos = pos
        grades.append(_reserve_grade(view, team, belief))
    return max(grades)


def return_chance(player, gm, pressure=0.0, stats=None):
    """Planning uncertainty, not an extension offer or guaranteed departure."""
    years = getattr(getattr(player, 'contract', None), 'years', 0)
    if years > 1: return 1.0
    if years <= 0: return 0.0
    age = float(getattr(player, 'age', 25))
    prime = 32 if player.pos == 'QB' else 28
    quality = max(-.15, min(.15, (player.ovr - 76.) / 60.))
    chance = (.45 + quality + .20 * (getattr(gm, 'loyalty', .5) - .5)
              - .25 * pressure - .07 * max(0., age - prime))
    if getattr(getattr(player, 'morale', None), 'requested', False): chance -= .25
    # Only established production changes this expectation; no hidden ceiling.
    stats = stats or {}
    attempts = stats.get('pass_att', 0) or 0
    if player.pos == 'QB' and attempts >= 200:
        efficiency = ((stats.get('pass_yds', 0) or 0) + 20 * (stats.get('pass_td', 0) or 0)
                      - 45 * (stats.get('ints', 0) or 0)) / attempts
        chance += max(-.20, min(.10, (efficiency - 6.) * .10))
    return max(.05, min(.75, chance))


def commitment_penalty(plan, prospect, ready_grade):
    """Discount a blocked role, while allowing a clearly better prospect."""
    row = plan['positions'][prospect.pos]
    room = row.get('retention', {})
    strength = room.get('commitment', 0.0)
    if strength <= 0: return 0.0
    improvement = max(0., ready_grade - room.get('incumbent_grade', ready_grade))
    relief = min(1., improvement / 5.)
    gm = getattr(plan.get('_roster'), 'gm', None)
    trust = float(getattr(gm, 'board_trust', .5))
    return 12. * strength * (1. - .35 * trust) * (1. - relief)


def redundancy_penalty(plan, prospect, grade=None, gain=0.0):
    """Soft draft-slot cost for another player with no useful roster opening.

    Applies in every round. Call with the same scouting grade and marginal
    package gain used by the board; never inspect the prospect's true ceiling.
    Strong upgrades can overcome a crowded room, and expiring/weak depth leaves
    space for successors. Existing picks enter the next assessment as retained
    players, so their value does not disappear at the end of round three.
    """
    position = plan['positions'][prospect.pos]
    room = position.get('retention', {})
    excess = max(0.0, room.get('occupied', 0.0) + 1.0 -
                 room.get('capacity', 1.0) - min(1.0, position['future'] / 12.0))
    gm = getattr(plan.get('_roster'), 'gm', None)
    competition_allowance = .5 + .5 * float(getattr(gm, 'dev_belief', .5))
    headcount = room.get('competition', position.get('family_count', position.get('count', 0)))
    competition = max(0., headcount + 1. - room.get('capacity', 1.)
                      - competition_allowance)
    excess = max(excess, competition)
    if excess <= 0:
        return 0.0
    # An identifiable role improvement is a replacement plan. Merely being
    # the best remaining player at this position is not one.
    relief = min(1.0, max(0.0, float(gain)) / 4.0)
    if grade is not None:
        relief = max(relief, min(1.0, max(0.0, float(grade) -
                                         room.get('best_grade', float(grade)) - 2.0) / 6.0))
    return round(min(140.0, 12.0 * excess + 14.0 * excess * excess) * (1.0 - relief), 4)


def assess(league, abbr, level=None, players=None):
    team = league.teams[abbr]
    men = projected_players(team, players)
    proxy = _Roster(team, men)
    report = RN.planning_assess(league, proxy, strict_roles=True)
    men = list(report.get('planned_players', men))
    proxy = _Roster(team, men)
    floors, group_floors = RN.roster_floors(proxy)
    level = level or {}
    by_pos = proxy.depth
    roles = defaultdict(list)
    used = set()
    for row in report['assignments']:
        roles[row['sources'][0]].append(row)
        if row['player'] is not None:
            used.add(row['player'].pid)

    # Project committed money without mutating a cap ledger or settling pay.
    year = int(getattr(league, 'year', 2026))
    limit = forecast_cap(league, year+1)
    committed = float(getattr(getattr(team, 'cap', None), 'dead_next', 0.0))
    for p in men:
        c = getattr(p, 'contract', None)
        if c:
            committed += c.cap_hit(1) if c.years > 1 else c.remaining_proration(1)
    pressure = max(0.0, min(1.0, (committed / max(limit, 1.0) - .80) / .20))
    belief = float(getattr(proxy.gm, 'dev_belief', .5))
    saved_stats = getattr(league, 'stats', {}) or {}
    prior_stats = saved_stats.get(year - 1, saved_stats.get(str(year - 1), {}))
    positions = {}
    for family in RN.PLANNING_FAMILIES:
        pos = family[0]
        bar = max(81.0 if pos == 'QB' else 76.0,
                  sum(float(level.get(p, 0.0)) for p in family) / len(family) - 2.5)
        assignments = [row for p in family for row in roles[p]]
        family_men = [p for native in family for p in by_pos.get(native, ())]
        floor = RN.planning_floor(floors, family)
        # Worst hole at this position within each package, averaged by usage.
        # Taking the maximum over all packages treats an occasional TE3 as
        # just as urgent as the every-down quarterback.
        package_gaps = {}
        for row in report['package_assignments']:
            if row['sources'][0] not in family:
                continue
            key = row['variant']
            gap = 12.0 if row['player'] is None else min(12.0, max(0.0, bar - row['grade']))
            package_gaps[key] = max(package_gaps.get(key, 0.0), gap * row['weight'])
        starter = min(12.0, sum(package_gaps.values()))
        if pos in ('K', 'P', 'LS'):
            starter = max((12.0 if row['player'] is None else min(12.0, max(0.0, bar-row['grade']))
                           for row in assignments), default=0.0)
        count = sum(report['counts'].get(p, 0) for p in family)
        depth = min(12.0, 3.0 * max(0, floor - count))
        for group, minimum in group_floors.items():
            if pos in RN.GROUPS[group]:
                short = max(0, minimum - sum(report['counts'].get(p, 0) for p in RN.GROUPS[group]))
                depth = max(depth, min(5.0, float(short)))
        reserves = [p for p in family_men if p.pid not in used]
        if reserves and floor > len(assignments):
            depth = max(depth, min(3.0, max(0.0, 68.0 - max(p.ovr for p in reserves)) / 4))

        incumbents = [row['player'] for row in assignments if row['player'] is not None]
        control = [(float(p.ovr), int(getattr(getattr(p, 'contract', None), 'years', 4)),
                    float(getattr(p, 'age', 25))) for p in incumbents]
        # A good expiring starter may be retained. Age-related succession
        # remains even if a short extension is plausible.
        succession = 0.0
        for p, line in zip(incumbents, control):
            full = GM.future_need({'expiring': {pos: [line]}}, pos, horizon=2)
            aging = GM.future_need({'expiring': {pos: [(line[0], 4, line[2])]}}, pos, horizon=2)
            chance = return_chance(p, proxy.gm, pressure, prior_stats.get(p.pid))
            succession += max(aging, full * (1. - chance))
        succession = 12. * min(1., succession)
        exposed = sum(yrs <= 1 or age + 2 >= (34 if pos == 'QB' else 31)
                      for _, yrs, age in control)
        # A young reserve is a possible successor, not a promise to reach his
        # ceiling. Use his visible range and at most six points of growth.
        successors = []
        for p in reserves:
            c = getattr(p, 'contract', None)
            if c is not None and c.years < 2:
                continue
            if len(family) > 1 and getattr(p, 'age', 25) + 2 >= 31:
                continue  # another aging edge is not long-term succession cover
            grade = _family_reserve_grade(p, proxy, belief, family)
            successors.append(max(0.0, min(1.0, (grade - (bar - 8)) / 8)))
        cover = sum(sorted(successors, reverse=True)[:max(1, exposed)]) / max(1, exposed)
        succession *= 1.0 - min(1.0, cover)

        # Expensive contracts matter when the future ledger is tight and
        # replacing the incumbent would actually save money. Never treat
        # sunk bonus as cash that a rookie can magically free.
        savings = max((max(0.0, p.contract.release(1, True)[2])
                       for p in incumbents if getattr(p, 'contract', None)
                       and p.contract.years > 1), default=0.0)
        contract = min(6.0, 60.0 * savings / max(limit, 1.0) * pressure)
        # A credible controlled replacement also resolves contract exposure;
        # otherwise an expensive starter keeps requesting another rookie even
        # after the club has already drafted his successor.
        contract *= 1.0 - min(1.0, cover)
        future = max(succession, contract)
        demand = sum(report['package_demand'].get(p, 0.0) for p in family)
        exposure = min(1.0, demand / max(1, len(assignments)))
        if pos not in ('K', 'P', 'LS'):
            future *= exposure
        need = max(starter, .6 * depth, .75 * future)
        # Fractional package use must not unlock an entire extra reserve when
        # it crosses an integer. Interchangeable edges share two reserve jobs.
        capacity = max(floor, len(assignments),
                       demand + len(family) if demand >= .25 else 0)
        if pos in ('FB', 'K', 'P', 'LS'):
            capacity = max(floor, len(assignments), ceil(demand - 1e-6))
        occupied = 0.0
        competition = 0.0
        reserve_grades = []
        for p in family_men:
            grade = _family_reserve_grade(p, proxy, belief, family)
            reserve_grades.append(grade)
            quality = max(0.0, min(1.0, (grade - (bar - 12.0)) / 8.0))
            years = getattr(getattr(p, 'contract', None), 'years', 4)
            retained = (.35 + .4 * return_chance(p, proxy.gm, pressure, prior_stats.get(p.pid))
                        if years <= 1 else 1.0)
            # Developmental players use real roster/practice opportunities,
            # even when none is yet a dependable future starter.
            recent_pick = (getattr(p, 'draft_overall', None) is not None
                           and getattr(getattr(p, 'contract', None), 'signed', None) == year
                           and getattr(p, 'accrued', 0) == 0)
            if recent_pick: quality = max(quality, 1.0)
            elif years >= 2 and getattr(p, 'age', 30) <= 25 and grade >= bar - 12.:
                quality = max(quality, .65)
            occupied += quality * retained
            if quality > 0:
                competition += (1.0 if years > 1 else
                                .75 + .25 * return_chance(p, proxy.gm, pressure, prior_stats.get(p.pid)))
        commitments = []
        for p in incumbents:
            years = getattr(getattr(p, 'contract', None), 'years', 0)
            grade = RN._grade(p, proxy)
            age_room = max(0., min(1., ((35 if pos == 'QB' else 32) - p.age) / 4.))
            commitments.append(min(1., max(0., (years - 1) / 3.)) * age_room
                               * min(1., max(0., (grade - bar + 4.) / 8.)))
        commitment = min(commitments, default=0.) * (1. - min(1., future / 12.))
        retention = dict(capacity=capacity, occupied=round(occupied, 4), competition=competition,
                         commitment=commitment,
                         incumbent_grade=min((RN._grade(p, proxy) for p in incumbents), default=0.),
                         best_grade=max(reserve_grades, default=0.0))
        shared = dict(starter=round(starter, 4), depth=round(depth, 4),
                              succession=round(succession, 4), contract=round(contract, 4),
                              future=round(future, 4), need=round(min(12.0, need), 4),
                              expiring=sum(yrs <= 1 for _, yrs, _ in control),
                              retention=retention)
        for native in family:
            positions[native] = dict(shared, count=report['counts'].get(native, 0),
                                     starters=len(roles[native]))
            if len(family) > 1:
                positions[native].update(family=family, family_count=count,
                                         family_starters=len(assignments))
    return dict(positions=positions, players=men, assignments=report['assignments'],
                roster_score=report['score'], committed_next=committed,
                cap_pressure=pressure, package_demand=report['package_demand'],
                _roster_report=report, _roster=proxy)


def prospect_gains(league, abbr, prospects, plan, grades):
    """Evaluate the scouting room's player, including its attribute uncertainty."""
    seen = []
    for p in prospects:
        view = league.scouting[abbr][p.pid]
        growth = min(6.0, max(0.0, grades[p.pid] - float(view['ovr'])))
        seen.append(observed_prospect(league, abbr, p, growth=growth))
    return RN.candidate_gains(plan['_roster'], seen, baseline=plan['_roster_report'])


def observed_prospect(league, abbr, prospect, growth=0.0):
    """A temporary rookie on this club's read, never the hidden player object."""
    from types import SimpleNamespace
    import scouting as SC
    view = league.scouting[abbr][prospect.pid]
    return SimpleNamespace(pid=prospect.pid, pos=prospect.pos,
                           ratings=SC.scouted_ratings(prospect, view, growth=growth),
                           ovr=float(view['ovr']) + growth, out_until=None,
                           retired=False,
                           weight=getattr(prospect, 'weight', None))
