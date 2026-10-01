"""Last pre-kickoff availability gate, separate from long-term roster planning."""
import copy
from collections import Counter

import defense_roles as DR
import offense_roles as OR
import practice_squad as PS


class FieldabilityError(ValueError):
    """The calendar must stay on this game until its roster problem is solved."""


def dressed(team, desk, week):
    players = {p.pid: p for p in team.active()}
    players.update((p.pid, p) for p in (getattr(team, '_elevated', None) or [])
                   if p in PS.squad(team) and not p.retired)
    return [p for p in players.values()
            if (desk.available(p, week) if desk is not None else p.out_until is None)]


# Compatible substitutions remain the engine's job. These are the minimum
# bodies needed for eleven distinct offensive/defensive players and specialists,
# not a second depth-chart allocation policy or a demand for ideal starter OVR.
REQUIREMENTS = (
    ('QB', ('QB',), 1), ('offensive line', tuple(OR.OL), 5),
    ('backs/receivers', ('HB', 'FB', 'WR', 'TE'), 5),
    ('defensive back', ('CB', 'FS', 'SS'), 1),
    ('defense', tuple(sorted(DR.DEFENSE)), 11),
    ('K', ('K',), 1), ('P', ('P',), 1),
    # game.snapper_for already uses a center when no long snapper is dressed.
    # Older saves can run out of LS before the new draft pipeline reaches camp.
    ('LS', ('LS', 'C'), 1),
)


def shortages(players):
    counts = Counter(p.pos for p in players)
    return [(label, positions, count - sum(counts[pos] for pos in positions))
            for label, positions, count in REQUIREMENTS
            if sum(counts[pos] for pos in positions) < count]


def _outgoing(league, team, available, incoming):
    """Use surplus depth, never the injured starter or another mandatory job."""
    import roster_needs as RN
    if len(team.active()) < 53:
        return [None]
    baseline = RN.assess(team)
    missing = Counter(baseline['uncovered'])
    starters = {row['player'].pid for row in baseline['assignments'] if row['player'] is not None}
    present = {p.pid for p in available}
    recent = {row.get('pid') for row in league.transactions
              if row.get('year') == league.year and row.get('team') == team.abbr
              and row.get('kind') in ('sign', 'ps_callup', 'ps_poach')
              and 0 <= int(league.week or 0) - int(row.get('week') or 0) <= 3}
    options = []
    before = {label: n for label, _, n in shortages(available + [incoming])}
    for q in team.active():
        if (q.pid not in present or q.pid in recent or q.pid in starters or q.pos == 'QB'
                or PS.locked(q, league.week) or PS.protected(team, q, league)):
            continue
        remaining = [p for p in available if p is not q] + [incoming]
        if any(n > before.get(label, 0) for label, _, n in shortages(remaining)):
            continue
        after = RN.assess(team, [p for p in team.active() if p is not q] + [incoming])
        if Counter(after['uncovered']) - missing:
            continue
        # Keep full-roster package value and developing depth in the decision.
        options.append((RN.departure_loss(team, q, baseline) + RN.retention_value(team, q), q))
    return [q for _, q in sorted(options, key=lambda item: (item[0], item[1].pid))]


def _funding(league, team, incoming, outgoing, contract):
    """Preview the complete move and only enough existing-deal conversion to pay it."""
    import contracts as CT
    import min_salary as MS
    from cap_engine import CAP
    from offer_reservations import held
    team.sync_cap()
    trial = copy.copy(team.cap)
    trial.contracts = [(pid, c, i) for pid, c, i in team.cap.contracts
                       if pid != incoming.pid and (outgoing is None or pid != outgoing.pid)]
    trial.contracts.append((incoming.pid, contract, 0))
    if outgoing and outgoing.contract:
        trial.dead += outgoing.contract.release(0, league.post_june1())[0]
        trial.earned += outgoing.contract.earned_base + outgoing.contract.earned_roster
    gap = trial.charges(team.phase) + held(league, team.abbr, exclude_pid=incoming.pid) - trial.limit
    if gap <= .0005:
        return []
    cap = CAP.get(league.year, 301.2)
    keepers = [p for p in team.active() if p is not outgoing and p.contract
               and CT.restructure_room(p, cap) > .0005]
    # Prefer younger keepers; an older existing deal is a final funding option
    # when the alternative is no playable team. Never add years to the deal.
    keepers.sort(key=lambda p: (CT._declining(p), -CT.restructure_room(p, cap), p.pid))
    plan = []
    for p in keepers:
        floor = max(MS.minimum_salary(p.accrued or 0, cap), p.contract.earned_base)
        room = CT.restructure_room(p, cap)
        amount = max(0., p.contract.base[0] - floor) * min(1., (gap + .001) / room)
        replacement = copy.deepcopy(p.contract)
        replacement.restructure(0, amount=amount, min_base=floor)
        freed = p.cap_hit(0) - replacement.cap_hit(0)
        plan.append((p, replacement, freed))
        gap -= freed
        if gap <= .0005:
            return plan
    return None


