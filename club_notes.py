"""
club_notes.py - the inbox items about your own club.

Written by the weekly roll and the season's turns, from state the engine already keeps:
- the injury report after each game
- a man back from injury, and whether his spot is still his
- a player turning unhappy, with his reason, before it becomes a trade request
- milestones: a rookie's first start, a 100th start, a season line passing a round number
- the week's honors when one of yours is named
- the owner's mid-season note when the seat warms
- the expiring contracts as one batch at the season's end
- scouting: a prospect on your board moving ten spots on the consensus

Every note posts once; digest items occupy separate rows and a small ledger stops repeats.
"""
from inbox import player_name as inbox_player
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
        span = ('for the season' if x.get('season_ending') or weeks >= 10 else f"{weeks} week{'s' if weeks != 1 else ''}") if weeks else 'a week'
        kind = str(x.get('injury') or 'injury').replace('_', ' ')
        line = f"{inbox_player(p)} ({p.pos}) is out {span} ({kind})"
        if was_starter and nxt is None: line += '; there is nobody behind him at the spot'
        lines.append(line + '.')
    if lines and _once(league, f"inj-{league.year}-{week}"):
        IB.post(league, 'injury', f"Injury report · {_period(week)}" + (f": {len(lines)} down" if len(lines) > 1 else f": {inbox_player(league.player(hurt[0]['pid']), _surname(league.player(hurt[0]['pid']).name))}"), '\n'.join(lines) + '\nThe depth chart has been updated.', sender='trainers', payload=dict(link='club:depth'))


def returns(league, week):
    """Wednesday: a player cleared to play again, and where he sits."""
    user = getattr(league, 'user_team', None)
    if not user: return
    t = league.teams[user]
    led = _ledger(league); out_seen = led.setdefault('_out', {})
    # remember who was out last week; anyone now clear is back
    now_out = {p.pid for p in t.roster if not p.retired and p.out_until is not None}
    back = [pid for pid in list(out_seen.keys()) if pid not in now_out]
    for pid in list(out_seen):
        if pid not in now_out: out_seen.pop(pid, None)
    for pid in now_out: out_seen[pid] = week
    for pid in back:
        p = league.player(pid)
        if p is None or p.retired or p.team != t.abbr or p.out_until is not None or any(q.pid == pid for q in (getattr(t, 'ir', None) or [])): continue
        if not _once(league, f"back-{p.pid}-{league.year}-{week}"): continue
        where = f'available at {p.pos}'
        IB.post(league, 'injury', f"{inbox_player(p)} cleared to play", f"{inbox_player(p)} ({p.pos}) is back from his injury and {where}.", sender='trainers', payload=dict(link='club:depth'))


def _honors(league, t, week):
    """The week's honors: the book's best line on your club, if it leads the league at the spot that week."""
    # Read only this round's recorded games. The scratch week_book can still
    # contain bye teams' lines from the preceding week during the playoffs.
    bk = {}
    prefix = f'{league.year}-{int(week)}-'
    for key, lines in (getattr(league, 'game_stats', {}) or {}).items():
        if key.startswith(prefix): bk.update(lines)
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
        line = ', '.join(x for x in [f"{int(d['pass_yds'])} passing yards" if d.get('pass_yds') else '', f"{d['pass_td']} touchdown passes" if d.get('pass_td') else '', f"{int(d['rush_yds'])} rushing yards" if d.get('rush_yds') else '', f"{int(d['rec_yds'])} receiving yards" if d.get('rec_yds') else '', f"{d.get('rush_td', 0) + d.get('rec_td', 0)} touchdowns" if (d.get('rush_td', 0) + d.get('rec_td', 0)) else '', f"{d['sacks']:g} sacks" if d.get('sacks') else '', f"{d['int_def']} interceptions" if d.get('int_def') else ''] if x)
        IB.post(league, 'result', f"{inbox_player(p)} named Player of the Week", f"{inbox_player(p)} ({p.pos}) had the league's best line in {_period(week)}: {line}.", sender='league')


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
                if why == 'contract':
                    p.xp_spent['_contract_concern'] = True
                reason = {'contract': 'he believes he is underpaid', 'role': 'he wants a bigger role than he has', 'losing': 'the losing has worn on him'}.get(why, 'the season has worn on him')
                word = {'quietly unhappy': 'is unhappy', 'publicly discontent': 'has gone public with his unhappiness', 'locker room distraction': 'is a problem in the room'}[st]
                IB.post(league, 'morale', f"{inbox_player(p)} {word}", f"{inbox_player(p)} ({p.pos}, {round(p.ovr)}) {word}: {reason}. Left alone this becomes a trade request. A talk, more snaps or a new deal are the ways to turn it.", sender='assistants', payload=dict(link=f'player:{p.pid}'))


