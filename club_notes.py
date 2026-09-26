"""
club_notes.py - the inbox items about your own club.

Written by the weekly roll and the season's turns, from state the engine already keeps:
- the injury report after each game, with who steps in
- a man back from injury, and whether his spot is still his
- a player turning unhappy, with his reason, before it becomes a trade request
- milestones: a rookie's first start, a 100th start, a season line passing a round number
- the week's honors when one of yours is named
- the owner's mid-season note when the seat warms
- the expiring contracts as one batch at the season's end
- scouting: a prospect on your board moving ten spots on the consensus

Every note is one paragraph and posts once; a small ledger on the league stops repeats.
"""
import inbox as IB

GROUP_STARTERS = {'QB': 1, 'HB': 1, 'WR': 3, 'TE': 1, 'LT': 1, 'LG': 1, 'C': 1, 'RG': 1, 'RT': 1, 'LEDG': 1, 'REDG': 1, 'DT': 2, 'MIKE': 1, 'WILL': 1, 'SAM': 1, 'CB': 3, 'FS': 1, 'SS': 1, 'K': 1, 'P': 1}


def _ledger(league):
    if getattr(league, 'notes_sent', None) is None: league.notes_sent = {}
    return league.notes_sent


def _once(league, key):
    led = _ledger(league)
    if key in led: return False
    led[key] = league.week; return True


def _surname(name):
    from views import surname
    return surname(name)


# ------------------------------------------------------------ after the games
def after_games(league, week, results):
    """Sunday night: the injury report and the honors."""
    user = getattr(league, 'user_team', None)
    if not user: return
    t = league.teams[user]
    _injury_report(league, t, week, results)
    _honors(league, t, week)


def _injury_report(league, t, week, results):
    # everything logged since the last report (the log's week is stamped before the calendar moves)
    led = _ledger(league); start = int(led.get('_inj_idx', 0) or 0)
    hurt = [x for x in league.transactions[start:] if x.get('kind') == 'injury' and x.get('team') == t.abbr]
    led['_inj_idx'] = len(league.transactions)
    if not hurt: return
    lines = []
    for x in hurt:
        p = league.player(x['pid'])
        if p is None: continue
        weeks = int(x.get('weeks') or 0)
        d = [q for q in t.depth.get(p.pos, []) if q.out_until is None and q.pid != p.pid]
        nxt = d[0] if d else None
        was_starter = t.depth.get(p.pos, [None])[0] is p or p in t.depth.get(p.pos, [])[:GROUP_STARTERS.get(p.pos, 1)]
        span = ('the season' if x.get('season_ending') or weeks >= 10 else f"{weeks} week{'s' if weeks != 1 else ''}") if weeks else 'a week'
        kind = str(x.get('injury') or 'injury').replace('_', ' ')
        line = f"{p.name} ({p.pos}) is out {span} ({kind})" 
        if was_starter and nxt is not None: line += f"; {_surname(nxt.name)} ({round(nxt.ovr)}) steps in"
        elif was_starter: line += '; there is nobody behind him at the spot'
        lines.append(line + '.')
    if lines and _once(league, f"inj-{league.year}-{week}"):
        IB.post(league, 'injury', f"Injury report · Week {week}" + (f": {len(lines)} down" if len(lines) > 1 else f": {_surname(league.player(hurt[0]['pid']).name)}"), ' '.join(lines) + ' The depth chart has been updated.', sender='trainers', payload=dict(link='club:depth'))


