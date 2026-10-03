from player_background import home_state
"""
THE SPRING. Between the season and the draft, the clubs learn.

Nothing here changes a prospect. His attributes stay what they are; what
moves is how well each room sees them, and each room learns different
things by where it was and how it weighs what everyone saw.

  combine     ~330 invited by consensus. Every club gets the exact
              measurables, so its physical error on him collapses to zero.
              His medical is public too; rooms weigh it by how much their
              GM fears risk.
  senior bowl ~110 seniors. A club attends by need at the position and by
              its scouting budget; attending rooms get a sharper second read.
  pro days    each club takes ~25 more looks at men at its positions of need.
  visits      the thirty: the AI picks men around its pick range; the user
              names his own (league.user_visits). The sharpest read there is.
  character   a room that looked hard reads his work ethic, with error; a
              low read is a concern on that room's board and no other.

After each event the consensus is recomputed and the men who moved fifteen
or more spots are the spring's stories, kept on league.spring_news.
"""
import numpy as np, collections
import scouting as SC
import draft_plan as DP

COMBINE_INVITES = 330
SENIOR_BOWL = 110
PRO_DAY_LOOKS = 70
VISITS = 30
STOCK_MOVE = 15


def _log(league, kind, *, year=None, **kw):
    league.spring_news = getattr(league, 'spring_news', None) or []
    league.spring_news.append(dict(kind=kind, year=league.year if year is None else year, **kw))


def _pool(league):
    return league.draft_pool or getattr(league, 'next_class', [])


def _stock_moves(league, event, *, year=None):
    """Who moved fifteen or more spots on the consensus board, and which way."""
    moves = []
    for pid, c in (league.consensus or {}).items():
        pr, r = c.get('prev_rank'), c.get('rank')
        if pr and r and abs(pr - r) >= STOCK_MOVE and min(pr, r) <= 150:
            p = league.player(pid)
            if p is not None and p.pos not in ('K', 'P'):      # specialists bounce on the slot curve; nobody writes about it
                moves.append((p, pr, r))
                _log(league, 'stock', year=year, event=event, pid=pid, name=p.name, pos=p.pos, home_state=home_state(p), frm=pr, to=r,
                     text=f"{p.name} ({p.pos}, {home_state(p)}) {'rises' if r < pr else 'falls'} from {pr} to {r} after the {event}")
    return moves


def measurables(p, rng):
    """The forty, the vertical, the bench, exact from his attributes."""
    r = p.ratings
    # the real scale: 99 speed is a 4.30, 90 a 4.48, 80 a 4.68, 70 a 4.88, 60 a 5.08; a 90-speed player had been reading 5.08
    forty = 4.30 + 0.020 * (99 - r.get('speed_rating', 70)) - 0.003 * (r.get('accel_rating', 70) - 70)
    vert = 26 + 0.38 * (r.get('jump_rating', 70) - 60)                       # 86 jump about 36 inches
    bench = 6 + 0.42 * (r.get('strength_rating', 70) - 50)                   # 64 strength about 12 reps, 90 about 23
    shuttle = 4.55 - 0.011 * (r.get('agility_rating', 70) - 60) - 0.004 * (r.get('change_of_direction_rating', 70) - 70)   # 90 agility about 4.15
    return dict(forty=round(float(np.clip(forty + rng.normal(0, 0.02), 4.2, 5.6)), 2), vertical=round(float(np.clip(vert, 22, 46)), 1),
                bench=int(np.clip(bench + rng.normal(0, 1), 3, 45)), shuttle=round(float(np.clip(shuttle, 3.9, 4.9)), 2),
                height=p.height, weight=p.weight)


