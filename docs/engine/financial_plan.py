"""Shared CPU financial strategy over the existing cap ledger (amounts in $M).

Pure projections: no RNG, transaction, save mutation, or cash-floor enforcement.
The reserve coefficients are initial policy settings, not fitted NFL estimates.
Hard transaction legality remains in cap_accounting; this layer prices flexibility.
"""
import copy
from statistics import median
from cap_engine import CAP
import min_salary as MS

EPS = .0005
HORIZON = 4


def _clip(x, lo=0., hi=1.):
    return max(lo, min(hi, float(x)))


def _trait(team, name, default=.5):
    return _clip(getattr(getattr(team, 'gm', None), name, default))


def _cap(league, team, year):
    return float(CAP.get(year, team.cap.cap * 1.055 ** (year - league.year)))


def _charge(contract, index):
    if index < contract.years:
        return contract.cap_hit(index)
    return contract.remaining_proration(index) if index == contract.years else 0.


def _retention_estimates(league, keepers):
    """Conservative renewal placeholders, including raises from rookie pay.

Use the nearest three veteran grades at the same position, excluding the
player himself and identifiable original rookie deals. This is an observed
pay comparison, not an agent quote. Rebuild locally so contracts, ratings and
save/load cannot leave stale estimates; no random valuation or second ledger.
"""
    positions = {p.pos for p, _, _ in keepers}
    peers = {pos: [] for pos in positions}
    for team in league.teams.values():
        for q in team.roster:
            c = q.contract
            if q.pos not in positions or q.retired or not c or not c.years:
                continue
            draft_year = getattr(q, 'draft_year', None)
            if draft_year is not None and c.signed in (int(draft_year), int(draft_year)+1):
                continue
            if q.apy > 0:
                peers[q.pos].append((q.pid, q.ovr, q.apy))
    out = []
    for p, expiry, known_pay in keepers:
        grade = p.ovr
        candidates = sorted((row for row in peers[p.pos]
                             if row[0] != p.pid and abs(row[1]-grade) <= 8),
                            key=lambda row: (abs(row[1]-grade), str(row[0])))[:3]
        market_pay = median(row[2] for row in candidates) if candidates else known_pay
        out.append((p, expiry, max(known_pay, market_pay)))
    return out


def _ledger(league, team, additions, removals, trial_cap):
    """Build from roster, not a possibly stale cache. A preview never syncs state."""
    cap = copy.copy(trial_cap if trial_cap is not None else team.cap)
    players = {p.pid: p for p in team.roster if not p.retired}
    additions = {p.pid: (p, c) for p, c in additions}
    removals = set(removals) - additions.keys()
    if trial_cap is None:
        cap.contracts = [(p.pid, p.contract, 0) for p in players.values() if p.contract]
        june1 = league.post_june1()
        for pid in removals:
            p = players.get(pid)
            if p is not None and p.contract:
                now, nxt, _ = p.contract.release(0, june1)
                cap.dead += now
                cap.dead_next += nxt
                cap.earned += p.contract.earned_base + p.contract.earned_roster
    else:
        cap.contracts = list(cap.contracts)
    for pid in removals:
        players.pop(pid, None)
    replaced = set(additions) | removals
    cap.contracts = [row for row in cap.contracts if row[0] not in replaced]
    for pid, (p, contract) in additions.items():
        players[pid] = p
        cap.contracts.append((pid, contract, 0))
    return cap, players


def _rookies(league, team, picks=None):
    """Unused picks replace vacancy placeholders, never add a second occupant.

Pick years label the completed season in this game; their contracts start +1.
Unknown slots use the middle of their round, explicitly a forecast.
"""
    import draft
    rows = []
    for pk in (team.picks if picks is None else picks):
        if pk.used_on:
            continue
        start = int(pk.year) + 1
        if start < league.year:
            continue
        selection = pk.selection or (int(pk.round)-1)*32+16
        rows.append((start, draft.rookie_contract(selection, _cap(league, team, start), signed=start)))
    return rows


