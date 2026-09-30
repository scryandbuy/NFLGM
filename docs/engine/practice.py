"""Weekly preparation. Read-only previews; one persisted award per player/week.

Budgets are deliberately small relative to 75 game-day XP plus 3 per snap.
Modifiers redistribute a fixed unit budget instead of inflating team earnings.
"""
import copy
import health as H
import xp as XP

UNITS = ('offense', 'defense', 'special')
INTENSITIES = {'recovery': (.0, .0, .045), 'light': (.55, .35, .025),
               'standard': (1., 1., .0), 'hard': (1.20, 2.7, -.018)}
OFFENSE = {'QB','HB','FB','WR','TE','LT','LG','C','RG','RT'}
WEEKLY_XP_PER_PLAYER = 12.0
MAX_PLAYER_XP = 24.0
# About 0.04 incidents/team/week at standard; much less than game exposure.
BASE_INJURY_RISK = .0007

def _unit(p):
    return 'special' if p.pos in ('K','P','LS') else 'offense' if p.pos in OFFENSE else 'defense'

def _roster(league, abbr):
    t = league.teams[abbr]
    return list({p.pid:p for p in list(t.roster)+list(getattr(t,'practice_squad',[]))
                 if not p.retired}.values())

def _health(league, runner, abbr, p):
    saved = (getattr(league,'practice_state',None) or {}).get('players',{}).get(p.pid,{})
    last_key=saved.get('last_key')
    if last_key and int(last_key.split(':')[0]) < int(league.year):
        saved={}
    st = runner.states.get(abbr) if runner else None
    # A transfer's authoritative state travels with the player until this club trains him.
    moved = saved.get('last_team') not in (None, abbr)
    c = st.cond.get(p.pid) if st and p.pid in st.cond.cond and not moved else saved.get('condition',100.)
    j = st.jaded.get(p.pid, saved.get('jaded',0.)) if st and not moved else saved.get('jaded',0.)
    return float(c), float(j), saved

def _rehab(runner, abbr, p):
    desk = getattr(runner,'desks',{}).get(abbr) if runner else None
    return p.out_until is not None or bool(desk and p.pid in getattr(desk,'playing_hurt',{}))

def _starters(team, depth):
    import offense_roles as OR, defense_roles as DR
    gm=getattr(team,'gm',None)
    selected=set()
    try:
        selected.update(p.pid for _,p in OR.assign(depth,OR.base_package(gm)))
    except ValueError:
        # Short emergency rosters still receive a preview before replacements arrive.
        selected.update(men[0].pid for pos,men in depth.items() if pos in OFFENSE and men)
    selected.update(row['player'].pid for row in DR.assign(depth,DR.coach_front(gm),'base') if row['player'])
    selected.update(depth[pos][0].pid for pos in ('K','P','LS') if depth.get(pos))
    return selected

def recommend_plan(league, runner, abbr, week, *, bye=False):
    players = _roster(league,abbr)
    units = {}
    for unit in UNITS:
        health = [_health(league,runner,abbr,p) for p in players if _unit(p)==unit]
        worn = any(c < 72 or j > .36 for c,j,_ in health)
        units[unit] = dict(intensity='recovery' if bye else 'light' if worn else 'standard',
                           reps='development' if worn or bye else 'balanced')
    individual = {p.pid:'rest' for p in players if _rehab(runner,abbr,p) or
                  _health(league,runner,abbr,p)[0] < 60}
    return dict(units=units, individual=individual, focus=[])

def _plan(league,runner,abbr,week,plan,bye):
    base = recommend_plan(league,runner,abbr,week,bye=bye)
    if not isinstance(plan,dict): return base
    for unit in UNITS:
        row = plan.get('units',{}).get(unit,{})
        if row.get('intensity') in INTENSITIES: base['units'][unit]['intensity']=row['intensity']
        if row.get('reps') in ('starters','balanced','development'): base['units'][unit]['reps']=row['reps']
    ids = {p.pid for p in _roster(league,abbr)}
    base['individual'] = {pid:mode for pid,mode in plan.get('individual',{}).items()
                          if pid in ids and mode in ('limited','rest')}
    base['focus'] = list(dict.fromkeys(pid for pid in plan.get('focus',[]) if pid in ids))[:3]
    return base

