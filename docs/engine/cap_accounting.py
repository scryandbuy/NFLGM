"""Shared cap transactions. Game calendar and emergency exceptions stay intact."""
from cap_engine import forecast_cap
import copy
from cap_engine import CAP, TeamCap


def pre_roll(league):
    return (league.phase == 'offseason' and
            getattr(league, 'season_closed_year', None) == league.year)


def settle_week(league, week):
    """Book pay once after the games, before that week's roster transactions."""
    import practice_squad as PS
    import min_salary as MS
    week = min(18, max(0, int(week)))
    for t in league.teams.values():
        last = t.cap.paid_week
        if week <= last: continue
        for p in t.roster:
            c = p.contract
            if not c or not c.years: continue
            remaining = max(1, 18 - max(last, c.pay_start))
            n = max(0, week - max(last, c.pay_start))
            c.earned_base += (c.base[0] - c.earned_base) * n / remaining
            c.earned_roster = c.rb[0]
        for p in PS.squad(t):
            pay = (PS.PAY_VET if (p.accrued or 0) > 2 else PS.PAY_YOUNG) / 18
            t.cap.ps_earned += pay * (week-last)
            if p in (getattr(t, '_elevated', None) or []):
                t.cap.ps_earned += max(0.0, MS.minimum_salary(p.accrued or 0, CAP.get(league.year,301.2))/18-pay)
        t.cap.paid_week = week
        t.sync_cap()


def depart(league, team, contract, june1=None):
    """Keep paid salary on the old team; caller removes or transfers the deal."""
    if contract is None: return 0.0, 0.0, 0.0
    if pre_roll(league): settle_week(league,18)
    now,nxt,saved = contract.release(0, league.post_june1() if june1 is None else june1)
    team.cap.dead += now
    team.cap.dead_next += nxt
    team.cap.earned += contract.earned_base + contract.earned_roster
    return now,nxt,saved


def transfer_contract(contract, paid_week):
    """An acquiring team assumes only unearned salary, never old bonus."""
    c = copy.deepcopy(contract)
    c.base[0] = max(0.0,c.base[0]-c.earned_base)
    c.rb[0] = max(0.0,c.rb[0]-c.earned_roster)
    c.earned_base=c.earned_roster=0.0
    c.pay_start=paid_week
    c.sb=0.0
    return c


def require_room(league, team, pid, contract, release_pid=None):
    """Validate an ordinary deal before mutation; emergency fills bypass this helper."""
    from offer_reservations import held
    pending = held(league, team.abbr, exclude_pid=pid)
    team.sync_cap()
    before=team.cap.charges(team.phase)
    trial=copy.copy(team.cap)
    trial.contracts=[x for x in team.cap.contracts if x[0]!=pid]+[(pid,contract,0)]
    if release_pid:
        outgoing=league.player(release_pid)
        if outgoing and outgoing.team==team.abbr and outgoing.contract:
            c=outgoing.contract
            trial.contracts=[x for x in trial.contracts if x[0]!=release_pid]
            trial.dead+=c.release(0,league.post_june1())[0]
            trial.earned+=c.earned_base+c.earned_roster
    after=trial.charges(team.phase)
    pending_now = 0.0 if pre_roll(league) else pending
    acquisition = not any(p.pid == pid for p in team.roster)
    if after + pending_now > team.cap.limit + .0005 and (acquisition or after > before + .0005):
        raise ValueError('Not enough cap space for this contract')
    if pre_roll(league):
        old=next((p.contract for p in team.roster if p.pid==pid),None)
        limit,committed,_,_=next_year_ledger(league,team)
        oldhit=old.cap_hit(1) if old and old.years>1 else (old.remaining_proration(1) if old else 0.0)
        newhit=contract.cap_hit(1) if contract.years>1 else contract.remaining_proration(1)
        if committed-oldhit+newhit+pending>limit+.0005 and (acquisition or newhit>oldhit+.0005):
            raise ValueError('Not enough cap space next year for this contract')


