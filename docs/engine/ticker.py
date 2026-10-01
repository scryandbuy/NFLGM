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
    from views import surname
    return surname(p.name)                                   # 'Mathieu Jr.', not 'Jr.' or 'Mathieu'


def _clock(secs):
    # a play at exactly the edge of a quarter (2700, 1800, 900 seconds left) is the first snap of the next one
    secs = round(float(secs), 2)                             # a play that lands a hair off the edge is on the edge
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
    if 0 < yardline_100 < 1.0: return f"inside the {def_abbr} 1"
    if y > 50: return f"{off_abbr} {max(1, 100 - y)}"
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
    return ('loss', f"a loss of {-y} yard{'s' if -y != 1 else ''}")


def play_line(league, p, off_abbr, def_abbr):
    """Returns dict(head, text, kind) for one play dict. kind: gain|loss|score|turnover|special|neutral."""
    t = p.get('type')
    head = ''
    if p.get('down') is not None:
        q, ck = _clock(p.get('clock', 0))
        head = f"{_down(p.get('down'), p.get('ydstogo'), p.get('yardline'))} · {_spot(p.get('yardline', 50), off_abbr, def_abbr)} · {ck}"
    elif p.get('clock') is not None and t in ('kickoff', 'penalty', 'timeout'):
        head = _clock(p['clock'])[1]
    carrier = _nm(league, p.get('carrier')); passer = _nm(league, p.get('passer')); target = _nm(league, p.get('target')); tackler = _nm(league, p.get('tackler'))
    td = bool(p.get('touchdown') and not p.get('defensive_td'))
    spot = float(p.get('yardline') or 0)
    gain = float(p.get('yards') or 0)
    near_goal_short = (t in ('run', 'complete', 'scramble') and not td and not p.get('nullified')
                       and 0 < gain < spot and 0 < spot - round(gain) < 1)
    kind = 'neutral'; text = ''
    if t == 'run':
        cls, yd = _yards(p.get('yards', 0))
        who = carrier or 'The back'
        how = {'inside_zone': 'up the middle', 'duo': 'between the tackles', 'power': 'behind the pulling guard', 'counter': 'on a counter', 'trap': 'on a trap',
               'outside_zone': 'off the edge', 'stretch': 'wide on the stretch', 'draw': 'on a draw', 'toss': 'on a toss', 'sweep': 'on a sweep'}.get(p.get('scheme'), 'inside' if p.get('sneak') else '')
        text = f"{who} {'sneaks' if p.get('sneak') else 'runs'}{(' ' + how) if how else ''} {'to inside the 1' if near_goal_short else 'for ' + yd}"
        if td:
            yl = float(p.get('yardline', 1) or 1)
            origin = 'inside the 1' if 0 < yl < 1 else f'the {int(round(yl))}'
            text = f"{who} runs it in from {origin}. TOUCHDOWN."; kind = 'score'
        else:
            kind = cls
            if p.get('broken_tackles'): text += f", breaking {int(p['broken_tackles'])} tackle{'s' if p['broken_tackles'] > 1 else ''}"
            text += (f". Tackled by {tackler}" + ('' if tackler.endswith('.') else '.')) if tackler else '.'
    elif t == 'complete':
        cls, yd = _yards(p.get('yards', 0))
        if td and 0 < gain < .5: yd = 'less than a yard'
        pre = 'Play action. ' if p.get('play_action') else ''
        press_name = passer or 'the quarterback'
        pres = f"Pressure on {press_name}{'' if press_name.endswith('.') else '.'} " if p.get('pressured') else ''
        gain_phrase = ('and is stopped inside the 1' if near_goal_short else
                       'for a touchdown from inside the 1' if td and 0 < spot < 1 else f'for {yd}')
        if p.get('screen'):
            text = f"{pre}{pres}{passer or 'The quarterback'} to {target or 'his receiver'} on a screen {gain_phrase}"
        elif p.get('swing'):
            text = f"{pre}{pres}{passer or 'The quarterback'} {'swings it to' if (p.get('yards', 0) or 0) >= 0 else 'checks down to'} {target or 'his back'} in the flat {gain_phrase}"
        else:
            text = f"{pre}{pres}{passer or 'The quarterback'} to {target or 'his receiver'} {gain_phrase}"
        if td:
            text += '.' if 0 < spot < 1 else '. TOUCHDOWN.'
            kind = 'score'
        else:
            kind = cls
            text += (f". Tackled by {tackler}" + ('' if tackler.endswith('.') else '.')) if tackler else '.'
    elif t == 'incomplete':
        pd = _nm(league, p.get('pass_def'))
        if p.get('throwaway'):
            text = f"{passer or 'The quarterback'} throws the ball away under pressure."
        else:
            text = f"{passer or 'The quarterback'} throws to {target or 'his receiver'}, incomplete" + (f". {pd} breaks it up." if pd else ('. Under pressure.' if p.get('pressured') else '.'))
        kind = 'neutral'
    elif t == 'drop':
        text = f"{passer or 'The quarterback'} to {target or 'his receiver'}, dropped."; kind = 'loss'
    elif t == 'sack':
        by = _nm(league, p.get('by')); beaten = _nm(league, p.get('beaten'))
        loss = int(round(-gain))
        text = f"{by or 'The rush'} sacks {passer or 'the quarterback'}" + (f" for a loss of {loss}" if loss else ' at the line of scrimmage') + (f", beating {beaten}{'' if beaten.endswith('.') else '.'}" if beaten else '.')
        kind = 'loss'
    elif t == 'scramble':
        cls, yd = _yards(p.get('yards', 0))
        text = f"{passer or 'The quarterback'} scrambles {'to inside the 1' if near_goal_short else 'for ' + yd}" + ((f". Tackled by {tackler}" + ('' if tackler.endswith('.') else '.')) if tackler else '.')
        if td: text = f"{passer or 'The quarterback'} scrambles in. TOUCHDOWN."; kind = 'score'
        else: kind = cls
    elif t == 'interception':
        by = _nm(league, p.get('by') or p.get('pass_def'))
        touchback = p.get('touchback')
        if touchback is None and p.get('yardline') is not None and p.get('air') is not None:
            caught = float(p['yardline']) - float(p['air'])
            touchback = caught <= 0 and caught + float(p.get('ret', 0) or 0) <= 0
        text = f"{passer or 'The quarterback'} throws to {target or 'his receiver'}, INTERCEPTED by {by or 'the defense'}" + (", touchback." if touchback else f", returned {int(round(p.get('ret', 0)))} yards." if p.get('ret') else '.')
        kind = 'turnover'
        if p.get('defensive_td'):
            text += f' TOUCHDOWN, {def_abbr}.'
            kind = 'score'
    elif t == 'fumble':
        who = carrier or target or passer or 'The ball carrier'
        text = f"{who} fumbles" + (". Recovered by the defense." if p.get('lost', True) else ". Recovered by the offense.")
        kind = 'turnover' if p.get('lost', True) else 'loss'
    elif t == 'punt':
        if p.get('blocked'):
            text = 'Punt BLOCKED.'; kind = 'turnover'
            if p.get('dead_end_line'):
                text += ' The ball goes out through the kicking team’s end zone.'
            elif p.get('recovery'):
                team = off_abbr if p['recovery'] == 'kicking' else def_abbr
                name = _nm(league, p.get('recoverer'))
                spot = _spot(p['recovery_spot'], off_abbr, def_abbr) if 0 < p['recovery_spot'] < 100 else 'the end zone'
                text += f" Recovered by {name + ' (' + team + ')' if name else team} at {spot}."
                if p.get('advance') and not p.get('touchdown') and not p.get('safety'):
                    text += f" Advanced to {_spot(p['end_spot'], off_abbr, def_abbr)}."
                if p.get('touchdown'):
                    text += f' TOUCHDOWN, {team}.'; kind = 'score'
                elif not p.get('safety'):
                    text += f' {off_abbr} keeps possession with a first down.' if p.get('retained') else f' {def_abbr} takes possession.'
                    if p.get('retained'): kind = 'special'
        else:
            _ny = p.get('new_yardline')
            _down_spot = _spot(100.0 - float(_ny), off_abbr, def_abbr) if _ny is not None else None
            ret = int(p.get('display_ret', round(p.get('ret', 0))))
            gross = int(p.get('display_gross', round(p.get('gross', 0))))
            text = f"Punt, {gross} yards" + (", touchback." if p.get('touchback') else (f", returned {ret} yard{'s' if ret != 1 else ''}." if p.get('how') == 'return' and p.get('ret') else (", fair catch." if p.get('how') == 'fair_catch' else (f", downed at the {_down_spot}." if p.get('how') == 'downed' and _down_spot else '.'))))
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
        yds = abs(float(p.get('yards', 0) or 0)); rule = p.get('rule_yards', E.RULE_YARDS.get(p.get('penalty')))
        half = p.get('penalty') != 'Defensive Pass Interference' and rule is not None and yds < rule - 0.01
        ydtxt = 'half the distance to the goal' if half else f"{yds:g} yard{'s' if yds != 1 else ''}"
        if p.get('end_zone'): ydtxt = f"in the end zone, ball placed at the {float(p.get('spot', 1)):g}"
        if p.get('safety'): ydtxt = 'in the end zone, SAFETY'
        if p.get('on_try'): ydtxt += ', enforced on the try'
        if p.get('try_type'):
            ydtxt += ', on the ' + ('extra-point attempt' if p['try_type'] == 'extra_point' else 'two-point attempt')
        elif p.get('timing') == 'before_snap':
            ydtxt += ', before the next snap; no play occurred'
        ending = (', loss of down.' if p.get('penalty') == 'Intentional Grounding' and not p.get('safety') else
                  ', automatic first down.' if (p.get('auto_first') and not p.get('on_offense') and not p.get('on_try')) else '.')
        text = f"Penalty, {p.get('penalty', 'flag')} on the {side}, {ydtxt}" + ending
        kind = 'neutral'
    elif t == 'kickoff':
        who = carrier if p.get('carrier') and not p.get('touchback') else None
        spot = _spot(float(p.get('new_yardline', 75)), off_abbr, def_abbr)
        if p.get('free_kick'):
            text = f"Free kick after the safety; {off_abbr} takes over at the {spot}."; kind = 'special'
        elif p.get('onside'):
            text = f"Onside kick, {'RECOVERED by the kicking team' if p.get('recovered') else 'recovered by ' + off_abbr} at the {spot}."; kind = 'turnover' if p.get('recovered') else 'special'
        else:
            text = "Kickoff" + (", touchback." if p.get('touchback') else (f", returned by {who} {int(round(p.get('ret', 0)))} yards to the {spot}." if who else f", returned to the {spot}.")); kind = 'special'
        if p.get('ends_period'):
            text += ' Time expires in ' + ('the first half.' if p.get('quarter') == 2 else 'overtime.' if p.get('quarter', 0) >= 5 else 'regulation.')
    elif t == 'injury':
        who = _nm(league, p.get('pid')) or 'A player'
        wk = int(p.get('weeks') or 0)
        text = f"{who} ({p.get('pos', '')}) is hurt on the play" + (' and will not return.' if wk >= 2 else '; he is done for the day.' if wk == 1 else '.'); kind = 'neutral'
    elif t == 'timeout':
        text = f"Timeout, {'the offense' if p.get('side') == 'off' else p.get('side_abbr') or p.get('side', '').upper()} ({p.get('left', 0)} left)."; kind = 'neutral'
    elif t == 'two_minute':
        text = 'Two-minute warning.'; kind = 'neutral'
    elif t == 'period':
        q = int(p.get('quarter', 1))
        text = ('Overtime begins.' if q >= 5 else 'Halftime. Third quarter begins.' if q == 3 else f'End of Q{q - 1}. Q{q} begins.')
        kind = 'neutral'
    elif t in ('audible', 'kneel', 'spike'):
        text = {'kneel': f"{passer or 'The quarterback'} kneels.", 'spike': f"{passer or 'The quarterback'} spikes it."}.get(t, ''); kind = 'neutral'
        if not text: return None
    else:
        return None
    if p.get('fumble'):
        recoverer = _nm(league, p.get('fumble_recovered_by'))
        if p.get('fumble_lost'):
            recovery = f'{recoverer} ({def_abbr})' if recoverer else def_abbr
            text = (text.rstrip('.') + f'. FUMBLE, recovered by {recovery}.') if text else f'FUMBLE, recovered by {recovery}.'
            if p.get('ret'):
                text += f" Returned {int(round(p['ret']))} yards."
            if p.get('defensive_td'):
                text += f' TOUCHDOWN, {def_abbr}.'
                kind = 'score'
            else:
                kind = 'turnover'
        else:
            text = (text.rstrip('.') + '. Fumbles, and the offense recovers.') if text else 'Fumble, recovered.'
    if p.get('safety'):
        text = (text.rstrip('.') + '. SAFETY.') if text else 'SAFETY.'; kind = 'turnover'
    if p.get('nullified'):
        text = (text.rstrip('.') + '. Play nullified by penalty.') if text else 'Play nullified by penalty.'
        kind = 'neutral'
    return dict(head=head, text=text, kind=kind, type=t, made=p.get('made'), safety=bool(p.get('safety')), nullified=bool(p.get('nullified')))


