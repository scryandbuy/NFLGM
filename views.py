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
INBOX_TAG = {'trade_offer': 'Trade', 'trade': 'Trade', 'extension': 'Contract', 'contract': 'Contract', 'contract_year': 'Contract', 'negotiation': 'Contract', 'waiver': 'Wire', 'waivers': 'Wire', 'wire': 'Wire',
             'squad': 'Squad', 'practice_squad': 'Squad', 'game': 'Game', 'result': 'Game', 'scouting': 'Scouting', 'spring': 'Scouting', 'morale': 'Locker Room', 'trade_request': 'Locker Room',
             'gameplan': 'Assistants', 'game_plan': 'Assistants', 'owner': 'Owner', 'staff': 'Staff', 'offer_sheet': 'Contract', 'match_request': 'Contract', 'injury': 'Squad', 'league': 'League', 'trade_done': 'Trade', 'waiver_notice': 'Wire', 'waiver_digest': 'Wire', 'injury_decision': 'Trainers', 'injury': 'Trainers'}
DECIDE_KINDS = {'trade_offer', 'match_request', 'staff', 'gameplan', 'game_plan', 'offer_sheet', 'contract_year', 'injury_decision'}


STADIUM = {'ARI': 'State Farm Stadium', 'ATL': 'Mercedes-Benz Stadium', 'BAL': 'M&T Bank Stadium', 'BUF': 'Highmark Stadium', 'CAR': 'Bank of America Stadium', 'CHI': 'Soldier Field', 'CIN': 'Paycor Stadium', 'CLE': 'Huntington Bank Field',
           'DAL': 'AT&T Stadium', 'DEN': 'Empower Field', 'DET': 'Ford Field', 'GB': 'Lambeau Field', 'HOU': 'NRG Stadium', 'IND': 'Lucas Oil Stadium', 'JAX': 'EverBank Stadium', 'KC': 'Arrowhead Stadium', 'LV': 'Allegiant Stadium', 'LAC': 'SoFi Stadium',
           'LA': 'SoFi Stadium', 'MIA': 'Hard Rock Stadium', 'MIN': 'U.S. Bank Stadium', 'NE': 'Gillette Stadium', 'NO': 'Caesars Superdome', 'NYG': 'MetLife Stadium', 'NYJ': 'MetLife Stadium', 'PHI': 'Lincoln Financial Field', 'PIT': 'Acrisure Stadium',
           'SF': "Levi's Stadium", 'SEA': 'Lumen Field', 'TB': 'Raymond James Stadium', 'TEN': 'Nissan Stadium', 'WAS': 'Northwest Stadium'}


SUFFIXES = ('Jr.', 'Sr.', 'St.', 'Dr.', 'Mr.', 'II.', 'III.', 'IV.')


def surname(name):
    """The last name, keeping a suffix with it: 'Marvin Mims Jr.' -> 'Mims Jr.'."""
    parts = str(name or '').split()
    if not parts: return ''
    if parts[-1] in ('Jr.', 'Sr.', 'II', 'III', 'IV', 'V') and len(parts) >= 2: return parts[-2] + ' ' + parts[-1]
    return parts[-1]


def sentence(text):
    """Every sentence starts with a capital; the engine writes its fragments in lower case.
    A period inside a suffix (Jr., Sr., St.) does not end a sentence."""
    if not text: return text
    s = str(text); out = []; cap = True
    for i, ch in enumerate(s):
        if cap and ch.isalpha(): out.append(ch.upper()); cap = False
        else: out.append(ch)
        if ch in '!?': cap = True
        elif ch == '.':
            tail = s[max(0, i - 3):i + 1]
            if not any(tail.endswith(sf) for sf in SUFFIXES): cap = True
    return ''.join(out)


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
    if k in ('cutdown', 'wire'): return dict(line='Camp', sub=f"{league.year} · cut to 53")
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
    try:
        import views_frontoffice as VF
        out['owner_name'] = VF._owner(league, t)['name']
    except Exception: out['owner_name'] = None
    out['standings'] = _division_standings(league, abbr)
    out['season'] = _season(league, abbr)
    return out


