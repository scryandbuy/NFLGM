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


def entitlement_of(team, p):
    depth = team.depth.get(p.pos, [])
    rank = next((i + 1 for i, q in enumerate(depth) if q is p), len(depth) or 1)
    pays = sorted((q.apy for q in team.active() if q.pos == p.pos), reverse=True)
    pay_rank = next((i + 1 for i, a in enumerate(pays) if a <= p.apy), len(pays) or 1)
    return MS.entitlement(p.ovr, pos_rank=rank, pay_rank=pay_rank)


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
        depth = team.depth
        for p in team.active():
            m = ensure(p)
            m.tick()
            if res == 'W': m.apply('win')
            elif res == 'L': m.apply('blowout_loss' if margin <= -17 else 'loss')
            if losing: m.apply('losing_season')
            e = entitlement_of(team, p)
            sn = snaps_by_pid.get(p.pid, 0)
            want = STARTER_SNAPS.get(GROUP.get(p.pos, p.pos), 45) * (0.55 + 0.45 * e)
            if p.out_until is None and res is not None:
                if sn >= want * 0.8: m.apply('well_used', entitle=e)
                elif sn < want * 0.35 and e >= 0.45: m.apply('underused', entitle=e)
            grp = depth.get(p.pos, [])
            rank = next((i for i, q in enumerate(grp) if q is p), 0)
            if rank >= 3 and e >= 0.5: m.apply('buried_on_depth', entitle=e)
            # benched: he lost two or more places on his depth chart since last week
            last = p.xp_spent.get('_depth_rank')
            if last is not None and rank - last >= 2 and e >= 0.5:
                m.apply('benched', entitle=e)
            p.xp_spent['_depth_rank'] = rank
            if game_lines and p.pid in game_lines:
                g = game_lines[p.pid]
                if g.get('good'): m.apply('good_game')
                elif g.get('bad'): m.apply('bad_game')
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
            m.slow += float(drag) if isinstance(drag, (int, float)) else float(drag.get('drag', 0.0))


# ------------------------------------------------------------ effects
def effective_ratings_from(ratings, p):
    """A card (already taxed for a position change, if any) with the morale
    modifiers on the mental and effort attributes."""
    m = getattr(p, 'morale', None)
    if m is None: return ratings
    mods = MS.attribute_modifiers(m.value)
    if not mods: return ratings
    return {k: (v + mods.get(k, 0)) for k, v in ratings.items()}


def effective_ratings(p):
    return effective_ratings_from(p.ratings, p)


def status(p, team=None):
    m = getattr(p, 'morale', None)
    if m is None: return 'settled'
    return MS.status(m, p.ovr, bool(p.xp_spent.get('_captain', False)))


def trade_requests(league):
    """Men who want out. AI clubs put them on the block; the user hears from the agent."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    out = []
    for abbr, team in league.teams.items():
        for p in team.active():
            if status(p, team) == 'trade request' and not p.xp_spent.get('_asked_out'):
                p.xp_spent['_asked_out'] = league.year
                out.append((abbr, p))
                league.log('trade_request', pid=p.pid, team=abbr, morale=round(p.morale.value))
                if abbr == user:
                    IB.post(league, 'trade_request', f'{p.name} has asked for a trade',
                            f"{p.name} ({p.pos}, {p.ovr:.0f}) is {status(p, team)}. His agent says he wants out. "
                            f"Morale {p.morale.value:.0f}.", sender=abbr, payload=dict(pid=p.pid, link=f'player:{p.pid}'))
    return out
