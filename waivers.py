"""
WAIVERS, on the real rules.

WHO GOES THROUGH. A released man with fewer than four accrued seasons is
subject to waivers; a vested veteran (four or more) is a free agent at
once. After the trade deadline everyone released goes through waivers.

PRIORITY. Through the third week of the season, the order is the draft
order (worst record last year first, regardless of trades). From week four
it is the reverse of the current standings. The club with the highest
priority that claims him gets him; if no one claims him in the period he
is a free agent and, if eligible, can be signed to any practice squad
including his own club's.

THE CONTRACT TRAVELS. A claimed man arrives on the terms he signed, base
and roster bonus, on the claiming club's cap. The waiving club has already
eaten his remaining bonus as dead money the moment it released him. A
claiming club must have a spot on the 53 in season; the AI clears one by
releasing its worst man at the position.

THE USER. Every waived man the user might want is a notice in the inbox,
with the player, his contract and the user's claim priority; claim from the
message. At cut-down the notices are one digest. Claims are awarded at the
next advance, so a higher-priority club that also claimed him wins, which
is how a real wire works.
"""
import collections
import numpy as np

VESTED = 4
DEADLINE_WEEK = 9


def pending(league):
    if not hasattr(league, 'waivers') or league.waivers is None:
        league.waivers = []
    return league.waivers


def subject(league, p, week):
    """Is this release subject to waivers?"""
    if (p.accrued or 0) < VESTED:
        return True
    return league.phase == 'regular' and (week or 0) > DEADLINE_WEEK


def waive(league, p, from_team, week):
    """Put a released man on the wire. Called by league.release."""
    pending(league).append(dict(pid=p.pid, from_team=from_team, week=week, year=league.year,
                                claims=[], user_notified=False))


def priority(league, week, standings=None):
    """Clubs in claim order, first claims first."""
    teams = list(league.teams)
    if league.phase != 'regular' or (week or 0) <= 3:
        # draft order: the slot of each club's own original first-round pick
        year = league.year if league.phase == 'regular' else league.year - 1
        slot = {}
        for t in league.teams.values():
            for pk in t.picks:
                if pk.year == year and pk.round == 1 and pk.original == t.abbr and pk.selection:
                    slot[t.abbr] = pk.selection
        if len(slot) >= 24:
            return sorted(teams, key=lambda a: slot.get(a, 99))
        # no order set yet (the very first offseason): worst record last year
        return sorted(teams, key=lambda a: (league.teams[a].prev_win_pct, a))
    return sorted(teams, key=lambda a: (league.teams[a].win_pct, league.teams[a].record[0], a))


# ------------------------------------------------------------ the AI's claim
def wants(league, abbr, p, week, market=None):
    """Does this club claim him? Need at the spot, value over the inherited
    cost, and room or a man it would drop for him. `market` is his valuation,
    computed once per man on the wire and shared by every club: the price
    does not depend on who is asking, and asking 32 times was most of the
    cost of a season."""
    import gm_surfaces as GS, valuation as VAL, min_salary as MS
    from cap_engine import CAP
    team = league.teams[abbr]
    if team.gm is None or p.pos in ('K', 'P') and any(q.pos == p.pos and q.ovr >= p.ovr for q in team.active()):
        return False
    depth = team.depth.get(p.pos, [])
    k = {'QB': 1, 'HB': 2, 'WR': 4, 'TE': 2, 'CB': 4, 'DT': 3, 'FS': 1, 'SS': 1}.get(p.pos, 2)
    incumbent = depth[k - 1].ovr if len(depth) >= k else 40.0
    if p.ovr < incumbent + 1.5:
        return False
    v = market if market is not None else VAL.value_player(league, p, side='team', rng=None)
    if not v:
        return False
    cost = float(p.contract.cap_hit(0) - p.contract.annual_proration) if p.contract else MS.minimum_salary(p.accrued or 0, CAP.get(league.year, 301.2))
    if cost > team.cap_space:
        return False
    row = dict(cost=cost, dead=0.0, accrued=p.accrued or 0)
    return GS.claim_value(row, v, team.gm, team.ctx()) > 0.0


def make_room(league, abbr, p):
    """In season the 53 is full: drop the worst man at his spot who is not locked."""
    import practice_squad as PSQ
    team = league.teams[abbr]
    if len(team.active()) < 53:
        return True
    cands = [q for q in team.active() if q.pos == p.pos and q is not p and not PSQ.locked(q, league.week)]
    if not cands:
        cands = [q for q in team.active() if not PSQ.locked(q, league.week)]
    if not cands:
        return False
    worst = min(cands, key=lambda q: q.ovr)
    league.release(worst.pid)
    return True