def preview(league, runner, abbr, week, plan=None, *, bye=False, recovery_done=False):
    key = f'{league.year}:{week}'
    state = getattr(league,'practice_state',None) or {}
    old = state.get('completed',{}).get(key,{}).get(abbr)
    if old is not None:
        done=copy.deepcopy(old); done['completed']=True
        return done
    plan = _plan(league,runner,abbr,week,plan,bye)
    st = runner.states.get(abbr) if runner else None
    depth = league.teams[abbr].depth
    starters = _starters(league.teams[abbr],depth)
    rows = []
    for p in _roster(league,abbr):
        c,j,saved = _health(league,runner,abbr,p)
        unit = _unit(p); settings=plan['units'][unit]; intensity=settings['intensity']
        gain,burden,shed = INTENSITIES[intensity]
        rehab = _rehab(runner,abbr,p)
        mode=plan['individual'].get(p.pid)
        duplicate=p.pid in state.get('participants',{}).get(key,{})
        snaps=0 if bye or week==1 else (getattr(st,'last_snaps',{}).get(p.pid,0) if st else 0)
        starter=snaps>=30 if st and getattr(st,'last_snaps',{}) and not bye and week!=1 else p.pid in starters
        reps = (1.25 if starter else .65) if settings['reps']=='starters' else (.55 if starter else 1.25) if settings['reps']=='development' else 1.
        if mode=='limited': reps *= .35
        if mode=='rest' or rehab or duplicate: reps=0.
        fitness=.6*float(p.ratings.get('injury_rating',80) or 80)+.4*float(p.ratings.get('tough_rating',80) or 80)
        after_j=max(0.,min(1.,j-shed + (.018*reps if intensity=='hard' else 0.)))
        if bye and not recovery_done: after_j=H.update_jadedness(after_j,0,fitness,bye=True)
        if mode=='rest' or rehab: after_j=max(0.,j-(.12 if bye and not recovery_done else .04))
        recovered=c if recovery_done else H.recover_between_games(c,fitness,7,after_j)
        after_c=max(0.,min(100.,recovered-burden*reps))
        streak=int(saved.get('hard_streak',0)) if saved.get('last_key')==f'{league.year}:{week-1}' else 0
        weight=reps*(.4 if starter else 1.) / (1+snaps/45.)
        weight*=XP.modifier(p)
        # Same work ethic/coaching factors as credit, normalized into the team budget.
        import personality as PT, staff as ST
        mult=PT.xp_mult(p)*ST.xp_mult(league.teams[abbr],p)
        weight*=mult
        if p.pid in plan['focus']: weight*=1.5
        if intensity=='hard': weight/=1+.22*streak
        risk=BASE_INJURY_RISK*reps*burden*H.condition_injury_multiplier(after_c)*(1+after_j)
        risk*= max(.6,min(1.5,(110-fitness)/40))*(.2 if unit=='special' else 1.)
        if duplicate: after_c,after_j=c,j
        rows.append(dict(pid=p.pid,name=p.name,pos=p.pos,unit=unit,condition=round(after_c,3),
                         before_condition=c,jaded=after_j,xp=0.,risk=risk,weight=weight,
                         multiplier=mult,intensity=intensity,reps=reps,duplicate=duplicate,
                         rehab=rehab,hard_streak=streak+1 if intensity=='hard' and reps else 0))
    for unit in UNITS:
        members=[r for r in rows if r['unit']==unit]
        budget=WEEKLY_XP_PER_PLAYER*len(members)*INTENSITIES[plan['units'][unit]['intensity']][0]
        if plan['units'][unit]['intensity']=='hard' and members:
            streak=sum(max(0,r['hard_streak']-1) for r in members)/len(members)
            budget*=max(.65,1./(1.+.12*streak))
        total=sum(r['weight'] for r in members)
        for r in members:
            r['xp']=min(MAX_PLAYER_XP,budget*r['weight']/total) if total else 0.
    totals=dict(xp=round(sum(r['xp'] for r in rows),2),expected_injuries=sum(r['risk'] for r in rows),
                condition=round(sum(r['condition'] for r in rows)/max(1,len(rows)),1))
    return dict(plan=plan,players=rows,totals=totals,completed=False,injuries=[],
                summary=['One weekly coaching budget is shared across participating players.'],
                metrics=[dict(label='Practice XP',value=round(totals['xp'])),
                         dict(label='Average condition',value=f"{totals['condition']}%"),
                         dict(label='Practice injury risk',value='Low' if totals['expected_injuries'] < .06 else 'Moderate' if totals['expected_injuries'] < .15 else 'High')])

