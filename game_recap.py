"""One saved, evidence-based assistant review per completed user game. No RNG."""
import copy
import inbox_events as IE
from inbox import player_name as inbox_player

SCRIMMAGE = {'run', 'scramble', 'complete', 'incomplete', 'drop', 'interception', 'sack'}
TWO_HIGH = {'cover_2', 'cover_4', 'cover_6', 'two_man', 'tampa_2', 'quarters'}


def capture(league, state, week):
    """Freeze the plan actually installed at kickoff, before it resets at full time."""
    wp = getattr(league, 'user_week_plan', None) or {}
    if wp.get('year') != league.year or wp.get('week') != week:
        return dict(changes={}, taken=[])
    changes = {k: copy.deepcopy(v) for k, v in wp.get('changes', {}).items()
               if hasattr(state.plan, k)}
    return dict(changes=changes, taken=list(wp.get('taken', [])),
                recommendations=[dict(text=text,
                                      changes=copy.deepcopy({k:v for k,v in ch.items() if k not in wp.get('manual', {})}),
                                      overridden=[k for k in ch if k in wp.get('manual', {})])
                                 for text, ch in wp.get('suggestions', {}).items()],
                installed={k: copy.deepcopy(getattr(state.plan, k)) for k in changes})


def plays(res, side, half=None):
    out = []
    for pos, drive in res.get('drives', []):
        if pos != side: continue
        q = getattr(drive, 'start_quarter', getattr(drive, 'quarter', 1))
        logged = getattr(drive, 'log', [])
        for index, p in enumerate(logged):
            if not isinstance(p, dict): continue
            if p.get('type') == 'period': q = p.get('quarter', q)
            if p.get('type') not in SCRIMMAGE or p.get('nullified'): continue
            # Play clock is seconds remaining in regulation; overtime is separate.
            pq = p.get('quarter', q)
            period = 3 if pq > 4 else (1 if p.get('clock', 1801 if pq <= 2 else 1800) > 1800 else 2)
            if half is None or half == period or (half == 'after_break' and period in (2, 3)):
                row = dict(p, score_diff=getattr(drive, 'score_diff', p.get('score_diff')))
                # Compare continuous in-bounds snap intervals only. Never
                # measure pace across possessions, stoppages, or quarter ends.
                if p['type'] in ('run', 'complete', 'scramble', 'sack') and not p.get('touchdown'):
                    nxt = logged[index + 1] if index + 1 < len(logged) else {}
                    if (nxt.get('type') in SCRIMMAGE and not nxt.get('nullified')
                            and p.get('clock') is not None and nxt.get('clock') is not None):
                        interval = p['clock'] - nxt['clock']
                        if 6 <= interval <= 50:
                            row['snap_interval'] = interval
                out.append(row)
    return out


def converted(p):
    """Prefer the field result; older saves use the field's whole-yard spot rule."""
    if p.get('nullified') or p.get('defensive_td') or p.get('fumble_lost') or p['type'] == 'interception':
        return False
    if 'converted' in p: return bool(p['converted'])
    return bool(p.get('touchdown')) or round(float(p.get('yards', 0) or 0)) >= float(p.get('ydstogo', 10) or 10)


def stats(rows):
    rows = [p for p in rows if not p.get('nullified')]
    passes = [p for p in rows if p.get('is_pass') or p['type'] in SCRIMMAGE - {'run'}]
    runs = [p for p in rows if p['type'] == 'run' and not p.get('is_pass')]
    yards = lambda ps: sum(float(p.get('yards', 0) or 0) for p in ps)
    thirds = [p for p in rows if p.get('down') == 3]
    return dict(snaps=len(rows), yards=yards(rows), passes=len(passes), pass_yards=yards(passes),
                runs=len(runs), run_yards=yards(runs), sacks=sum(p['type']=='sack' for p in passes),
                pressure=sum(bool(p.get('pressured')) or p['type']=='sack' for p in passes),
                turnovers=sum(p['type']=='interception' or bool(p.get('fumble_lost')) for p in rows),
                third=len(thirds), converted=sum(converted(p) for p in thirds))


def rate(n, d): return f'{n / d:.1f}' if d else '—'


def evidence(rows, kind):
    s = stats(rows)
    if kind == 'run': return f"{rate(s['run_yards'], s['runs'])} yards per designed run ({s['runs']} runs)"
    if kind == 'protection': return f"pressure or sacks on {s['pressure']}/{s['passes']} dropbacks; {s['sacks']} sacks"
    if kind == 'passing': return f"{rate(s['pass_yards'], s['passes'])} net yards per dropback ({s['passes']} dropbacks)"
    if kind == 'mix': return f"{s['passes']} dropbacks / {s['runs']} designed runs; {rate(s['yards'],s['snaps'])} yards per play"
    if kind == 'third': return f"{s['converted']}/{s['third']} third downs converted"
    predicates = {'screens': lambda p:p.get('screen'), 'deep':lambda p:p.get('depth')=='deep' or float(p.get('air',0) or 0)>=20,
                  'blitz':lambda p:p.get('blitz'), 'shell':lambda p:p.get('shell') in TWO_HIGH,
                  'single shell':lambda p:p.get('shell') and p.get('shell') not in TWO_HIGH,
                  'coverage':lambda p:p.get('in_man'), 'motion':lambda p:p.get('motion'),
                  'play action':lambda p:p.get('play_action'),
                  'matchup':lambda p:p.get('travelled') or p.get('bracketed')}
    picked=[p for p in rows if predicates.get(kind,lambda p:True)(p)]
    total=sum(float(p.get('yards',0) or 0) for p in picked)
    return f"{len(picked)} logged {kind} plays, {rate(total,len(picked))} yards per play" + (' (small sample)' if len(picked)<5 else '')


