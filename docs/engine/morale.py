"""
MORALE, WIRED. morale_system.py was designed and never called; this hooks it
to the calendar.

Weekly in season:  results move the fast clock for everyone (a blowout
  loss more), each man's own game moves it for him; snap share against
  what he believes he is owed (entitlement) and a losing season move the
  slow clock; the room pass carries a captain's or veteran's mood to his
  group; every clock decays.
Shocks as they happen:  benched (a drop of two or more places in his
  depth rank), an extension signed, a man signed over him at his spot in
  free agency, a playoff berth, a title.
Offseason:  contract pressure against the market for men on cheap deals.
Effects:  the on-field modifiers go into the game rows (mental and effort
  attributes only, capped at -3); the negotiation effect goes into
  extensions (an unhappy man asks up to 30% more, a man you broke a
  promise to trusts you less); a trade request puts him on the AI's list
  and in the user's inbox.
Nothing here talks to a player. No team talks, no press.
"""
import numpy as np, collections
import morale_system as MS

GROUP = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL', 'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL',
         'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'FB': 'HB'}
STARTER_SNAPS = {'QB': 60, 'HB': 35, 'WR': 50, 'TE': 45, 'OL': 60, 'DL': 40, 'LB': 45, 'DB': 55, 'K': 8, 'P': 6}


def ensure(p):
    if getattr(p, 'morale', None) is None:
        p.morale = MS.Morale(p.pid, MS.NEUTRAL)
    return p.morale


def entitlement_of(team, p, cache=None):
    """cache: a per-club dict for one tick, so the depth chart and the pay
    order at each spot are built once a week rather than once per man."""
    if cache is None: cache = {}
    if p.pos not in cache:
        depth = team.depth.get(p.pos, [])
        cache[p.pos] = (depth, sorted((q.apy for q in depth), reverse=True))
    depth, pays = cache[p.pos]
    rank = next((i + 1 for i, q in enumerate(depth) if q is p), len(depth) or 1)
    pay_rank = next((i + 1 for i, a in enumerate(pays) if a <= p.apy), len(pays) or 1)
    import personality as PT
    return float(np.clip(MS.entitlement(p.ovr, pos_rank=rank, pay_rank=pay_rank) * PT.entitlement_mult(p), 0.0, 1.0))


# ------------------------------------------------------------ weekly
def weekly(league, week, results, snaps_by_pid, game_lines=None):
    """
    results: {abbr: ('W'|'L'|'T', margin)}. snaps_by_pid: {pid: snaps} for
    men who played this week. game_lines: {pid: dict} with a 'good' or
    'bad' flag when the box score says so.
    """
    for abbr, team in league.teams.items():
        res, margin = results.get(abbr, (None, 0))
        losing = team.win_pct < 0.5 and (team.record[0] + team.record[1]) >= 4
        depth = team.depth                      # built once per club per week
        cache = {pos: (ps, sorted((q.apy for q in ps), reverse=True)) for pos, ps in depth.items()}
        import staff as ST, staff_traits as STR
        disc = {role: (c is not None and STR.has(c, 'disciplinarian')) for role, c in (getattr(team, 'staff', None) or {}).items()}
        for p in team.active():
            m = ensure(p)
            m.tick()
            if res == 'W': m.apply('win')
            elif res == 'L': m.apply('blowout_loss' if margin <= -17 else 'loss')
            if losing: m.apply('losing_season')
            e = entitlement_of(team, p, cache)
            sn = snaps_by_pid.get(p.pid, 0)
            want = STARTER_SNAPS.get(GROUP.get(p.pos, p.pos), 45) * (0.55 + 0.45 * e)
            just_back = p.xp_spent.get('_was_hurt') or (p.xp_spent.get('_cleared_wk') is not None and week - int(p.xp_spent.get('_cleared_wk')) < 1)
            if p.out_until is None and res is not None and not just_back:
                if sn >= want * 0.8: m.apply('well_used', entitle=e)
                elif sn < want * 0.35 and e >= 0.45: m.apply('underused', entitle=e)
            grp = depth.get(p.pos, [])
            rank = next((i for i, q in enumerate(grp) if q is p), 0)
            # A HURT MAN DOES NOT COMPLAIN ABOUT THE DEPTH CHART, and neither does a man who just got healthy:
            # the club gets a week's grace after he clears to move him back before he reads anything into
            # where he sits. Without this a back on the shelf raged about losing his starting spot to the man
            # covering for him, and the moment he was cleared the same week triggered it again.
            hurt = p.out_until is not None
            cleared_wk = p.xp_spent.get('_cleared_wk')
            if not hurt and p.xp_spent.get('_was_hurt'):
                p.xp_spent['_cleared_wk'] = week; p.xp_spent.pop('_was_hurt', None); cleared_wk = week
            if hurt: p.xp_spent['_was_hurt'] = True
            grace = hurt or (cleared_wk is not None and week - int(cleared_wk) < 1) or bool(p.xp_spent.pop('_hurt_desig', None))
            if not grace:
                if rank >= 3 and e >= 0.5: m.apply('buried_on_depth', entitle=e)
                # benched: he lost two or more places on his depth chart since last week
                last = p.xp_spent.get('_depth_rank')
                if last is not None and rank - last >= 2 and e >= 0.5:
                    m.apply('benched', entitle=e)
                p.xp_spent['_depth_rank'] = rank
            else:
                # his place while hurt is not held against the club, and the comparison restarts from where he is when the grace ends
                p.xp_spent['_depth_rank'] = rank
            if game_lines and p.pid in game_lines:
                g = game_lines[p.pid]
                if g.get('good'): m.apply('good_game')
                elif g.get('bad'): m.apply('bad_game')
            # a Disciplinarian's unit: the ambitious men chafe a little each week
            if disc.get('oc' if p.pos in ST.OFFENSE_POS else 'dc') and float((getattr(p, 'traits', None) or {}).get('ambition', 50)) >= 62:
                m.apply('chafes')
        _room_pass(team)


