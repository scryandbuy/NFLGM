"""
VIEWS. One function per page, returning a plain dict the browser renders.
Nothing here changes the league. The mockups' sample numbers are replaced
by these.
"""
import numpy as np

CLUB_COLOR = {'ARI': '#97233f', 'ATL': '#a71930', 'BAL': '#241773', 'BUF': '#00338d', 'CAR': '#0085ca', 'CHI': '#0b162a', 'CIN': '#fb4f14', 'CLE': '#311d00',
              'DAL': '#003594', 'DEN': '#fb4f14', 'DET': '#0076b6', 'GB': '#203731', 'HOU': '#03202f', 'IND': '#002c5f', 'JAX': '#006778', 'KC': '#c8102e',
              'LV': '#000000', 'LAC': '#0080c6', 'LA': '#003594', 'MIA': '#008e97', 'MIN': '#4f2683', 'NE': '#002244', 'NO': '#d3bc8d', 'NYG': '#0b2265',
              'NYJ': '#125740', 'PHI': '#004c54', 'PIT': '#ffb612', 'SF': '#aa0000', 'SEA': '#002244', 'TB': '#d50a0a', 'TEN': '#0c2340', 'WAS': '#5a1414'}
CLUB_ACCENT = {'KC': '#ffb612', 'PIT': '#101820', 'NO': '#101820', 'LV': '#a5acaf'}
CLUB_NAME = {'ARI': 'Arizona', 'ATL': 'Atlanta', 'BAL': 'Baltimore', 'BUF': 'Buffalo', 'CAR': 'Carolina', 'CHI': 'Chicago', 'CIN': 'Cincinnati', 'CLE': 'Cleveland',
             'DAL': 'Dallas', 'DEN': 'Denver', 'DET': 'Detroit', 'GB': 'Green Bay', 'HOU': 'Houston', 'IND': 'Indianapolis', 'JAX': 'Jacksonville', 'KC': 'Kansas City',
             'LV': 'Las Vegas', 'LAC': 'LA Chargers', 'LA': 'LA Rams', 'MIA': 'Miami', 'MIN': 'Minnesota', 'NE': 'New England', 'NO': 'New Orleans', 'NYG': 'NY Giants',
             'NYJ': 'NY Jets', 'PHI': 'Philadelphia', 'PIT': 'Pittsburgh', 'SF': 'San Francisco', 'SEA': 'Seattle', 'TB': 'Tampa Bay', 'TEN': 'Tennessee', 'WAS': 'Washington'}
NICK = {'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills', 'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns', 'DAL': 'Cowboys',
        'DEN': 'Broncos', 'DET': 'Lions', 'GB': 'Packers', 'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs', 'LV': 'Raiders', 'LAC': 'Chargers', 'LA': 'Rams',
        'MIA': 'Dolphins', 'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants', 'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SF': '49ers', 'SEA': 'Seahawks',
        'TB': 'Buccaneers', 'TEN': 'Titans', 'WAS': 'Commanders'}
INBOX_TAG = {'trade_offer': 'Trade', 'trade': 'Trade', 'extension': 'Contract', 'contract': 'Contract', 'negotiation': 'Contract', 'waiver': 'Wire', 'waivers': 'Wire', 'wire': 'Wire',
             'squad': 'Squad', 'practice_squad': 'Squad', 'game': 'Game', 'result': 'Game', 'scouting': 'Scouting', 'spring': 'Scouting', 'morale': 'Locker Room', 'trade_request': 'Locker Room',
             'gameplan': 'Assistants', 'game_plan': 'Assistants', 'owner': 'Owner', 'staff': 'Staff', 'offer_sheet': 'Contract', 'match_request': 'Contract', 'injury': 'Squad'}
DECIDE_KINDS = {'trade_offer', 'match_request', 'staff', 'gameplan', 'game_plan', 'offer_sheet'}


def club(abbr):
    return dict(abbr=abbr, name=CLUB_NAME.get(abbr, abbr), nick=NICK.get(abbr, abbr).upper(), color=CLUB_COLOR.get(abbr, '#555'), accent=CLUB_ACCENT.get(abbr, '#ffb612'))


def money(x):
    return f"${x:.1f}m"