def groups(changes):
    mapping = [('Protection',{'protection'},'off','protection'),
        ('Run/pass and personnel',{'pass_bias','heavy_lean'},'off','mix'),
        ('Passing depth',{'depth_mix'},'off','deep'), ('Screens',{'screen_boost'},'off','screens'),
        ('Play action',{'play_action_rate'},'off','play action'), ('Motion',{'motion_rate'},'off','motion'),
        ('Tempo',{'tempo'},'off','tempo'), ('Run defense',{'box_bias'},'def','run'),
        ('Pressure calls',{'blitz_lean','blitz_rate'},'def','blitz'), ('Safety shell',{'shell_lean'},'def','shell'),
        ('Coverage',{'man_rate','zone_aggression','sub_lean'},'def','passing'),
        ('Receiver matchup',{'travel','travel_target','bracket'},'def','matchup')]
    used=set(); out=[]
    for label, keys, side, metric in mapping:
        found=keys & changes.keys()
        if found: out.append((label,side,metric)); used |= found
    if changes.keys()-used: out.append(('Other plan changes','unknown','unknown'))
    return out


def choices(changes):
    """Explain manual overrides too, not only the assistant buttons accepted."""
    names={'pass_bias':('passing','running'),'heavy_lean':('heavy personnel','spread personnel'),
           'blitz_lean':('blitzing','four-man pressure'),'blitz_rate':('blitzing','less blitzing'),'box_bias':('heavier boxes','lighter boxes'),
           'shell_lean':('two-high shells','single-high shells'),'man_rate':('man coverage','zone coverage'),
           'tempo':('faster tempo','slower tempo'),'screen_boost':('screens','fewer screens'),
           'play_action_rate':('play action','less play action'),'motion_rate':('motion','less motion'),
           'sub_lean':('sub packages','base personnel'),'zone_aggression':('tighter underneath zones','safer zones')}
    out=[]
    for k,v in changes.items():
        if k in names and isinstance(v,(int,float)) and v:
            out.append(names[k][0 if v>0 else 1])
        elif k=='protection': out.append('protection: '+{'six':'six-player','empty':'five-player','half_slide':'half-slide','full_slide':'full-slide'}.get(v,str(v)))
        elif k=='depth_mix': out.append('adjusted short/intermediate/deep passing mix')
        elif k=='travel': out.append('corner travel on' if v else 'corner travel off')
        elif k=='bracket': out.append('receiver bracket on' if v else 'receiver bracket off')
    return ', '.join(out)


def strengths(me, them):
    good=[]; bad=[]
    for label,s,defense in [('Our offense',me,False),('Our defense',them,True)]:
        if s['snaps']>=10:
            y=s['yards']/s['snaps']; line=f"{label}: {y:.1f} yards per play across {s['snaps']} snaps."
            (good if (y<=4.5 if defense else y>=5.5) else bad if (y>=6 if defense else y<4.5) else []).append(line)
        if s['runs']>=6:
            y=s['run_yards']/s['runs']; line=f"{'Run defense allowed' if defense else 'The ground game produced'} {y:.1f} yards per designed run."
            (good if (y<=3.5 if defense else y>=4.5) else bad if (y>=5 if defense else y<3.5) else []).append(line)
        if s['passes']>=8 and s['sacks']>=3:
            (good if defense else bad).append(f"{'We generated' if defense else 'We allowed'} {s['sacks']} sacks on {s['passes']} dropbacks.")
        if s['third']>=4:
            pct=s['converted']/s['third']; line=f"{'They' if defense else 'We'} converted {s['converted']}/{s['third']} third downs."
            (good if (pct<=.25 if defense else pct>=.5) else bad if (pct>=.5 if defense else pct<=.25) else []).append(line)
        if s['turnovers']:
            (good if defense else bad).append(f"{'We took the ball away' if defense else 'We gave the ball away'} {s['turnovers']} time{'s' if s['turnovers'] != 1 else ''}.")
    return good[:3],bad[:3]


def receiver_line(rows, target, name='The targeted receiver'):
    aimed = [p for p in rows if not p.get('nullified') and p.get('target') == target
             and p.get('type') in ('complete', 'incomplete', 'drop', 'interception')]
    catches = [p for p in aimed if p['type'] == 'complete']
    yards = sum(float(p.get('yards', 0) or 0) for p in catches)
    touchdowns = sum(bool(p.get('touchdown') or p.get('td')) and not p.get('defensive_td') for p in catches)
    explosive = sum(float(p.get('yards', 0) or 0) >= 20 for p in catches)
    detail = (f"{name}: {len(catches)} catches on {len(aimed)} targets for {yards:.0f} yards, "
              f"{touchdowns} receiving touchdowns; {explosive} {'catch' if explosive == 1 else 'catches'} of 20+ yards")
    return dict(n=len(aimed), yards=yards, td=touchdowns, explosive=explosive, detail=detail)


def receiver_assessment(rows, target, name):
    if not target:
        return 'ungraded', 'The targeted receiver was not recorded; team-wide yardage cannot grade this matchup.'
    s = receiver_line(rows, target, name)
    if s['n'] < 4:
        return 'limited', s['detail'] + '. Too few targets for a firm matchup verdict.'
    ypt = s['yards'] / s['n']
    if s['td'] >= 2 or s['yards'] >= 100 or ypt >= 10:
        return 'negative', 'The receiver still hurt us: ' + s['detail'] + '.'
    if ypt <= 6 and not s['td'] and s['explosive'] <= 1:
        return 'positive', ('Mostly contained, with one explosive allowed: ' if s['explosive'] else 'The matchup held up: ') + s['detail'] + '.'
    return 'mixed', 'Mixed matchup results: ' + s['detail'] + '.'