def require_squad_room(league, team, player):
    from offer_reservations import held
    if player not in team.roster or not player.contract:
        return  # Squad pay does not use cap room.
    team.sync_cap()
    before = team.cap.charges(team.phase)
    trial = copy.copy(team.cap)
    trial.contracts = list(team.cap.contracts)
    c = player.contract
    trial.contracts = [x for x in trial.contracts if x[0] != player.pid]
    trial.dead += c.release(0, league.post_june1())[0]
    trial.earned += c.earned_base + c.earned_roster
    pending_now = 0.0 if pre_roll(league) else held(league, team.abbr, exclude_pid=player.pid)
    after = trial.charges(team.phase)
    if after + pending_now > trial.limit + .0005 and after > before + .0005:
        raise ValueError('Not enough cap space for this release')


def next_year_ledger(league, team):
    team.sync_cap()
    base=forecast_cap(league, league.year+1)
    rollover=max(0.0,team.cap.space('season'))
    dead=team.cap.dead_next+sum(p.contract.remaining_proration(1) for p in team.roster
                              if p.contract and p.contract.years==1)
    committed=sum(p.contract.cap_hit(1) for p in team.roster if p.contract and p.contract.years>1)+dead
    return base+rollover,committed,rollover,dead


def trade_projection(league, abbr, outgoing, incoming):
    team=league.teams[abbr]; team.sync_cap()
    trial=copy.copy(team.cap); trial.contracts=list(team.cap.contracts)
    for pid in outgoing:
        p=league.player(pid) if isinstance(pid,str) else None
        if not p or not p.contract: continue
        c=p.contract
        now,nxt,_=c.release(0,league.post_june1())
        trial.dead+=now; trial.dead_next+=nxt
        trial.earned+=c.earned_base+c.earned_roster
        trial.contracts=[row for row in trial.contracts if row[0]!=pid]
    for pid in incoming:
        p=league.player(pid) if isinstance(pid,str) else None
        if p and p.contract:
            trial.contracts.append((pid,transfer_contract(p.contract,team.cap.paid_week),0))
    return trial


def require_trade_room(league, a, b, a_sends, b_sends, roster_releases=None):
    from offer_reservations import held
    roster_releases = roster_releases or {}
    for abbr,outgoing,incoming in [(a,a_sends,b_sends),(b,b_sends,a_sends)]:
        team=league.teams[abbr]
        trial=trade_projection(league,abbr,list(outgoing)+list(roster_releases.get(abbr,())),incoming)
        after=trial.charges(team.phase)
        pending = held(league, abbr)
        pending_now = 0.0 if pre_roll(league) else pending
        acquisition = any(isinstance(x, str) for x in incoming)
        if after+pending_now>trial.limit+.0005 and (acquisition or after>team.cap.charges(team.phase)+.0005):
            raise ValueError(f'{abbr} cannot fit this trade under the cap')
        # Future-year commitments inform CPU valuation, not trade legality.
        # Each club must become cap compliant when that league year arrives.


def migrate_earned(team, league_data):
    """Legacy snapshots have no earned-pay ledger. Start from retained players.

    Do not invent departed-player charges that old saves did not retain.
    """
    schedule=league_data.get('schedule') or []
    weeks={w for w,*_ in schedule if w<=18}
    completed=max((w for w in weeks if all(g[3] is not None and g[4] is not None
                      for g in schedule if g[0]==w)),default=0)
    if league_data.get('phase')=='playoffs' or league_data.get('season_closed_year')==league_data['year']:
        completed=18
    team.cap.paid_week=completed
    import practice_squad as PS
    team.cap.ps_earned=sum(PS.PAY_VET if (p.accrued or 0)>2 else PS.PAY_YOUNG
                           for p in PS.squad(team))*completed/18
    for p in team.roster:
        c=p.contract
        if c:
            c.earned_base=c.base[0]*completed/18
            c.earned_roster=c.rb[0] if completed else 0.0