def combine(league, rng):
    pool = _pool(league); cons = league.consensus or {}
    invited = sorted(pool, key=lambda p: cons.get(p.pid, {}).get('rank', 9999))[:COMBINE_INVITES]
    # a flag is the bottom tenth of the class on durability, whatever the scale
    cut = float(np.percentile([p.ratings.get('injury_rating', 80) for p in invited], 10))
    for p in invited:
        p.combine = measurables(p, rng)
        inj = float(p.ratings.get('injury_rating', 80))
        p.medical = dict(injury=inj, flag=inj <= cut, cut=cut)      # the risk exists; a visit is what uncovers it
        for abbr, team in league.teams.items():
            v = league.scouting[abbr].get(p.pid)
            if v is None: continue
            v['e_phys'] = 0.0                     # every room saw the same forty
            v['cert'] = float(min(SC.CERT_MAX, float(v.get('cert', SC.CERT_START_TOP) or 0.0) + SC.CERT_COMBINE))
            SC._refresh(v, p)
    SC.consensus(league)
    for p in []:
        _log(league, 'medical', pid=p.pid, name=p.name, pos=p.pos, text=f"{p.name} ({p.pos}, {home_state(p)}) has a medical flag out of the combine")
    return len(invited), _stock_moves(league, 'combine')


def _attends(team, p, base, rng, plan):
    need = plan['positions'][p.pos]['need'] > .5
    budget = float(getattr(team.gm, 'scouting', 0.5))
    return rng.random() < base * (1.35 if need else 0.8) * (0.7 + 0.6 * budget)


def senior_bowl(league, rng):
    """Fallback calendar uses the same event as the interactive postseason."""
    before = sum(v.get('reads', 1) for room in league.scouting.values() for v in room.values())
    start = len(getattr(league, 'spring_news', None) or [])
    SC.senior_bowl(league, rng, event_year=league.year)
    after = sum(v.get('reads', 1) for room in league.scouting.values() for v in room.values())
    moves = [(league.player(x['pid']), x['frm'], x['to'])
             for x in league.spring_news[start:] if x.get('kind') == 'stock']
    return int(round((after - before) / 0.7)), moves


def completed(league, year=None):
    """A finished visit stage, including springs completed by older builds."""
    year = league.year if year is None else year
    news = [x for x in (getattr(league, 'spring_news', None) or []) if x.get('year') == year]
    if any(x.get('kind') == 'complete' and x.get('event') == 'spring' for x in news):
        return True
    # Old saves may lack the explicit completion marker. A new staged spring
    # carries pre_visits, so pro-day news cannot prematurely lock its visits.
    return (not any(x.get('kind') == 'stage' and x.get('event') == 'pre_visits' for x in news)
            and any(x.get('event') in ('pro days', 'visits', 'visit') for x in news))


def pre_visits_completed(league, year=None):
    year = league.year if year is None else year
    return completed(league, year) or any(
        x.get('year') == year and x.get('kind') == 'stage' and x.get('event') == 'pre_visits'
        for x in (getattr(league, 'spring_news', None) or []))


def pro_days(league, rng):
    pool = _pool(league); cons = league.consensus or {}
    looks = 0
    import draft as DFT
    level = DFT.league_starter_level(league)
    for abbr, team in league.teams.items():
        sd = SC.error_sd(team.gm, team)
        # a room's scouts are at most of the pro days: every position where the club is thin, and half the rest
        needs = DP.assess(league, abbr, level)['positions']
        R = SC.room(team)
        cands = sorted([p for p in pool if needs[p.pos]['need'] > .5 or rng.random() < 0.5],
                       key=lambda p: (-needs[p.pos]['need'], cons.get(p.pid, {}).get('rank', 9999)))
        if not R['day3_reads']: cands = [p for p in cands if cons.get(p.pid, {}).get('rank', 9999) <= 150]
        for p in cands[:int(PRO_DAY_LOOKS * R['looks_mult'])]:
            SC.second_look(league.scouting[abbr][p.pid], p, sd * 0.75, rng, R=R, team=team); looks += 1     # a controlled workout: a good look
    SC.consensus(league)
    return looks, _stock_moves(league, 'pro days')


def _pick_windows(league, abbr):
    """Every owned selection gets a scouting window, including acquired picks."""
    picks = [pk for pk in league.teams[abbr].picks
             if pk.year == league.year - 1 and not pk.used_on and pk.owner == abbr]
    if not picks:
        # A club without a pick can still investigate a possible trade-in.
        return [(40, 120, 80)]
    slots = sorted(int(pk.selection or ((pk.round - 1) * 32 + 16)) for pk in picks)
    return [(max(1, slot - 12), min(260, slot + 20), slot) for slot in slots]