def measurement(rows, kind):
    predicates = {
        'run': lambda p: p['type'] == 'run' and not p.get('is_pass'),
        'passing': lambda p: p.get('is_pass') or p['type'] in SCRIMMAGE - {'run'},
        'protection': lambda p: p.get('is_pass') or p['type'] in SCRIMMAGE - {'run'},
        'deep': lambda p: p.get('depth') == 'deep' or float(p.get('air', 0) or 0) >= 20,
        'screens': lambda p: p.get('screen'), 'play action': lambda p: p.get('play_action'),
        'motion': lambda p: p.get('motion'), 'blitz': lambda p: p.get('blitz'),
        'shell': lambda p: p.get('shell') in TWO_HIGH,
        'single shell': lambda p: p.get('shell') and p.get('shell') not in TWO_HIGH}
    rows = [p for p in rows if not p.get('nullified')]
    picked = [p for p in rows if predicates[kind](p)] if kind in predicates else rows
    s = stats(picked)
    n, total, low, high, unit = s['snaps'], s['yards'], 4.5, 6.0, 'yards per play'
    if kind == 'run': n, total, low, high, unit = s['runs'], s['run_yards'], 3.5, 4.5, 'yards per designed run'
    elif kind == 'passing': n, total, low, high, unit = s['passes'], s['pass_yards'], 5.0, 7.0, 'net yards per dropback'
    elif kind == 'deep': low, high = 6.0, 9.0
    elif kind == 'protection':
        n, total, low, high, unit = s['passes'], s['pressure'] * 100, 20., 35., '% of dropbacks under pressure or sacked'
    minimum = 8 if kind in ('passing', 'protection', 'mix') else 5
    return s, n, total, low, high, unit, minimum


def assessment(rows, kind, defense=False):
    """A football outcome judgment, never an estimate of an adjustment's causal effect."""
    if kind == 'matchup': return receiver_assessment(rows, None, '')
    s, n, total, low, high, unit, minimum = measurement(rows, kind)
    if not n: return 'ungraded', 'No relevant plays were logged, so this choice has no on-field result to assess.'
    value = total / n
    detail = f"{value:.1f} {unit} across {n} {'play' if n == 1 else 'plays'}"
    if kind == 'protection': detail += f"; {s['sacks']} sack{'s' if s['sacks'] != 1 else ''}"
    if n < minimum: return 'limited', f"Too little evidence for a firm verdict: {detail}."
    lower_better = defense or kind == 'protection'
    good = value <= low if lower_better else value >= high
    bad = value >= high if lower_better else value <= low
    # A productive average must not hide giveaways on the selected calls.
    if not defense and s['turnovers']:
        detail += f"; {s['turnovers']} turnover" + ('s' if s['turnovers'] != 1 else '')
        if good: return 'mixed', f"Mixed results: productive yardage came with lost possessions ({detail})."
    if good:
        return 'positive', (f"Held up well: the opponent was limited to {detail}." if defense else f"Productive results: {detail}.")
    if bad:
        return 'negative', (f"Did not hold up: the opponent produced {detail}." if defense else f"Struggled on the field: {detail}.")
    return 'mixed', f"Mixed results: {detail}, without a clear statistical edge."


def relative_assessment(previous, rows, kind, defense, verdict, line):
    """Halftime success is meaningful improvement in the problem being addressed."""
    a, an, at, _, _, unit, minimum = measurement(previous, kind)
    b, bn, bt, _, _, _, _ = measurement(rows, kind)
    if an < minimum or bn < minimum:
        return 'limited', line + ' Too little before/after evidence to judge the change. Before the adjustment: ' + evidence(previous, kind) + '.'
    old, new = at / an, bt / bn
    gain = old - new if defense or kind == 'protection' else new - old
    threshold = 5.0 if kind == 'protection' else .5 if kind == 'run' else .75
    if abs(gain) < threshold:
        return verdict, line + ' No meaningful change from the first-half rate. Before the adjustment: ' + evidence(previous, kind) + '.'
    improved = gain > 0
    caveat = (not defense and b['turnovers'] > a['turnovers']) or (
        kind == 'protection' and b['sacks'] >= 3 and b['sacks'] / bn > a['sacks'] / an + .03)
    grade = ('mixed' if caveat else 'positive') if improved else 'negative'
    label = 'Improved after halftime' if improved else 'Worsened after halftime'
    sample = 'runs' if kind == 'run' else 'dropbacks' if kind in ('passing', 'protection') else 'plays'
    text = f"{label}: {old:.1f} → {new:.1f} {unit} ({an} {sample} before, {bn} after)."
    if improved and verdict == 'negative': text += ' The problem eased, although the final level still needs work.'
    if improved and caveat: text += ' The improvement came with worse sack or turnover outcomes.'
    return grade, text


def pace(rows):
    intervals = [float(p['snap_interval']) for p in rows
                 if not p.get('nullified') and p.get('snap_interval') is not None]
    return len(intervals), sum(intervals) / len(intervals) if intervals else None


def tempo_finding(rows, previous, change):
    n, seconds = pace(rows); pn, old = pace(previous)
    if n < 4:
        return dict(label='Tempo', verdict='limited',
                    text=f'Only {n} comparable in-bounds snap intervals; too little timing evidence to grade pace.')
    text = f'Average in-bounds snap interval: {seconds:.1f} seconds across {n} intervals.'
    grade = 'limited'
    if pn >= 4:
        text += f' Before the adjustment: {old:.1f} seconds across {pn} intervals.'
        gain = seconds - old if change < 0 else old - seconds
        grade = 'positive' if gain >= 2 else 'negative' if gain <= -2 else 'mixed'
        text += (' Pace moved in the intended direction.' if gain >= 2 else
                 ' Pace moved against the intended direction.' if gain <= -2 else
                 ' No meaningful change in measured pace.')
    else:
        text += ' Too little comparable timing evidence before the adjustment.'
    return dict(label='Tempo', verdict=grade, text=text)


