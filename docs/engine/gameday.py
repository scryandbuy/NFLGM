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
            drives.append(dict(n=i + 1, off=off_abbr, start=round(100 - start, 1), end=round(100 - end, 1), plays_n=int(getattr(dr, 'plays', len(plays))), yards=round(start - end, 1),
                               result=getattr(dr, 'result', ''), points=pts, quarter=int(getattr(dr, 'quarter', 1) or 1), clock=_clock(getattr(dr, 'clock', 0)),
                               score=f"{hs}–{as_}", plays=plays))
            diff = (hs - as_) if me_home else (as_ - hs)
            wp.append(round(100 * _wp(diff, float(getattr(dr, 'clock', 0) or 0), me_home)))
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
                p = league.player(pid); box['passing'].append(dict(team=abbr, name=p.name, ca=f"{int(l.get('pass_cmp', 0))}/{int(l.get('pass_att', 0))}", yds=int(l.get('pass_yds', 0)), td=int(l.get('pass_td', 0)), int_=int(l.get('pass_int', 0))))
            for pid, l in top(pids, 'rush_att', 2):
                p = league.player(pid); box['rushing'].append(dict(team=abbr, name=p.name, att=int(l.get('rush_att', 0)), yds=int(l.get('rush_yds', 0)), td=int(l.get('rush_td', 0))))
            for pid, l in top(pids, 'rec', 3):
                p = league.player(pid); box['receiving'].append(dict(team=abbr, name=p.name, tgt=int(l.get('targets', 0)), rec=int(l.get('rec', 0)), yds=int(l.get('rec_yds', 0)), td=int(l.get('rec_td', 0))))
            for pid, l in top(pids, 'tackles', 3):
                p = league.player(pid); box['defense'].append(dict(team=abbr, name=p.name, tkl=int(l.get('tackles', 0)), sk=float(l.get('sacks', 0)), int_=int(l.get('interceptions', 0)), pd=int(l.get('pass_def', 0))))
        out['game'] = dict(home=home, away=away, hs=res['home'], as_=res['away'], ot=bool(res.get('overtime')), me=user, opp=opp, me_home=me_home,
                           drives=drives, wp=wp, box=box, env=res.get('env', {}))
    return out
