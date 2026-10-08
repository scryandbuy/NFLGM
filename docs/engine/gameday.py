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
import ticker


def _name(league, pid, short=True):
    p = league.player(pid) if pid else None
    if p is None: return 'the ball carrier'
    if not short: return p.name
    parts = p.name.split()
    return parts[-1] if len(parts) > 1 else p.name


def _spot(yardline, off_abbr, def_abbr):
    """yardline is distance to the goal (100 = own goal line)."""
    return ticker._spot(yardline, off_abbr, def_abbr)


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
              td=bool(q.get('touchdown') or q.get('td') or q.get('defensive_td')), defensive_td=bool(q.get('defensive_td')), clock=q.get('clock'), down=q.get('down'), togo=q.get('ydstogo'), made=q.get('made'), safety=bool(q.get('safety')), fumble=bool(q.get('fumble')), fumble_lost=bool(q.get('fumble_lost')), nullified=bool(q.get('nullified')))
    ln['display_togo'] = TK.display_distance(q.get('yardline'), q.get('ydstogo'), off_abbr, def_abbr)
    ln['yardline'] = q.get('yardline')
    for role in ('passer', 'target', 'carrier', 'returner'):
        ln[role + '_pid'] = q.get(role)
    if q.get('type') == 'injury':
        injured = league.player(q.get('pid'))
        ln['injury'] = dict(pid=q.get('pid'), name=injured.name if injured else None,
                            pos=q.get('pos'), kind=q.get('kind'), weeks=q.get('weeks'),
                            team=def_abbr if q.get('side') == 'def' else off_abbr)
    ln['scoring_side'] = q.get('scoring_side') or ('defense' if q.get('defensive_td') or (q.get('blocked') and q.get('recovery') == 'receiving') else 'offense')
    ln['offensive_fumble_td'] = bool(q.get('offensive_fumble_td'))
    ln['stat_yards'] = round(float(q.get('carrier_yards', q.get('yards', 0)) or 0))
    if q.get('type') == 'two_point': ln['try_points'] = q.get('points', 2 if q.get('made') else 0)
    if q.get('type') == 'sack':
        import rush_matchup as RM
        ln.update(sacker=q.get('by'), sack_credits=RM.credited_sackers(q))
    if q.get('type') in ('punt', 'kickoff') and q.get('returner'):
        ln.update(returner=nm(q['returner']), return_team=def_abbr if q['type']=='punt' else off_abbr,
                  return_yards=float(q.get('ret', 0)), return_td=bool(q.get('touchdown')),
                  turnover_team=(def_abbr if q['type']=='punt' else off_abbr) if q.get('fumble_lost') else None)
    if q.get('type') == 'timeout':
        ln.update(timeout_side=q.get('side'), timeout_team=q.get('side_abbr'),
                  timeouts_left=q.get('left'))
    return ln


def _wp(score_diff, sec_left, pos_is_home):
    """A simple in-game win probability for the drawing: score and time, home side."""
    # spread the margin by time remaining: a 7-point lead with a minute left is near certain, at kickoff it is ~70%
    t = max(0.0, min(1.0, sec_left / 3600.0))
    z = score_diff / (3.0 + 11.0 * np.sqrt(t))
    return float(1.0 / (1.0 + np.exp(-z)))


