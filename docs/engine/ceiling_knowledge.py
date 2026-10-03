"""What clubs know about a professional player's fixed development ceiling.

Knowledge is saved in the existing XP ledger. Reads are pure; lifecycle hooks
persist confirmations and evidence. No rating, potential, XP or RNG is changed.
"""
import hashlib
import math

KEY = '_ceiling_knowledge'
VERSION = 1


def _initial(player):
    pot = float(player.potential)
    ledger = getattr(player, 'xp_spent', None) or {}
    estimate = getattr(player, 'potential_range', None)
    if estimate:
        unlocks = int(ledger.get('_unlocks', 0))
        lo, hi = (float(v) + unlocks for v in estimate)
    else:
        # Older saves gave some young veterans no range. Give them a stable,
        # asymmetric estimate without drawing a new ceiling or using game RNG.
        seed = hashlib.sha256(str(player.pid).encode()).digest()
        width = 12 + seed[0] % 9
        left = 3 + seed[1] % (width - 5)
        lo, hi = pot - left, pot + width - left
    lo = max(0, math.floor(min(lo, pot)))
    hi = min(99, math.ceil(max(hi, pot)))
    if hi - lo < 2:
        lo = max(0, min(lo, hi - 2))
        hi = min(99, max(hi, lo + 2))
    return dict(version=VERSION, base_range=[lo, hi], base_potential=pot,
                seasons=0, snaps=0, known=False, reason=None)


def _evidence(player, league, state):
    career = getattr(player, 'career', None) or {}
    regular = {int(y): max(0, int(line.get('snaps', 0) or 0))
               for y, line in career.items()}
    postseason = 0
    if league is not None:
        for year, book in (getattr(league, 'stats', None) or {}).items():
            # career and league.stats describe the SAME regular-season snaps.
            regular[int(year)] = max(regular.get(int(year), 0),
                                    int(book.get(player.pid, {}).get('snaps', 0) or 0))
        postseason = sum(max(0, int(book.get(player.pid, {}).get('snaps', 0) or 0))
                         for book in (getattr(league, 'post_stats', None) or {}).values())
    state['snaps'] = max(state['snaps'], sum(regular.values()) + postseason)
    year = getattr(league, 'year', None) if league is not None else getattr(player, 'development_year', None)
    if year is not None:
        closed = max(int(year) - 1, int(getattr(league, 'season_closed_year', None) or (int(year) - 1)))
        entry = (state.get('entry_year') or getattr(player, 'entry_year', None)
                 or getattr(player, 'draft_year', None) or int(year) - int(getattr(player, 'accrued', 0)))
        state['entry_year'] = int(entry)
        state['seasons'] = max(state['seasons'], max(0, closed - int(entry) + 1))


def knowledge(player, league=None):
    """Return a new state, without changing the player or consuming RNG."""
    if getattr(player, 'potential', None) is None:
        return None
    ledger = getattr(player, 'xp_spent', None) or {}
    saved = ledger.get(KEY)
    state = dict(saved) if saved and saved.get('version') == VERSION else _initial(player)
    _evidence(player, league, state)
    if not state['known']:
        import xp as XP
        if float(player.age) >= 28:
            state.update(known=True, reason='age')
        elif XP.at_ceiling(player) or '_ceiling_notice_ack' in ledger:
            state.update(known=True, reason='reached')
    return state


def visible_range(player, league=None):
    """Known ceilings are a single value; estimates retain two points of width."""
    state = knowledge(player, league)
    if state is None:
        return None
    pot = float(player.potential)
    if state['known']:
        return (round(pot), round(pot))
    shift = pot - state['base_potential']
    lo, hi = state['base_range']
    lo = max(0, math.floor(min(pot, lo + shift)))
    hi = min(99, math.ceil(max(pot, hi + shift)))
    # Unlocks near 99 must still leave an uncertain interval until confirmed.
    if hi - lo < 2:
        lo = max(0, hi - 2)
        hi = min(99, max(hi, lo + 2))
    for _ in range(min(100, state['seasons'] + state['snaps'] // 500)):
        if hi - lo <= 2:
            break
        lower = min(lo + 1, math.floor(pot))
        upper = max(hi - 1, math.ceil(pot))
        if upper - lower < 2:
            # Last odd point: tighten the less accurate boundary first.
            if pot - lo >= hi - pot:
                upper = hi
            else:
                lower = lo
        lo, hi = lower, upper
    return (lo, hi)


def sync_player(player, league=None):
    state = knowledge(player, league)
    if state is not None:
        player.xp_spent[KEY] = state


def observed_range(player):
    """Planning uses established professional knowledge, not prospect truth."""
    if KEY in (getattr(player, 'xp_spent', None) or {}):
        return visible_range(player)
    return getattr(player, 'potential_range', None)


def sync(league):
    # College scouting has its own reports. A drafted rookie or signed UDFA
    # joins this system, even if the historical draft pool still lists him.
    prospects = {p.pid for name in ('draft_pool', 'next_class')
                 for p in (getattr(league, name, None) or [])
                 if not p.team and not getattr(p, 'draft_overall', None)}
    for player in league.players.values():
        if player.pid not in prospects:
            sync_player(player, league)


def display(player, league=None):
    state = knowledge(player, league)
    bounds = visible_range(player, league)
    if bounds is None:
        return dict(ceiling=None, room=None, ceiling_estimated=False,
                    ceiling_reason=None, ceiling_range=None)
    import targets as TG
    raw = round(TG.position_score(player.ratings, player.pos))
    lo, hi = bounds
    return dict(ceiling=lo if state['known'] else f'{lo}–{hi}',
                room=max(0, lo - raw) if state['known'] else f'{max(0, lo-raw)}–{max(0, hi-raw)}',
                ceiling_estimated=not state['known'], ceiling_reason=state['reason'],
                ceiling_range=None if state['known'] else [lo, hi])