def morale_word(p):
    m = getattr(p, 'morale', None)
    if m is None: return 'Content'
    v = m.value
    return 'Happy' if v >= 65 else 'Content' if v >= 40 else 'Unsettled' if v >= 25 else 'Unhappy'


def player_plate(p, note=''):
    return dict(pid=p.pid, no=getattr(p, 'number', None) or '', name=p.name, short=_short(p.name), pos=p.pos, ovr=round(p.ovr), note=note,
                morale=morale_word(p), out=p.out_until is not None)


def _short(name):
    parts = name.split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else name


# ------------------------------------------------------------ the rail
def rail(session, league, abbr):
    t = league.teams[abbr]
    w, l, d = t.record
    div = _division_place(league, abbr)
    nxt = session.next_label(); blocking = session.blocking()
    return dict(club=club(abbr), coach=t.gm.name if t.gm else '', year=league.year, week=league.week,
                phase=league.phase, record=f"{w}–{l}" + (f"–{d}" if d else ''), place=div, cap=money(t.cap_space), prestige=round(getattr(t.gm, 'prestige', 0)) if t.gm else None,
                advance=nxt, blocking=blocking, inbox_unread=sum(1 for m in getattr(league, 'inbox', []) if m.get('status') == 'unread'),
                clock=_clock(league, session))


def _clock(league, session):
    k = session.stop[0]
    if k == 'week': return dict(line=f"Week {session.stop[1]}", sub=f"{league.year}")
    if k == 'playoffs': return dict(line='Playoffs', sub=f"{league.year}")
    return dict(line='Offseason', sub=f"{league.year}")


def _division_place(league, abbr):
    t = league.teams[abbr]
    div = [x for x in league.teams.values() if x.division == t.division]
    div.sort(key=lambda x: (-(x.record[0] + 0.5 * x.record[2]), x.record[1]))
    i = next(i for i, x in enumerate(div) if x.abbr == abbr) + 1
    return f"{i}{'st' if i == 1 else 'nd' if i == 2 else 'rd' if i == 3 else 'th'} {t.division}"


# ------------------------------------------------------------ the Portal
def portal(session, league, abbr):
    t = league.teams[abbr]
    out = dict(rail=rail(session, league, abbr))
    out['matchup'] = _matchup(session, league, abbr)
    out['desk'] = _desk(league, abbr)
    out['inbox'] = _inbox(league)
    out['cap'] = _cap(league, t)
    out['room'] = _room(league, t)
    out['front_office'] = _front_office(league, t)
    out['standings'] = _division_standings(league, abbr)
    out['season'] = _season(league, abbr)
    return out