def snapshot(league, team, *, additions=(), removals=(), trial_cap=None,
             pending=(), picks=None):
    """Four actual cap-year rows. Pending (player, Contract) pairs count once.

`picks` optionally supplies the post-trade pick inventory. Current-year raw_room
uses legal accounting; funded_room forecasts retained contracts plus missing
53-man slots/rookies. Retention is a separate soft, incremental placeholder.
"""
    from cap_accounting import pre_roll
    additions = list(additions)
    added_ids = {p.pid for p, _ in additions}
    roster_ids = {p.pid for p in team.roster}
    held = {p.pid: (p, c) for p, c in pending
            if p.pid not in added_ids and p.pid not in roster_ids}
    ledger, players = _ledger(league, team, list(held.values())+additions, removals, trial_cap)
    start = int(pre_roll(league))
    rookies = _rookies(league, team, picks)
    ir = {p.pid for p in getattr(team, 'ir', ())}
    contracts = {pid: c for pid, c, _ in ledger.contracts}
    # Named retention estimates use current veteran pay, not agent quotes.
    # Only leading players clearly above an existing replacement are held.
    groups = {}
    for p in players.values():
        groups.setdefault(p.pos, []).append(p)
    keepers = []
    for pos, group in groups.items():
        group.sort(key=lambda p: (-p.ovr, str(p.pid)))
        n = {'WR': 3, 'CB': 3, 'DT': 2}.get(pos, 1)
        replacement = group[n].ovr if len(group) > n else 65.
        for p in group[:n]:
            c = contracts.get(p.pid)
            if c and p.ovr >= 76 and p.ovr-replacement >= 3:
                # Pay is the contract under evaluation, not the player's old deal.
                apy = (sum(c.base)+sum(c.rb)+c.sb)/max(1,c.years-c.start_offset)
                keepers.append((p, c.years, apy))
    # No renewal falls inside this horizon for longer committed contracts.
    keepers = _retention_estimates(league, [(p,e,a) for p,e,a in keepers
                                          if e < start+HORIZON])

    patience = _trait(team, 'patience')
    risk = _trait(team, 'risk')
    aggression = _trait(team, 'aggression')
    security = _trait(team, 'job_security', .6)
    contender = _clip(team.contender)
    # Continuous opportunity cost. No classification by team abbreviation.
    opportunity_pct = _clip(.010 + .014*patience + .008*(1-contender)
                            - .006*aggression - .004*risk
                            - .005*(1-security), .003, .035)
    rows = []
    for index in range(start, start+HORIZON):
        year = league.year+index
        base = _cap(league, team, year)
        fraction = max(0., 18-ledger.paid_week)/18 if index == 0 else 1.
        floor = MS.minimum_salary(2, base)*fraction
        alive = [(pid,c) for pid,c in contracts.items() if c.years>index]
        active = sum(pid not in ir or index>0 for pid,c in alive)
        rookie_hits = [c.cap_hit(year-y) for y,c in rookies if 0<=year-y<c.years]
        # Drafted players disappear from unused-pick forecasts on selection.
        rookie_reserve = sum(rookie_hits)
        vacancies = max(0,53-active-len(rookie_hits))
        vacancy_reserve = vacancies*floor
        # Draft/camp additions displace paid roster slots, rather than funding
        # a permanent 60- or 90-man roster. Credit at most a minimum salary per
        # excess slot, capped by real net release savings (bonus acceleration
        # included). This is a conservative forecast, never a booked release.
        # Keep IR salaries and all hard current cap charges in the ledger.
        excess = max(0, active+len(rookie_hits)-53)
        savings = sorted(min(floor, max(0., c.release(index, False)[2]))
                         for pid,c in alive if pid not in ir or index>0)
        displacement = sum(savings[:excess])
        if index == 0:
            limit = ledger.limit
            charge = ledger.charges(team.phase)
            full_charge = ledger.charges('season')
        else:
            # Only completed-season carryover is available at the pre-roll stop.
            # No speculative future rollover is counted as guaranteed room.
            carry = max(0.,ledger.space('season')) if start and index==1 else 0.
            limit = base+carry
            charge = sum(_charge(c,index) for c in contracts.values())
            if index == 1:
                charge += ledger.dead_next
            full_charge = charge
        raw = limit-charge
        funded = limit-full_charge-rookie_reserve-vacancy_reserve+displacement
        # Vacancy costs already fund a replacement, so retain only the premium.
        retention = sum(max(0.,apy-MS.minimum_salary(2,base))*.5
                        for p,expiry,apy in keepers if expiry<=index)
        injury = base * .008 * fraction
        opportunity = base * opportunity_pct
        row = dict(year=year, limit=limit, raw_room=raw, committed=charge,
                   active_contracts=active, vacant_slots=vacancies,
                   rookie_reserve=rookie_reserve, vacancy_reserve=vacancy_reserve,
                   displacement_credit=displacement,
                   full_roster_adjustment=full_charge-charge,
                   funded_room=funded, retention_reserve=retention,
                   injury_reserve=injury, opportunity_reserve=opportunity,
                   soft_reserve=retention+injury+opportunity,
                   discretionary_room=funded-retention-injury-opportunity)
        rows.append(row)
    return dict(team=team.abbr, cap_year=league.year+start, phase=league.phase,
                years=rows, pending_count=len(held), **{k:rows[0][k] for k in
                ('raw_room','funded_room','soft_reserve','discretionary_room',
                 'rookie_reserve','vacancy_reserve','retention_reserve')})