def resolve(league, runner, abbr, week, plan=None, *, bye=False, recovery_done=False):
    recap=preview(league,runner,abbr,week,plan,bye=bye,recovery_done=recovery_done)
    if recap.get('completed'): return recap
    key=f'{league.year}:{week}'
    state=league.__dict__.setdefault('practice_state',{})
    state['version']=1
    for field in ('completed','participants'):
        ledger=state.setdefault(field,{})
        for old in list(ledger):
            if int(old.split(':')[0]) < int(league.year)-1: del ledger[old]
    health=state.setdefault('players',{})
    # Retired/departed historical players must not grow the save indefinitely.
    for pid,record in list(health.items()):
        last=record.get('last_key')
        if last and int(last.split(':')[0]) < int(league.year)-1: del health[pid]
    people=state['participants'].setdefault(key,{})
    roster={p.pid:p for p in _roster(league,abbr)}
    st=runner.states[abbr]
    if bye:
        st.last_snaps={}; st.snaps={}; st.cond.snaps={}
    for row in recap['players']:
        p=roster[row['pid']]
        if row['duplicate']:
            st.cond.cond[p.pid]=row['condition']; st.jaded[p.pid]=row['jaded']
            continue
        people[p.pid]=abbr
        st.cond.cond[p.pid]=row['condition']; st.jaded[p.pid]=row['jaded']
        health[p.pid]=dict(condition=row['condition'],jaded=row['jaded'],hard_streak=row['hard_streak'],last_key=key,last_team=abbr)
        # Divide out the modifier already included in the allocation. credit records
        # the exact bounded award and remains the common staff/work-ethic entry point.
        p._team_ref=league.teams[abbr]
        p.xp+=XP.credit(p,row['xp']/max(.001,row['multiplier']),'practice')
        if row['risk'] and runner.rng.random()<row['risk']:
            duration=runner.rng.random()
            weeks=1 if duration<.92 else 2 if duration<.99 else 4
            kind=str(runner.rng.choice(['Ankle','Hamstring','Calf','Shoulder']))
            p.out_until=week+weeks
            p.xp_spent['_inj_kind']=kind; p.xp_spent['_inj_week']=week
            count=f'_inj_count_{kind}'; p.xp_spent[count]=int(p.xp_spent.get(count,0) or 0)+1
            injury=dict(pid=p.pid,player=p.pid,name=p.name,kind=kind,week=week,year=league.year,weeks_out=weeks,season_ending=False,source='practice')
            p.injury_history.append(dict(injury))
            recap['injuries'].append(injury)
            st.out.add(p.pid)
    recap['completed']=True
    recap['summary']=[f"Practice complete: {round(recap['totals']['xp'])} XP shared across the team.",
                      f"Average condition: {recap['totals']['condition']}%."]
    recap['summary'] += [f"{i['name']}: {i['kind']}, estimated {i['weeks_out']} week(s)." for i in recap['injuries']] or ['No new practice injuries.']
    # Keep detailed results only for the user's report. CPU completion needs
    # totals, not a full duplicate of every player's weekly forecast.
    recap['players'] = ([{k:row[k] for k in ('pid','name','xp','condition','jaded')}
                         for row in recap['players']] if abbr == getattr(league,'user_team',None) else [])
    state.setdefault('plans',{})[abbr]=copy.deepcopy(recap['plan'])
    state['completed'].setdefault(key,{})[abbr]=copy.deepcopy(recap)
    return recap