def _matchup(session, league, abbr):
    if session.stop[0] != 'week':
        return None
    wk = session.stop[1]; opp = session._opponent(wk)
    if opp is None:
        return dict(bye=True, week=wk)
    opp_abbr, away = opp
    me, them = league.teams[abbr], league.teams[opp_abbr]
    rep = None
    try:
        import gameplan_week as GW
        rep = GW.opponent_report(league, abbr, opp_abbr, wk)
    except Exception:
        rep = None
    wp = _win_prob(league, abbr, opp_abbr, away)
    def inj(team):
        return [f"{_short(p.name)} ({p.pos}) out" + (f" to week {p.out_until}" if isinstance(p.out_until, int) else '') for p in team.roster if p.out_until is not None][:3]
    def form(team):
        res = [g for g in league.schedule if g[0] < wk and team.abbr in (g[1], g[2]) and g[3] is not None]
        out = []
        for (w_, a, h, ap, hp) in res[-5:]:
            mine = ap if a == team.abbr else hp; theirs = hp if a == team.abbr else ap
            out.append('w' if mine > theirs else 'l' if mine < theirs else 't')
        return out
    say = ''
    watch = []
    if rep:
        # the assistants speak in sentences: each suggestion's reason is one
        say = ' '.join((s.get('why') or s.get('text') or '').rstrip('.') + '.' for s in rep.get('suggestions', [])[:3]).strip()
        if not say:
            say = 'Nothing to report yet. The assistants read tendencies from the games played; the first report with teeth comes after week one.' if wk <= 1 else 'The assistants have no suggestion this week. The plan stays as it is unless you move it.'
        watch = rep.get('stars', [])[:2]
    # the two panels: when we have the ball, when they do. Each row is our unit against theirs, by rank.
    panels = None
    if rep is not None:
        U, M = rep['units'] or {}, rep['my_units'] or {}
        T = rep['tendencies'] or {}; MT = rep['my_tendencies'] or {}
        def rk(d, k):
            x = d.get(k); return (x[0] if x else None)
        def pct(d, k): return (round(d[k] * 100) if d and d.get(k) is not None else None)
        panels = dict(
            ours=[dict(label='Passing Game', mine=rk(M, 'QB'), theirs=rk(U, 'corners')), dict(label='Receivers vs Coverage', mine=rk(M, 'receivers'), theirs=rk(U, 'safeties')),
                  dict(label='Running Game', mine=rk(M, 'backs') or rk(M, 'run block'), theirs=rk(U, 'run front')), dict(label='Pass Protection', mine=rk(M, 'pass block'), theirs=rk(U, 'pass rush')),
                  dict(label='Tight End', mine=rk(M, 'tight end'), theirs=rk(U, 'linebackers'))],
            theirs=[dict(label='Passing Game', mine=rk(U, 'QB'), theirs=rk(M, 'corners')), dict(label='Receivers vs Coverage', mine=rk(U, 'receivers'), theirs=rk(M, 'safeties')),
                    dict(label='Running Game', mine=rk(U, 'backs') or rk(U, 'run block'), theirs=rk(M, 'run front')), dict(label='Pass Protection', mine=rk(U, 'pass block'), theirs=rk(M, 'pass rush')),
                    dict(label='Tight End', mine=rk(U, 'tight end'), theirs=rk(M, 'linebackers'))],
            our_tend=[dict(label='They blitz', v=pct(T, 'blitz'), unit='% of snaps'), dict(label='They play two-high', v=pct(T, 'two_high'), unit='% of snaps'), dict(label='They play man', v=pct(T, 'man'), unit='% of pass snaps'), dict(label='Eight in the box', v=pct(T, 'box8'), unit='% of snaps')],
            their_tend=[dict(label='They throw', v=pct(T, 'pass_rate'), unit='% of plays'), dict(label='Play action', v=pct(T, 'pa_rate'), unit='% of dropbacks'), dict(label='Deep shots', v=pct(T, 'deep'), unit='% of throws'), dict(label='Go on fourth', v=pct(T, 'fourth_go'), unit='% of chances')],
            suggestions=[dict(i=i, side=('Offense' if s['side'] == 'offence' else 'Defense'), text=s['text'], why=s['why']) for i, s in enumerate(rep['suggestions'])],
            taken=[i for i, s in enumerate(rep['suggestions']) if s['text'] in ((getattr(league, 'user_week_plan', None) or {}).get('taken', []) if (getattr(league, 'user_week_plan', None) or {}).get('week') == wk else [])])
    # this season's earlier meeting, if any
    series = [dict(week=g[0], home=g[2], away=g[1], hp=g[4], ap=g[3]) for g in league.schedule if g[3] is not None and {g[1], g[2]} == {abbr, opp_abbr}]
    return dict(week=wk, away=away, panels=panels, series=series, me=dict(club=club(abbr), record=f"{me.record[0]}–{me.record[1]}", place=_division_place(league, abbr), coach=me.gm.name if me.gm else ''),
                them=dict(club=club(opp_abbr), record=f"{them.record[0]}–{them.record[1]}", place=_division_place(league, opp_abbr), coach=them.gm.name if them.gm else '',
                          prestige=round(getattr(them.gm, 'prestige', 0)) if them.gm else None),
                wp=wp, forecast=(rep or {}).get('forecast', {}).get('text') if rep else None,
                injuries=dict(me=inj(me), them=inj(them)), form=dict(me=form(me), them=form(them)),
                say=say, watch=watch, has_report=rep is not None)


