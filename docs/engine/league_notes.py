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
import inbox as IB

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


def _wins(t): return t.record[0] + 0.5 * (t.record[2] if len(t.record) > 2 else 0)
def _played(t): return sum(t.record[:2]) + (t.record[2] if len(t.record) > 2 else 0)
def _max_wins(t): return _wins(t) + (GAMES - _played(t))


# ------------------------------------------------------------ the standings
def standings(league, week):
    """Clinches and eliminations that are mathematically settled as of this week."""
    if week < 13: return
    user = getattr(league, 'user_team', None)
    teams = list(league.teams.values())
    for conf in sorted({_conf(league, t) for t in teams}):
        ct = [t for t in teams if _conf(league, t) == conf]
        divs = sorted({t.division for t in ct})
        # division: a club has clinched when its wins exceed every rival's ceiling
        for d in divs:
            dt = [t for t in ct if t.division == d]
            for t in dt:
                if all(_wins(t) > _max_wins(o) for o in dt if o is not t) and _once(league, f"div-{league.year}-{t.abbr}"):
                    _post(league, user, t, f"{t.abbr} clinch the {d}", f"{league.teams[t.abbr].abbr} have clinched the {d} at {t.record[0]}–{t.record[1]}.", mine_subject=f"You clinch the {d}")
        # a playoff spot: seven make it. A club is in when at most six others can still pass its win total
        # (a club can pass it only if its ceiling is above the club's wins); out when it cannot reach the seventh-best club's wins
        for t in ct:
            others = [o for o in ct if o is not t]
            can_pass = sum(1 for o in others if _max_wins(o) > _wins(t))
            if can_pass <= 6 and _once(league, f"po-{league.year}-{t.abbr}"):
                _post(league, user, t, f"{t.abbr} clinch a playoff spot", f"{t.abbr} are in the postseason at {t.record[0]}–{t.record[1]}.", mine_subject='You clinch a playoff spot')
            seventh = sorted((_wins(o) for o in others), reverse=True)[6] if len(others) >= 7 else 0
            if _max_wins(t) < seventh and _once(league, f"out-{league.year}-{t.abbr}"):
                _post(league, user, t, f"{t.abbr} eliminated from playoff contention", f"{t.abbr} can no longer reach the postseason at {t.record[0]}–{t.record[1]}.", mine_subject='You are eliminated from playoff contention')
        # the bye: the 1 seed, when its wins exceed every other club's ceiling
        for t in ct:
            if all(_wins(t) > _max_wins(o) for o in ct if o is not t) and _once(league, f"bye-{league.year}-{t.abbr}"):
                _post(league, user, t, f"{t.abbr} clinch the {conf}'s 1 seed and a bye", f"{t.abbr} have locked the {conf}'s top seed and the first-round bye.", mine_subject='You clinch the 1 seed and a bye')
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
    win, lose = (th, ta) if hp > ap else (ta, th)
    line = f"{win.abbr} beat {lose.abbr} {max(hp, ap)}–{min(hp, ap)}"
    if me.division in (th.division, ta.division):
        rival = th if th.division == me.division else ta
        line += f". {rival.abbr} are {rival.record[0]}–{rival.record[1]} in your division; you are {me.record[0]}–{me.record[1]}"
    IB.news(league, f"Week {week} around the league: {win.abbr} over {lose.abbr}", line + '.', payload=dict(link='league:schedule'))


