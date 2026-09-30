"""One saved, evidence-based assistant review per completed user game. No RNG."""
import copy
import inbox_events as IE

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
                installed={k: copy.deepcopy(getattr(state.plan, k)) for k in changes})


def plays(res, side, half=None):
    out = []
    for pos, drive in res.get('drives', []):
        if pos != side: continue
        q = getattr(drive, 'start_quarter', getattr(drive, 'quarter', 1))
        for p in getattr(drive, 'log', []):
            if not isinstance(p, dict): continue
            if p.get('type') == 'period': q = p.get('quarter', q)
            if p.get('type') not in SCRIMMAGE or p.get('nullified'): continue
            # Play clock is seconds remaining in regulation; overtime is separate.
            period = 3 if q > 4 else (1 if p.get('clock', 1801 if q <= 2 else 1800) > 1800 else 2)
            if half is None or half == period: out.append(p)
    return out


def stats(rows):
    passes = [p for p in rows if p.get('is_pass') or p['type'] in SCRIMMAGE - {'run'}]
    runs = [p for p in rows if p['type'] == 'run' and not p.get('is_pass')]
    yards = lambda ps: sum(float(p.get('yards', 0) or 0) for p in ps)
    thirds = [p for p in rows if p.get('down') == 3]
    return dict(snaps=len(rows), yards=yards(rows), passes=len(passes), pass_yards=yards(passes),
                runs=len(runs), run_yards=yards(runs), sacks=sum(p['type']=='sack' for p in passes),
                pressure=sum(bool(p.get('pressured')) or p['type']=='sack' for p in passes),
                turnovers=sum(p['type']=='interception' or bool(p.get('fumble_lost')) for p in rows),
                third=len(thirds), converted=sum(bool(p.get('touchdown')) or float(p.get('yards',0) or 0)>=float(p.get('ydstogo',10) or 10) for p in thirds))


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
        ('Tempo',{'tempo'},'off','mix'), ('Run defense',{'box_bias'},'def','run'),
        ('Pressure calls',{'blitz_lean'},'def','blitz'), ('Safety shell',{'shell_lean'},'def','shell'),
        ('Coverage',{'man_rate','zone_aggression','sub_lean'},'def','passing'),
        ('Receiver matchup',{'travel','travel_target','bracket'},'def','matchup')]
    used=set(); out=[]
    for label, keys, side, metric in mapping:
        found=keys & changes.keys()
        if found: out.append((label,side,metric)); used |= found
    if changes.keys()-used: out.append(('Other plan changes','off','mix'))
    return out


def choices(changes):
    """Explain manual overrides too, not only the assistant buttons accepted."""
    names={'pass_bias':('passing','running'),'heavy_lean':('heavy personnel','spread personnel'),
           'blitz_lean':('blitzing','four-man pressure'),'box_bias':('heavier boxes','lighter boxes'),
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
            (good if defense else bad).append(f"{'We took the ball away' if defense else 'We gave the ball away'} {s['turnovers']} time(s).")
    return good[:3],bad[:3]


def post(league, home, away, week, res, playoffs=False):
    user=getattr(league,'user_team',None)
    if user not in (home,away): return None
    side='home' if user==home else 'away'; other='away' if side=='home' else 'home'
    opp=away if side=='home' else home
    key=f'game-recap-{league.year}-{week}-{home}-{away}-{int(playoffs)}'
    if IE.seen(league,key): return None
    own=plays(res,side); against=plays(res,other)
    me,them=stats(own),stats(against); good,bad=strengths(me,them)
    ours,theirs=int(res[side]),int(res[other]); outcome='Win' if ours>theirs else 'Loss' if ours<theirs else 'Tie'
    sections=[f"{outcome}, {ours}–{theirs} against {opp}. We gained {me['yards']:.0f} scrimmage yards and allowed {them['yards']:.0f}; turnovers {me['turnovers']} committed, {them['turnovers']} forced.",
              'WHAT WENT WELL\n'+('\n'.join(good) or 'No clear statistical strength stood out in the recorded scrimmage plays.'),
              'WHAT NEEDS WORK\n'+('\n'.join(bad) or 'No clear statistical weakness stood out in the recorded scrimmage plays.')]
    kicks=[p for pos,d in res.get('drives',[]) if pos==side for p in getattr(d,'log',[])
           if p.get('type')=='field_goal' and not p.get('nullified')]
    if kicks: sections.append(f"SPECIAL TEAMS\nWe made {sum(bool(p.get('made')) for p in kicks)}/{len(kicks)} field goals.")
    context=res.get('coaching_review') or {}
    pre=context.get('pregame')
    lines=[]
    if pre is None: lines=['The kickoff plan was not recorded for this game.']
    elif not pre.get('changes'): lines=['You kept the base weekly plan; no pregame overrides were applied.']
    else:
        if pre.get('taken'): lines.append('Accepted advice: '+'; '.join(pre['taken'])+'.')
        if choices(pre['changes']): lines.append('Your plan: '+choices(pre['changes'])+'.')
        for label,s,metric in groups(pre['changes']):
            lines.append(f"{label} ({'our offense' if s=='off' else 'opponent offense'}): {evidence(own if s=='off' else against,metric)}.")
    sections.append('PREGAME PLAN\n'+'\n'.join(lines))
    taken=context.get('halftime',[]); lines=[]
    if not taken: lines=['No halftime recommendations were accepted.']
    else:
        lines.append('Accepted at the break: '+'; '.join(r['text'] for r in taken)+'.')
        changes={k:v for r in taken for k,v in r.get('changes',{}).items()}
        for label,s,metric in groups(changes):
            target=side if s=='off' else other
            before,after=plays(res,target,1),plays(res,target,2)
            if not before or not after: lines.append(f'{label}: not enough logged plays in both halves to compare.')
            else: lines.append(f"{label}: first half {evidence(before,metric)}; second half {evidence(after,metric)}.")
        for target,label in ((side,'Our offensive'),(other,'Their offensive')):
            first,second=stats(plays(res,target,1)),stats(plays(res,target,2))
            if min(first['snaps'],second['snaps'])>=8:
                delta=second['yards']/second['snaps']-first['yards']/first['snaps']
                trend='improved' if delta>.5 else 'fell' if delta<-.5 else 'was broadly unchanged'
                lines.append(f"{label} efficiency {trend} after the break ({rate(first['yards'],first['snaps'])} to {rate(second['yards'],second['snaps'])} yards per play).")
        lines.append('Half comparisons exclude overtime. These are observed results, not proof of cause; opponent adjustments and game situation also mattered.')
    sections.append('HALFTIME ADJUSTMENTS\n'+'\n'.join(lines))
    if pre and pre.get('changes') and not taken:
        sections.append('Plan results describe what happened with those choices; they do not isolate their effect from execution or the opponent.')
    coach=(getattr(league.teams[user],'staff',None) or {}).get('oc')
    name=getattr(coach,'name',None)
    msg=IE.post(league,key,'result',f"Assistant review: {user} {ours}–{theirs} {opp}", '\n\n'.join(sections),
                sender=f'{name} · Offensive coordinator' if name else 'Assistant coaches',
                payload=dict(link=f'gameday:{week}',game_key=key,coaching_review=context))
    if msg: msg['week']=week
    return msg