def pressure_finding(rows, previous=None):
    s = stats(rows); n = s['passes']
    text = 'On blitz calls: ' + evidence(rows, 'protection') + '.'
    grade = 'limited'
    if n >= 8:
        pct = s['pressure'] / n
        grade = 'positive' if pct >= .35 else 'negative' if pct <= .12 else 'mixed'
    if previous is not None:
        old = stats(previous)
        text += ' Before halftime: ' + evidence(previous, 'protection') + '.'
        if n < 8 or old['passes'] < 8:
            grade = 'limited'; text += ' Too little evidence to compare pass-rush pressure.'
        else:
            gain = s['pressure']/n - old['pressure']/old['passes']
            if abs(gain) >= .08:
                grade = 'positive' if gain > 0 else 'negative'
                text += ' Pressure rate increased.' if gain > 0 else ' Pressure rate decreased.'
            else:
                text += ' No meaningful change in pressure rate.'
    return dict(label='Pass-rush pressure', verdict=grade, text=text)


def clock_control_finding(rows, previous, final_margin):
    # Grade only snaps while protecting a meaningful lead. A later comeback
    # drive or overtime must not masquerade as an attempt to burn the clock.
    relevant = [p for p in rows if p.get('score_diff') is not None and p['score_diff'] >= 9]
    now, old = stats(relevant), stats(previous)
    n, seconds = pace(relevant)
    if now['snaps'] < 8:
        return dict(label='Clock control', verdict='limited',
                    text='Too few recorded snaps with a two-score lead to judge clock control.')
    share = now['runs'] / now['snaps']
    ypc = now['run_yards'] / max(1, now['runs'])
    text = (f"While leading by at least two scores, we ran on {now['runs']}/{now['snaps']} snaps "
            f"({share:.0%}), gaining {ypc:.1f} yards per designed run.")
    if old['snaps']:
        text += f" Before halftime: {old['runs']}/{old['snaps']} snaps were designed runs ({old['runs']/old['snaps']:.0%})."
    if n >= 4:
        text += f' In-bounds snap intervals averaged {seconds:.1f} seconds across {n} comparable intervals.'
    else:
        text += ' Too few comparable snap intervals to verify the pace.'
    text += f" We committed {now['turnovers']} turnovers during these snaps."
    if final_margin is not None:
        text += f' Final margin: {final_margin:+d}.'
    grade = 'limited'
    if final_margin is not None and final_margin <= 0:
        grade = 'negative'; text += ' The lead was not protected.'
    elif n >= 4 and final_margin is not None:
        if now['turnovers']:
            grade = 'mixed'; text += ' Giveaways undermined clock control.'
        elif share >= .6 and ypc >= 3.5 and seconds >= 28:
            grade = 'positive'; text += ' The offense sustained a productive ground game, used the clock, and protected the win.'
        else:
            grade = 'mixed'; text += ' The results do not establish all parts of the clock-control objective.'
    return dict(label='Clock control', verdict=grade, text=text)


def assess_choice(changes, own, against, before=None, league=None):
    findings = []
    for label, side, metric in groups(changes):
        if metric == 'unknown':
            findings.append(dict(label=label, verdict='ungraded', text='No matching evidence measure is available for these settings.'))
            continue
        if metric == 'tempo':
            findings.append(tempo_finding(own, before[0] if before else [], changes.get('tempo', 0)))
            continue
        if metric == 'mix' and 'pass_bias' in changes:
            metric = 'run' if changes['pass_bias'] < 0 else 'passing'
        if metric == 'deep' and changes.get('depth_mix', (0, 0, 0))[2] <= 0:
            metric = 'passing'
        if metric == 'shell' and changes.get('shell_lean', 0) < 0: metric = 'single shell'
        if metric == 'blitz' and changes.get('blitz_lean', changes.get('blitz_rate', 0)) < 0: metric = 'passing'
        if metric in ('screens', 'play action', 'motion'):
            key = {'screens':'screen_boost', 'play action':'play_action_rate', 'motion':'motion_rate'}[metric]
            if changes.get(key, 0) < 0: metric = 'passing' if metric != 'motion' else 'mix'
        rows = own if side == 'off' else against
        if metric == 'matchup':
            targets = list(dict.fromkeys(v for v in (changes.get('travel_target'), changes.get('bracket'))
                                         if isinstance(v, str) and v))
            if not targets:
                verdict, line = receiver_assessment(rows, None, '')
                findings.append(dict(label=label, verdict=verdict, text=line))
            for target in targets:
                player = league.player(target) if league is not None and hasattr(league, 'player') else None
                name = getattr(player, 'name', 'The targeted receiver')
                verdict, line = receiver_assessment(rows, target, name)
                if before is not None:
                    a = receiver_line(before[1], target, name)
                    b = receiver_line(rows, target, name)
                    if a['n'] >= 4 and b['n'] >= 4:
                        delta = a['yards'] / a['n'] - b['yards'] / b['n']
                        if abs(delta) >= 1:
                            verdict = ('positive' if b['td'] <= a['td'] else 'mixed') if delta > 0 else 'negative'
                            line = ('Improved after halftime: ' if delta > 0 else 'Worsened after halftime: ') + b['detail'] + '.'
                            if delta > 0 and b['td'] > a['td']: line += ' Receiving efficiency fell, but touchdowns increased.'
                    line += ' Before the adjustment: ' + a['detail'] + '.'
                findings.append(dict(label=label, verdict=verdict, text=line))
            continue
        verdict, line = assessment(rows, metric, side == 'def')
        if before is not None:
            previous = before[0 if side == 'off' else 1]
            verdict, line = relative_assessment(previous, rows, metric, side == 'def', verdict, line)
        if label == 'Pressure calls':
            selected = [p for p in rows if p.get('blitz')] if metric == 'blitz' else rows
            line += ' Pass-rush evidence: ' + evidence(selected, 'protection') + '.'
        findings.append(dict(label=label, verdict=verdict, text=line))
        if label == 'Pressure calls' and metric == 'blitz':
            earlier = [p for p in before[1] if p.get('blitz')] if before is not None else None
            findings.append(pressure_finding(selected, earlier))
    return findings


