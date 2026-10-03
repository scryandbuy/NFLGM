"""
league_notes.py - what the league tells every GM.

Weekly, from the standings: clinches (a playoff spot, the division, the 1 seed's bye) and
eliminations from the point they are mathematically possible, and the week's biggest result
with what it did to your division. From the transaction log since the last roll: a star's
extension or signing elsewhere (85 or better), a franchise tag, a coaching change. At the
season's end: the awards, the All-Pro teams, the Hall of Fame class, and the retirements of
players 85 or better.

Clinch math is conservative: strict inequalities on wins, so a note is never wrong and a
club that is in only on a tiebreaker is announced a week later than the league would.
"""
from inbox import player_name as inbox_player
import inbox as IB
import inbox_events as IE

GAMES = 17
CONF_OF = None


def _ledger(league):
    if getattr(league, 'league_notes_sent', None) is None: league.league_notes_sent = {}
    return league.league_notes_sent


def _once(league, key):
    led = _ledger(league)
    if key in led: return False
    led[key] = league.week; return True


def _conf(league, t):
    return (t.division or '').split(' ')[0]


def _sb_numeral(league):
    try:
        import postseason as PS; return PS.sb_venue(league)['numeral']
    except Exception: return ''


def _wins(t): return t.record[0] + 0.5 * (t.record[2] if len(t.record) > 2 else 0)
def _played(t): return sum(t.record[:2]) + (t.record[2] if len(t.record) > 2 else 0)
def _max_wins(t): return _wins(t) + (GAMES - _played(t))


# ------------------------------------------------------------ the standings
def clinch_status(league, week):
    """Read-only clinch flags shared by standings tables and league notices."""
    teams = list(league.teams.values())
    statuses = {}
    # Before the last game, use pessimistic bounds: ties can still beat us.
    # At completion use exactly the same seeding/tiebreakers as the bracket.
    final = None
    schedule = getattr(league, 'schedule', []) or []
    games = [(h, a, hp, ap) for wk, a, h, ap, hp in schedule
             if wk <= 18 and hp is not None and ap is not None]
    if week >= 18 and teams and all(_played(t) >= GAMES for t in teams):
        import standings_and_seeding as SS
        state = SS.Season.live({t.abbr: t.division for t in teams},
                              {t.abbr: _conf(league, t) for t in teams}, games, league.year)
        if all(sum(state.rec[t.abbr]) == _played(t) for t in teams):
            final = {c: SS.seed_conference(state, c) for c in {_conf(league, t) for t in teams}}
            div_rank = SS.division_ranks(state)
    for conf in sorted({_conf(league, t) for t in teams}):
        ct = [t for t in teams if _conf(league, t) == conf]
        divs = sorted({t.division for t in ct})
        for t in ct:
            others = [o for o in ct if o is not t]
            rivals = [o for o in others if o.division == t.division]
            div_in = bool(rivals) and all(_wins(t) > _max_wins(o) for o in rivals)
            div_out = any(_wins(o) > _max_wins(t) for o in rivals)
            # One division winner per division comes out of the wildcard race.
            possible_ahead = sum(max(0, sum(_max_wins(o) >= _wins(t)
                                 for o in others if o.division == d) - 1) for d in divs)
            certain_ahead = sum(max(0, sum(_wins(o) > _max_wins(t)
                                for o in others if o.division == d) - 1) for d in divs)
            in_field = div_in or possible_ahead < 3
            out_field = div_out and certain_ahead >= 3
            bye = div_in and all(_wins(t) > _max_wins(o) for o in others)
            if final is not None:
                seeds = final[conf]
                div_in = div_rank[t.abbr] == 1
                in_field = t.abbr in seeds
                out_field = not in_field
                bye = bool(seeds) and seeds[0] == t.abbr
            statuses[t.abbr] = dict(division=div_in, playoffs=in_field,
                                    eliminated=out_field and not in_field, bye=bye)
    return statuses


