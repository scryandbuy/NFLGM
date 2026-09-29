"""One read-only offseason roster plan for drafting, scouting and pick trades.

Reuse the coach's role assignments and GM future-needs model. A roster-depth
shortage is not a vacant starting job, and an IR designation is not a departure.
Scores are on the draft board's existing 0..12 need scale.
"""
from collections import defaultdict
import gm_engine as GM
import roster_needs as RN
from offense_roles import fullback_score
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
    limit = float(CAP.get(year + 1, CAP.get(year, 301.2) * 1.055))
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
        starter = max((12.0 if row['player'] is None else
                       min(12.0, max(0.0, bar - (fullback_score(row['player'])
                                                if row['role'] == 'FB' else row['grade'])))
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
        if pos == 'QB' and any(getattr(p, 'age', 25) >= 34 for p in incumbents):
            succession = max(succession, 8.0)
        exposed = sum(yrs <= 1 or age + 2 >= (34 if pos == 'QB' else 31)
                      for _, yrs, age in control)
        # A young reserve is a possible successor, not a promise to reach his
        # ceiling. Use his visible range and at most six points of growth.
        successors = []
        for p in reserves:
            c = getattr(p, 'contract', None)
            if c is not None and c.years < 2:
                continue
            grade = RN._grade(p, proxy)
            pr = getattr(p, 'potential_range', None)
            if getattr(p, 'age', 25) <= 26 and pr:
                grade += min(6.0, max(0.0, sum(pr) / 2 - p.ovr)) * (.5 + .5 * belief)
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
        future = max(succession, contract)
        need = max(starter, .6 * depth, .75 * future)
        positions[pos] = dict(starter=round(starter, 4), depth=round(depth, 4),
                              succession=round(succession, 4), contract=round(contract, 4),
                              future=round(future, 4), need=round(min(12.0, need), 4),
                              count=count, starters=len(assignments),
                              expiring=sum(yrs <= 1 for _, yrs, _ in control))
    return dict(positions=positions, players=men, assignments=report['assignments'],
                roster_score=report['score'], committed_next=committed,
                cap_pressure=pressure)
