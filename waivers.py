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
from inbox import player_name as inbox_player
import collections
import numpy as np
import valuation as VAL

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


def reaches_user(league, e, week, market=None, *, _assessments=None):
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
        if abbr != e['from_team'] and wants(league, abbr, p, week, market=market, _assessments=_assessments):
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
def wants(league, abbr, p, week, market=None, *, _assessments=None):
    """Does this club claim him? Need at the spot, value over the inherited
    cost, and room or a man it would drop for him. `market` is his valuation,
    computed once per man on the wire and shared by every club: the price
    does not depend on who is asking, and asking 32 times was most of the
    cost of a season."""
    import gm_surfaces as GS, valuation as VAL, min_salary as MS
    import roster_needs as RN
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
        baseline = None
        if _assessments is not None:
            # The caller owns this sweep and discards snapshots on a move.
            # No assessment survives the notification or claim-award call.
            if abbr not in _assessments:
                _assessments[abbr] = RN.assess(team)
            baseline = _assessments[abbr]
        if RN.move_gain(team, p, baseline=baseline) < 3.0:
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


def make_room(league, abbr, p, entry):
    """Open a roster spot only when the release and claim fit together."""
    import practice_squad as PSQ
    import roster_needs as RN
    team = league.teams[abbr]
    # A healthy specialist upgrade replaces the incumbent. Keeping both by
    # releasing an unrelated player can exhaust the market for another club.
    incumbents = [q for q in team.active() if q.pos == p.pos and q.out_until is None]
    if (abbr != getattr(league, 'user_team', None) and p.pos in ('K', 'P', 'LS')
            and incumbents):
        if p.out_until is not None:
            return False
        recent = PSQ._recent_additions(league, team)
        for q in sorted(incumbents, key=lambda q: (q.ovr, q.pid)):
            if (q.pid in recent or q.ovr >= p.ovr - .5 or PSQ.locked(q, league.week)
                    or PSQ.protected(team, q, league, incoming=p)):
                continue
            if (claim_fits(league, entry, abbr, release_pid=q.pid)
                    and _claim_budget(league, team, p, q)):
                league.release(q.pid)
                return True
        return False
    if len(team.active()) < 53:
        return claim_fits(league, entry, abbr) and _claim_budget(league, team, p)
    if abbr == getattr(league, 'user_team', None):
        return False  # Only an explicitly named release may open the user's spot.
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
    # Claims must not undo the essential backup repairs made before the wire.
    # Share their coverage and recent-arrival checks across acquisition routes.
    safe = {q.pid for q in PSQ._room_candidates(league, team, p)}
    def ok(q): return q.pid in safe and q.ovr < p.ovr - 0.5 and q.dead_if_cut(0) <= ceiling
    grp = GRP.get(p.pos, p.pos)
    cands = [q for q in team.active() if GRP.get(q.pos, q.pos) == grp and ok(q)]
    if not cands:
        cands = [q for q in team.active() if ok(q)]
    if not cands:
        return False
    # Prefer the release that leaves the coach's playable roster strongest.
    # Searching the bottom few avoids repeatedly scoring an entire roster for
    # every man on the wire.
    baseline = RN.assess(team)
    ranked = sorted(((RN.move_gain(team, p, q, baseline=baseline), q)
                     for q in sorted(cands, key=lambda q: q.ovr)[:8]),
                    key=lambda row: row[0], reverse=True)
    for gain, outgoing in ranked:
        if gain < 0.0:
            break
        if (claim_fits(league, entry, abbr, release_pid=outgoing.pid)
                and _claim_budget(league, team, p, outgoing)):
            league.release(outgoing.pid)
            return True
    return False


def _claim_budget(league, team, player, outgoing=None):
    import practice_squad as PS
    return PS._cpu_move_budget(league, team, player, claim_contract(league, player, team.abbr),
                               outgoing, action='waiver_claim')


def claim_contract(league, p, abbr):
    import copy, min_salary as MS
    from cap_engine import CAP, Contract
    c=copy.deepcopy(p.contract) if p.contract else Contract(1,[MS.minimum_salary(p.accrued or 0,CAP.get(league.year,301.2))])
    c.sb=0.0
    paid=league.teams[abbr].cap.paid_week
    if paid>c.pay_start:
        c.base[0]*=max(0,18-paid)/max(1,18-c.pay_start)
    c.pay_start=paid
    return c


def claim_fits(league, entry, abbr, release_pid=None):
    from cap_accounting import require_room
    p=league.player(entry['pid'])
    rel = release_pid
    if rel is None and abbr == getattr(league, 'user_team', None):
        rel = entry.get('release_if_awarded')
    try: require_room(league,league.teams[abbr],p.pid,claim_contract(league,p,abbr),release_pid=rel)
    except ValueError: return False
    return True