def _matchup(session, league, abbr):
    if session.stop[0] not in ('week', 'cutdown', 'wire'):
        return None
    wk = session.stop[1] if session.stop[0] == 'week' else 1; opp = session._opponent(wk)
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
        desk = (session.runner.desks.get(team.abbr) if getattr(session, 'runner', None) is not None else None)
        status = getattr(desk, 'status', {}) if desk is not None else {}
        out = []
        for p in sorted(team.roster, key=lambda p: -p.ovr):
            d = status.get(p.pid)
            if d in ('questionable', 'doubtful'): out.append(f"{_short(p.name)} ({p.pos}) {d}")
            elif p.out_until is not None: out.append(f"{_short(p.name)} ({p.pos}) out" + (f" to week {p.out_until}" if isinstance(p.out_until, int) else ''))
        return out[:3]
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
        say = _say_paragraph(league, abbr, opp_abbr, rep)
        if not say:
            say = 'Nothing to report yet. The assistants read tendencies from the games played; the first report with teeth comes after week one.' if wk <= 1 else 'The assistants have no suggestion this week. The plan stays as it is unless you move it.'
        watch = _watch_notes(league, abbr, opp_abbr, rep)
    # the header line: where, and in what
    home_abbr = opp_abbr if away else abbr
    env = None
    try:
        import weather as W
        env = W.draw(home_abbr, wk, np.random.default_rng(league.year * 100 + wk))
    except Exception: pass
    where = STADIUM.get(home_abbr, '')
    weather_line = (env.describe() if env is not None and not env.dome else 'Indoors' if env is not None else '')
    header = ' · '.join(x for x in (weather_line, where) if x)
    import math
    spread = -round(2 * math.log(max(0.02, wp / 100.0) / max(0.02, 1 - wp / 100.0)) * 3.0) / 2
    pf_me, pa_me = _points(league, abbr); pf_them, pa_them = _points(league, opp_abbr)
    gp_me = sum(me.record); gp_them = sum(them.record)
    total = round(((pf_me + pa_me) / gp_me + (pf_them + pa_them) / gp_them) / 2 / 0.5) * 0.5 if gp_me and gp_them else 45.5
    line = f"Spread {abbr} {spread:+.1f} · Total {total:g}" if abs(spread) >= 0.5 else f"Pick'em · Total {total:g}"
    # the two panels: when we have the ball, when they do. Each row is our unit against theirs, by rank.
    panels = None
    if rep is not None:
        U, M = rep['units'] or {}, rep['my_units'] or {}
        T = rep['tendencies'] or {}; MT = rep['my_tendencies'] or {}
        def rk(d, k):
            x = d.get(k); return (x[0] if x else None)
        def pct(d, k): return (round(d[k] * 100) if d and d.get(k) is not None else None)
        # the matchup rows under the ranks: the deep ball against their shell, our WR1 against their CB1, their play action against our safeties, their quarterback under pressure, their best rusher against our tackles
        S = league.stats.get(league.year, {})
        def wr1(tm): return max((p for p in tm.active() if p.pos == 'WR' and p.out_until is None), key=lambda p: p.ovr, default=None)
        def cb1(tm): return max((p for p in tm.active() if p.pos == 'CB' and p.out_until is None), key=lambda p: p.ovr, default=None)
        def rusher(tm): return max((p for p in tm.active() if p.pos in ('LEDG', 'REDG', 'DT') and p.out_until is None), key=lambda p: p.ovr, default=None)
        def sep(p):
            l = S.get(p.pid, {}) if p else {}; return (round(l['sep_total'] / l['sep_n'], 1) if l.get('sep_n') else None)
        def prw(p):
            l = S.get(p.pid, {}) if p else {}; return (round(l['pr_wins'] / l['pr_reps'] * 100) if l.get('pr_reps') else None)
        mw, tc, tw, mc = wr1(me), cb1(them), wr1(them), cb1(me); tr_, mr_ = rusher(them), rusher(me)
        def name(p): return p.name.split()[-1] if p else '—'
        ours_extra = [dict(label='Deep Ball', sub=(f"{abbr} {pct(MT, 'deep')}% of throws" if pct(MT, 'deep') is not None else ''), left=(f"{pct(MT, 'deep')}% deep" if pct(MT, 'deep') is not None else '—'), right=(f"Two-high {pct(T, 'two_high')}%" if pct(T, 'two_high') is not None else '—')),
                      dict(label=f"{name(mw)} vs {name(tc)}", sub=(f"They shadow {pct(T, 'shadow')}%" if pct(T, 'shadow') else 'No shadow yet'), left=(f"{sep(mw)} sep" if sep(mw) is not None else f"{round(mw.ovr) if mw else '—'} WR"), right=(f"{round(tc.ovr)} CB" if tc else '—')),
                      dict(label='Pressure', sub=(f"They blitz {pct(T, 'blitz')}%" if pct(T, 'blitz') is not None else ''), left=(f"{rk(M, 'pass block')}{_ord(rk(M, 'pass block'))} protection" if rk(M, 'pass block') else '—'), right=(f"{rk(U, 'pass rush')}{_ord(rk(U, 'pass rush'))} rush" if rk(U, 'pass rush') else '—'))]
        theirs_extra = [dict(label='Play Action', sub=(f"{them.abbr} {pct(T, 'pa_rate')}% of dropbacks" if pct(T, 'pa_rate') is not None else ''), left=(f"{pct(T, 'pa_rate')}% PA" if pct(T, 'pa_rate') is not None else '—'), right=(f"{rk(M, 'safeties')}{_ord(rk(M, 'safeties'))} safeties" if rk(M, 'safeties') else '—')),
                        dict(label='Under Pressure', sub=name(next((p for p in them.active() if p.pos == 'QB'), None)), left=(f"{rk(U, 'QB')}{_ord(rk(U, 'QB'))} QB" if rk(U, 'QB') else '—'), right=(f"Pressure {pct(MT, 'blitz')}% blitz" if pct(MT, 'blitz') is not None else '—')),
                        dict(label=f"{name(tr_)} vs Your Tackles", sub=(f"{prw(tr_)}% win rate" if prw(tr_) is not None else ''), left=(f"{round(tr_.ovr)} rusher" if tr_ else '—'), right=(f"{rk(M, 'pass block')}{_ord(rk(M, 'pass block'))} protection" if rk(M, 'pass block') else '—'))]
        panels = dict(
            ours=[dict(label='Passing Game', mine=rk(M, 'QB'), theirs=rk(U, 'corners')), dict(label='Running Game', mine=rk(M, 'backs') or rk(M, 'run block'), theirs=rk(U, 'run front')), dict(label='Pass Protection', mine=rk(M, 'pass block'), theirs=rk(U, 'pass rush'))],
            theirs=[dict(label='Passing Game', mine=rk(U, 'QB'), theirs=rk(M, 'corners')), dict(label='Running Game', mine=rk(U, 'backs') or rk(U, 'run block'), theirs=rk(M, 'run front')), dict(label='Pass Protection', mine=rk(U, 'pass block'), theirs=rk(M, 'pass rush'))],
            ours_extra=ours_extra, theirs_extra=theirs_extra,
            suggestions=[dict(i=i, side=('Offense' if s['side'] == 'offence' else 'Defense'), text=sentence(s['text']), why=sentence(s['why']), change=_change_words(s['changes'])) for i, s in enumerate(rep['suggestions'])],
            taken=[i for i, s in enumerate(rep['suggestions']) if s['text'] in ((getattr(league, 'user_week_plan', None) or {}).get('taken', []) if (getattr(league, 'user_week_plan', None) or {}).get('week') == wk else [])])
    # this season's earlier meeting, if any
    series = [dict(week=g[0], home=g[2], away=g[1], hp=g[4], ap=g[3]) for g in league.schedule if g[3] is not None and {g[1], g[2]} == {abbr, opp_abbr}]
    return dict(week=wk, away=away, panels=panels, series=series, header=header, line=line, me=dict(club=club(abbr), record=f"{me.record[0]}–{me.record[1]}", place=_division_place(league, abbr), coach=me.gm.name if me.gm else ''),
                them=dict(club=club(opp_abbr), record=f"{them.record[0]}–{them.record[1]}", place=_division_place(league, opp_abbr), coach=them.gm.name if them.gm else '',
                          prestige=round(getattr(them.gm, 'prestige', 0)) if them.gm else None),
                wp=wp, forecast=(rep or {}).get('forecast', {}).get('text') if rep else None,
                injuries=dict(me=inj(me), them=inj(them)), form=dict(me=form(me), them=form(them)),
                say=sentence(say), watch=watch, has_report=rep is not None)