def _result_word(r):
    return {'Touchdown': 'touchdown', 'Defensive touchdown': 'defensive touchdown', 'Field goal': 'field goal', 'Punt': 'punt', 'Turnover': 'turnover', 'Interception': 'interception', 'Fumble': 'fumble',
            'Missed FG': 'missed field goal', 'End of half': 'end of half', 'End of game': 'end of game', 'Turnover on downs': 'turnover on downs', 'Safety': 'safety'}.get(r, str(r).lower() if r else '')


def drive_result(dr, overtime=False):
    """Distinguish the regulation boundary from the actual end of a game."""
    if dr.result == 'End of half' and getattr(dr, 'quarter', 0) >= 4:
        return 'End of regulation' if dr.quarter == 4 and overtime else 'End of game'
    return dr.result


def offensive_drive_end(dr):
    """Exclude defensive return yards from offensive drive progress."""
    if dr.result in ('Turnover', 'Interception', 'Defensive touchdown'):
        interception = next((p for p in reversed(dr.log) if isinstance(p, dict)
                             and p.get('type') == 'interception' and not p.get('nullified')), None)
        if interception is not None and interception.get('yardline') is not None:
            return float(interception['yardline'])
        fumble = next((p for p in reversed(dr.log) if isinstance(p, dict)
                       and p.get('fumble_lost') and not p.get('nullified')), None)
        if fumble is not None:
            if fumble.get('return_start') is not None:
                return float(fumble['return_start'])
            if fumble.get('yardline') is not None:
                return float(fumble['yardline']) - float(fumble.get('yards', 0) or 0)
    return float(getattr(dr, 'yardline', getattr(dr, 'start', 75)))


