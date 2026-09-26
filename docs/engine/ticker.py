"""
THE TICKER. Every play as one sentence about the people: who got the ball,
what happened, who made the stop. Down, spot and clock on every line so the
reader never loses the situation. No formation, personnel or box counts.

  write_game(league, res, home, away)  -> list of drives, each with header and lines
"""
import math


def _nm(league, pid, short=True):
    p = league.player(pid) if pid else None
    if p is None: return None
    if not short: return p.name
    parts = p.name.split()
    return parts[-1] if len(parts) == 1 else (parts[-1] if parts[-1] not in ('Jr.', 'II', 'III', 'Sr.') else parts[-2])


def _clock(secs):
    # a play at exactly the edge of a quarter (2700, 1800, 900 seconds left) is the first snap of the next one
    q = int((3600 - secs) // 900) + 1 if secs > 0 else 4
    q = max(1, min(q, 4))
    rem = secs - (4 - q) * 900
    if rem <= 0 and q < 4 and secs > 0:
        q += 1; rem = 900.0
    rem = max(0.0, rem)
    return q, f"{int(rem // 60)}:{int(rem % 60):02d}"


def _spot(yardline_100, off_abbr, def_abbr):
    """yardline is yards to the end zone. 60 means own 40."""
    y = int(round(yardline_100))
    if y > 50: return f"{off_abbr} {100 - y}"
    if y == 50: return "50"
    return f"{def_abbr} {y}"


def _down(d, togo, yardline):
    if d is None: return ''
    word = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th'}.get(int(d), str(d))
    if yardline is not None and togo is not None and togo >= yardline - 0.01: return f"{word} & Goal"
    return f"{word} & {int(round(togo))}" if togo is not None else word


def _yards(y):
    y = int(round(y))
    if y > 0: return ('gain', f"{y} yard{'s' if y != 1 else ''}")
    if y == 0: return ('none', "no gain")
    return ('loss', f"loss of {-y} yard{'s' if -y != 1 else ''}")


def play_line(league, p, off_abbr, def_abbr):
    """Returns dict(head, text, kind) for one play dict. kind: gain|loss|score|turnover|special|neutral."""
    t = p.get('type')
    head = ''
    if p.get('down') is not None:
        q, ck = _clock(p.get('clock', 0))
        head = f"{_down(p.get('down'), p.get('ydstogo'), p.get('yardline'))} · {_spot(p.get('yardline', 50), off_abbr, def_abbr)} · {ck}"
    carrier = _nm(league, p.get('carrier')); passer = _nm(league, p.get('passer')); target = _nm(league, p.get('target')); tackler = _nm(league, p.get('tackler'))
    td = bool(p.get('touchdown'))
    kind = 'neutral'; text = ''
    if t == 'run':
        cls, yd = _yards(p.get('yards', 0))
        who = carrier or 'The back'
        how = 'up the middle' if p.get('scheme') in ('inside_zone', 'duo', 'power') else 'off the edge' if p.get('scheme') in ('outside_zone', 'toss', 'sweep') else 'inside' if p.get('sneak') else ''
        text = f"{who} {'sneaks' if p.get('sneak') else 'runs'}{(' ' + how) if how else ''} for {yd}"
        if td: text = f"{who} runs it in from the {int(round(p.get('yardline', 1)))}. TOUCHDOWN."; kind = 'score'
        else:
            kind = cls
            if p.get('broken_tackles'): text += f", breaking {int(p['broken_tackles'])} tackle{'s' if p['broken_tackles'] > 1 else ''}"
            text += f". Tackled by {tackler}." if tackler else '.'
    elif t == 'complete':
        cls, yd = _yards(p.get('yards', 0))
        pre = 'Play action. ' if p.get('play_action') else ''
        pres = f"Pressure on {passer or 'the quarterback'}. " if p.get('pressured') else ''
        text = f"{pre}{pres}{passer or 'The quarterback'} to {target or 'his receiver'}" + (" on a screen" if p.get('screen') else '') + f" for {yd}"
        if td: text += f". TOUCHDOWN."; kind = 'score'
        else:
            kind = cls
            text += f". Tackled by {tackler}." if tackler else '.'
    elif t == 'incomplete':
        pd = _nm(league, p.get('pass_def'))
        text = f"{passer or 'The quarterback'} throws to {target or 'his receiver'}, incomplete" + (f". {pd} breaks it up." if pd else ('. Under pressure.' if p.get('pressured') else '.'))
        kind = 'neutral'
    elif t == 'drop':
        text = f"{passer or 'The quarterback'} to {target or 'his receiver'}, dropped."; kind = 'loss'
    elif t == 'sack':
        by = _nm(league, p.get('by')); beaten = _nm(league, p.get('beaten'))
        text = f"{by or 'The rush'} sacks {passer or 'the quarterback'} for a loss of {int(round(-p.get('yards', 0)))}" + (f", beating {beaten}." if beaten else '.')
        kind = 'loss'
    elif t == 'scramble':
        cls, yd = _yards(p.get('yards', 0))
        text = f"{passer or 'The quarterback'} scrambles for {yd}" + (f". Tackled by {tackler}." if tackler else '.')
        if td: text = f"{passer or 'The quarterback'} scrambles in. TOUCHDOWN."; kind = 'score'
        else: kind = cls
    elif t == 'interception':
        by = _nm(league, p.get('by') or p.get('pass_def'))
        text = f"{passer or 'The quarterback'} throws to {target or 'his receiver'}, INTERCEPTED by {by or 'the defense'}" + (f", returned {int(round(p.get('ret', 0)))} yards." if p.get('ret') else '.')
        kind = 'turnover'
    elif t == 'fumble':
        who = carrier or target or passer or 'The ball carrier'
        text = f"{who} fumbles" + (". Recovered by the defense." if p.get('lost', True) else ". Recovered by the offense.")
        kind = 'turnover' if p.get('lost', True) else 'loss'
    elif t == 'punt':
        if p.get('blocked'): text = "Punt BLOCKED."; kind = 'turnover'
        else:
            text = f"Punt, {int(round(p.get('gross', 0)))} yards" + (", touchback." if p.get('touchback') else (f", returned {int(round(p.get('ret', 0)))} yards." if p.get('how') == 'return' and p.get('ret') else (", fair catch." if p.get('how') == 'fair_catch' else '.')))
            kind = 'special'
    elif t == 'field_goal':
        d = int(round(p.get('distance', 0)))
        text = f"{d}-yard field goal is {'GOOD.' if p.get('made') else 'NO GOOD.'}"
        kind = 'score' if p.get('made') else 'loss'
    elif t == 'extra_point':
        text = f"Extra point is {'good.' if p.get('made', True) else 'NO GOOD.'}"; kind = 'special'
    elif t == 'two_point':
        text = f"Two-point try is {'GOOD.' if p.get('made') else 'no good.'}"; kind = 'score' if p.get('made') else 'loss'
    elif t == 'penalty':
        side = 'defense' if not p.get('on_offense') else 'offense'
        import events as E
        yds = abs(float(p.get('yards', 0) or 0)); rule = E.RULE_YARDS.get(p.get('penalty'))
        half = rule is not None and yds < rule - 0.01
        ydtxt = (f"{yds:g} yards" if yds != 1 else '1 yard') + (', half the distance to the goal' if half else '')
        if p.get('end_zone'): ydtxt = 'in the end zone, ball placed at the 1'
        text = f"Penalty, {p.get('penalty', 'flag')} on the {side}, {ydtxt}" + (", automatic first down." if (p.get('auto_first') and not p.get('on_offense')) else '.')
        kind = 'neutral'
    elif t == 'kickoff':
        who = carrier if p.get('carrier') and not p.get('touchback') else None
        spot = _spot(float(p.get('new_yardline', 75)), off_abbr, def_abbr)
        text = "Kickoff" + (", touchback." if p.get('touchback') else (f", returned by {who} {int(round(p.get('ret', 0)))} yards to the {spot}." if who else f", returned to the {spot}.")); kind = 'special'
    elif t == 'injury':
        who = _nm(league, p.get('pid')) or 'A player'
        wk = int(p.get('weeks') or 0)
        text = f"{who} ({p.get('pos', '')}) is hurt on the play" + (' and will not return.' if wk >= 2 else '; he is done for the day.' if wk == 1 else '.'); kind = 'neutral'
    elif t == 'timeout':
        text = f"Timeout, {'the offense' if p.get('side') == 'off' else p.get('side_abbr') or p.get('side', '').upper()} ({p.get('left', 0)} left)."; kind = 'neutral'
    elif t == 'two_minute':
        text = 'Two-minute warning.'; kind = 'neutral'
    elif t in ('audible', 'kneel', 'spike'):
        text = {'kneel': f"{passer or 'The quarterback'} kneels.", 'spike': f"{passer or 'The quarterback'} spikes it."}.get(t, ''); kind = 'neutral'
        if not text: return None
    else:
        return None
    if p.get('nullified'):
        text = (text.rstrip('.') + '. No play; flag on the field.') if text else 'No play; flag on the field.'; kind = 'neutral'
    if p.get('fumble'):
        text = (text.rstrip('.') + (f". FUMBLE, recovered by {def_abbr}." if p.get('fumble_lost') else ". Fumbles, and the offense recovers.")) if text else ('FUMBLE.' if p.get('fumble_lost') else 'Fumble, recovered.')
        if p.get('fumble_lost'): kind = 'turnover'
    if p.get('safety'):
        text = (text.rstrip('.') + '. SAFETY.') if text else 'SAFETY.'; kind = 'turnover'
    return dict(head=head, text=text, kind=kind, type=t, made=p.get('made'), safety=bool(p.get('safety')), nullified=bool(p.get('nullified')))


def _result_word(r):
    return {'Touchdown': 'touchdown', 'Field goal': 'field goal', 'Punt': 'punt', 'Turnover': 'turnover', 'Interception': 'interception', 'Fumble': 'fumble',
            'Missed FG': 'missed field goal', 'End of half': 'end of half', 'End of game': 'end of game', 'Turnover on downs': 'turnover on downs', 'Safety': 'safety'}.get(r, str(r).lower() if r else '')


def write_game(league, res, home, away):
    """The whole game as drives: header, lines, and the numbers the drive chart needs."""
    out = []
    for i, (pos, dr) in enumerate(res['drives']):
        off = home if pos == 'home' else away; deff = away if pos == 'home' else home
        lines = [x for x in (play_line(league, p, off, deff) for p in dr.log if isinstance(p, dict)) if x]
        real = [p for p in dr.log if isinstance(p, dict) and p.get('type') not in ('penalty', 'audible', 'extra_point')]
        yards = sum(float(p.get('yards', 0) or 0) for p in real if p.get('type') in ('run', 'complete', 'sack', 'scramble'))
        q = int(getattr(dr, 'quarter', 1) or 1)
        start = float(getattr(dr, 'start', 75) or 75); end = float(getattr(dr, 'yardline', start) or start)
        secs = 0.0
        if real:
            c0 = real[0].get('clock'); c1 = real[-1].get('clock')
            if c0 is not None and c1 is not None: secs = max(0.0, float(c0) - float(c1))
        header = f"Drive {i + 1} · {off} · Q{q} · Started at the {_spot(start, off, deff)} · {len(real)} play{'s' if len(real) != 1 else ''}, {int(round(yards))} yard{'s' if int(round(yards)) != 1 else ''}" + (f", {int(secs // 60)}:{int(secs % 60):02d}" if secs else '') + (f" · {_result_word(dr.result)}" if dr.result else '')
        out.append(dict(index=i + 1, team=off, quarter=q, start=round(100 - start, 1), end=round(100 - end, 1), result=dr.result, points=int(getattr(dr, 'points', 0) or 0),
                        header=header, lines=lines))
    return out