def standings(league, week):
    """Clinches and eliminations that are mathematically settled as of this week."""
    if week < 13: return
    user = getattr(league, 'user_team', None)
    teams = list(league.teams.values())
    statuses = clinch_status(league, week)
    for conf in sorted({_conf(league, t) for t in teams}):
        for t in (t for t in teams if _conf(league, t) == conf):
            flags = statuses[t.abbr]
            div_in, in_field, out_field, bye = (flags[k] for k in
                                               ('division', 'playoffs', 'eliminated', 'bye'))
            notices = []
            for flag, prefix, wording in (
                (div_in, 'div', f'clinch the {t.division}'),
                (in_field, 'po', 'clinch a playoff spot'),
                (out_field and not in_field, 'out', 'are eliminated from playoff contention'),
                (bye, 'bye', f"clinch the {conf}'s 1 seed and a bye")):
                if flag and _once(league, f'{prefix}-{league.year}-{t.abbr}'):
                    notices.append(wording)
            if notices:
                subject = (notices[-1] if bye else notices[0])
                body = f"{t.abbr}: " + '; '.join(notices) + f". Record: {t.record[0]}–{t.record[1]}."
                _post(league, user, t, f'{t.abbr} {subject}', body,
                      mine_subject=f'You {subject}')
    # the picture, one week out, for the user if nothing is settled
    if week == GAMES and user:
        me = league.teams[user]
        led = _ledger(league)
        if f"po-{league.year}-{user}" not in led and f"out-{league.year}-{user}" not in led and _once(league, f"picture-{league.year}"):
            ct = [t for t in teams if _conf(league, t) == _conf(league, me)]
            near = sorted([t for t in ct if t is not me and abs(_wins(t) - _wins(me)) <= 1.0 and f"po-{league.year}-{t.abbr}" not in led and f"out-{league.year}-{t.abbr}" not in led], key=lambda t: -_wins(t))
            rivals = ', '.join(t.abbr for t in near[:4]) or 'nobody in particular'
            IB.news(league, 'The playoff picture, one week out', f"At {me.record[0]}–{me.record[1]} you are alive with one to play. The last spots come down to you and {rivals}. Win and you are in the conversation; a loss and you need help.", payload=dict(link='league:standings'))


def _post(league, user, t, subject, body, mine_subject=None):
    if t.abbr == user:
        IB.post(league, 'result', mine_subject or subject, body.replace(f"{t.abbr} have", 'You have').replace(f"{t.abbr} are", 'You are').replace(f"{t.abbr} can", 'You can'), sender='league', payload=dict(link='league:standings'))
    else:
        IB.news(league, subject, body, payload=dict(link='league:standings'))


# ------------------------------------------------------------ the week's big result
def big_result(league, week, results):
    """The week's biggest game elsewhere, and what it did to your division."""
    user = getattr(league, 'user_team', None)
    if not user or not results: return
    me = league.teams[user]
    best = None
    for g in results:
        h, a, hp, ap = g[0], g[1], g[2], g[3]                   # (home, away, home points, away points)
        if user in (h, a) or h not in league.teams or a not in league.teams: continue
        th, ta = league.teams[h], league.teams[a]
        stake = _wins(th) + _wins(ta)                         # two good clubs
        div_hit = 1.5 if me.division in (th.division, ta.division) else 0.0
        close = abs(hp - ap) <= 3
        score = stake + div_hit + (1.0 if close else 0.0)
        if best is None or score > best[0]: best = (score, (hp, ap), th, ta)
    if best is None or not _once(league, f"big-{league.year}-{week}"): return
    _, (hp, ap), th, ta = best
    if hp == ap:
        IB.news(league, f'Week {week} around the league: {th.abbr} and {ta.abbr} tie',
                f'{th.abbr} and {ta.abbr} tied {hp}–{ap}.', payload=dict(link='league:schedule'))
        return
    win, lose = (th, ta) if hp > ap else (ta, th)
    line = f"{win.abbr} beat {lose.abbr} {max(hp, ap)}–{min(hp, ap)}"
    if int(week) >= 19:
        # THE PLAYOFFS. Records mean nothing now: the winner moves on, the loser is done
        NEXT = {19: 'the Divisional Round', 20: 'the Conference Finals', 21: f'Championship Game {_sb_numeral(league)}', 22: None}
        nxt = NEXT.get(int(week))
        line += f". {win.abbr} {'are champions' if nxt is None else 'advance to ' + nxt}"
    elif me.division in (th.division, ta.division):
        rival = th if th.division == me.division else ta
        line += f". {rival.abbr} are {rival.record[0]}–{rival.record[1]} in your division; you are {me.record[0]}–{me.record[1]}"
    ROUND_ = {19: 'Wild Card Weekend', 20: 'Divisional Round', 21: 'Conference Finals', 22: 'Championship Game'}
    when = ROUND_.get(int(week), f"Week {week}")
    IB.news(league, f"{when} around the league: {win.abbr} over {lose.abbr}", line + '.', payload=dict(link='league:bracket' if int(week) >= 19 else 'league:schedule'))