def award(league, entry, abbr):
    p = league.player(entry['pid'])
    if p.pid in league.free_agents: league.free_agents.remove(p.pid)
    if p.contract is not None:
        p.contract.sb = 0.0                     # the bonus stayed with the club that paid it
        c = p.contract
    else:
        import min_salary as MS
        from cap_engine import CAP, Contract
        mn = MS.minimum_salary(p.accrued or 0, CAP.get(league.year, 301.2))
        c = Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year)
    p.team = abbr; p.contract = c
    league.teams[abbr].roster.append(p); league.teams[abbr].sync_cap()
    league.log('waiver_claim', pid=p.pid, team=abbr, from_team=entry['from_team'])


# ------------------------------------------------------------ the wire
def notify_user(league, entries, week, digest=False):
    """Inbox notices for the user's club: one per man in season, one digest at cut-down."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if not user: return
    order = priority(league, week)
    mine = order.index(user) + 1 if user in order else None
    ents = [e for e in entries if not e['user_notified']]
    for e in ents: e['user_notified'] = True
    seen = set(); ents = [e for e in ents if not (e['pid'] in seen or seen.add(e['pid']))]
    if not ents: return
    if digest:
        import draft as DFT
        scale = DFT.position_scale(league)
        top = sorted(ents, key=lambda e: -DFT.common_scale(league.player(e['pid']).ovr, league.player(e['pid']).pos, scale))
        body = (f"{len(ents)} players were waived at cut-down. Your claim priority is {mine} of 32. "
                "Claims are awarded at the next advance to the highest-priority club that claims.")
        IB.post(league, 'waiver_digest', f'Waiver wire: {len(ents)} players available', body, sender='league',
                payload=dict(players=[dict(pid=e['pid'], from_team=e['from_team'],
                                           name=league.player(e['pid']).name, pos=league.player(e['pid']).pos,
                                           ovr=round(league.player(e['pid']).ovr, 1), age=round(league.player(e['pid']).age),
                                           accrued=league.player(e['pid']).accrued or 0,
                                           cap_hit=round(league.player(e['pid']).contract.cap_hit(0) - league.player(e['pid']).contract.annual_proration, 2) if league.player(e['pid']).contract else None,
                                           link=f'player:{e["pid"]}') for e in top],
                             priority=mine), expires_week=(week or 0) + 1)
        return
    # the eight best of the week by common-scale grade; the rest are on the
    # wire but not in the inbox
    import draft as DFT
    scale = DFT.position_scale(league)
    ents = sorted(ents, key=lambda e: -DFT.common_scale(league.player(e['pid']).ovr, league.player(e['pid']).pos, scale))[:8]
    for e in ents:
        p = league.player(e['pid'])
        hit = round(p.contract.cap_hit(0) - p.contract.annual_proration, 2) if p.contract else None
        yrs = p.contract.years if p.contract else 0
        body = (f"{p.name}, {p.pos}, age {p.age:.0f}, {p.accrued or 0} accrued seasons, was waived by {e['from_team']}. "
                f"Inherited deal: {yrs} year(s) at ${hit}m this season. Your claim priority is {mine} of 32.")
        IB.post(league, 'waiver_notice', f'On waivers: {p.name} ({p.pos})', body, sender='league',
                payload=dict(pid=p.pid, from_team=e['from_team'], link=f'player:{p.pid}', priority=mine,
                             cap_hit=hit, years=yrs), expires_week=(week or 0) + 1)


def user_claim(league, pid):
    """The user claims from the inbox. Awarded at the next advance by priority."""
    user = getattr(league, 'user_team', None)
    for e in pending(league):
        if e['pid'] == pid and user and user not in e['claims']:
            e['claims'].append(user); return True
    return False


def process(league, rng, week, verbose=False):
    """
    Award every man on the wire: AI clubs decide, the user's claim (if any)
    was lodged from the inbox, highest priority wins. Unclaimed men become
    free agents. Returns [(pid, team)].
    """
    import inbox as IB
    ents = pending(league)
    if not ents: return []
    order = priority(league, week)
    user = getattr(league, 'user_team', None)
    awarded = []
    import valuation as VAL
    pool = VAL.pool_from_league(league) if ents else None
    for e in list(ents):
        p = league.player(e['pid'])
        if p is None or p.retired or p.team is not None:
            ents.remove(e); continue
        # his price, once
        market = VAL.value_player(league, p, side='team', rng=None, pool=pool)
        if not market:
            ents.remove(e); continue
        for abbr in order:
            if abbr == user:
                if user in e['claims'] and make_room(league, user, p):
                    award(league, e, user); awarded.append((p.pid, user)); break
                continue
            if wants(league, abbr, p, week, market=market) and make_room(league, abbr, p):
                award(league, e, abbr); awarded.append((p.pid, abbr)); break
        ents.remove(e)
    # close the notices
    done = {pid for pid, _ in awarded}
    for m in IB.pending(league, 'waiver_notice'):
        if m['payload'].get('pid') in done or True:
            m['status'] = 'expired' if m['payload'].get('pid') not in done else 'closed'
    if verbose and awarded:
        print(f'  waivers: {len(awarded)} claimed')
    return awarded