def _win_prob(league, abbr, opp, away):
    """Pregame, from the two rosters' starter strength and home field. The model
    in the game itself is the drive-by-drive one; this is the number on the tile."""
    def strength(t):
        men = sorted((p.ovr for p in t.active() if p.out_until is None), reverse=True)[:22]
        return float(np.mean(men)) if men else 70.0
    a, b = strength(league.teams[abbr]), strength(league.teams[opp])
    edge = (a - b) * 0.22 + (-0.25 if away else 0.25)
    return int(round(100 / (1 + np.exp(-edge))))


def _desk(league, abbr):
    """Things on your desk: open decisions."""
    cards = []
    for m in getattr(league, 'inbox', []):
        if m.get('status') not in ('unread', 'open'): continue
        if m.get('kind') in DECIDE_KINDS:
            cards.append(dict(id=m['id'], kind=INBOX_TAG.get(m['kind'], m['kind']), subject=m['subject'], body=m['body'][:220], payload=_payload(m.get('payload') or {})))
    return cards[:4]


def _payload(pl):
    out = {}
    for k, v in pl.items():
        if isinstance(v, (str, int, float, bool)) or v is None: out[k] = v
        elif isinstance(v, (list, tuple)): out[k] = [x if isinstance(x, (str, int, float, bool)) else str(x) for x in v][:12]
        elif isinstance(v, dict): out[k] = {kk: (vv if isinstance(vv, (str, int, float, bool)) else str(vv)) for kk, vv in v.items()}
        elif hasattr(v, 'name'): out[k] = v.name
        else: out[k] = str(v)
    return out


def _inbox(league, limit=14):
    box = getattr(league, 'inbox', []) or []
    rows = []
    for m in sorted(box, key=lambda m: -m['id'])[:limit]:
        rows.append(dict(id=m['id'], subject=m['subject'], body=(m.get('body') or '')[:140], tag=INBOX_TAG.get(m.get('kind'), (m.get('kind') or '').title()), decide=(m.get('status') in ('unread', 'open') and m.get('kind') in DECIDE_KINDS),
                         kind=m.get('kind'), unread=m.get('status') == 'unread', week=m.get('week'), year=m.get('year'), sender=m.get('sender')))
    return dict(rows=rows, total=len(box), unread=sum(1 for m in box if m.get('status') == 'unread'), decide=sum(1 for m in box if m.get('status') in ('unread', 'open') and m.get('kind') in DECIDE_KINDS))