# ------------------------------------------------------------ the log
def transactions(league, week, skip_signings=False):
    """Since the last roll: star extensions and signings elsewhere, tags, coaching changes. During a free-agency
    round the round's own note carries the signings (skip_signings), so the inbox is not one message a deal."""
    user = getattr(league, 'user_team', None)
    led = _ledger(league); start = int(led.get('_tx_idx', 0) or 0)
    new = league.transactions[start:]
    led['_tx_idx'] = len(league.transactions)
    for x in new:
        k = x.get('kind'); team = x.get('team')
        if team == user: continue
        if k in ('extension', 'sign'):
            if skip_signings and k == 'sign': continue
            p = league.player(x.get('pid'))
            if p is not None and p.ovr >= 85 and x.get('apy') and p.pos not in ('K', 'P', 'LS'):      # a punter is not a star signing
                verb = 'extend' if k == 'extension' else 'sign'
                IB.news(league, f"{team} {verb} {inbox_player(p)}", f"{team} {verb} {inbox_player(p)} ({p.pos}, {round(p.ovr)}) for {x.get('years')} years at ${float(x['apy']):.1f}m a year.", payload=dict(link=f'player:{p.pid}'))
        elif k == 'franchise_tag':
            p = league.player(x.get('pid'))
            if p is not None: IB.news(league, f"{team} tag {inbox_player(p)}", f"{team} place the franchise tag on {inbox_player(p)} ({p.pos}, {round(p.ovr)})" + (f" at ${float(x['price']):.1f}m" if x.get('price') else '') + '.', payload=dict(link=f'player:{p.pid}'))
        elif k == 'gm_change':
            IE.post(league, f"coach-hire-{x.get('year', league.year)}-{team}-{x.get('hired')}", 'league', f"{team} hire {x.get('hired')}", f"{team} have a new head coach and general manager: {x.get('hired')}" + (f", {x.get('background')}" if x.get('background') else '') + '.', payload=dict(link='league:coaching'))
        elif k == 'staff_in' and x.get('why') and 'head' in str(x.get('why')).lower():
            IB.news(league, f"{team} hire {x.get('name')}", f"{team} hire {x.get('name')}: {x.get('why')}.", payload=dict(link='league:coaching'))


def coaching_summary(league):
    """One offseason digest, after the carousel has resolved its pending hires.

    Use the same action labels as Transactions so promotions and expiring deals
    are not reported as firings. Keep each move in its own explicit inbox row.
    """
    from copy import copy
    from views_league import _coaching_moves
    from staff import ROLE_NAME
    from views import CLUB_NAME
    key = f'coaching-carousel-summary-{league.year}'
    if IE.seen(league, key): return None
    context = copy(league)
    context.transactions = [x for x in league.transactions
                            if x.get('year') == league.year
                            and x.get('phase', 'offseason') == 'offseason']
    groups = {'Hired': [], 'Fired / released / replaced': [], 'Other departures': []}
    seen = set()
    for move in _coaching_moves(context, recent=False):
        action = move['action']
        if action in ('Extended', 'Search Open', 'Poached'): continue
        identity = (move['club']['abbr'], move['role'], move['person'], action)
        if identity in seen: continue
        seen.add(identity)
        group = ('Hired' if action == 'Hired' else 'Fired / released / replaced'
                 if action in ('Fired', 'Released', 'Replaced') else 'Other departures')
        groups[group].append(move)
    rows = ['The coaching carousel has run. Moves recorded this offseason:']
    for heading, moves in groups.items():
        rows.append(f'{heading} ({len(moves)})')
        if not moves: rows.append('None')
        for move in sorted(moves, key=lambda m: (m['club']['name'], m['role'], m['person'])):
            role = 'Head Scout' if move['role'] == 'SCOUT' else move['role']
            rows.append(f"{move['club']['name']} — {role} — {move['person']} — {move['action']}"
                        + (f" ({move['detail']})" if move['detail'] else ''))
    vacancies = []
    for abbr, team in sorted(league.teams.items()):
        if getattr(team, 'gm', None) is None:
            vacancies.append(f"{CLUB_NAME.get(abbr, abbr)} — Head Coach")
        for role, coach in (getattr(team, 'staff', {}) or {}).items():
            if coach is None:
                vacancies.append(f"{CLUB_NAME.get(abbr, abbr)} — {ROLE_NAME.get(role, role.upper())}")
    if vacancies:
        rows += [f'Jobs still open ({len(vacancies)})', *vacancies]
    return IE.post(league, key, 'league', f'Coaching carousel summary · {league.year} offseason',
                   '\n'.join(rows), sender='league',
                   payload=dict(link='league:transactions', body_rows=rows))