def conclusion(findings):
    grades = {x['verdict'] for x in findings}
    if not grades or grades <= {'limited', 'ungraded'}:
        return 'Not enough relevant plays for a firm verdict on these choices.'
    if grades & {'limited', 'ungraded'}:
        return 'The available findings are incomplete; there is not enough evidence to grade the whole recommendation.'
    if 'negative' in grades and ('positive' in grades or 'mixed' in grades):
        return 'A mixed return: some parts of the plan held up, while others struggled.'
    if 'negative' in grades: return 'The evaluated parts of the plan struggled; the intended payoff did not show up in those results.'
    if 'positive' in grades and 'mixed' not in grades:
        return 'The evaluated parts of the plan delivered favorable results.'
    return 'The results were mixed, with no consistent advantage across the evaluated choices.'


def review_choices(pre, own, against, before=None, league=None, final_margin=None):
    findings = []
    for rec in pre:
        changes = rec.get('changes', {})
        if (rec.get('review_key') == 'clock_control' or rec.get('text') == 'Up two scores: shorten the game, run it') and before is not None:
            items = [clock_control_finding(own, before[0], final_margin)]
        elif rec.get('review_key') == 'blitz_opportunity':
            faced = [p for p in own if p.get('blitz')]
            prior = ([p for p in before[0] if p.get('blitz')], []) if before else None
            items = assess_choice({'pass_bias': 1}, faced, [], prior, league)
            for item in items: item['label'] = 'Passing against the blitz'
        else:
            items = assess_choice(changes, own, against, before, league)
        summary = conclusion(items)
        if rec.get('overridden'):
            summary = (summary + ' ' if items else '') + 'Your manual settings replaced ' + ', '.join(k.replace('_', ' ') for k in rec['overridden']) + '; those choices are reviewed under Your saved plan.'
        findings.append(dict(title=rec['text'], conclusion=summary, findings=items))
    return findings


def declined_evidence(key, own, against, before):
    """Review the recommendation's actual concern, not every setting in its bundle.

    Opportunity advice needs evidence of both an available strength and a costly
    alternative. Absence of the suggested tactic alone is not a bad decision.
    """
    a, b = stats(own), stats(against)
    first, opp_first = stats(before[0]), stats(before[1])
    def avg(s, kind):
        n = s['runs' if kind == 'run' else 'passes']
        return s['run_yards' if kind == 'run' else 'pass_yards'] / max(1, n)
    def deep(rows):
        return [p for p in rows if p['type'] in ('complete', 'incomplete', 'drop', 'interception')
                and (p.get('depth') == 'deep' or float(p.get('air', 0) or 0) >= 20)]
    def completions(rows):
        caught = [p for p in rows if p['type'] == 'complete']
        return len(caught), sum(float(p.get('yards', 0) or 0) for p in caught)
    def line(detail, baseline): return detail + ' Before halftime: ' + baseline + '.'
    if key == 'protection':
        if a['passes'] >= 8 and (a['sacks'] >= 3 or (a['passes'] >= 12 and
                a['pressure'] / a['passes'] >= .4 and
                a['pressure'] / a['passes'] >= first['pressure'] / max(1, first['passes']) - .05)):
            return line(f"We allowed {a['sacks']} sacks after halftime on {a['passes']} dropbacks; pressure or sacks affected {a['pressure']} of them.", evidence(before[0], 'protection'))
    elif key in ('run_working', 'run_stalled'):
        if key == 'run_working' and first['runs'] >= 6 and avg(first, 'run') >= 5.2 and a['runs'] >= 5 and avg(a, 'run') >= 5 and a['passes'] >= 12 and a['passes'] > a['runs'] * 1.5 and avg(a, 'pass') <= 4:
            return line(f"The run remained productive at {avg(a, 'run'):.1f} yards on {a['runs']} carries, but we chose {a['passes']} dropbacks for only {avg(a, 'pass'):.1f} net yards each after halftime.", evidence(before[0], 'run'))
        if key == 'run_stalled' and a['runs'] >= 8 and avg(a, 'run') <= 2.6 and avg(a, 'run') <= avg(first, 'run') + .5:
            return line(f"We continued running into the same problem after halftime: {evidence(own, 'run')}.", evidence(before[0], 'run'))
    elif key in ('deep_stalled', 'deep_working', 'blitz_opportunity'):
        old_deep, new_deep = deep(before[0]), deep(own)
        if key == 'deep_stalled' and len(new_deep) >= 4 and completions(new_deep)[0] == 0:
            return line(f"The shots still did not connect: 0 completions on {len(new_deep)} deep attempts after halftime.", f"{completions(old_deep)[0]} of {len(old_deep)} deep attempts completed")
        if key == 'deep_working' and completions(old_deep)[0] >= 2 and completions(old_deep)[1] >= 60 and a['passes'] >= 12 and len(new_deep) <= 1 and avg(a, 'pass') <= 4:
            return line(f"We took only {len(new_deep)} deep shots after halftime while the passing game stalled at {avg(a, 'pass'):.1f} net yards on {a['passes']} dropbacks.", f"{completions(old_deep)[0]} deep completions for {completions(old_deep)[1]:.0f} yards")
        if key == 'blitz_opportunity':
            old = stats([p for p in before[0] if p.get('blitz') and p['type'] != 'run'])
            passing = stats([p for p in own if p.get('blitz') and p['type'] != 'run'])
            runs = stats([p for p in own if p.get('blitz') and p['type'] == 'run'])
            if old['passes'] >= 4 and avg(old, 'pass') >= 8 and passing['passes'] >= 4 and avg(passing, 'pass') >= 8 and runs['runs'] >= 6 and avg(runs, 'run') <= 2.6:
                return line(f"Against their blitz after halftime, we ran {runs['runs']} times for {avg(runs, 'run'):.1f} yards each despite gaining {avg(passing, 'pass'):.1f} net yards on {passing['passes']} dropbacks against it.", f"{avg(old, 'pass'):.1f} net yards per dropback against the blitz")
    elif key in ('screens_stalled', 'screens_defense'):
        defense = key == 'screens_defense'
        rows, earlier = (against, before[1]) if defense else (own, before[0])
        screen = [p for p in rows if p.get('screen')]
        old = [p for p in earlier if p.get('screen')]
        now = sum(float(p.get('yards', 0) or 0) for p in screen) / max(1, len(screen))
        prior = sum(float(p.get('yards', 0) or 0) for p in old) / max(1, len(old))
        if len(screen) >= 5 and ((defense and now >= 7 and now >= prior - .75) or (not defense and now <= 1)):
            return line(('Their screens kept hurting us' if defense else 'Our screens continued to stall') + f" after halftime: {evidence(rows, 'screens')}.", evidence(earlier, 'screens'))
    elif key in ('third_offense', 'third_defense'):
        defense = key == 'third_defense'
        s, old = (b, opp_first) if defense else (a, first)
        now, prior = s['converted'] / max(1, s['third']), old['converted'] / max(1, old['third'])
        if s['third'] >= 5 and old['third'] >= 4 and ((defense and now >= .6 and now >= prior - .1) or (not defense and now <= .25 and now <= prior + .1)):
            return line(f"{'They' if defense else 'We'} converted {s['converted']}/{s['third']} third downs after halftime; the third-down problem persisted.", evidence(before[1 if defense else 0], 'third'))
    elif key == 'turnovers':
        if a['snaps'] >= 12 and a['turnovers'] >= 2:
            return line(f"We committed {a['turnovers']} more turnovers after halftime on {a['snaps']} offensive plays.", f"{first['turnovers']} turnovers")
    elif key in ('run_defense', 'pass_defense'):
        run = key == 'run_defense'
        metric, n, minimum, threshold, improvement = ('run', 'runs', 8, 5, .5) if run else ('passing', 'passes', 12, 8.5, .75)
        kind = 'run' if run else 'pass'
        if b[n] >= minimum and opp_first[n] >= (6 if run else 8) and avg(b, kind) >= threshold and avg(b, kind) >= avg(opp_first, kind) - improvement:
            return line(f"The opponent's problem area remained productive after halftime: {evidence(against, metric)}.", evidence(before[1], metric))
    elif key == 'deep_defense':
        throws = deep(against)
        caught, yards = completions(throws)
        if len(throws) >= 4 and caught >= 2 and yards >= 60:
            return line(f"The opponent completed {caught} of {len(throws)} deep throws for {yards:.0f} yards after halftime.", evidence(before[1], 'deep'))
    elif key == 'pressure_defense':
        if b['passes'] >= 12 and b['pressure'] / b['passes'] <= .12 and avg(b, 'pass') >= 7:
            return line(f"We generated pressure or a sack on only {b['pressure']}/{b['passes']} opposing dropbacks after halftime, and allowed {avg(b, 'pass'):.1f} net yards per dropback.", evidence(before[1], 'protection'))
    elif key in ('hurry', 'clock_control'):
        chasing = key == 'hurry'
        # Use the actual score on each drive, not the final score or halftime lead.
        relevant = [p for p in own if p.get('down') in (1, 2) and p.get('score_diff') is not None
                    and (p['score_diff'] <= -9 if chasing else p['score_diff'] >= 9)]
        s = stats(relevant)
        if s['snaps'] >= 8:
            if chasing and s['runs'] >= 6 and s['runs'] / s['snaps'] >= .6 and avg(s, 'run') <= 3:
                return f"While still down at least two scores after halftime, we ran on {s['runs']}/{s['snaps']} early downs for {avg(s, 'run'):.1f} yards per carry. The offense kept using downs on an ineffective ground game while chasing the score."
            misses = sum(p['type'] in ('incomplete', 'drop') for p in relevant)
            if not chasing and s['passes'] >= 8 and s['passes'] / s['snaps'] >= .65 and misses >= 5 and avg(s, 'pass') <= 4:
                return f"While still leading by at least two scores after halftime, we chose {s['passes']} dropbacks on {s['snaps']} early downs for {avg(s, 'pass'):.1f} net yards each; {misses} incompletions stopped the clock. The passing choices did little to move the ball or protect the clock."
    return None


