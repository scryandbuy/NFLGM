"""
HALFTIME. The assistants read the first half from the drive logs and say what to change: the base plan,
the pregame recommendations the GM accepted, and how the game has actually gone. Each recommendation
carries the same shape as a pregame one (side, text, why, changes) so the GM accepts or declines it the
same way, and what he accepts is applied to the plan the second half reads.
"""
import numpy as np

SCRIM = ('run', 'scramble', 'complete', 'incomplete', 'drop', 'interception', 'sack')


def first_half(drives, me_side):
    """Totals for one side from the drive logs so far. me_side is 'home' or 'away'."""
    def fresh(): return dict(runs=0, run_yds=0.0, passes=0, pass_yds=0.0, cmp=0, sacks=0, pressures=0, screens=0, screen_yds=0.0,
                             deep=0, deep_cmp=0, deep_yds=0.0, int=0, fum=0, third=0, third_conv=0, blitz_faced=0, blitz_yds=0.0,
                             box8=0, two_high=0, snaps=0, first_downs=0, points=0, drives=0)
    me, them = fresh(), fresh()
    for pos, dr in drives:
        t = me if pos == me_side else them
        t['drives'] += 1; t['points'] += max(0, int(getattr(dr, 'points', 0) or 0)); t['first_downs'] += int(getattr(dr, 'first_downs', 0) or 0)
        for p in getattr(dr, 'log', []):
            ty = p.get('type')
            if ty not in SCRIM or p.get('nullified'): continue
            y = float(p.get('yards', 0.0) or 0.0); t['snaps'] += 1
            if ty in ('run', 'scramble'): t['runs'] += 1; t['run_yds'] += y
            else:
                t['passes'] += 1
                if ty == 'complete': t['cmp'] += 1; t['pass_yds'] += y
                if ty == 'sack': t['sacks'] += 1; t['pass_yds'] += y
                if p.get('pressured'): t['pressures'] += 1
                if p.get('screen'): t['screens'] += 1; t['screen_yds'] += y
                if (p.get('depth') or '') == 'deep' or float(p.get('air', 0) or 0) >= 20:
                    t['deep'] += 1
                    if ty == 'complete': t['deep_cmp'] += 1; t['deep_yds'] += y
                if ty == 'interception': t['int'] += 1
                if p.get('blitz'): t['blitz_faced'] += 1; t['blitz_yds'] += y
            if p.get('fumble_lost'): t['fum'] += 1
            if p.get('down') == 3:
                t['third'] += 1
                if p.get('touchdown') or y >= float(p.get('ydstogo', 10) or 10): t['third_conv'] += 1
            if p.get('box') and int(p.get('box')) >= 8: t['box8'] += 1
            if str(p.get('shell', '')).lower() in ('two_high', 'quarters', 'cover2', 'two-high', '2-high', 'cover 2', 'cover 4'): t['two_high'] += 1
    return me, them