def _win_prob(league, abbr, opp, away):
    """Pregame, from the two rosters' starter strength and home field. The model
    in the game itself is the drive-by-drive one; this is the number on the tile."""
    def strength(t):
        men = sorted((p.ovr for p in t.active() if p.out_until is None), reverse=True)[:22]
        return float(np.mean(men)) if men else 70.0
    a, b = strength(league.teams[abbr]), strength(league.teams[opp])
    edge = (a - b) * 0.22 + (-0.25 if away else 0.25)
    return int(round(100 / (1 + np.exp(-edge))))


CHANGE_WORDS = {'pass_bias': 'Pass lean', 'play_action_rate': 'Play action', 'motion_rate': 'Motion', 'blitz_rate': 'Blitz', 'man_rate': 'Man coverage', 'shell_lean': 'Two-high', 'zone_aggression': 'Zone aggression', 'box_bias': 'Box', 'screen_boost': 'Screens'}


def _change_words(changes):
    """'Pass lean −5 · Depth toward medium', from a suggestion's plan deltas."""
    out = []
    for k, v in (changes or {}).items():
        if k == 'depth_mix':
            d = list(v); i = max(range(3), key=lambda j: d[j]); out.append('Depth toward ' + ['short', 'medium', 'deep'][i])
        elif k == 'protection': out.append(f"Protection {str(v).replace('_', ' ')}")
        elif k == 'travel': out.append('Shadow their WR1' if v else 'No shadow')
        elif k == 'bracket': out.append('Bracket their WR1')
        elif k == 'box_bias' and isinstance(v, (int, float)): out.append('Box heavier' if v > 0 else 'Box lighter')
        elif isinstance(v, (int, float)) and not isinstance(v, bool): out.append(f"{CHANGE_WORDS.get(k, k)} {'+' if v > 0 else '−'}{abs(round(v * 100))}" + ('%' if k in ('blitz_rate', 'man_rate', 'play_action_rate', 'motion_rate') else ''))
    return ' · '.join(out)