def _cap(league, t):
    from cap_engine import CAP
    yr = league.year
    groups = {'QB': ['QB'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT'], 'WR': ['WR'], 'DL': ['LEDG', 'REDG', 'DT'], 'DB': ['CB', 'FS', 'SS'], 'LB': ['MIKE', 'WILL', 'SAM'], 'TE': ['TE'], 'RB': ['HB', 'FB'], 'ST': ['K', 'P']}
    by = {g: 0.0 for g in groups}
    for p in t.roster:
        if p.contract is None: continue
        hit = p.contract.cap_hit(0)
        for g, poss in groups.items():
            if p.pos in poss: by[g] += hit; break
    cap = CAP.get(yr, 301.2)
    committed = sum(v for v in by.values())
    dead = float(getattr(t, 'dead_money', {}).get(yr, 0.0)) if isinstance(getattr(t, 'dead_money', None), dict) else float(getattr(t, 'dead_now', 0.0) or 0.0)
    years = []
    for i in range(3):
        c = CAP.get(yr + i, cap * 1.07 ** i)
        com = sum(p.contract.cap_hit(i) for p in t.roster if p.contract and p.contract.years > i)
        years.append(dict(year=yr + i, cap=round(c, 1), committed=round(com, 1)))
    return dict(space=money(t.cap_space), cap=round(cap, 1), by_group={g: round(v, 1) for g, v in by.items()}, dead=round(dead, 1), years=years)


def _room(league, t):
    words = {'Happy': 0, 'Content': 0, 'Unsettled': 0, 'Unhappy': 0}
    watch = []
    for p in t.active():
        w = morale_word(p); words[w] += 1
        if w == 'Unhappy': watch.append(player_plate(p, note=_why_unhappy(p)))
    mean = float(np.mean([p.morale.value for p in t.active() if p.morale is not None])) if any(p.morale for p in t.active()) else 50.0
    return dict(counts=words, mean=round(mean), watch=watch[:3])


def _why_unhappy(p):
    m = p.morale
    if m is None: return ''
    if getattr(m, 'request', None): return f"Asked out · {m.request.get('reason', '')}"
    return 'Unhappy'


def _front_office(league, t):
    import staff as ST
    gm = t.gm
    sec = float(getattr(gm, 'job_security', 0.7)) if gm else 0.7
    return dict(owner_mood=_owner_mood(t), job=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'),
                prestige=round(getattr(gm, 'prestige', 0)) if gm else None, staff_budget=money(ST.budget(t)) if getattr(t, 'staff', None) else None,
                scouting_rank=_scout_rank(league, t))


def _owner_mood(t):
    w, l, _ = t.record
    if w + l == 0: return 'Settled'
    pct = w / (w + l)
    return 'Pleased' if pct >= 0.65 else 'Settled' if pct >= 0.45 else 'Restless' if pct >= 0.3 else 'Angry'


def _scout_rank(league, t):
    import scouting as SC
    errs = sorted(SC.error_sd(x.gm, x) for x in league.teams.values())
    mine = SC.error_sd(t.gm, t)
    return errs.index(mine) + 1


def _division_standings(league, abbr):
    t = league.teams[abbr]
    rows = []
    for x in sorted((x for x in league.teams.values() if x.division == t.division), key=lambda x: (-(x.record[0] + 0.5 * x.record[2]), x.record[1])):
        pf, pa = _points(league, x.abbr)
        rows.append(dict(club=club(x.abbr), w=x.record[0], l=x.record[1], t=x.record[2], pf=pf, pa=pa, pd=pf - pa, me=x.abbr == abbr, form=_form(league, x.abbr)))
    return dict(division=t.division, rows=rows)


def _points(league, abbr):
    pf = pa = 0
    for (wk, a, h, ap, hp) in league.schedule:
        if ap is None: continue
        if a == abbr: pf += ap; pa += hp
        elif h == abbr: pf += hp; pa += ap
    return pf, pa


def _form(league, abbr):
    out = []
    for (wk, a, h, ap, hp) in league.schedule:
        if ap is None or abbr not in (a, h): continue
        mine = ap if a == abbr else hp; theirs = hp if a == abbr else ap
        out.append('w' if mine > theirs else 'l' if mine < theirs else 't')
    return out[-5:]


def _season(league, abbr):
    games = []
    for (wk, a, h, ap, hp) in sorted(league.schedule, key=lambda g: g[0]):
        if abbr not in (a, h): continue
        home = h == abbr; opp = a if home else h
        res = None
        if ap is not None:
            mine = hp if home else ap; theirs = ap if home else hp
            res = 'W' if mine > theirs else 'L' if mine < theirs else 'T'
        games.append(dict(week=wk, opp=opp, home=home, result=res, score=(f"{hp}–{ap}" if home else f"{ap}–{hp}") if ap is not None else None))
    weeks = {g['week'] for g in games}
    for wk in range(1, 19):
        if wk not in weeks: games.append(dict(week=wk, bye=True))
    games.sort(key=lambda g: g['week'])
    return dict(games=games)


# ============================================================ GAME DAY
def gameday(session, league, abbr):
    """The last week's games: the scoreboard, and the user's game in full."""
    gd = getattr(session, 'gameday', None)
    r = rail(session, league, abbr)
    if not gd:
        return dict(rail=r, empty=True, line='No game has been played yet. Advance to play the week.')
    scores = []
    for s in gd['scores']:
        scores.append(dict(home=club(s['home']), away=club(s['away']), hs=s['hs'], as_=s['as_'], ot=s['ot'], mine=abbr in (s['home'], s['away'])))
    g = gd.get('game')
    game = None
    if g:
        game = dict(home=club(g['home']), away=club(g['away']), hs=g['hs'], as_=g['as_'], ot=g['ot'], me=g['me'], opp=g['opp'], me_home=g['me_home'],
                    drives=g['drives'], wp=g['wp'], box=g['box'], env=g.get('env', {}), team_stats=g.get('team_stats', {}), reads=g.get('reads', []),
                    home_rec=league.teams[g['home']].record[:2], away_rec=league.teams[g['away']].record[:2])
    return dict(rail=r, empty=False, week=gd['week'], scores=scores, game=game)