def _room_pass(team):
    import pandas as pd
    rows = [dict(pid=p.pid, grp=GROUP.get(p.pos, p.pos), ovr=p.ovr, years_exp=p.accrued or 0,
                 is_captain=bool(p.xp_spent.get('_captain', False))) for p in team.active()]
    if len(rows) < 2: return
    morales = {p.pid: ensure(p) for p in team.active()}
    MS.locker_room_pass(pd.DataFrame(rows), morales)


# ------------------------------------------------------------ shocks
def shock(league, pid, kind, note=''):
    p = league.player(pid)
    if p is None: return
    team = league.teams.get(p.team)
    e = entitlement_of(team, p) if team else None
    ensure(p).apply(kind, note=note, entitle=e)


def offseason_reset(league):
    for p in league.players.values():
        if getattr(p, 'morale', None) is not None and not wants_out(p):
            p.morale.offseason()
        if isinstance(p.xp_spent, dict):
            p.xp_spent.pop('_request_streak', None)


def postseason(league, post):
    seeds = post.r.seeds() if hasattr(post, 'r') else {}
    in_playoffs = {t for sd in seeds.values() for t in sd}
    for abbr, team in league.teams.items():
        for p in team.active():
            m = ensure(p)
            if abbr in in_playoffs: m.apply('playoff_berth')
            if abbr == getattr(post, 'champion', None): m.apply('won_title')


def offseason_contracts(league, rng):
    """Underpaid men against the market: the slow drag of a cheap deal."""
    import valuation as VAL
    for team in league.teams.values():
        for p in team.active():
            if not p.contract or p.ovr < 76: continue
            v = VAL.value_player(league, p, side='agent', rng=rng)
            if not v: continue
            surplus = v['apy'] - p.apy
            if surplus <= 2.0: continue
            drag = MS.contract_pressure(surplus, v['apy'], on_rookie_deal=(p.draft_round is not None and (league.year - (p.draft_year or league.year)) < 4),
                                        yrs_left=p.contract.years)
            m = ensure(p)
            d = float(drag) if isinstance(drag, (int, float)) else float(drag.get('drag', 0.0))
            m.slow += d; m._contract_drag = d


# ------------------------------------------------------------ effects
def effective_ratings_from(ratings, p):
    """A card (already taxed for a position change, if any) with the morale
    modifiers on the mental and effort attributes."""
    m = getattr(p, 'morale', None)
    if m is None: return ratings
    mods = MS.attribute_modifiers(m.value)
    if wants_out(p) and p.xp_spent['_request'].get('years', 1) <= 1:
        # the doubled penalty runs one season; a professional does not play
        # worse every year forever
        mods = {k: v * UNRESOLVED_PENALTY for k, v in mods.items()} if mods else {k: -1 for k in MS.AFFECTED}
    if not mods: return ratings
    return {k: (v + mods.get(k, 0)) for k, v in ratings.items()}


def effective_ratings(p):
    return effective_ratings_from(p.ratings, p)


def status(p, team=None):
    m = getattr(p, 'morale', None)
    if m is None: return 'settled'
    return MS.status(m, p.ovr, bool(p.xp_spent.get('_captain', False)))


REQUEST_FLOOR = 28.0       # under this at season's end he rolls
UNRESOLVED_DRAG = -0.6     # a week on the slow clock while his club ignores him
UNRESOLVED_PENALTY = 2.0   # his on-field penalty doubles while he waits


