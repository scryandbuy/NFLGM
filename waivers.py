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
CLAIMS_PER_SEASON = 8    # in-season claims a club, about the real pace
CUTDOWN_CLAIMS = 1       # at the cut-down, a club: the real day sees 20-30 claims across the league, not 89


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


def reaches_user(league, e, week, market=None):
    """Does this man reach the user's priority? False when a club ahead of him wants the man
    (the wants() read is the same one the award uses, so this is the award foretold)."""
    user = getattr(league, 'user_team', None)
    if not user: return False
    if 'ahead' in e: return e['ahead'] is None
    p = league.player(e['pid'])
    if p is None: e['ahead'] = 'gone'; return False
    order = priority(league, week)
    import valuation as VAL
    if market is None:
        try: market = VAL.value_player(league, p, side='team', rng=None)
        except Exception: market = None
    e['ahead'] = None
    for abbr in order:
        if abbr == user: break
        if abbr != e['from_team'] and wants(league, abbr, p, week, market=market):
            e['ahead'] = abbr; break
    return e['ahead'] is None


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
    # A REAL UPGRADE, or nothing: claims at +1.5 over the k-th man, with the
    # released man going back on the wire, fed a loop that ran 689 claims a
    # season against a real ~150 in season
    if p.ovr < incumbent + 3.0:
        return False
    if not week:
        # the cut-down wave: a club makes one or two claims, not a dozen
        if sum(1 for x in league.transactions[-3000:] if x.get('kind') == 'waiver_claim' and x.get('team') == abbr
               and x.get('year') == league.year and not x.get('week')) >= CUTDOWN_CLAIMS:
            return False
    if week and week > 0:
        claims_this_season = sum(1 for x in league.transactions if x.get('kind') == 'waiver_claim' and x.get('team') == abbr and x.get('year') == league.year and (x.get('week') or 0) > 0)
        if claims_this_season >= CLAIMS_PER_SEASON: return False
        if any(x.get('kind') == 'waiver_claim' and x.get('team') == abbr and x.get('year') == league.year and x.get('week') == week for x in league.transactions[-400:]):
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
    # THE MAN WHO GOES IS WORSE THAN THE MAN WHO COMES, AND CHEAP TO CUT. It used to
    # drop the worst man at the exact spot, and when the only other man at the spot
    # was the starter, the starter went: San Francisco released Trent Williams (91,
    # $18m dead) to claim a 70 off the wire. Now: same position group first, then the
    # whole roster; never anyone better than the claim; never a release whose dead
    # money is more than a minimum salary; nobody locked.
    GRP = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL', 'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL', 'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB',
           'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'HB': 'RB', 'FB': 'RB', 'K': 'ST', 'P': 'ST', 'LS': 'ST'}
    import min_salary as MS
    from cap_engine import CAP
    ceiling = MS.minimum_salary(3, CAP.get(league.year, 301.2))
    def ok(q): return q is not p and not PSQ.locked(q, league.week) and q.ovr < p.ovr - 0.5 and q.dead_if_cut(0) <= ceiling
    grp = GRP.get(p.pos, p.pos)
    cands = [q for q in team.active() if GRP.get(q.pos, q.pos) == grp and ok(q)]
    if not cands:
        cands = [q for q in team.active() if ok(q)]
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
    league.assign_number(p, abbr)
    if abbr == getattr(league, 'user_team', None):
        import inbox as IB
        IB.post(league, 'waiver_notice', f"Claim awarded: {p.name}", f"You were awarded {p.name} ({p.pos}, {round(p.ovr)}) off waivers from {entry['from_team']}. He is on your roster with his contract" + (f", ${p.apy:.1f}m a year" if p.contract else '') + '.', sender='league')
    # the user named the man to make room with
    rel = entry.get('release_if_awarded')
    if rel and abbr == getattr(league, 'user_team', None) and league.player(rel) is not None and league.player(rel).team == abbr:
        league.release(rel)