# ------------------------------------------------------------ the season's end
def season_end(league, votes):
    """Awards and All-Pro, the Hall of Fame class, retirements of players 85 or better."""
    year = league.year
    if votes and _once(league, f"awards-{year}"):
        def nm(v):
            if v is None: return None
            if hasattr(v, 'pid'): return f"{inbox_player(v)} ({v.pos}, {v.team})"
            p = league.player(v) if isinstance(v, str) and v in league.players else None
            return f"{inbox_player(p)} ({p.pos}, {p.team})" if p else str(v)
        rows = [[label, nm(votes.get(k))] for k, label in (('mvp', 'MVP'), ('opoy', 'Offensive Player of the Year'), ('dpoy', 'Defensive Player of the Year'), ('oroy', 'Offensive Rookie of the Year'), ('droy', 'Defensive Rookie of the Year'), ('protector', 'Protector of the Year'), ('coty', 'Coach of the Year'), ('sb_mvp', 'Championship Game MVP')) if votes.get(k)]
        IB.news(league, f"{year} awards", 'The season’s award winners.', payload=dict(link='league:awards', mail_sections=[IB.mail_section('Awards', rows, ['Award', 'Recipient'])]))
        sections = []
        for key, label in (('all_pro_1', 'First team'), ('all_pro_2', 'Second team')):
            players = votes.get(key) or []
            rows = [[inbox_player(p), p.pos, p.team, 'your team' if p.team == getattr(league, 'user_team', None) else ''] for p in players if hasattr(p, 'name')]
            if rows: sections.append(IB.mail_section(label, rows, ['Player', 'Position', 'Team', '']))
        if sections:
            IB.news(league, f'{year} All-Pro teams', 'First- and second-team selections.', payload=dict(link='league:awards', mail_sections=sections))
    hof = [x for x in league.transactions if x.get('kind') == 'hall_of_fame' and x.get('year') == year]
    if hof and _once(league, f"hof-{year}"):
        rows = [[inbox_player(league.player(x.get('pid')), x.get('name')), x.get('pos', '')] for x in hof]
        IB.news(league, f"Hall of Fame class of {year}", 'This year’s inductees.', payload=dict(link='league:almanac', mail_sections=[IB.mail_section('Hall of Fame', rows, ['Player', 'Position'])]))
    ret = [x for x in league.transactions if x.get('kind') == 'retire' and x.get('year') == year and league.player(x.get('pid')) is not None and league.player(x['pid']).ovr >= 85]
    if ret and _once(league, f"retire-{year}"):
        rows = [[inbox_player(league.player(x['pid']), x.get('name')), x.get('pos', ''), str(round(league.player(x['pid']).ovr))] for x in ret]
        IB.news(league, f"{len(ret)} star{'s' if len(ret) > 1 else ''} retire", 'These players are calling it a career.', payload=dict(link='league:almanac', mail_sections=[IB.mail_section('Retirements', rows, ['Player', 'Position', 'OVR'])]))
