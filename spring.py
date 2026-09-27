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

COMBINE_INVITES = 330
SENIOR_BOWL = 110
PRO_DAY_LOOKS = 25
VISITS = 30
STOCK_MOVE = 15


def _log(league, kind, **kw):
    league.spring_news = getattr(league, 'spring_news', None) or []
    league.spring_news.append(dict(kind=kind, year=league.year, **kw))


def _pool(league):
    return league.draft_pool or getattr(league, 'next_class', [])


def _stock_moves(league, event):
    """Who moved fifteen or more spots on the consensus board, and which way."""
    moves = []
    for pid, c in (league.consensus or {}).items():
        pr, r = c.get('prev_rank'), c.get('rank')
        if pr and r and abs(pr - r) >= STOCK_MOVE and min(pr, r) <= 150:
            p = league.player(pid)
            if p is not None and p.pos not in ('K', 'P'):      # specialists bounce on the slot curve; nobody writes about it
                moves.append((p, pr, r))
                _log(league, 'stock', event=event, pid=pid, name=p.name, pos=p.pos, college=p.college, frm=pr, to=r,
                     text=f"{p.name} ({p.pos}, {p.college}) {'rises' if r < pr else 'falls'} from {pr} to {r} after the {event}")
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
            SC._refresh(v, p)
    SC.consensus(league)
    for p in []:
        _log(league, 'medical', pid=p.pid, name=p.name, pos=p.pos, text=f"{p.name} ({p.pos}, {p.college}) has a medical flag out of the combine")
    return len(invited), _stock_moves(league, 'combine')


def _attends(team, p, base, rng):
    need = len([q for q in team.depth.get(p.pos, []) if q.out_until is None]) < 2
    budget = float(getattr(team.gm, 'scouting', 0.5))
    return rng.random() < base * (1.35 if need else 0.8) * (0.7 + 0.6 * budget)


def senior_bowl(league, rng):
    pool = _pool(league); cons = league.consensus or {}
    seniors = [p for p in pool if p.age >= 22.0]
    invited = sorted(seniors, key=lambda p: cons.get(p.pid, {}).get('rank', 9999))[:SENIOR_BOWL]
    looks = 0
    for abbr, team in league.teams.items():
        sd = SC.error_sd(team.gm, team)
        for p in invited:
            if _attends(team, p, 0.55, rng):
                SC.second_look(league.scouting[abbr][p.pid], p, sd * 0.8, rng, R=SC.room(team)); looks += 1
                _character(league, abbr, team, p, sd, rng)
    SC.consensus(league)
    return looks, _stock_moves(league, 'Senior Bowl')


def pro_days(league, rng):
    pool = _pool(league); cons = league.consensus or {}
    looks = 0
    for abbr, team in league.teams.items():
        sd = SC.error_sd(team.gm, team)
        needs = [pos for pos, ps in team.depth.items() if len([q for q in ps if q.out_until is None]) < 2]
        R = SC.room(team)
        cands = sorted([p for p in pool if p.pos in needs or rng.random() < 0.15], key=lambda p: cons.get(p.pid, {}).get('rank', 9999))
        if not R['day3_reads']: cands = [p for p in cands if cons.get(p.pid, {}).get('rank', 9999) <= 96]
        for p in cands[:int(PRO_DAY_LOOKS * R['looks_mult'])]:
            SC.second_look(league.scouting[abbr][p.pid], p, sd * 0.9, rng, R=R); looks += 1
    SC.consensus(league)
    return looks, _stock_moves(league, 'pro days')


def _pick_range(league, abbr):
    picks = [pk for pk in league.teams[abbr].picks if pk.year == league.year - 1 and not pk.used_on]
    if not picks: return (40, 120)
    order = getattr(league, 'draft_order', None)
    rounds = sorted(pk.round for pk in picks)
    lo = (rounds[0] - 1) * 32 + 1
    return (max(1, lo - 20), min(260, lo + 60))