# ------------------------------------------------------------ the wire
def notify_user(league, entries, week, digest=False):
    """Inbox notices for the user's club. Cut-down: one note pointing at the wire page, which lists every
    man who reaches his priority. In season: one note a man, and only for the men who reach him; a man a
    club ahead will take is never offered."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if not user: return
    order = priority(league, week)
    mine = order.index(user) + 1 if user in order else None
    ents = [e for e in entries if not e['user_notified'] and e.get('from_team') != user]
    for e in ents: e['user_notified'] = True
    seen = set(); ents = [e for e in ents if not (e['pid'] in seen or seen.add(e['pid']))]
    if not ents: return
    import valuation as VAL
    pool = VAL.pool_from_league(league)
    reach = []
    for e in ents:
        p = league.player(e['pid'])
        if p is None: continue
        try: market = VAL.value_player(league, p, side='team', rng=None, pool=pool)
        except Exception: market = None
        if reaches_user(league, e, week, market=market): reach.append(e)
    if not reach: return
    if digest or len(reach) > 12:
        IB.post(league, 'waiver_digest', f'The wire: {len(reach)} players reach your priority', f"{len(ents)} players were waived and {len(reach)} of them clear every club ahead of you (you are {mine} of 32). They are on the wire page; claim any you want before the Advance, or leave them and nothing happens.", sender='league', payload=dict(link='personnel:waivers', n=len(reach), priority=mine), expires_week=(week or 0) + 1)
        return
    for e in reach:
        p = league.player(e['pid'])
        hit = round(p.contract.cap_hit(0) - p.contract.annual_proration, 2) if p.contract else None
        yrs = p.contract.years if p.contract else 0
        body = (f"{p.name}, {p.pos}, {round(p.ovr)} overall, age {p.age:.0f}, {p.accrued or 0} accrued seasons, waived by {e['from_team']}. "
                f"No club ahead of you wants him; he is yours if you claim before the Advance." + (f" Inherited deal: {yrs} year(s) at ${hit}m this season." if hit is not None else ''))
        IB.post(league, 'waiver_notice', f'Available on waivers: {p.name} ({p.pos})', body, sender='league',
                payload=dict(pid=p.pid, from_team=e['from_team'], link=f'player:{p.pid}', priority=mine, cap_hit=hit, years=yrs), expires_week=(week or 0) + 1)


def user_claim(league, pid, release_pid=None):
    """The user claims from the inbox. Awarded at the next advance by priority. release_pid
    names the man to cut if the claim is awarded and the roster is full."""
    user = getattr(league, 'user_team', None)
    for e in pending(league):
        if e['pid'] == pid and user:
            if user not in e['claims']: e['claims'].append(user)
            if release_pid: e['release_if_awarded'] = release_pid
            return True
    return False


def user_withdraw(league, pid):
    user = getattr(league, 'user_team', None)
    for e in pending(league):
        if e['pid'] == pid and user in e['claims']:
            e['claims'].remove(user); e.pop('release_if_awarded', None); return True
    return False


def done_ids(awarded): return {pid for pid, _ in awarded}


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
            if p is not None and user in e.get('claims', []) and p.team is not None:
                IB.post(league, 'waiver_notice', f"Claim void: {p.name}", f"{p.name} ({p.pos}) was signed by {p.team} before the wire cleared. Your claim did not go through.", sender='league')
            ents.remove(e); continue
        # his price, once
        market = VAL.value_player(league, p, side='team', rng=None, pool=pool)
        if not market:
            ents.remove(e); continue
        for abbr in order:
            if abbr == user:
                if user in e['claims']:
                    # the user named his own man to make room with; only if he did not does the engine pick one
                    rel = e.get('release_if_awarded')
                    if (rel and league.player(rel) is not None and league.player(rel).team == user) or make_room(league, user, p):
                        award(league, e, user); awarded.append((p.pid, user)); break
                    IB.post(league, 'waiver_notice', f"Claim failed: {p.name}", f"Your claim on {p.name} ({p.pos}) could not be processed: no roster spot could be opened for him. He stays on the wire.", sender='league')
                continue
            if wants(league, abbr, p, week, market=market) and make_room(league, abbr, p):
                award(league, e, abbr); awarded.append((p.pid, abbr))
                if user in e.get('claims', []):
                    import inbox as IB
                    IB.post(league, 'waiver_notice', f"Claim lost: {p.name} to {abbr}", f"You claimed {p.name} ({p.pos}) and {abbr} held the higher priority. He is theirs.", sender='league')
                break
        ents.remove(e)
        # the club that waived him meant him for its practice squad: if nobody claimed, he goes there
        intent = (getattr(league, 'ps_intent', None) or {})
        if intent.get(p.pid):
            import practice_squad as PSQ
            club = intent.pop(p.pid)
            if p.pid in done_ids(awarded):
                to = next(a for pid_, a in awarded if pid_ == p.pid)
                if club == user: IB.post(league, 'waiver_notice', f"{p.name} claimed by {to}", f"You waived {p.name} for the practice squad and {to} claimed him off the wire. He is theirs.", sender='assistants')
            elif PSQ.sign_to_squad(league, club, p.pid):
                league.log('ps_sign', pid=p.pid, team=club, cleared=True)
                if club == user: IB.post(league, 'waiver_notice', f"{p.name} cleared to the practice squad", f"{p.name} cleared waivers and is on your practice squad.", sender='assistants')
            elif club == user: IB.post(league, 'waiver_notice', f"{p.name} cleared, no room on the squad", f"{p.name} cleared waivers but the squad had no room for him under its rules; he is a free agent.", sender='assistants')
    # close the notices
    done = {pid for pid, _ in awarded}
    for m in IB.pending(league, 'waiver_notice'):
        if m['payload'].get('pid') in done or True:
            m['status'] = 'expired' if m['payload'].get('pid') not in done else 'closed'
    if verbose and awarded:
        print(f'  waivers: {len(awarded)} claimed')
    return awarded