def recommendations(league, me_abbr, opp_abbr, drives, me_side, score, plan, base):
    """What the assistants would change at the break. Returns a list of dict(side, text, why, changes)."""
    me, them = first_half(drives, me_side)
    out = []
    def sug(side, text, why, changes): out.append(dict(side=side, text=text, why=why, changes=changes))
    ypc = me['run_yds'] / me['runs'] if me['runs'] >= 6 else None
    ypa = me['pass_yds'] / me['passes'] if me['passes'] >= 8 else None
    tx = (score.get(me_side, 0) or 0) - (score.get('away' if me_side == 'home' else 'home', 0) or 0)
    # ---- offense: what is and is not working
    if ypc is not None and ypc >= 5.2 and me['runs'] < me['passes']:
        sug('offence', 'Stay on the ground: the run is working', f"{ypc:.1f} a carry on {me['runs']} runs; we have thrown {me['passes']} times", {'pass_bias': -0.06, 'heavy_lean': +0.4})
    if ypc is not None and ypc <= 2.6 and me['runs'] >= 8:
        sug('offence', 'The run is not there: throw more, spread them out', f"{ypc:.1f} a carry on {me['runs']} runs", {'pass_bias': +0.06, 'heavy_lean': -0.4})
    if me['passes'] >= 10 and me['sacks'] + me['pressures'] >= 0.35 * me['passes']:
        sug('offence', 'Protect: keep a back in, quick game, screens', f"pressure or a sack on {me['sacks'] + me['pressures']} of {me['passes']} dropbacks", {'protection': 'six', 'depth_mix': (+0.08, -0.05, -0.03), 'screen_boost': +0.03, 'heavy_lean': +0.3})
    if me['deep'] >= 3 and me['deep_cmp'] == 0:
        sug('offence', 'Stop taking the shots: work the intermediate game', f"0 for {me['deep']} on throws twenty yards down the field", {'depth_mix': (+0.02, +0.06, -0.08)})
    if me['deep'] >= 2 and me['deep_cmp'] >= 2 and me['deep_yds'] >= 60:
        sug('offence', 'Keep attacking down the field', f"{me['deep_cmp']} of {me['deep']} deep throws for {me['deep_yds']:.0f} yards", {'depth_mix': (-0.05, 0.0, +0.05), 'play_action_rate': +0.05})
    if me['screens'] >= 3 and me['screen_yds'] / max(1, me['screens']) <= 1.0:
        sug('offence', 'Shelve the screens', f"{me['screens']} screens for {me['screen_yds']:.0f} yards", {'screen_boost': -0.05})
    if me['blitz_faced'] >= 4 and me['blitz_yds'] / me['blitz_faced'] >= 8.0:
        sug('offence', 'They are blitzing and it is costing them: keep throwing into it', f"{me['blitz_yds'] / me['blitz_faced']:.1f} a play when they bring pressure", {'depth_mix': (-0.03, +0.03, 0.0), 'play_action_rate': +0.04})
    if me['third'] >= 4 and me['third_conv'] / me['third'] <= 0.25:
        sug('offence', 'Third down is killing us: shorter throws, stay ahead of the chains', f"{me['third_conv']} of {me['third']} on third down", {'depth_mix': (+0.06, -0.03, -0.03), 'pass_bias': -0.02})
    if me['int'] + me['fum'] >= 2:
        sug('offence', 'Protect the ball: fewer risks, more play action off the run', f"{me['int'] + me['fum']} turnovers in the half", {'pass_bias': -0.04, 'depth_mix': (+0.05, 0.0, -0.05)})
    # ---- defense: what they are doing to us
    typc = them['run_yds'] / them['runs'] if them['runs'] >= 6 else None
    typa = them['pass_yds'] / them['passes'] if them['passes'] >= 8 else None
    if typc is not None and typc >= 5.0:
        sug('defence', 'They are running through us: heavier fronts, more in the box', f"{typc:.1f} a carry on {them['runs']} runs", {'box_bias': +0.06, 'sub_lean': -0.5, 'blitz_lean': -0.02})
    if typa is not None and typa >= 8.5:
        sug('defence', 'They are carving us up: more sub packages, two-high', f"{typa:.1f} an attempt on {them['passes']} throws", {'sub_lean': +0.5, 'shell_lean': +0.08, 'man_rate': -0.06})
    if them['deep_cmp'] >= 2:
        sug('defence', 'Take the deep ball away: keep two safeties back', f"{them['deep_cmp']} completions over twenty yards", {'shell_lean': +0.10, 'blitz_lean': -0.04})
    if them['passes'] >= 10 and them['sacks'] + them['pressures'] <= 0.12 * them['passes']:
        sug('defence', 'We are not getting home: bring pressure', f"a sack or a pressure on {them['sacks'] + them['pressures']} of {them['passes']} dropbacks", {'blitz_lean': +0.06})
    if them['blitz_faced'] == 0 and them['passes'] >= 10 and typa is not None and typa <= 5.5:
        pass
    if them['third'] >= 4 and them['third_conv'] / them['third'] >= 0.6:
        sug('defence', 'They are converting third downs: tighter coverage underneath', f"{them['third_conv']} of {them['third']} on third down", {'zone_aggression': +0.08, 'man_rate': +0.05})
    if them['screens'] >= 3 and them['screen_yds'] / them['screens'] >= 7.0:
        sug('defence', 'Their screens are working: less blitz, keep the edges home', f"{them['screens']} screens for {them['screen_yds']:.0f} yards", {'blitz_lean': -0.05})
    # ---- the score
    if tx <= -10:
        sug('offence', 'We are down two scores: pick up the tempo, throw to move', f"down {-tx} at the half", {'tempo': +0.2, 'pass_bias': +0.05})
    if tx >= 14 and (ypc is None or ypc >= 3.5):
        sug('offence', 'Up two scores: shorten the game, run it', f"up {tx} at the half", {'tempo': -0.2, 'pass_bias': -0.05, 'heavy_lean': +0.3})
    return out[:6]