def scoring_quarter(dr):
    """Score in the period of the scoring snap, including older saved drives."""
    if getattr(dr, 'quarter', 1) >= 5:
        return 5
    for p in reversed(dr.log):
        if (p.get('touchdown') or p.get('defensive_td')) and not p.get('nullified') and p.get('clock') is not None:
            return min(4, int((3600 - float(p['clock'])) // 900) + 1)
    # A kick ending exactly at a boundary belongs to the period just ended.
    return min(4, max(1, int((3600 - max(0, dr.clock) - 1e-6) // 900) + 1))


def box_score(league, book, home, away, longest, states=None, live=False):
    """All recorded participants. Read-only; never rerun simulation for a view."""
    box = {k: [] for k in ('passing', 'rushing', 'receiving', 'defense', 'blocking',
                           'kicking', 'punting', 'returns', 'snaps')}
    snaps_known = bool(states and all(a in states for a in (home, away)))
    for abbr in (away, home):
        state = (states or {}).get(abbr)
        counts = getattr(state, 'snap_counts' if live else 'last_snap_counts', {}) or {}
        players = {p.pid: p for p in league.teams[abbr].roster}
        players.update((p.pid, p) for p in (getattr(league.teams[abbr], '_elevated', None) or []))
        for unit in counts.values():
            for pid in unit.get('players', {}):
                p = league.player(pid)
                if p is not None: players[pid] = p
        for pid, p in players.items():
            l = book.p.get(pid, {})
            base = dict(team=abbr, pid=pid, name=p.name, pos=p.pos)
            def add(category, **stats):
                box[category].append(dict(base, **stats))
            def n(key): return l.get(key, 0)
            def avg(yards, attempts): return round(n(yards) / n(attempts), 1) if n(attempts) else None
            if n('pass_att') or n('sacked'):
                add('passing', ca=f"{int(n('pass_cmp'))}/{int(n('pass_att'))}", att=n('pass_att'),
                    yds=round(n('pass_yds')), td=n('pass_td'), int_=n('ints'), sk=n('sacked'), lng=longest.get(('pass', pid), 0))
            if n('rush_att'):
                add('rushing', att=n('rush_att'), yds=round(n('rush_yds')), avg=avg('rush_yds', 'rush_att'),
                    td=n('rush_td'), lng=longest.get(('rush', pid), 0), fum=n('fumbles_lost'))
            if n('tgt') or n('rec'):
                add('receiving', tgt=n('tgt'), rec=n('rec'), yds=round(n('rec_yds')), avg=avg('rec_yds', 'rec'),
                    td=n('rec_td'), lng=longest.get(('rec', pid), 0), drops=n('drops'))
            if any(n(k) for k in ('tackles', 'sacks', 'int_def', 'pass_def', 'pressures', 'ff', 'fum_rec', 'def_td', 'pr_reps', 'cov_snaps')):
                add('defense', tkl=n('tackles'), sk=n('sacks'), int_=n('int_def'), pd=n('pass_def'),
                    pressures=n('pressures'), ff=n('ff'), fr=n('fum_rec'), td=n('def_td'))
            if n('pb_snaps') or n('rb_snaps'):
                add('blocking', pb=n('pb_snaps'), pb_pct=round(100*n('pb_wins')/n('pb_snaps'), 1) if n('pb_snaps') else None,
                    pressures=n('pressures_allowed'), sk=n('sacks_allowed'), rb=n('rb_snaps'),
                    rb_pct=round(100*n('rb_wins')/n('rb_snaps'), 1) if n('rb_snaps') else None)
            if n('fg_att') or n('xp_att'):
                add('kicking', fg=f"{int(n('fg_made'))}/{int(n('fg_att'))}", xp=f"{int(n('xp_made'))}/{int(n('xp_att'))}",
                    pct=round(100*n('fg_made')/n('fg_att'), 1) if n('fg_att') else None, lng=n('fg_long'))
            if n('punts'):
                add('punting', att=n('punts'), yds=round(n('punt_yds')), avg=avg('punt_yds', 'punts'),
                    net=avg('punt_net_yds', 'punts'), in20=n('punt_in20'), tb=n('punt_tb'))
            if n('kr') or n('pr'):
                add('returns', kr=n('kr'), kr_yds=round(n('kr_yds')), kr_avg=avg('kr_yds', 'kr'), kr_td=n('kr_td'),
                    pr=n('pr'), pr_yds=round(n('pr_yds')), pr_avg=avg('pr_yds', 'pr'), pr_td=n('pr_td'), td=n('kr_td')+n('pr_td'))
            for unit, row in counts.items():
                snaps = row.get('players', {}).get(pid, 0)
                if snaps:
                    add('snaps', unit=unit.title(), snaps=snaps,
                        pct=round(100*snaps/row['total'], 1) if row.get('total') else None)
    if not snaps_known: box.pop('snaps')
    return box


def capture(league, played, user, states=None):
    """played: list of (home, away, res, book) from the week. Returns the Game Day record."""
    from game_recap import converted
    out = dict(week=league.week, year=getattr(league, 'year', None), scores=[], game=None)
    for home, away, res, book in played:
        out['scores'].append(dict(home=home, away=away, hs=res['home'], as_=res['away'], ot=bool(res.get('overtime'))))
        if user not in (home, away):
            continue
        me_home = (user == home); opp = away if me_home else home
        drives, wp, plays_all = [], [], []
        hs = as_ = 0
        previous_quarter = 1
        for i, (pos, dr) in enumerate(res['drives']):
            off_abbr = home if pos == 'home' else away; def_abbr = away if pos == 'home' else home
            qb = (dr.off or {}).get('qb', {}).get('pid'); rb = ((dr.off or {}).get('rb') or {}).get('pid')
            plays = []
            start_quarter = int(getattr(dr, 'start_quarter', dr.quarter))
            pending_period = start_quarter > previous_quarter
            for p in dr.log:
                if not isinstance(p, dict): continue
                play_pos = p.get('possession', pos)
                play_off, play_def = (home, away) if play_pos == 'home' else (away, home)
                line = write_play(league, p, qb, play_off, play_def, rb_pid=rb)
                line['quarter'] = (5 if start_quarter >= 5 else
                                   p.get('quarter') or (min(4, int((3600 - float(p['clock'])) // 900) + 1)
                                                       if p.get('clock') is not None else
                                                       (plays[-1].get('quarter', start_quarter) if plays else start_quarter)))
                # A kickoff can start in the old quarter and finish in the new
                # one. Announce the new period only after that return is shown.
                if pending_period and line['quarter'] >= start_quarter:
                    if p.get('type') != 'period':
                        marker = write_play(league, dict(type='period', quarter=start_quarter), qb, off_abbr, def_abbr)
                        marker['quarter'] = start_quarter
                        plays.append(marker)
                    pending_period = False
                plays.append(line)
            previous_quarter = max(start_quarter, scoring_quarter(dr))
            pts = int(getattr(dr, 'points', 0) or 0)
            if pts > 0:
                if pos == 'home': hs += pts
                else: as_ += pts
            elif pts < 0:
                if pos == 'home': as_ += abs(pts)
                else: hs += abs(pts)
            # The possession endpoint includes an interception's catch/return.
            # Offensive drive yardage ends at that pass's line of scrimmage.
            # Derive it from the log so previously saved games render correctly.
            start = float(getattr(dr, 'start', 75)); end = ticker.offensive_drive_end(dr)
            res_word = ticker.drive_result(dr, res.get('overtime', False))
            drives.append(dict(n=i + 1, off=off_abbr, start=round(100 - start, 1), start_label=ticker._spot(start, off_abbr, def_abbr), end=round(100 - end, 1), plays_n=int(getattr(dr, 'plays', len(plays))), yards=ticker.display_drive_yards(start, end, off_abbr, def_abbr), first_downs=int(getattr(dr, 'first_downs', 0) or 0),
                               result=res_word, points=pts, return_only=bool(getattr(dr, 'return_only', False)), quarter=start_quarter, scoring_quarter=scoring_quarter(dr), clock=_clock(getattr(dr, 'clock', 0)),
                               score=f"{hs}–{as_}", plays=plays))
            diff = (hs - as_) if me_home else (as_ - hs)
            wp.append(round(100 * _wp(diff, float(getattr(dr, 'clock', 0) or 0), me_home)))
        # longest plays and the team totals, from the drive log
        longest = {}; T = {home: dict(plays=0, yards=0, pass_yds=0, rush_yds=0, first_downs=0, third_att=0, third_conv=0, fourth_att=0, fourth_conv=0, turnovers=0, sacks_allowed=0, penalties=0, pen_yds=0, top=0.0, red_zone=0, red_zone_td=0), away: None}
        T[away] = dict(T[home])
        for pos, dr in res['drives']:
            off = home if pos == 'home' else away; t_ = T[off]; d_ = T[away if pos == 'home' else home]
            first_clock = last_clock = None
            red_zone_trip = False
            for pl in dr.log:
                if not isinstance(pl, dict): continue
                ty = pl.get('type'); y = float(pl.get('carrier_yards', pl.get('yards', 0)) or 0)
                # A trip requires an actual snap in the red zone. Crossing it
                # on a long score, a nullified play, or a victory kneel is not
                # an opportunity to finish a red-zone possession.
                if (not pl.get('nullified') and pl.get('yardline') is not None
                        and ty in ('run', 'complete', 'incomplete', 'sack', 'scramble',
                                   'drop', 'interception', 'field_goal')
                        and 0 < float(pl['yardline']) <= 20):
                    red_zone_trip = True
                if ty == 'penalty':
                    side_ = t_ if pl.get('on_offense', True) else d_
                    side_['penalties'] += 1; side_['pen_yds'] += abs(int(round(y))); continue
                if pl.get('nullified'): continue                   # a play wiped by a flag is not a play
                if ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception', 'kneel'):
                    t_['plays'] += 1
                    if pl.get('clock') is not None:
                        if first_clock is None: first_clock = float(pl['clock'])
                        last_clock = float(pl['clock'])
                if ty in ('run', 'scramble'): t_['rush_yds'] += y; t_['yards'] += y; k = ('rush', pl.get('carrier') or pl.get('passer')); longest[k] = max(longest.get(k, 0), int(round(y)))
                elif ty == 'complete': t_['pass_yds'] += y; t_['yards'] += y; longest[('pass', pl.get('passer'))] = max(longest.get(('pass', pl.get('passer')), 0), int(round(y))); longest[('rec', pl.get('target'))] = max(longest.get(('rec', pl.get('target')), 0), int(round(y)))
                elif ty == 'sack': t_['pass_yds'] += y; t_['yards'] += y; t_['sacks_allowed'] += 1
                elif ty == 'kneel': t_['rush_yds'] += y; t_['yards'] += y
                elif ty == 'interception': t_['turnovers'] += 1
                if pl.get('fumble_lost'):
                    (d_ if ty == 'punt' else t_)['turnovers'] += 1
                if pl.get('down') == 3 and ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    t_['third_att'] += 1; t_['third_conv'] += int(converted(pl))
                if pl.get('down') == 4 and ty in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    t_['fourth_att'] += 1; t_['fourth_conv'] += int(converted(pl))
            t_['first_downs'] += int(getattr(dr, 'first_downs', 0) or 0)
            # possession: from the drive's first entry (the kick that opened it, or the first snap) to the clock when it ended
            _clocks = [float(pl['clock']) for pl in getattr(dr, 'log', []) if isinstance(pl, dict) and pl.get('clock') is not None]
            if _clocks: t_['top'] += max(0.0, _clocks[0] - float(getattr(dr, 'clock', _clocks[-1]) or _clocks[-1]))
            if red_zone_trip:
                t_['red_zone'] += 1
                t_['red_zone_td'] += int(dr.result == 'Touchdown')
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
        box = box_score(league, book, home, away, longest, states, bool(res.get('live')))
        injuries = []
        raw_injuries = res.get('injuries', [])
        if res.get('live') and states:
            raw_injuries = [i for a in (home, away) for i in getattr(states.get(a), 'injuries', [])]
        for inj in raw_injuries:
            p = league.player(inj.get('player') or inj.get('pid'))
            if p is None: continue
            team = next((a for a in (home, away) if any(x.pid == p.pid for x in league.teams[a].roster)), None)
            injuries.append(dict(pid=p.pid, name=p.name, pos=p.pos, kind=inj.get('kind'), team=team, status='Out for this game'))
        # line score by quarter, from the score at each drive's end
        quarters = {home: [0, 0, 0, 0, 0], away: [0, 0, 0, 0, 0]}
        for d in drives:
            if not d.get('points'): continue
            qi = min(4, max(0, int(d.get('scoring_quarter', d.get('quarter', 1))) - 1))
            scorer = d['off'] if d['points'] > 0 else (away if d['off'] == home else home)
            quarters[scorer][qi] += abs(int(d['points']))
        # each drive: how it started and what came before it, in words
        prev_result = None
        for i, d in enumerate(drives):
            how = {'Touchdown': 'after a touchdown', 'Defensive touchdown': 'after a defensive touchdown', 'Field goal': 'after a field goal', 'Punt': 'after a punt', 'Turnover': 'after a turnover', 'Turnover on downs': 'after a stop on fourth down', 'Missed field goal': 'after a missed field goal'}.get(prev_result, 'to open' if i == 0 else '')
            if i and d['quarter'] >= 5 and drives[i - 1]['quarter'] < 5: how = 'to open overtime'
            elif i and d['quarter'] == 3 and drives[i - 1]['quarter'] <= 2: how = 'to open the second half'
            d['head'] = f"Drive {d['n']} · {d['off']} · {ticker.drive_start_text(d['start_label'], d.get('return_only', False))} {how}".rstrip() + f" · {d['plays_n']} play{'s' if d['plays_n'] != 1 else ''}, {int(round(d['yards']))} net field yards (including penalties)" + (f", {str(d['result']).lower()}" if d.get('result') else '')
            prev_result = d.get('result')
        out['game'] = dict(home=home, away=away, hs=res['home'], as_=res['away'], ot=bool(res.get('overtime')), me=user, opp=opp, me_home=me_home,
                           drives=drives, wp=wp, box=box, box_version=2, injuries=injuries, env=res.get('env', {}), team_stats=team_stats, reads=reads, quarters=quarters,
                           home_rec=list(getattr(league.teams[home], 'record', [])), away_rec=list(getattr(league.teams[away], 'record', [])))
    return out