def returns(league, week):
    """Wednesday: a man cleared to play again, and where he sits."""
    user = getattr(league, 'user_team', None)
    if not user: return
    t = league.teams[user]
    led = _ledger(league); out_seen = led.setdefault('_out', {})
    # remember who was out last week; anyone now clear is back
    now_out = {p.pid for p in t.active() if p.out_until is not None}
    back = [pid for pid in list(out_seen.keys()) if pid not in now_out]
    for pid in list(out_seen): 
        if pid not in now_out: out_seen.pop(pid, None)
    for pid in now_out: out_seen[pid] = week
    for pid in back:
        p = league.player(pid)
        if p is None or p.team != t.abbr or not _once(league, f"back-{p.pid}-{league.year}-{week}"): continue
        d = t.depth.get(p.pos, []); rank = next((i for i, q in enumerate(d) if q.pid == p.pid), None)
        where = 'back in his starting spot' if rank is not None and rank < GROUP_STARTERS.get(p.pos, 1) else f"listed {['first', 'second', 'third', 'fourth', 'fifth', 'sixth'][min(5, rank or 0)]} at {p.pos} while he was out" if rank is not None else 'back on the roster'
        IB.post(league, 'injury', f"{p.name} cleared to play", f"{p.name} ({p.pos}) is back from his injury and {where}. Set the depth chart if you want him elsewhere.", sender='trainers', payload=dict(link='club:depth'))


def _honors(league, t, week):
    """The week's honors: the book's best line on your club, if it leads the league at the spot that week."""
    bk = getattr(league, 'week_book', None)
    if not bk: return
    # the strongest single line league-wide this week, by a plain score
    best = None
    for pid, d in bk.items():
        p = league.player(pid)
        if p is None: continue
        score = d.get('pass_yds', 0) * 0.04 + d.get('pass_td', 0) * 4 - d.get('ints', 0) * 3 + d.get('rush_yds', 0) * 0.1 + d.get('rec_yds', 0) * 0.1 + (d.get('rush_td', 0) + d.get('rec_td', 0)) * 6 + d.get('sacks', 0) * 4 + d.get('int_def', 0) * 5 + d.get('ff', 0) * 3 + d.get('tackles', 0) * 0.5
        if best is None or score > best[1]: best = (p, score, d)
    if best and best[0].team == t.abbr and best[1] >= 20 and _once(league, f"potw-{league.year}-{week}"):
        p, _, d = best
        line = ', '.join(x for x in [f"{int(d['pass_yds'])} passing yards" if d.get('pass_yds') else '', f"{d['pass_td']} touchdown passes" if d.get('pass_td') else '', f"{int(d['rush_yds'])} rushing yards" if d.get('rush_yds') else '', f"{int(d['rec_yds'])} receiving yards" if d.get('rec_yds') else '', f"{d['rush_td'] + d['rec_td']} touchdowns" if (d.get('rush_td', 0) + d.get('rec_td', 0)) else '', f"{d['sacks']:g} sacks" if d.get('sacks') else '', f"{d['int_def']} interceptions" if d.get('int_def') else ''] if x)
        IB.post(league, 'result', f"{p.name} named Player of the Week", f"{p.name} ({p.pos}) had the league's best line in Week {week}: {line}.", sender='league')


# ------------------------------------------------------------ the roll
def weekly(league, week):
    """After the roll: morale turns, milestones, the owner, the board."""
    user = getattr(league, 'user_team', None)
    if not user: return
    t = league.teams[user]
    _morale(league, t, week)
    _milestones(league, t, week)
    _owner(league, t, week)
    _board(league, t, week)


def _morale(league, t, week):
    import morale as MO
    for p in t.active():
        st = MO.status(p, t)
        last = p.xp_spent.get('_mood_seen', 'settled')
        if st != last:
            p.xp_spent['_mood_seen'] = st
            if st in ('quietly unhappy', 'publicly discontent', 'locker room distraction') and last == 'settled' or (st == 'publicly discontent' and last == 'quietly unhappy'):
                why = MO.request_reason(p)
                reason = {'contract': 'he believes he is underpaid', 'role': 'he wants a bigger role than he has', 'losing': 'the losing has worn on him'}.get(why, 'the season has worn on him')
                word = {'quietly unhappy': 'is unhappy', 'publicly discontent': 'has gone public with his unhappiness', 'locker room distraction': 'is a problem in the room'}[st]
                IB.post(league, 'morale', f"{p.name} {word}", f"{p.name} ({p.pos}, {round(p.ovr)}) {word}: {reason}. Left alone this becomes a trade request. A talk, more snaps or a new deal are the ways to turn it.", sender='assistants', payload=dict(link=f'player:{p.pid}'))