def declined_reviews(recs, own, against, before, accepted=(), installed=None):
    """Mention only substantial continuing problems relevant to unaccepted advice."""
    findings = []
    covered = {'protection': (installed or {}).get('protection')}
    covered.update({k: v for r in accepted for k, v in r.get('changes', {}).items()})
    for rec in recs:
        ch = rec.get('changes') or {}
        key = rec.get('review_key')
        if key:
            # Shared primary adjustments count as acting on the advice, even if
            # they came from a different accepted recommendation.
            primary = {
                'run_working': ('pass_bias',), 'run_stalled': ('pass_bias',),
                'protection': ('protection',), 'deep_stalled': ('depth_mix',),
                'deep_working': ('depth_mix',), 'screens_stalled': ('screen_boost',),
                'blitz_opportunity': ('depth_mix',), 'third_offense': ('depth_mix',),
                'turnovers': ('depth_mix',), 'run_defense': ('box_bias',),
                'pass_defense': ('sub_lean', 'shell_lean'), 'deep_defense': ('shell_lean',),
                'pressure_defense': ('blitz_lean',), 'third_defense': ('zone_aggression',),
                'screens_defense': ('blitz_lean',), 'hurry': ('tempo', 'pass_bias'),
                'clock_control': ('tempo', 'pass_bias')}.get(key, ())
            def aligned(k):
                wanted, actual = ch.get(k), covered.get(k)
                if wanted is None or actual is None: return False
                if isinstance(wanted, (tuple, list)) and isinstance(actual, (tuple, list)):
                    return len(wanted) == len(actual) and all(not w or w * a > 0 for w, a in zip(wanted, actual))
                if isinstance(wanted, (int, float)) and isinstance(actual, (int, float)):
                    return wanted * actual > 0
                return wanted == actual
            if primary and all(aligned(k) for k in primary): continue
            detail = declined_evidence(key, own, against, before)
            if detail:
                findings.append(dict(title=rec['text'],
                    conclusion='You left this recommendation off; the later results make it worth revisiting.',
                    findings=[dict(label='Not taken at halftime', verdict='negative', text=detail)]))
            continue
        metric, defense, detail = None, False, None
        if ch.get('protection') and covered.get('protection') != ch['protection']:
            after = stats(own); earlier = stats(before[0])
            if after['passes'] >= 8 and (after['sacks'] >= 3 or (
                after['passes'] >= 12 and after['pressure'] / after['passes'] >= .4
                and after['pressure'] / after['passes'] >= earlier['pressure'] / max(1, earlier['passes']) - .05)):
                metric = 'protection'
                detail = f"We allowed {after['sacks']} sacks after halftime on {after['passes']} dropbacks; pressure or sacks affected {after['pressure']} of them."
        elif ch.get('box_bias', 0) > 0 and covered.get('box_bias', 0) <= 0:
            after, earlier = stats(against), stats(before[1])
            if after['runs'] >= 8 and earlier['runs'] >= 6:
                now, old = after['run_yards'] / after['runs'], earlier['run_yards'] / earlier['runs']
                if now >= 5 and now >= old - .5:
                    metric, defense = 'run', True
                    detail = f"The opponent still gained {now:.1f} yards per designed run after halftime ({after['runs']} runs), after {old:.1f} before the break."
        elif any(ch.get(k, 0) > 0 for k in ('sub_lean', 'zone_aggression')) and not any(k in covered for k in ('sub_lean', 'zone_aggression')):
            after, earlier = stats(against), stats(before[1])
            if after['passes'] >= 12 and earlier['passes'] >= 8:
                now, old = after['pass_yards'] / after['passes'], earlier['pass_yards'] / earlier['passes']
                if now >= 8.5 and now >= old - .75:
                    metric, defense = 'passing', True
                    detail = f"The opponent still produced {now:.1f} net yards per dropback after halftime ({after['passes']} dropbacks)."
        elif ch.get('shell_lean', 0) > 0 and covered.get('shell_lean', 0) <= 0:
            deep = [p for p in against if p.get('depth') == 'deep' or float(p.get('air', 0) or 0) >= 20]
            caught = [p for p in deep if p['type'] == 'complete' and not p.get('nullified')]
            yards = sum(float(p.get('yards', 0) or 0) for p in caught)
            if len(deep) >= 4 and len(caught) >= 2 and yards >= 60:
                metric, defense = 'deep', True
                detail = f"The opponent completed {len(caught)} of {len(deep)} deep throws for {yards:.0f} yards after halftime."
        elif ch.get('screen_boost', 0) < 0 and covered.get('screen_boost', 0) >= 0:
            screen = [p for p in own if p.get('screen')]
            if len(screen) >= 5 and sum(float(p.get('yards', 0) or 0) for p in screen) / len(screen) <= 1:
                metric = 'screens'
                detail = f"The screens continued to stall after halftime: {evidence(own, 'screens')}."
        if metric:
            findings.append(dict(title=rec['text'],
                conclusion='You left this recommendation off; the concern remained worth addressing.',
                findings=[dict(label='Not taken at halftime', verdict='negative', text=detail +
                    ' Before halftime: ' + evidence(before[1 if defense else 0], metric) + '.')]))
    return findings