def _say_paragraph(league, abbr, opp_abbr, rep):
    """The assistants in three sentences: what to lean on, what to attack, what to respect."""
    T = rep.get('tendencies') or {}; U = rep.get('units') or {}; them = league.teams[opp_abbr].abbr
    parts = []
    two_high = T.get('two_high'); blitz = T.get('blitz'); pa = T.get('pa_rate')
    if two_high is not None and two_high >= 0.5: parts.append(f"{them} sit in two-high on {round(two_high * 100)}% of their snaps, which leaves light boxes to run into, so we would lean on the run early and work the intermediate middle when they drop")
    elif two_high is not None and two_high <= 0.3: parts.append(f"{them} play single-high on most snaps and load the box, so the outside throws and the play-action shots are where the yards are")
    def rk(k):
        x = U.get(k); return x[0] if x else None
    weak = sorted([(rk(k), k) for k in ('pass block', 'QB', 'run front', 'corners', 'safeties', 'pass rush', 'linebackers') if rk(k) is not None], key=lambda x: -x[0])
    if weak and weak[0][0] >= 22:
        r, k = weak[0]
        words = {'pass block': f"their line ranks {r}{_ord(r)} in pass protection, so we can bring pressure without much risk", 'QB': f"their quarterback ranks {r}{_ord(r)} of 32, so we can load the box and make him beat us",
                 'run front': f"their front ranks {r}{_ord(r)} against the run, so we can run it until they stop it", 'corners': f"their corners rank {r}{_ord(r)}, so the outside receivers should win", 'safeties': f"their safeties rank {r}{_ord(r)}, so the seams and the deep middle are there",
                 'pass rush': f"their rush ranks {r}{_ord(r)}, so the quarterback should have time", 'linebackers': f"their linebackers rank {r}{_ord(r)}, so the tight end and the backs should work underneath"}[k]
        parts.append(words)
    resp = []
    if pa is not None and pa >= 0.25: resp.append(f"their play action at {round(pa * 100)}% of dropbacks, among the highest rates we have seen")
    if blitz is not None and blitz >= 0.28: resp.append(f"a blitz rate of {round(blitz * 100)}%")
    strong = sorted([(rk(k), k) for k in ('pass rush', 'corners', 'QB', 'receivers', 'backs') if rk(k) is not None], key=lambda x: x[0])
    if strong and strong[0][0] <= 5: resp.append(f"their {strong[0][1]}, ranked {strong[0][0]}{_ord(strong[0][0])} in the league")
    if resp: parts.append(('The one thing to respect is ' + resp[0]) if len(resp) == 1 else ('The things to respect are ' + ' and '.join(resp[:2])))
    if not parts: parts.append("Nothing on film sets them apart yet; the plan stays the coordinators' own unless you move it")
    return sentence('. '.join(p.rstrip('.') for p in parts) + '.')