def evaluate(league, team, *, additions=(), removals=(), trial_cap=None,
             gain=0., essential=False, action='', pending=(), before=None,
             picks=None):
    """Screen a CPU proposal; callers still perform authoritative legal checks.

Existing unfunded future commitments do not freeze cap-improving moves. A
meaningful football gain releases a bounded part of the soft reserve; essential
repairs can release it all, but cannot worsen legal cap debt. `before` may be
reused only while roster/contracts/phase/pending commitments are unchanged.
"""
    before = before or snapshot(league,team,pending=pending)
    after = snapshot(league,team,additions=additions,removals=removals,
                     trial_cap=trial_cap,pending=pending,picks=picks)
    result = dict(approved=True, reason='approved_normal', action=action,
                  before=before, after=after, reserve_used=0.)
    if team.abbr == getattr(league,'user_team',None):
        result['reason']='user_control'
        return result
    benefit = max(0.,float(gain))
    # Package-score units, already used by roster_needs candidate valuation.
    threshold = 8.+6.*_trait(team,'patience')-3.*_trait(team,'aggression')
    release = _clip((benefit-threshold)/20.,0.,.8)
    for b,a in zip(before['years'],after['years']):
        if a['raw_room'] < -EPS and a['raw_room'] < b['raw_room']-EPS:
            result.update(approved=False,reason='legal_cap_failure')
            return result
        if not essential and a['funded_room'] < -EPS and a['funded_room'] < b['funded_room']-EPS:
            result.update(approved=False,reason='fund_required_roster')
            return result
        if essential:
            continue
        floor = a['soft_reserve']*(1-release)
        before_gap = max(0., b['soft_reserve']*(1-release)-b['funded_room'])
        gap = max(0.,floor-a['funded_room'])
        if gap > before_gap+EPS:
            result.update(approved=False,reason='preserve_retention' if a['retention_reserve']
                          else 'preserve_flexibility')
            return result
        result['reserve_used'] = max(result['reserve_used'],max(0.,a['soft_reserve']-a['funded_room']))
    if essential:
        result['reason']='approved_emergency'
    elif result['reserve_used']>EPS:
        result['reason']='approved_exceptional_upgrade'
    return result


def roster_funding_target(league,team):
    """Concrete roster/draft funding only; never restructure to refill a cushion."""
    row=snapshot(league,team)['years'][0]
    return max(0.,row['raw_room']-row['funded_room'])