def _pick_range(league, abbr):
    """Compatibility envelope; selection uses individual windows, not this span."""
    windows = _pick_windows(league, abbr)
    return min(lo for lo, _, _ in windows), max(hi for _, hi, _ in windows)


def _visit_targets(league, abbr, pool, plan):
    cons = league.consensus or {}
    queues = []
    for lo, hi, slot in _pick_windows(league, abbr):
        choices = [p for p in pool if lo <= cons.get(p.pid, {}).get('rank', 9999) <= hi]
        choices.sort(key=lambda p: (-plan['positions'][p.pos]['need'],
                                    abs(cons[p.pid]['rank'] - slot), cons[p.pid]['rank']))
        queues.append(choices)
    chosen, seen = [], set()
    # Distribute finite visits across owned picks, rather than exhausting all
    # thirty on the earliest round. Overlapping windows never duplicate a visit.
    while len(chosen) < VISITS:
        added = False
        for queue in queues:
            while queue and queue[0].pid in seen:
                queue.pop(0)
            if queue and len(chosen) < VISITS:
                p = queue.pop(0); chosen.append(p); seen.add(p.pid); added = True
        if not added:
            break
    return chosen


def fill_user_visits(league, abbr):
    """Let the scout use unassigned visits after the user's selections close."""
    if not abbr or completed(league): return list(getattr(league, 'user_visits', None) or [])
    chosen = list(dict.fromkeys(getattr(league, 'user_visits', None) or []))[:VISITS]
    if len(chosen) >= VISITS: return chosen
    import draft as DFT
    pool = _pool(league)
    plan = DP.assess(league, abbr, DFT.league_starter_level(league))
    suggested = _visit_targets(league, abbr, pool, plan)
    # Pick windows can contain fewer than thirty prospects. Fill the remaining
    # seats from the scout's board instead of wasting visits.
    remaining = sorted(pool, key=lambda p: (-(league.scouting.get(abbr, {}).get(p.pid, {}).get('ovr', 0)),
                                            (league.consensus or {}).get(p.pid, {}).get('rank', 9999)))
    for p in suggested + remaining:
        if p.pid not in chosen:
            chosen.append(p.pid)
            if len(chosen) == VISITS: break
    league.user_visits = chosen
    return chosen


def visits(league, rng):
    """The thirty. The AI picks men around its pick range at its needs; the user names his own."""
    pool = _pool(league); cons = league.consensus or {}
    user = getattr(league, 'user_team', None); looks = 0
    import draft as DFT
    level = DFT.league_starter_level(league)
    for abbr, team in league.teams.items():
        sd = SC.error_sd(team.gm, team)
        if abbr == user:
            chosen = [league.player(pid) for pid in (getattr(league, 'user_visits', None) or [])[:VISITS]]
            chosen = [p for p in chosen if p is not None]
        else:
            chosen = _visit_targets(league, abbr, pool, DP.assess(league, abbr, level))
        for p in chosen:
            v = league.scouting[abbr].get(p.pid)
            if v is None: continue
            # what the room thought before the visit, kept so the change shows
            import character_assessment as CA
            v['pre_visit'] = dict(ovr=float(v.get('ovr', 0) or 0), lo=float(v.get('pot_lo', 0) or 0), hi=float(v.get('pot_hi', 0) or 0), rank=(cons.get(p.pid, {}) or {}).get('rank'), flags=list(v.get('flags', [])), character_flags=CA.flags(v))
            SC.second_look(v, p, sd * 0.55, rng, weight=SC.CERT_VISIT_MULT, R=SC.room(team), team=team); looks += 1
            v['flags'] = list(set(v.get('flags', []) + ['visited']))
            SC._refresh(v, p)                                   # the visit's read, with most of the tape seen through
            _character(league, abbr, team, p, sd * 0.7, rng)
            _medical(league, abbr, team, p, rng)
    SC.consensus(league)
    return looks, _stock_moves(league, 'visits')