# ------------------------------------------------------------ the log
def transactions(league, week):
    """Since the last roll: star extensions and signings elsewhere, tags, coaching changes."""
    user = getattr(league, 'user_team', None)
    led = _ledger(league); start = int(led.get('_tx_idx', 0) or 0)
    new = league.transactions[start:]
    led['_tx_idx'] = len(league.transactions)
    for x in new:
        k = x.get('kind'); team = x.get('team')
        if team == user: continue
        if k in ('extension', 'sign'):
            p = league.player(x.get('pid'))
            if p is not None and p.ovr >= 85 and x.get('apy'):
                verb = 'extend' if k == 'extension' else 'sign'
                IB.news(league, f"{team} {verb} {p.name}", f"{team} {verb} {p.name} ({p.pos}, {round(p.ovr)}) for {x.get('years')} years at ${float(x['apy']):.1f}m a year.", payload=dict(link=f'player:{p.pid}'))
        elif k == 'franchise_tag':
            p = league.player(x.get('pid'))
            if p is not None: IB.news(league, f"{team} tag {p.name}", f"{team} place the franchise tag on {p.name} ({p.pos}, {round(p.ovr)})" + (f" at ${float(x['price']):.1f}m" if x.get('price') else '') + '.', payload=dict(link=f'player:{p.pid}'))
        elif k == 'gm_change':
            IB.news(league, f"{team} hire {x.get('hired')}", f"{team} have a new head coach and general manager: {x.get('hired')}" + (f", {x.get('background')}" if x.get('background') else '') + '.', payload=dict(link='league:coaching'))
        elif k == 'staff_in' and x.get('why') and 'head' in str(x.get('why')).lower():
            IB.news(league, f"{team} hire {x.get('name')}", f"{team} hire {x.get('name')}: {x.get('why')}.", payload=dict(link='league:coaching'))


# ------------------------------------------------------------ the season's end
def season_end(league, votes):
    """Awards and All-Pro, the Hall of Fame class, retirements of players 85 or better."""
    year = league.year
    if votes and _once(league, f"awards-{year}"):
        def nm(v):
            if v is None: return None
            if hasattr(v, 'pid'): return f"{v.name} ({v.pos}, {v.team})"
            p = league.player(v) if isinstance(v, str) and v in league.players else None
            return f"{p.name} ({p.pos}, {p.team})" if p else str(v)
        parts = [f"{label}: {nm(votes.get(k))}" for k, label in (('mvp', 'MVP'), ('opoy', 'Offensive Player of the Year'), ('dpoy', 'Defensive Player of the Year'), ('oroy', 'Offensive Rookie of the Year'), ('droy', 'Defensive Rookie of the Year'), ('protector', 'Protector of the Year'), ('coty', 'Coach of the Year')) if votes.get(k)]
        IB.news(league, f"{year} awards", '. '.join(parts) + '.', payload=dict(link='league:awards'))
        first = votes.get('all_pro_1') or []
        if first:
            names = ', '.join(f"{p.name} ({p.pos})" for p in first if hasattr(p, 'name'))
            IB.news(league, f"{year} All-Pro first team", names + '.', payload=dict(link='league:awards'))
        mine = [p for p in first if hasattr(p, 'team') and p.team == getattr(league, 'user_team', None)]
        if mine: IB.post(league, 'result', f"{len(mine)} of yours named All-Pro", ', '.join(f"{p.name} ({p.pos})" for p in mine) + ' made the first team.', sender='league', payload=dict(link='league:awards'))
    hof = [x for x in league.transactions if x.get('kind') == 'hall_of_fame' and x.get('year') == year]
    if hof and _once(league, f"hof-{year}"):
        IB.news(league, f"Hall of Fame class of {year}", ', '.join(f"{x.get('name')} ({x.get('pos')})" for x in hof) + ' inducted.', payload=dict(link='league:almanac'))
    ret = [x for x in league.transactions if x.get('kind') == 'retire' and x.get('year') == year and league.player(x.get('pid')) is not None and league.player(x['pid']).ovr >= 85]
    if ret and _once(league, f"retire-{year}"):
        IB.news(league, f"{len(ret)} star{'s' if len(ret) > 1 else ''} retire", ', '.join(f"{x.get('name')} ({x.get('pos')}, {round(league.player(x['pid']).ovr)})" for x in ret) + (' hang it up.' if len(ret) > 1 else ' hangs it up.'), payload=dict(link='league:almanac'))