def _ord(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def _watch_notes(league, abbr, opp_abbr, rep):
    """Their two players to watch, each with the reason: the corner who shadows, the rusher's sacks, the receiver's yards."""
    them = league.teams[opp_abbr]; T = rep.get('tendencies') or {}
    S = league.stats.get(league.year, {})
    def stat(p, k): return (S.get(p.pid, {}) or {}).get(k, 0)
    cands = []
    for p in sorted(them.active(), key=lambda p: -p.ovr)[:14]:
        if p.out_until is not None: continue
        note = ''
        if p.pos == 'CB' and p.ovr >= 82: note = f"shadows your WR1 on {round(T.get('shadow', 0) * 100)}% of snaps" if T.get('shadow') else 'their top corner'
        elif p.pos in ('LEDG', 'REDG', 'DT') and p.ovr >= 82: sk = stat(p, 'sacks'); note = f"{sk:g} sack{'s' if sk != 1 else ''} this season" if sk else 'their best rusher'
        elif p.pos in ('WR', 'TE') and p.ovr >= 82: y = int(stat(p, 'rec_yds')); note = f"{y} receiving yards" if y else 'their top target'
        elif p.pos == 'HB' and p.ovr >= 84: y = int(stat(p, 'rush_yds')); note = f"{y} rushing yards" if y else 'their lead back'
        elif p.pos == 'QB' and p.ovr >= 86: note = 'their quarterback'
        if note: cands.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), note=note, no=getattr(p, 'number', None) or ''))
        if len(cands) >= 2: break
    if len(cands) < 2:
        for s in rep.get('stars', []):
            if all(c['pid'] != s['pid'] for c in cands): cands.append(dict(s, note='', no=''))
            if len(cands) >= 2: break
    return cands[:2]


def _desk(league, abbr):
    """Things on your desk: open decisions."""
    cards = []
    for m in getattr(league, 'inbox', []):
        if m.get('status') not in ('unread', 'open'): continue
        if m.get('kind') in DECIDE_KINDS:
            card = dict(id=m['id'], kind=INBOX_TAG.get(m['kind'], m['kind']), raw_kind=m['kind'], subject=m['subject'], body=m['body'][:220], payload=_payload(m.get('payload') or {}), expires=m.get('expires_week'))
            card.update(_desk_detail(league, abbr, m))
            cards.append(card)
    return cards[:4]