def _medical(league, abbr, team, p, rng):
    """A visit uncovers a medical risk: the room's doctors read the injury history and the room marks him down."""
    if p.pos in ('K', 'P', 'LS'): return                     # durability is not a draft question on a specialist
    med = getattr(p, 'medical', None)
    inj = float(p.ratings.get('injury_rating', 80))
    cut = float((med or {}).get('cut', 70.0))
    if inj > cut: return
    v = league.scouting[abbr].get(p.pid)
    if v is None or 'medical' in v.get('flags', []): return
    fear = 1.0 - float(getattr(team.gm, 'risk', 0.5))
    # a flag costs a round or two, not six: at most three grade points on this room's board
    v['adj'] = v.get('adj', 0.0) - min(3.0, (1.0 + 1.5 * fear) * max(0.5, (cut - inj) / 8.0 + 0.5))
    v['flags'] = list(set(v.get('flags', []) + ['medical']))
    SC._refresh(v, p)
    if abbr == getattr(league, 'user_team', None):
        _log(league, 'flag', event='visit', flag='medical', pid=p.pid, name=p.name, pos=p.pos, home_state=home_state(p), text=f"Uncovered a medical flag at the {p.name} visit")


def _character(league, abbr, team, p, sd, rng):
    """Learn risk separately from football ability; repeated visits cannot reroll it."""
    import character_assessment as CA
    v = league.scouting[abbr][p.pid]
    R = SC.room(team)
    CA.film(p, abbr, v, small_school=not SC._power(p))
    changed = CA.visit(p, abbr, v, R, sd)
    if changed and abbr == getattr(league, 'user_team', None):
        for report in CA.report(v):
            if report['status'] == 'concern':
                _log(league, 'flag', event='visit', flag=report['key'], pid=p.pid,
                     name=p.name, pos=p.pos, home_state=home_state(p),
                     text=f"{p.name}: {report['summary']} ({report['confidence'].lower()} confidence)")


def run_pre_visits(league, rng):
    """Run workouts, then leave a decision window before private visits."""
    if pre_visits_completed(league): return dict(already_completed=True)
    # Preserve this class's early Senior Bowl results across the year roll.
    if completed(league):
        return dict(already_completed=True)
    league.spring_news = [x for x in (getattr(league, 'spring_news', None) or [])
                          if x.get('year') == league.year and x.get('event') == 'Senior Bowl']
    if not getattr(league, 'consensus', None): SC.consensus(league)
    n_c, m_c = combine(league, rng)
    # The interactive calendar already staged the Senior Bowl after the
    # conference championships. The one-shot franchise runner reaches it here.
    pool = _pool(league)
    already_held = any(p.xp_spent.get('_senior_bowl') in (league.year, league.year - 1) for p in pool)
    n_s, m_s = (0, []) if already_held else senior_bowl(league, rng)
    n_p, m_p = pro_days(league, rng)
    _log(league, 'stage', event='pre_visits')
    return dict(combine=n_c, senior_bowl_looks=n_s, pro_day_looks=n_p,
                moves=len(m_c) + len(m_s) + len(m_p))


def run_visits(league, rng):
    """Resolve selected visits once the club has seen the workouts."""
    if completed(league): return dict(already_completed=True)
    if not pre_visits_completed(league):
        raise ValueError('Combine and pro days must finish before visits.')
    n_v, m_v = visits(league, rng)
    _log(league, 'complete', event='spring')
    return dict(visit_looks=n_v, moves=len(m_v), news=len(league.spring_news))


def run_spring(league, rng, verbose=False):
    """One-shot path for batch franchise simulations."""
    if completed(league): return dict(already_completed=True)
    pre = run_pre_visits(league, rng)
    visit = run_visits(league, rng)
    out = dict(combine=pre.get('combine', 0), senior_bowl_looks=pre.get('senior_bowl_looks', 0),
               pro_day_looks=pre.get('pro_day_looks', 0), visit_looks=visit.get('visit_looks', 0),
               moves=pre.get('moves', 0) + visit.get('moves', 0), news=len(league.spring_news))
    if verbose: print('  spring:', out)
    return out


def set_user_visits(league, pids):
    from views_draft import spring_year
    if completed(league, spring_year(league)):
        raise ValueError('Spring visits are complete; selections are locked.')
    league.user_visits = list(dict.fromkeys(pids))[:VISITS]
    return league.user_visits