def combine_saved_reports(league):
    """Join existing paired reports by exact game identity, retaining analysis ID."""
    messages = getattr(league, 'inbox', [])
    reviews = {(m.get('payload') or {}).get('game_key'): m for m in messages
               if (m.get('payload') or {}).get('recap')}
    remove = set()
    for m in messages:
        payload = m.get('payload') or {}
        key = payload.get('game_key', '')
        if payload.get('snap_counts') and key.startswith('snap-counts-'):
            review = reviews.get(key.replace('snap-counts-', 'game-recap-', 1))
            if review is not None:
                review['payload']['snap_counts'] = payload['snap_counts']
                remove.add(m['id'])
    if remove:
        league.inbox = [m for m in messages if m['id'] not in remove]


def post_snap_counts(league, home, away, week, states, playoffs=False):
    """Freeze one game of participation, including reserves with zero snaps."""
    import defense_roles as DR
    user = getattr(league, 'user_team', None)
    if user not in (home, away): return None
    key = f'snap-counts-{league.year}-{week}-{home}-{away}-{int(playoffs)}'
    if IE.seen(league, key): return None
    review_key = key.replace('snap-counts-', 'game-recap-', 1)
    if any((m.get('payload') or {}).get('game_key') == review_key
           and (m.get('payload') or {}).get('snap_counts')
           for m in getattr(league, 'inbox', [])):
        return None
    state = states[user]
    counts = getattr(state, 'last_snap_counts', None)
    if not counts: return None  # No invented counts for a result imported from an older build.
    team = league.teams[user]
    roster = {p.pid: p for p in team.active()}
    roster.update((p.pid, p) for p in (getattr(team, '_elevated', None) or []))
    for unit in counts.values():
        for pid in unit['players']:
            p = league.player(pid)
            if p is not None: roster[pid] = p
    order = dict(offense=('QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'),
                 defense=('LEDG', 'DT', 'REDG', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS'))
    report = {}
    for unit, positions in order.items():
        recorded = counts.get(unit, dict(total=0, players={}))
        rows = [dict(pid=p.pid, name=p.name, pos=DR.position(p), snaps=int(recorded['players'].get(p.pid, 0)))
                for p in roster.values() if DR.position(p) in positions or p.pid in recorded['players']]
        rows.sort(key=lambda row: (-row['snaps'],
                                   positions.index(row['pos']) if row['pos'] in positions else len(positions),
                                   row['name'], row['pid']))
        report[unit] = dict(total=int(recorded['total']), rows=rows)
    report['note'] = ('Recorded offensive and defensive participation, including overtime, two-point attempts '
                      'and live plays erased by penalties. Kneeldowns and kicking plays are not tracked.')
    body = []
    for unit in order:
        body.append(unit.upper() + '\n' + '\n'.join(
            f"{inbox_player(league.player(p['pid']), p['name'])}: {p['snaps']}/{report[unit]['total']} Snaps" for p in report[unit]['rows']))
    opp = away if user == home else home
    review_key = key.replace('snap-counts-', 'game-recap-', 1)
    review = next((m for m in getattr(league, 'inbox', [])
                   if (m.get('payload') or {}).get('game_key') == review_key), None)
    if review is not None:
        review['payload']['snap_counts'] = report
        return review
    msg = IE.post(league, key, 'game', f'Snap counts: {user} vs {opp} · {__import__("club_notes")._period(week)}',
                  '\n\n'.join(body), sender='Coaching staff',
                  payload=dict(snap_counts=report, game_key=key, link=f'gameday:{week}'))
    if msg: msg['week'] = week
    return msg


def post(league, home, away, week, res, playoffs=False):
    user = getattr(league, 'user_team', None)
    if user not in (home, away): return None
    side = 'home' if user == home else 'away'; other = 'away' if side == 'home' else 'home'
    opp = away if side == 'home' else home
    key = f'game-recap-{league.year}-{week}-{home}-{away}-{int(playoffs)}'
    if IE.seen(league, key): return None
    own, against = plays(res, side), plays(res, other)
    me, them = stats(own), stats(against); good, bad = strengths(me, them)
    ours, theirs = int(res[side]), int(res[other])
    outcome = 'Win' if ours > theirs else 'Loss' if ours < theirs else 'Tie'
    ot_own, ot_against = plays(res, side, 3), plays(res, other, 3)
    has_ot = bool(res.get('overtime') or ot_own or ot_against)
    intro = (f"{outcome}, {ours}–{theirs} against {opp}{' in overtime' if has_ot else ''}. "
             f"We gained {me['yards']:.0f} scrimmage yards and allowed {them['yards']:.0f}; "
             f"turnovers {me['turnovers']} committed, {them['turnovers']} forced.")
    sections = []
    def add(title, lines=None, reviews=None):
        sections.append(dict(title=title, lines=lines or [], reviews=reviews or []))
    add('What went well', good or ['No clear statistical strength stood out in the recorded scrimmage plays.'])
    add('What needs work', bad or ['No clear statistical weakness stood out in the recorded scrimmage plays.'])
    kicks = [p for pos, d in res.get('drives', []) if pos == side for p in getattr(d, 'log', [])
             if p.get('type') == 'field_goal' and not p.get('nullified')]
    if kicks: add('Special teams', [f"We made {sum(bool(p.get('made')) for p in kicks)}/{len(kicks)} field goals."])
    context = res.get('coaching_review') or {}; pre = context.get('pregame')
    if pre is None: add('Pregame plan', ['The kickoff plan was not recorded for this game.'])
    elif not pre.get('changes'): add('Pregame plan', ['You kept the base weekly plan; no pregame overrides were applied.'])
    else:
        recs = list(pre.get('recommendations') or [])
        covered = {k for r in recs for k in r.get('changes', {})}
        remaining = {k:v for k,v in pre['changes'].items() if k not in covered}
        if remaining: recs.append(dict(text='Your saved plan', changes=remaining))
        reviews = review_choices(recs, own, against, league=league)
        lines = ['Your plan: ' + choices(pre['changes']) + '.',
                 'Game-wide results' + (' including overtime.' if has_ot else '.')]
        if pre.get('taken') and not pre.get('recommendations'):
            lines.insert(0, 'Accepted advice: ' + '; '.join(pre['taken']) + '.')
        add('Pregame plan', lines, reviews)
    taken = context.get('halftime', [])
    after = (plays(res, side, 'after_break'), plays(res, other, 'after_break'))
    before = (plays(res, side, 1), plays(res, other, 1))
    if not taken: add('Halftime adjustments', ['No halftime recommendations were accepted.'])
    else:
        add('Halftime adjustments', ['Results after halftime' + (' include overtime.' if has_ot else '.')],
            review_choices(taken, *after, before=before, league=league, final_margin=ours-theirs))
    # A later overtime decision must not be blamed on the halftime choice.
    contextual_own = [dict(p, score_diff=getattr(d, 'score_diff', None))
                      for pos, d in res.get('drives', []) if pos == side
                      for p in plays({'drives': [(pos, d)]}, side, 2)]
    missed = declined_reviews(context.get('halftime_declined', []), contextual_own,
                              plays(res, other, 2), before, accepted=taken,
                              installed=context.get('halftime_existing'))
    if missed: add('Halftime advice not taken', reviews=missed)
    if has_ot:
        lines = [f"Overtime offense: {evidence(ot_own, 'mix')}. Opponent offense: {evidence(ot_against, 'mix')}."]
        taken = context.get('overtime', [])
        if not taken: lines.append('No overtime recommendations were accepted; the existing plan carried forward.')
        add('Overtime adjustments', lines, review_choices(taken, ot_own, ot_against, league=league))
    # Keep plain text for previews, exports and old clients; the inbox renders the same structured report.
    body = [intro]
    for section in sections:
        lines = [section['title'].upper()] + section['lines']
        for review in section['reviews']:
            lines.extend([review['title'] + ' — ' + review['conclusion']])
            lines.extend(x['label'] + ': ' + x['text'] for x in review['findings'])
        body.append('\n'.join(lines))
    coach = (getattr(league.teams[user], 'staff', None) or {}).get('oc'); name = getattr(coach, 'name', None)
    msg = IE.post(league, key, 'result', f"Assistant review: {user} {ours}–{theirs} {opp}", '\n\n'.join(body),
                  sender=f'{name} · Offensive coordinator' if name else 'Assistant coaches',
                  payload=dict(link=f'gameday:{week}', game_key=key, coaching_review=context,
                               recap=dict(intro=intro, sections=sections)))
    if msg: msg['week'] = week
    return msg