def award(league, entry, abbr):
    p = league.player(entry['pid'])
    if p.pid in league.free_agents: league.free_agents.remove(p.pid)
    c = claim_contract(league,p,abbr)
    p.team = abbr; p.contract = c
    league.teams[abbr].roster.append(p); league.teams[abbr].sync_cap()
    league.log('waiver_claim', pid=p.pid, team=abbr, from_team=entry['from_team'])
    league.assign_number(p, abbr)
    if abbr == getattr(league, 'user_team', None):
        import inbox as IB
        IB.post(league, 'waiver_notice', f"Claim awarded: {inbox_player(p)}", f"You were awarded {inbox_player(p)} ({p.pos}, {round(p.ovr)}) off waivers from {entry['from_team']}. He is on your roster with his contract" + (f", ${p.apy:.1f}m a year" if p.contract else '') + '.', sender='league')
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
    assessments = {}  # Discard before any later roster, rating or coach change.
    with VAL.comparison_batch():
        for e in ents:
            p = league.player(e['pid'])
            if p is None: continue
            try: market = VAL.value_player(league, p, side='team', rng=None, pool=pool)
            except Exception: market = None
            if reaches_user(league, e, week, market=market, _assessments=assessments): reach.append(e)
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
        IB.post(league, 'waiver_notice', f'Available on waivers: {inbox_player(p)} ({p.pos})', body, sender='league',
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


@VAL.comparison_batch()
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
    # Snapshot only availability messages. New result mail stays unread.
    notices = [m for m in IB.pending(league) if m.get('kind') == 'waiver_digest'
               or (m.get('kind') == 'waiver_notice' and (m.get('payload') or {}).get('pid'))]
    processed = {e['pid'] for e in ents}
    import valuation as VAL
    pool = VAL.pool_from_league(league) if ents else None
    assessments = {}
    for e in list(ents):
        user_failed = False
        p = league.player(e['pid'])
        if p is None or p.retired or p.team is not None:
            if p is not None and user in e.get('claims', []) and p.team is not None:
                IB.post(league, 'waiver_notice', f"Claim void: {inbox_player(p)}", f"{inbox_player(p)} ({p.pos}) was signed by {p.team} before the wire cleared. Your claim did not go through.", sender='league')
            ents.remove(e); continue
        # his price, once
        market = VAL.value_player(league, p, side='team', rng=None, pool=pool)
        if not market:
            ents.remove(e); continue
        for abbr in order:
            if abbr == user:
                if user in e['claims']:
                    if not claim_fits(league,e,user):
                        user_failed = True
                        IB.post(league,'waiver_notice',f'Claim failed: {inbox_player(p)}','The inherited contract does not fit under your cap.',sender='league')
                        continue
                    # Only the user's explicitly named active player may be cut.
                    rel = e.get('release_if_awarded')
                    active = league.teams[user].active()
                    if len(active) < 53 or (len(active) == 53 and rel and league.player(rel) in active):
                        award(league, e, user); awarded.append((p.pid, user))
                        assessments.clear()
                        break
                    user_failed = True
                    IB.post(league, 'waiver_notice', f"Claim failed: {inbox_player(p)}", f"Your claim on {inbox_player(p)} ({p.pos}) could not be processed: no roster spot could be opened for him. The claim window has closed; he may join another club or clear to free agency.", sender='league')
                continue
            import practice_squad as _PSQ
            if _PSQ.shunned(p, abbr, league) or getattr(league.teams[abbr], '_moved_week', None) == week: continue     # released him lately, or moved already this week
            if not wants(league, abbr, p, week, market=market, _assessments=assessments):
                continue
            # make_room may release a player. Expire this club's read before
            # trying it, even if no claim is ultimately awarded.
            assessments.pop(abbr, None)
            if make_room(league, abbr, p, e):
                league.teams[abbr]._moved_week = week
                award(league, e, abbr); awarded.append((p.pid, abbr))
                assessments.clear()
                if user in e.get('claims', []) and not user_failed:
                    import inbox as IB
                    IB.post(league, 'waiver_notice', f"Claim lost: {inbox_player(p)} to {abbr}", f"You claimed {inbox_player(p)} ({p.pos}) and {abbr} held the higher priority. He is theirs.", sender='league')
                break
        ents.remove(e)
        # CLEARED AND UNCLAIMED, HE IS A FREE AGENT: the contract he carried on the wire (for a claiming club to
        # inherit) comes off him. The club that waived him already ate the dead money; left on, the deal showed
        # on his card as if a club still owed it
        if p.pid not in done_ids(awarded) and p.team is None:
            p.contract = None
        # the club that waived him meant him for its practice squad: if nobody claimed, he goes there
        intent = (getattr(league, 'ps_intent', None) or {})
        if intent.get(p.pid):
            import practice_squad as PSQ
            club = intent.pop(p.pid)
            if p.pid in done_ids(awarded):
                to = next(a for pid_, a in awarded if pid_ == p.pid)
                if club == user: IB.post(league, 'waiver_notice', f"{inbox_player(p)} claimed by {to}", f"You waived {inbox_player(p)} for the practice squad and {to} claimed him off the wire. He is theirs.", sender='assistants')
            elif PSQ.sign_to_squad(league, club, p.pid):          # sign_to_squad logs the move
                assessments.clear()
                if club == user: IB.post(league, 'waiver_notice', f"{inbox_player(p)} cleared to the practice squad", f"{inbox_player(p)} cleared waivers and is on your practice squad.", sender='assistants')
            elif club == user: IB.post(league, 'waiver_notice', f"{inbox_player(p)} cleared, no room on the squad", f"{inbox_player(p)} cleared waivers but the squad had no room for him under its rules; he is a free agent.", sender='assistants')
    # Close availability for this batch, including its digest, never results.
    for m in notices:
        pl = m.get('payload') or {}
        if m.get('kind') == 'waiver_digest' or pl.get('pid') in processed:
            m['status'] = 'closed'
    if verbose and awarded:
        print(f'  waivers: {len(awarded)} claimed')
    return awarded