def _asset_words(league, a):
    import re
    s = str(a)
    if isinstance(a, dict) and a.get('pick'): return f"{a.get('year')} R{a.get('round')}"
    m = re.match(r"DraftPick\(year=(\d+), round=(\d+)", s)
    if m: return f"{m.group(1)} R{m.group(2)}"
    p = league.player(s); return p.name.split()[-1] if p else s


def _desk_detail(league, abbr, m):
    """What the card shows by kind: a trade offer's two sides and value gap; a contract ask's price and years."""
    pl = m.get('payload') or {}; k = m.get('kind')
    if k == 'trade_offer':
        buyer = pl.get('buyer'); sends = pl.get('sends') or []; gets = pl.get('gets') or []
        gap = None
        try:
            import views_personnel as VP, trades as TR, trade_engine as TE, valuation as VAL
            me, them = league.teams[abbr], league.teams[buyer]; rng = np.random.default_rng(7); pool = VAL.pool_from_league(league)
            a_ids = [str(x) for x in gets]; b_ids = [(f"{x['year']}-{x['round']}-{x.get('original', buyer)}" if isinstance(x, dict) else str(x)) for x in sends]
            r = TE.evaluate(dict(a_sends=VP._assets(league, abbr, a_ids, pool, rng, viewer=them), a_gets=VP._assets(league, buyer, b_ids, pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, TR.persona(me.gm), TR.persona(them.gm))
            gap = round(float(r.get('a_gain', 0.0)), 1)
            if abs(gap) > 100: gap = None       # blocked on the cap: no number to show
        except Exception: gap = None
        return dict(buyer=club(buyer) if buyer in league.teams else None, they_send=' + '.join(_asset_words(league, x) for x in sends), you_send=' + '.join(_asset_words(league, x) for x in gets), gap=gap, read=(m.get('body') or '').split('. ')[0].rstrip('.') + '.')
    if k in ('contract_year', 'negotiation', 'match_request', 'offer_sheet'):
        pid = pl.get('pid'); p = league.player(pid) if pid else None
        if p is None: return {}
        ask = None; years = None
        try:
            import extensions as EXT
            tm = EXT.terms(league, p, np.random.default_rng(abs(hash(pid)) % (2 ** 32)))
            if tm: ask = round(float(tm['ask']), 1); years = int(tm['years'])
        except Exception: pass
        return dict(pid=pid, ask=ask, ask_years=years, years_left=(p.contract.years if p.contract else 0), line=f"{p.pos}, {round(p.ovr)}, age {int(p.age)}, ${p.apy:.1f}m a year." if p.contract else f"{p.pos}, {round(p.ovr)}, age {int(p.age)}.")
    return {}


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
    for m in (sorted(box, key=lambda m: -m['id'])[:limit] if limit else sorted(box, key=lambda m: -m['id'])):
        rows.append(dict(id=m['id'], subject=m['subject'], body=(m.get('body') or '')[:140], tag=INBOX_TAG.get(m.get('kind'), (m.get('kind') or '').title()), decide=(m.get('status') in ('unread', 'open') and m.get('kind') in DECIDE_KINDS),
                         kind=m.get('kind'), unread=m.get('status') == 'unread', week=m.get('week'), year=m.get('year'), sender=m.get('sender'), **{'from': m.get('sender')}, when=(f"Wk {m.get('week')}" if m.get('week') else str(m.get('year') or ''))))
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
        if w in ('Unhappy', 'Unsettled') and len(watch) < 2: watch.append(player_plate(p, note=(w + ' · ' + _why_unhappy(p)).rstrip(' ·')))
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
    import firing_model as FM
    sec = FM.job_security(t.hist())
    exp = float(t.hist().get('expected_pct') or 0.5); pat = float(getattr(t, 'owner_patience', 0.5))
    wants = 'a title run' if exp >= 0.72 else 'a playoff berth' if exp >= 0.56 else 'a winning season' if exp >= 0.5 else 'progress' if exp >= 0.4 else 'patience while you rebuild'
    draft = 'Patient with the draft.' if pat >= 0.6 else 'Wants the draft to pay off now.' if pat <= 0.35 else 'Measured on the draft.'
    return dict(owner_mood=_owner_mood(t), job=('High' if sec >= 0.7 else 'Good' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), expects=f"Wants {wants}. {draft}",
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
    S = league.stats.get(league.year, {}); t = league.teams[abbr]; gp = max(1, sum(t.record))
    pf, pa = _points(league, abbr)
    pids = {p.pid for p in t.roster}
    import advanced_stats as AS
    off_epa = sum((S.get(pid, {}) or {}).get('pass_epa', 0) + (S.get(pid, {}) or {}).get('rush_epa', 0) for pid in pids); off_plays = sum((S.get(pid, {}) or {}).get('pass_plays', 0) + (S.get(pid, {}) or {}).get('rush_plays', 0) for pid in pids)
    pr_w = sum((S.get(pid, {}) or {}).get('pr_wins', 0) for pid in pids); pr_n = sum((S.get(pid, {}) or {}).get('pr_reps', 0) for pid in pids)
    numbers = dict(pf=round(pf / gp, 1) if sum(t.record) else None, pa=round(pa / gp, 1) if sum(t.record) else None, epa=(round(off_epa / off_plays, 2) if off_plays else None), prw=(round(pr_w / pr_n * 100) if pr_n else None))
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
    return dict(games=games, numbers=numbers)


# ============================================================ GAME DAY
def gameday(session, league, abbr, gd=None):
    """This week's game. Before Sunday: the preview (the matchup, the plan, the Sim button). After: the
    scoreboard and the user's game in full. A past week's, when gd is given."""
    r = rail(session, league, abbr)
    if gd is None:
        in_week = session.stop[0] in ('week', 'cutdown', 'wire')
        if in_week and not getattr(session, 'played', False):
            m = _matchup(session, league, abbr)
            wk = session.stop[1] if session.stop[0] == 'week' else 1
            if m is None or m.get('bye'):
                return dict(rail=r, preview=True, week=wk, bye=True, matchup=None, line=f'Week {wk} is your bye. Sim the week to play the rest of the league.')
            plan_ok = bool((getattr(league, 'user_week_plan', None) or {}).get('changes'))
            return dict(rail=r, preview=True, week=wk, bye=False, matchup=m, plan_set=plan_ok, line=None)
        gd = getattr(session, 'gameday', None)
    if not gd:
        return dict(rail=r, empty=True, line='No game has been played yet.')
    scores = []
    for s in gd['scores']:
        scores.append(dict(home=club(s['home']), away=club(s['away']), hs=s['hs'], as_=s['as_'], ot=s['ot'], mine=abbr in (s['home'], s['away'])))
    g = gd.get('game')
    game = None
    if g:
        game = dict(home=club(g['home']), away=club(g['away']), hs=g['hs'], as_=g['as_'], ot=g['ot'], me=g['me'], opp=g['opp'], me_home=g['me_home'],
                    drives=g['drives'], wp=g['wp'], box=g['box'], env=g.get('env', {}), team_stats=g.get('team_stats', {}), reads=g.get('reads', []), quarters=g.get('quarters', {}),
                    home_rec=league.teams[g['home']].record[:2], away_rec=league.teams[g['away']].record[:2])
    return dict(rail=r, empty=False, week=gd['week'], scores=scores, game=game)



def next_year_cap(league, t):
    """Next year's cap as it will actually roll: the league cap plus the space this club has unspent now
    (unused space carries over), and the money committed against it including the dead money already
    assigned to next year. Returns (limit, committed, rollover, dead_next)."""
    from cap_engine import CAP
    base = CAP.get(league.year + 1, CAP.get(league.year, 301.2) * 1.055)
    rollover = max(0.0, float(t.cap_space)) if hasattr(t, 'cap_space') else 0.0
    dead_next = float(getattr(t.cap, 'dead_next', 0.0) or 0.0) if hasattr(t, 'cap') else 0.0
    committed = sum(p.contract.cap_hit(1) for p in t.roster if p.contract and p.contract.years >= 2) + dead_next
    return round(base + rollover, 1), round(committed, 1), round(rollover, 1), round(dead_next, 1)