def _first_start_line(league, team, player, week):
    """Read the finished game's line, never the season total or scratch book."""
    prefix = f'{league.year}-{int(week)}-'
    line = None
    for key, book in (getattr(league, 'game_stats', None) or {}).items():
        if key.startswith(prefix) and team.abbr in key[len(prefix):].split('-'):
            if player.pid in book:
                line = book[player.pid]
                break
    if line is None:
        return ''
    d = line
    def n(key): return float(d.get(key, 0) or 0)
    pos = player.pos
    if pos in ('LT', 'LG', 'C', 'RG', 'RT'):
        blocks = []
        if n('pb_snaps'):
            blocks.append(f"Pass blocking: {n('pb_wins'):g}/{n('pb_snaps'):g} wins; "
                          f"{n('pressures_allowed'):g} pressures and {n('sacks_allowed'):g} sacks allowed.")
        if n('rb_snaps'):
            blocks.append(f"Run blocking: {n('rb_wins'):g}/{n('rb_snaps'):g} wins.")
        return '\n'.join(blocks)
    if pos == 'QB':
        text = (f"Passing: {n('pass_cmp'):g}/{n('pass_att'):g}, {n('pass_yds'):g} yards, "
                f"{n('pass_td'):g} TD, {n('ints'):g} INT.")
        if n('rush_att'):
            text += f"\nRushing: {n('rush_att'):g} carries, {n('rush_yds'):g} yards, {n('rush_td'):g} TD."
        return text
    if pos in ('HB', 'FB', 'WR', 'TE'):
        rows = []
        if pos in ('HB', 'FB') or n('rush_att'):
            rows.append(f"Rushing: {n('rush_att'):g} carries, {n('rush_yds'):g} yards, {n('rush_td'):g} TD.")
        rows.append(f"Receiving: {n('rec'):g} catches on {n('tgt'):g} targets, {n('rec_yds'):g} yards, {n('rec_td'):g} TD.")
        if n('fumbles_lost'): rows[-1] += f" Fumbles lost: {n('fumbles_lost'):g}."
        return '\n'.join(rows)
    if pos == 'K':
        return f"Kicking: {n('fg_made'):g}/{n('fg_att'):g} field goals; {n('xp_made'):g}/{n('xp_att'):g} extra points."
    if pos == 'P':
        if not n('punts'): return 'Punting: 0 punts.'
        return (f"Punting: {n('punts'):g} punts, {n('punt_yds') / n('punts'):.1f} yards per punt, "
                f"{n('punt_net_yds') / n('punts'):.1f} net; {n('punt_in20'):g} inside the 20.")
    if pos == 'LS':
        return f"Special teams: {n('snaps'):g} long snaps."
    text = (f"{n('tackles'):g} tackles, {n('sacks'):g} sacks, "
            f"{n('pressures'):g} pressures")
    if pos not in ('DT', 'LEDG', 'REDG'):
        text += f"; {n('int_def'):g} interceptions, {n('pass_def'):g} passes defended"
    text += '.'
    if n('ff') or n('fum_rec'):
        text += f"\n{n('ff'):g} forced fumbles, {n('fum_rec'):g} fumble recoveries."
    return text


def _milestones(league, t, week):
    if int(week or 0) > 18: return                               # season milestones are regular-season numbers; playoff lines sit in their own book
    bk = league.stats.get(league.year, {}) if getattr(league, 'stats', None) else {}
    for p in t.active():
        gs = int(p.xp_spent.get('_starts', 0) or 0)
        if gs == 1 and (p.accrued or 0) <= 1 and float(p.age) <= 24.0 and _once(league, f"first-start-{p.pid}"):
            body = f"{inbox_player(p)} ({p.pos}) started his first game for you in {_period(week)}."
            stats = _first_start_line(league, t, p, week)
            if stats: body += '\n\n' + stats
            IB.post(league, 'result', f"{inbox_player(p)} makes his first start", body, sender='assistants')
        if gs in (50, 100, 150, 200) and _once(league, f"starts-{gs}-{p.pid}"):
            IB.post(league, 'result', f"{inbox_player(p)}'s {gs}th start", f"{inbox_player(p)} ({p.pos}) made his {gs}th career start in {_period(week)}.", sender='assistants')
        d = bk.get(p.pid) or {}
        for key, label, marks in (('pass_yds', 'passing yards', (3000, 4000, 5000)), ('rush_yds', 'rushing yards', (1000, 1500, 2000)), ('rec_yds', 'receiving yards', (1000, 1500)), ('sacks', 'sacks', (10, 15, 20)), ('int_def', 'interceptions', (5, 8))):
            v = d.get(key, 0)
            for m in marks:
                if v >= m and _once(league, f"{key}-{m}-{p.pid}-{league.year}"):
                    IB.post(league, 'result', f"{inbox_player(p)} passes {m:,} {label}", f"{inbox_player(p)} ({p.pos}) reached {m:,} {label} for the season in {_period(week)}.", sender='assistants')


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
            if p is not None: moves.append(f"{inbox_player(p)} ({p.pos}) {'rises' if r < pr else 'falls'} from {pr} to {r}")
        last[pid] = r
    if moves and _once(league, f"board-{league.year}-{week}"):
        IB.post(league, 'scouting', f"Your board: {len(moves)} mover{'s' if len(moves) > 1 else ''}", '\n'.join(moves) + '.', sender='scouts', payload=dict(link='draft:board'))


# ------------------------------------------------------------ the season's turns
def season_end(league):
    """The expiring contracts as one batch."""
    user = getattr(league, 'user_team', None)
    if not user: return
    import inbox_events as IE
    if IE.seen(league, f"extwin-{league.year}"): return
    t = league.teams[user]
    exp = sorted([p for p in t.active() if p.contract and p.contract.years <= 1], key=lambda p: -p.ovr)
    if not exp or not _once(league, f"expiring-{league.year}"): return
    import valuation as VAL
    rows = []
    for p in exp:
        try: v = VAL.value_player(league, p, side='agent', rng=None); ask = f"about ${v['apy']:.1f}m a year" if v else 'no read yet'
        except Exception: ask = 'no read yet'
        rows.append([inbox_player(p), p.pos, str(round(p.ovr)), str(int(p.age)), ask])
    IB.post(league, 'contract_year', f"{len(exp)} contracts expire this offseason", 'Review these expiring deals before the offseason.', sender='assistants', payload=dict(link='personnel:extensions', mail_sections=[IB.mail_section('Expiring contracts', rows, ['Player', 'Position', 'OVR', 'Age', 'Agent estimate'])]))


def _period(week):
    return {19: "Wild Card", 20: "Divisional Round", 21: "Conference Championship", 22: "Championship Game"}.get(int(week), f"Week {week}")