def write_game(league, res, home, away):
    """The whole game as drives: header, lines, and the numbers the drive chart needs."""
    out = []
    for i, (pos, dr) in enumerate(res['drives']):
        off = home if pos == 'home' else away; deff = away if pos == 'home' else home
        lines = [x for x in (play_line(league, p,
                 home if p.get('possession', pos) == 'home' else away,
                 away if p.get('possession', pos) == 'home' else home)
                 for p in dr.log if isinstance(p, dict)) if x]
        real = [p for p in dr.log if isinstance(p, dict) and not p.get('nullified') and p.get('type') in ('run', 'complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble', 'kneel', 'spike', 'punt', 'field_goal')]
        yards = sum(float(p.get('yards', 0) or 0) for p in real if p.get('type') in ('run', 'complete', 'sack', 'scramble', 'kneel'))
        q = int(getattr(dr, 'quarter', 1) or 1)
        start = float(getattr(dr, 'start', 75)); end = offensive_drive_end(dr)
        secs = 0.0
        if real:
            c0 = real[0].get('clock'); c1 = real[-1].get('clock')
            if c0 is not None and c1 is not None: secs = max(0.0, float(c0) - float(c1))
        result = drive_result(dr, res.get('overtime', False))
        header = f"Drive {i + 1} · {off} · Q{q} · Started at the {_spot(start, off, deff)} · {len(real)} play{'s' if len(real) != 1 else ''}, {int(round(yards))} yard{'s' if int(round(yards)) != 1 else ''}" + (f", {int(secs // 60)}:{int(secs % 60):02d}" if secs else '') + (f" · {_result_word(result)}" if result else '')
        out.append(dict(index=i + 1, team=off, quarter=q, start=round(100 - start, 1), end=round(100 - end, 1), result=result, points=int(getattr(dr, 'points', 0) or 0),
                        header=header, lines=lines))
    return out