def _milestones(league, t, week):
    bk = league.stats.get(league.year, {}) if getattr(league, 'stats', None) else {}
    for p in t.active():
        gs = int(p.xp_spent.get('_starts', 0) or 0)
        if gs == 1 and (p.accrued or 0) <= 1 and float(p.age) <= 24.0 and _once(league, f"first-start-{p.pid}"):
            IB.post(league, 'result', f"{p.name} makes his first start", f"{p.name} ({p.pos}) started his first game for you in Week {week}.", sender='assistants')
        if gs in (50, 100, 150, 200) and _once(league, f"starts-{gs}-{p.pid}"):
            IB.post(league, 'result', f"{p.name}'s {gs}th start", f"{p.name} ({p.pos}) made his {gs}th career start in Week {week}.", sender='assistants')
        d = bk.get(p.pid) or {}
        for key, label, marks in (('pass_yds', 'passing yards', (3000, 4000, 5000)), ('rush_yds', 'rushing yards', (1000, 1500, 2000)), ('rec_yds', 'receiving yards', (1000, 1500)), ('sacks', 'sacks', (10, 15, 20)), ('int_def', 'interceptions', (5, 8))):
            v = d.get(key, 0)
            for m in marks:
                if v >= m and _once(league, f"{key}-{m}-{p.pid}-{league.year}"):
                    IB.post(league, 'result', f"{p.name} passes {m:,} {label}", f"{p.name} ({p.pos}) reached {m:,} {label} for the season in Week {week}.", sender='assistants')


def _owner(league, t, week):
    if week not in (9, 13): return
    import firing_model as FM
    sec = FM.job_security(t.hist())
    key = f"owner-{league.year}-{week}"
    w, l, _ = t.record
    if sec < 0.45 and _once(league, key):
        from views_frontoffice import _owner as owner_of
        o = owner_of(league, t)
        word = 'has noticed' if sec >= 0.25 else 'is running out of patience'
        IB.post(league, 'owner', f"{o['name']} {word}", f"At {w}–{l} the owner {word}. He expected {'more' if sec >= 0.25 else 'a great deal more'} from this roster and this staff. The second half of the season decides how the review reads.", sender=o['name'], payload=dict(link='front_office:owner'))


def _board(league, t, week):
    """A prospect on your board moves ten spots on the consensus."""
    ub = getattr(league, 'user_board', None) or {}
    order = ub.get('order') or []
    if not order: return
    cons = getattr(league, 'consensus', None) or {}
    last = league.__dict__.setdefault('_cons_seen', {})
    moves = []
    for pid in order:
        r = (cons.get(pid) or {}).get('rank')
        if r is None: continue
        pr = last.get(pid)
        if pr is not None and abs(pr - r) >= 10:
            p = league.player(pid)
            if p is not None: moves.append(f"{p.name} ({p.pos}) {'rises' if r < pr else 'falls'} from {pr} to {r}")
        last[pid] = r
    if moves and _once(league, f"board-{league.year}-{week}"):
        IB.post(league, 'scouting', f"Your board: {len(moves)} mover{'s' if len(moves) > 1 else ''}", '. '.join(moves) + '.', sender='scouts', payload=dict(link='draft:board'))


# ------------------------------------------------------------ the season's turns
def season_end(league):
    """The expiring contracts as one batch."""
    user = getattr(league, 'user_team', None)
    if not user: return
    t = league.teams[user]
    exp = sorted([p for p in t.active() if p.contract and p.contract.years <= 1], key=lambda p: -p.ovr)
    if not exp or not _once(league, f"expiring-{league.year}"): return
    import valuation as VAL
    rows = []
    for p in exp[:14]:
        try: v = VAL.value_player(league, p, side='agent', rng=None); ask = f"about ${v['apy']:.1f}m a year" if v else 'no read yet'
        except Exception: ask = 'no read yet'
        rows.append(f"{p.name} ({p.pos}, {round(p.ovr)}, {int(p.age)}): {ask}")
    IB.post(league, 'contract_year', f"{len(exp)} contracts expire this offseason", "Deals up: " + '; '.join(rows) + ('.' if len(exp) <= 14 else f"; and {len(exp) - 14} more."), sender='assistants', payload=dict(link='personnel:extensions'))