def _acquire(league, team, available, positions, desk, week):
    from cap_accounting import require_room
    import cutdown
    if len(team.active()) > 53:
        return False  # An invalid roster needs cutdown, not another acquisition.
    # Own squad/street first; another squad is a last resort for an unavailable
    # or unaffordable mandatory role. No invented players and no waiver bypass.
    local = [p for p in PS.squad(team) + PS.available_free_agents(league)
             if p.pos in positions and not p.retired and p.out_until is None
             and (desk is None or desk.available(p, week))]
    other = [p for t in league.teams.values() if t is not team for p in PS.squad(t)
             if p.pos in positions and not p.retired and p.out_until is None
             and (desk is None or desk.available(p, week))]
    for pool in (local, other):
        # Affordability is checked for every candidate, not just the highest OVR.
        for p in sorted(pool, key=lambda p: (-p.ovr, p.pid)):
            contract = PS.minimum_contract(league, team, p)
            for q in _outgoing(league, team, available, p):
                funding = _funding(league, team, p, q, contract)
                if funding is None:
                    continue
                for keeper, revised, freed in funding:
                    keeper.contract = revised
                    league.log('restructure', pid=keeper.pid, team=team.abbr,
                               freed=round(freed, 3), enforcement=True, emergency=True)
                team.sync_cap()
                require_room(league, team, p.pid, contract, release_pid=q.pid if q else None)
                if q:
                    league.release(q.pid)
                if not cutdown._sign_replacement(league, team, p, contract):
                    raise FieldabilityError(f'{team.abbr}: emergency signing of {p.name} could not complete')
                league.log('emergency', pid=p.pid, team=team.abbr, position=p.pos,
                           reason='Game-day availability')
                return True
    return False


def ensure(league, team, desk, week, playoffs=False):
    """CPU repairs are idempotent: only an actual hole can trigger a move."""
    available = dressed(team, desk, week)
    missing = shortages(available)
    if team.abbr != getattr(league, 'user_team', None):
        while missing:
            _, positions, _ = missing[0]
            candidates = sorted([p for p in PS.squad(team) if p.pos in positions
                                 and not p.retired and p.out_until is None
                                 and (desk is None or desk.available(p, week))],
                                key=lambda p: (-p.ovr, p.pid))
            elevated = False
            for p in candidates:
                # Fourth use needs a vetted permanent roster move. Do not let
                # elevate's ordinary call-up fallback pick an unrelated cut.
                if (p not in (getattr(team, '_elevated', None) or [])
                        and (playoffs or p.xp_spent.get('_elevations', 0) < PS.ELEVATIONS_PER_MAN)
                        and len(getattr(team, '_elevated', None) or []) < PS.ELEVATIONS_PER_GAME):
                    elevated = bool(PS.elevate(league, team.abbr, [p.pid], week, playoffs))
                    if elevated: break
            if not elevated and not _acquire(league, team, available, positions, desk, week):
                break
            updated = dressed(team, desk, week)
            if {p.pid for p in updated} == {p.pid for p in available}:
                break
            available = updated
            missing = shortages(available)
    if missing:
        detail = ', '.join(f'{label} (short {count})' for label, _, count in missing)
        raise FieldabilityError(f'Week {week}: {team.abbr} cannot field a team: {detail}. '
                               'Add an eligible player or free cap/roster space before advancing.')
    return available


def require_scores(league, week):
    missing = [f'{away} at {home}' for wk, away, home, ap, hp in league.schedule
               if wk == week and (ap is None or hp is None)]
    if missing:
        raise FieldabilityError(f'Week {week} still has unplayed games: {", ".join(missing)}. '
                               'Finish those games before advancing.')