def visits(league, rng):
    """The thirty. The AI picks men around its pick range at its needs; the user names his own."""
    pool = _pool(league); cons = league.consensus or {}
    user = getattr(league, 'user_team', None); looks = 0
    for abbr, team in league.teams.items():
        sd = SC.error_sd(team.gm, team)
        if abbr == user:
            chosen = [league.player(pid) for pid in (getattr(league, 'user_visits', None) or [])[:VISITS]]
            chosen = [p for p in chosen if p is not None]
        else:
            lo, hi = _pick_range(league, abbr)
            needs = [pos for pos, ps in team.depth.items() if len([q for q in ps if q.out_until is None]) < 2]
            ranked = [p for p in pool if lo <= cons.get(p.pid, {}).get('rank', 9999) <= hi]
            ranked.sort(key=lambda p: (0 if p.pos in needs else 1, cons.get(p.pid, {}).get('rank', 9999)))
            chosen = ranked[:VISITS]
        for p in chosen:
            v = league.scouting[abbr].get(p.pid)
            if v is None: continue
            # what the room thought before the visit, kept so the change shows
            v['pre_visit'] = dict(ovr=float(v.get('ovr', 0) or 0), lo=float(v.get('pot_lo', 0) or 0), hi=float(v.get('pot_hi', 0) or 0), rank=(cons.get(p.pid, {}) or {}).get('rank'), flags=list(v.get('flags', [])))
            SC.second_look(v, p, sd * 0.55, rng, weight=1.5, R=SC.room(team)); looks += 1
            v['flags'] = list(set(v.get('flags', []) + ['visited']))
            _character(league, abbr, team, p, sd * 0.7, rng)
            _medical(league, abbr, team, p, rng)
    SC.consensus(league)
    return looks, _stock_moves(league, 'visits')


def _medical(league, abbr, team, p, rng):
    """A visit uncovers a medical risk: the room's doctors read the injury history and the room marks him down."""
    med = getattr(p, 'medical', None)
    inj = float(p.ratings.get('injury_rating', 80))
    cut = float((med or {}).get('cut', 70.0))
    if inj > cut: return
    v = league.scouting[abbr].get(p.pid)
    if v is None or 'medical' in v.get('flags', []): return
    fear = 1.0 - float(getattr(team.gm, 'aggression', 0.5))
    v['adj'] = v.get('adj', 0.0) - (1.0 + 3.0 * fear) * max(0.5, (cut - inj) / 8.0 + 0.5)
    v['flags'] = list(set(v.get('flags', []) + ['medical']))
    SC._refresh(v, p)
    if abbr == getattr(league, 'user_team', None):
        _log(league, 'flag', event='visit', flag='medical', pid=p.pid, name=p.name, pos=p.pos, college=p.college, text=f"Uncovered a medical flag at the {p.name} visit")


def _character(league, abbr, team, p, sd, rng):
    """A room that looked hard reads his work ethic, with error; a low read is a concern on its board."""
    import personality as PT
    v = league.scouting[abbr][p.pid]
    if 'character_read' in v: return
    R = SC.room(team)
    if R['character'] == 'none': return                    # Trusts the Tape: the visit sharpens the ratings and stops there
    read = PT.scout_read(p, (sd / 4.0) * (0.35 if R['character'] == 'sharp' else 1.0), rng)['work_ethic']
    v['character_read'] = round(read)
    if read < 35:
        v['adj'] = v.get('adj', 0.0) - 2.0
        v['flags'] = list(set(v.get('flags', []) + ['character']))
        if abbr == getattr(league, 'user_team', None):
            _log(league, 'flag', event='visit', flag='character', pid=p.pid, name=p.name, pos=p.pos, college=p.college, text=f"Uncovered a character flag at the {p.name} visit")
        SC._refresh(v, p)


def run_spring(league, rng, verbose=False):
    """The whole spring in order. The UI will step it; the calendar runs it whole."""
    league.spring_news = []
    if not getattr(league, 'consensus', None): SC.consensus(league)
    n_c, m_c = combine(league, rng)
    n_s, m_s = senior_bowl(league, rng)
    n_p, m_p = pro_days(league, rng)
    n_v, m_v = visits(league, rng)
    out = dict(combine=n_c, senior_bowl_looks=n_s, pro_day_looks=n_p, visit_looks=n_v,
               moves=len(m_c) + len(m_s) + len(m_p) + len(m_v), news=len(league.spring_news))
    if verbose: print('  spring:', out)
    return out


def set_user_visits(league, pids):
    league.user_visits = list(pids)[:VISITS]
    return league.user_visits
