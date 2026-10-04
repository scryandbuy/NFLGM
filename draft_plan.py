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
    report = RN.assess(proxy, strict_roles=True)
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
    positions = {}
    for pos in RN.POSITIONS:
        bar = max(81.0 if pos == 'QB' else 76.0, float(level.get(pos, 0.0)) - 2.5)
        assignments = roles[pos]
        # Worst hole at this position within each package, averaged by usage.
        # Taking the maximum over all packages treats an occasional TE3 as
        # just as urgent as the every-down quarterback.
        package_gaps = {}
        for row in report['package_assignments']:
            if row['sources'][0] != pos:
                continue
            key = row['variant']
            gap = 12.0 if row['player'] is None else min(12.0, max(0.0, bar - row['grade']))
            package_gaps[key] = max(package_gaps.get(key, 0.0), gap * row['weight'])
        starter = min(12.0, sum(package_gaps.values()))
        if pos in ('K', 'P', 'LS'):
            starter = max((12.0 if row['player'] is None else min(12.0, max(0.0, bar-row['grade']))
                           for row in assignments), default=0.0)
        count = report['counts'].get(pos, 0)
        depth = min(12.0, 3.0 * max(0, floors[pos] - count))
        for group, minimum in group_floors.items():
            if pos in RN.GROUPS[group]:
                short = max(0, minimum - sum(report['counts'].get(p, 0) for p in RN.GROUPS[group]))
                depth = max(depth, min(5.0, float(short)))
        reserves = [p for p in by_pos.get(pos, ()) if p.pid not in used]
        if reserves and floors[pos] > len(assignments):
            depth = max(depth, min(3.0, max(0.0, 68.0 - max(p.ovr for p in reserves)) / 4))

        incumbents = [row['player'] for row in assignments if row['player'] is not None]
        control = [(float(p.ovr), int(getattr(getattr(p, 'contract', None), 'years', 4)),
                    float(getattr(p, 'age', 25))) for p in incumbents]
        succession = 12.0 * GM.future_need({'expiring': {pos: control}}, pos, horizon=2)
        exposed = sum(yrs <= 1 or age + 2 >= (34 if pos == 'QB' else 31)
                      for _, yrs, age in control)
        # A young reserve is a possible successor, not a promise to reach his
        # ceiling. Use his visible range and at most six points of growth.
        successors = []
        for p in reserves:
            c = getattr(p, 'contract', None)
            if c is not None and c.years < 2:
                continue
            grade = _reserve_grade(p, proxy, belief)
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
        exposure = min(1.0, report['package_demand'].get(pos, 0.0) / max(1, len(assignments)))
        if pos not in ('K', 'P', 'LS'):
            future *= exposure
        need = max(starter, .6 * depth, .75 * future)
        demand = report['package_demand'].get(pos, 0.0)
        capacity = max(floors[pos], len(assignments),
                       ceil(demand - 1e-6) + 1 if demand >= .25 else 0)
        if pos in ('FB', 'K', 'P', 'LS'):
            capacity = max(floors[pos], len(assignments), ceil(demand - 1e-6))
        occupied = 0.0
        reserve_grades = []
        for p in by_pos.get(pos, ()):
            grade = _reserve_grade(p, proxy, belief)
            reserve_grades.append(grade)
            quality = max(0.0, min(1.0, (grade - (bar - 12.0)) / 8.0))
            years = getattr(getattr(p, 'contract', None), 'years', 4)
            retained = .35 if years <= 1 else 1.0
            occupied += quality * retained
        retention = dict(capacity=capacity, occupied=round(occupied, 4),
                         best_grade=max(reserve_grades, default=0.0))
        positions[pos] = dict(starter=round(starter, 4), depth=round(depth, 4),
                              succession=round(succession, 4), contract=round(contract, 4),
                              future=round(future, 4), need=round(min(12.0, need), 4),
                              count=count, starters=len(assignments),
                              expiring=sum(yrs <= 1 for _, yrs, _ in control),
                              retention=retention)
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
