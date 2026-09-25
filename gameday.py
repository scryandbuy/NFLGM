"""
GAME DAY. After a week is played, the session keeps a compact record of every
game (scores) and a full record of the user's game (drives, plays written as
a ticker, the drive chart, the win-probability line, the box score). The
browser replays it play by play; the engine has already decided everything.

  capture(league, played, user)   -> dict, small enough to save
  write_play(league, p, drive)    -> one line of ticker in the house style:
                                     down, spot and clock; who got the ball,
                                     who made the play; gains as "N yards",
                                     losses as "a loss of N yards"
"""
import numpy as np


def _name(league, pid, short=True):
    p = league.player(pid) if pid else None
    if p is None: return 'the ball carrier'
    if not short: return p.name
    parts = p.name.split()
    return parts[-1] if len(parts) > 1 else p.name


def _spot(yardline, off_abbr, def_abbr):
    """yardline is distance to the goal (100 = own goal line)."""
    y = int(round(yardline))
    if y == 50: return '50'
    return f"{off_abbr} {100 - y}" if y > 50 else f"{def_abbr} {y}"


def _clock(sec):
    sec = max(0, int(round(sec)))
    q_sec = sec - 900 * ((sec - 1) // 900) if sec > 0 else 0        # 3600 reads 15:00, not 0:00
    return f"{q_sec // 60}:{q_sec % 60:02d}"


def _yards(y):
    y = int(round(y))
    if y > 0: return f"{y} yard{'s' if y != 1 else ''}"
    if y == 0: return 'no gain'
    return f"a loss of {abs(y)} yard{'s' if abs(y) != 1 else ''}"


def write_play(league, p, qb_pid, off_abbr, def_abbr, rb_pid=None):
    """One play as a line about the people. ticker.play_line does the writing; the
    drive's quarterback and back fill in when the play did not name them."""
    import ticker as TK
    q = dict(p)
    if not q.get('passer') and q.get('type') in ('complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble'): q['passer'] = qb_pid
    if not q.get('carrier') and q.get('type') == 'run': q['carrier'] = rb_pid
    ln = TK.play_line(league, q, off_abbr, def_abbr)
    if ln is None:
        return dict(head='', text='', kind='neutral', type=q.get('type'))
    # the structured bones, so the page can keep a live box score as plays are revealed
    def nm(pid):
        pp = league.player(pid) if pid else None
        if pp is None: return None
        parts = pp.name.split(); return parts[-2] + ' ' + parts[-1] if parts[-1] in ('Jr.', 'Sr.', 'II', 'III', 'IV') and len(parts) > 1 else parts[-1]
    ln.update(off=off_abbr, yards=(round(float(q.get('yards', 0) or 0)) if q.get('yards') is not None else 0), passer=nm(q.get('passer')), target=nm(q.get('target')), carrier=nm(q.get('carrier')),
              td=bool(q.get('touchdown') or q.get('td')), clock=q.get('clock'), down=q.get('down'), togo=q.get('ydstogo'), made=q.get('made'), safety=bool(q.get('safety')), fumble=bool(q.get('fumble')), fumble_lost=bool(q.get('fumble_lost')))
    return ln


def _wp(score_diff, sec_left, pos_is_home):
    """A simple in-game win probability for the drawing: score and time, home side."""
    # spread the margin by time remaining: a 7-point lead with a minute left is near certain, at kickoff it is ~70%
    t = max(0.0, min(1.0, sec_left / 3600.0))
    z = score_diff / (3.0 + 11.0 * np.sqrt(t))
    return float(1.0 / (1.0 + np.exp(-z)))


def capture(league, played, user):
    """played: list of (home, away, res, book) from the week. Returns the Game Day record."""
    out = dict(week=league.week, scores=[], game=None)
    for home, away, res, book in played:
        out['scores'].append(dict(home=home, away=away, hs=res['home'], as_=res['away'], ot=bool(res.get('overtime'))))
        if user not in (home, away):
            continue
        me_home = (user == home); opp = away if me_home else home
        drives, wp, plays_all = [], [], []
        hs = as_ = 0
        for i, (pos, dr) in enumerate(res['drives']):
            off_abbr = home if pos == 'home' else away; def_abbr = away if pos == 'home' else home
            qb = (dr.off or {}).get('qb', {}).get('pid'); rb = ((dr.off or {}).get('rb') or {}).get('pid')
            plays = []
            for p in dr.log:
                if not isinstance(p, dict): continue
                plays.append(write_play(league, p, qb, off_abbr, def_abbr, rb_pid=rb))
            pts = int(getattr(dr, 'points', 0) or 0)
            if pos == 'home': hs += pts
            else: as_ += pts
            start = float(getattr(dr, 'start', 75)); end = float(getattr(dr, 'yardline', start))
            drives.append(dict(n=i + 1, off=off_abbr, start=round(100 - start, 1), end=round(100 - end, 1), plays_n=int(getattr(dr, 'plays', len(plays))), yards=round(start - end, 1), first_downs=int(getattr(dr, 'first_downs', 0) or 0),
                               result=getattr(dr, 'result', ''), points=pts, quarter=int(getattr(dr, 'quarter', 1) or 1), clock=_clock(getattr(dr, 'clock', 0)),
                               score=f"{hs}–{as_}", plays=plays))
            diff = (hs - as_) if me_home else (as_ - hs)
            wp.append(round(100 * _wp(diff, float(getattr(dr, 'clock', 0) or 0), me_home)))
        # longest plays and the team totals, from the drive log
        longest = {}; T = {home: dict(plays=0, yards=0, pass_yds=0, rush_yds=0, first_downs=0, third_att=0, third_conv=0, fourth_att=0, fourth_conv=0, turnovers=0, sacks_allowed=0, penalties=0, pen_yds=0, top=0.0, red_zone=0, red_zone_td=0), away: None}
        T[away] = dict(T[home])
        for pos, dr in res['drives']:
            off = home if pos == 'home' else away; t_ = T[off]
            first_clock = last_clock = None
            for pl in dr.log:
                if not isinstance(pl, dict): continue
                ty = pl.get('type'); y = float(pl.get('yards', 0) or 0)
                if ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    t_['plays'] += 1
                    if pl.get('clock') is not None:
                        if first_clock is None: first_clock = float(pl['clock'])
                        last_clock = float(pl['clock'])
                if ty in ('run', 'scramble'): t_['rush_yds'] += y; t_['yards'] += y; k = ('rush', pl.get('carrier') or pl.get('passer')); longest[k] = max(longest.get(k, 0), int(round(y)))
                elif ty == 'complete': t_['pass_yds'] += y; t_['yards'] += y; longest[('pass', pl.get('passer'))] = max(longest.get(('pass', pl.get('passer')), 0), int(round(y))); longest[('rec', pl.get('target'))] = max(longest.get(('rec', pl.get('target')), 0), int(round(y)))
                elif ty == 'sack': t_['pass_yds'] += y; t_['yards'] += y; t_['sacks_allowed'] += 1
                elif ty == 'interception': t_['turnovers'] += 1
                elif ty == 'fumble' and pl.get('lost', True): t_['turnovers'] += 1
                elif ty == 'penalty': t_['penalties'] += 1; t_['pen_yds'] += abs(int(round(y)))
                if pl.get('down') == 3 and ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    t_['third_att'] += 1; t_['third_conv'] += int(y >= float(pl.get('ydstogo', 10) or 10) and ty in ('run', 'complete', 'scramble'))
                if pl.get('down') == 4 and ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    t_['fourth_att'] += 1; t_['fourth_conv'] += int(y >= float(pl.get('ydstogo', 10) or 10) and ty in ('run', 'complete', 'scramble'))
            t_['first_downs'] += int(getattr(dr, 'first_downs', 0) or 0)
            if first_clock is not None and last_clock is not None: t_['top'] += max(0.0, first_clock - last_clock)
            if float(getattr(dr, 'yardline', 99) or 99) <= 20 or (dr.result == 'Touchdown'): t_['red_zone'] += 1; t_['red_zone_td'] += int(dr.result == 'Touchdown')
        team_stats = {}
        for abbr_, t_ in T.items():
            team_stats[abbr_] = dict(plays=t_['plays'], yards=int(round(t_['yards'])), pass_yds=int(round(t_['pass_yds'])), rush_yds=int(round(t_['rush_yds'])), ypp=(round(t_['yards'] / t_['plays'], 1) if t_['plays'] else 0.0), first_downs=t_['first_downs'],
                                     third=f"{t_['third_conv']}/{t_['third_att']}", fourth=f"{t_['fourth_conv']}/{t_['fourth_att']}", turnovers=t_['turnovers'], sacks_allowed=t_['sacks_allowed'], penalties=f"{t_['penalties']} for {t_['pen_yds']}",
                                     top=f"{int(t_['top'] // 60)}:{int(t_['top'] % 60):02d}", red_zone=f"{t_['red_zone_td']}/{t_['red_zone']}")
        # the assistants' read of the game: what decided it
        me_s, op_s = team_stats[user], team_stats[opp]
        reads = []
        if me_s['turnovers'] != op_s['turnovers']: reads.append(f"Turnovers {me_s['turnovers']} to {op_s['turnovers']}" + (', and that was the game.' if abs(me_s['turnovers'] - op_s['turnovers']) >= 2 else '.'))
        if abs(me_s['rush_yds'] - op_s['rush_yds']) >= 60: reads.append(f"The ground game: {me_s['rush_yds']} rushing yards to {op_s['rush_yds']}.")
        if me_s['sacks_allowed'] >= 4: reads.append(f"Protection broke down: {me_s['sacks_allowed']} sacks allowed.")
        if op_s['sacks_allowed'] >= 4: reads.append(f"The rush got home: {op_s['sacks_allowed']} sacks.")
        try:
            a, b = map(int, me_s['third'].split('/')); c, d = map(int, op_s['third'].split('/'))
            if b >= 8 and a / b >= 0.5: reads.append(f"Third downs went our way: {me_s['third']}.")
            if d >= 8 and c / d >= 0.5: reads.append(f"We could not get off the field on third down: they went {op_s['third']}.")
        except Exception: pass
        if not reads: reads.append('An even game on the sheet; the score came down to the drives that finished.')
        # box score: the top lines from the book
        def line(pid):
            l = book.p.get(pid, {}); p = league.player(pid); return p, l
        def top(pids, key, n=3):
            rows = [(pid, book.p[pid]) for pid in pids if pid in book.p and book.p[pid].get(key, 0) > 0]
            return sorted(rows, key=lambda x: -x[1].get(key, 0))[:n]
        box = dict(passing=[], rushing=[], receiving=[], defense=[])
        for abbr in (home, away):
            pids = [p.pid for p in league.teams[abbr].roster]
            for pid, l in top(pids, 'pass_att', 2):
                p = league.player(pid); box['passing'].append(dict(team=abbr, name=p.name, ca=f"{int(l.get('pass_cmp', 0))}/{int(l.get('pass_att', 0))}", yds=int(l.get('pass_yds', 0)), td=int(l.get('pass_td', 0)), int_=int(l.get('ints', 0)), lng=longest.get(('pass', pid), 0)))
            for pid, l in top(pids, 'rush_att', 2):
                p = league.player(pid); box['rushing'].append(dict(team=abbr, name=p.name, att=int(l.get('rush_att', 0)), yds=int(l.get('rush_yds', 0)), td=int(l.get('rush_td', 0)), lng=longest.get(('rush', pid), 0)))
            for pid, l in top(pids, 'rec', 3):
                p = league.player(pid); box['receiving'].append(dict(team=abbr, name=p.name, tgt=int(l.get('tgt', 0)), rec=int(l.get('rec', 0)), yds=int(l.get('rec_yds', 0)), td=int(l.get('rec_td', 0)), lng=longest.get(('rec', pid), 0)))
            for pid, l in top(pids, 'tackles', 3):
                p = league.player(pid); box['defense'].append(dict(team=abbr, name=p.name, tkl=int(l.get('tackles', 0)), sk=float(l.get('sacks', 0)), int_=int(l.get('int_def', 0)), pd=int(l.get('pass_def', 0))))
        # line score by quarter, from the score at each drive's end
        quarters = {home: [0, 0, 0, 0, 0], away: [0, 0, 0, 0, 0]}
        for d in drives:
            if not d.get('points'): continue
            qi = min(4, max(0, int(d.get('quarter', 1)) - 1)); quarters[d['off']][qi] += int(d['points'])
        # each drive: how it started and what came before it, in words
        prev_result = None
        for i, d in enumerate(drives):
            how = {'Touchdown': 'after a touchdown', 'Field Goal': 'after a field goal', 'Punt': 'after a punt', 'Interception': 'after an interception', 'Fumble': 'after a fumble', 'Turnover on Downs': 'after a stop on fourth down', 'Missed FG': 'after a missed field goal'}.get(prev_result, 'to open' if i == 0 else 'after the kickoff' if prev_result in ('Touchdown', 'Field Goal') else '')
            spot = d.get('start', 50); side = d['off'] if spot <= 50 else (away if d['off'] == home else home)
            yard = int(round(spot if spot <= 50 else 100 - spot))
            d['head'] = f"Drive {d['n']} · {d['off']} · Started at the {side} {yard} {how}".rstrip() + f" · {d['plays_n']} play{'s' if d['plays_n'] != 1 else ''}, {int(round(d['yards']))} yard{'s' if int(round(d['yards'])) != 1 else ''}" + (f", {str(d['result']).lower()}" if d.get('result') else '')
            prev_result = d.get('result')
        out['game'] = dict(home=home, away=away, hs=res['home'], as_=res['away'], ot=bool(res.get('overtime')), me=user, opp=opp, me_home=me_home,
                           drives=drives, wp=wp, box=box, env=res.get('env', {}), team_stats=team_stats, reads=reads, quarters=quarters)
    return out