def request_reason(p):
    """Why he wants out, from what his season did to him."""
    ev = collections.Counter(k for k, _ in (p.morale.events if p.morale else []))
    role = ev.get('underused', 0) + ev.get('buried_on_depth', 0) + 3 * ev.get('benched', 0)
    lose = ev.get('losing_season', 0)
    contract = 1 if getattr(p.morale, '_contract_drag', 0) < -4 else 0
    if contract and role < 6: return 'contract'
    if role >= 6: return 'role'
    if lose >= 6: return 'losing'
    return 'role'


def clear_free_agents(league):
    """A man who walked took his grievance with him."""
    for pid in list(getattr(league, 'free_agents', [])):
        p = league.player(pid)
        if p is not None and wants_out(p):
            p.xp_spent.pop('_request', None)


def offseason_requests(league, rng):
    """
    THE ROLL, ONCE A YEAR. After the season, every man with real entitlement
    whose morale finished under 28 rolls against how far under he is:
    about 20% at 28, 80% at 10. A fail means he asks out. A man already
    asking does not roll; he asks again. The request travels with its
    reason, which decides what fixes it.
    """
    import inbox as IB
    user = getattr(league, 'user_team', None); out = []
    for abbr, team in league.teams.items():
        cache = {pos: (ps, sorted((q.apy for q in ps), reverse=True)) for pos, ps in team.depth.items()}
        for p in team.active():
            if p.morale is None: continue
            req = p.xp_spent.get('_request')
            if req:
                req['years'] = req.get('years', 1) + 1
                out.append((abbr, p, req['reason'], 'again')); continue
            v = p.morale.value
            if v >= REQUEST_FLOOR: continue
            if entitlement_of(team, p, cache) < 0.55: continue
            import personality as PT
            pr = float(np.clip(0.2 + 0.6 * (REQUEST_FLOOR - v) / (REQUEST_FLOOR - 10.0), 0.2, 0.85)) * PT.request_mult(p)
            if rng.random() < pr:
                reason = request_reason(p)
                p.xp_spent['_request'] = dict(year=league.year, reason=reason, years=1)
                league.log('trade_request', pid=p.pid, team=abbr, morale=round(v), reason=reason)
                out.append((abbr, p, reason, 'new'))
    for abbr, p, reason, how in out:
        if abbr == user:
            why = {'role': 'he wants to start and does not see it here', 'contract': 'he believes he is underpaid',
                   'losing': 'he wants to play for a winner'}[reason]
            IB.post(league, 'trade_request', f"{p.name} {'still ' if how == 'again' else ''}wants out",
                    f"{p.name} ({p.pos}, {p.ovr:.0f}, age {p.age:.0f}) has asked to be traded: {why}. Morale {p.morale.value:.0f}. "
                    f"Trade him, {'make him the starter' if reason == 'role' else 'extend him' if reason == 'contract' else 'win'}, or he plays on unhappy and it shows.",
                    sender=abbr, payload=dict(pid=p.pid, reason=reason, link=f'player:{p.pid}'))
    return out


def wants_out(p):
    return bool(isinstance(p.xp_spent, dict) and p.xp_spent.get('_request'))


def resolve_request(league, pid, how):
    """Cleared by a trade, a starting job or an extension; a fresh start lifts him."""
    p = league.player(pid)
    if p is None or not wants_out(p): return False
    p.xp_spent.pop('_request', None)
    if p.morale is not None:
        p.morale.shock += {'traded': 10.0, 'starter': 8.0, 'extension': 6.0, 'winning': 8.0}.get(how, 6.0)
        p.morale.events.append(('request_resolved', how))
    league.log('trade_request_resolved', pid=pid, team=p.team, how=how)
    return True


def check_resolutions(league, week=None):
    """Week one: the role man who starts is settled; a winning season settles
    the losing man at its end; and a request is withdrawn when it stops being
    true: his morale is back over 40, or he is out of contract and walking."""
    for abbr, team in league.teams.items():
        for p in team.active():
            if not wants_out(p): continue
            if p.morale is not None and p.morale.value >= 40.0:
                resolve_request(league, p.pid, 'settled'); continue
            reason = p.xp_spent['_request']['reason']
            if reason == 'role' and week == 1:
                ps = team.depth.get(p.pos, [])
                if ps and ps[0] is p: resolve_request(league, p.pid, 'starter')
            if reason == 'losing' and week is None and team.win_pct >= 0.5:
                resolve_request(league, p.pid, 'winning')


def unresolved_weekly(league):
    """His club ignored him: the slow clock drags and the baseline does not recover."""
    for team in league.teams.values():
        for p in team.active():
            if wants_out(p) and p.morale is not None:
                p.morale.slow += UNRESOLVED_DRAG
                p.morale.base = float(np.clip(p.morale.base - MS.BASE_RECOVERY * (MS.NEUTRAL - p.morale.base), 10, 90))
