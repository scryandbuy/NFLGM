"""Weekly preparation. Read-only previews; one persisted award per player/week.

Individual ceilings decline with elapsed seasons, including practice-squad years.
Development, coaching and preparation determine the fraction earned each week.
"""
import copy
import health as H
import xp as XP

UNITS = ('offense', 'defense', 'special')
# Light work offsets part of a typical starter's game fatigue, not all of it.
INTENSITIES = {'recovery': (.0, .0, .045), 'light': (.55, .35, .006),
               'standard': (1., 1., .0), 'hard': (1.20, 2.7, -.018)}
OFFENSE = {'QB','HB','FB','WR','TE','LT','LG','C','RG','RT'}
WEEKLY_XP_CEILINGS = (1000., 850., 700., 550., 425., 325., 250., 200., 175., 150.)
MAX_COACH_XP_MULT = 1.15 * 1.15  # top coordinator plus Teacher/eligible Developer
# About 0.04 incidents/team/week at standard; much less than game exposure.
BASE_INJURY_RISK = .0007

def _entry_year(league, p):
    for value in (getattr(p, 'entry_year', None), getattr(p, 'draft_year', None),
                  p.xp_spent.get('_practice_entry_year')):
        if value is not None:
            return min(int(league.year), int(value))
    # Legacy players without either date get an anchor at their first practice.
    # Persisted on resolution only; previewing must never change the save.
    return int(league.year) - max(0, int(getattr(p, 'accrued', 0) or 0))

def _xp_award(league, team, p, reps, gain, focused, streak):
    import staff as ST
    experience = max(0, int(league.year) - _entry_year(league, p))
    ceiling = WEEKLY_XP_CEILINGS[min(experience, len(WEEKLY_XP_CEILINGS)-1)]
    clamp = lambda value: max(0., min(1., float(value)))
    factors = dict(development=clamp(XP.modifier(p)/max(XP.DEV_MULT.values())),
                   coaching=clamp(ST.xp_mult(team, p)/MAX_COACH_XP_MULT),
                   reps=clamp(reps/1.25*max(1.,gain)/(1.+.22*streak)),
                   focus=1. if focused else 2./3., intensity=clamp(gain))
    fraction = 1.
    for value in factors.values(): fraction *= value
    award = min(ceiling, max(0., ceiling*fraction))
    experience_word = 'Rookie' if experience == 0 else f'Year {experience+1}'
    explanation = (f'{experience_word}: {ceiling:,.0f} XP weekly ceiling. '
                   + '; '.join(f'{name.title()} {value:.0%}' for name,value in factors.items())
                   + f'. Award capped at {ceiling:,.0f} XP.')
    return dict(xp=award, xp_ceiling=ceiling, xp_experience=experience,
                xp_factors=factors, xp_explanation=explanation)

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

def _fitness(p):
    return (.6*float(p.ratings.get('injury_rating',80) or 80)+
            .4*float(p.ratings.get('tough_rating',80) or 80))


def recommend_plan(league, runner, abbr, week, *, bye=False):
    players = _roster(league,abbr)
    team = league.teams[abbr]
    starters = _starters(team,team.depth)
    st = runner.states.get(abbr) if runner else None
    snaps = (getattr(st,'last_snaps',None) or {}) if week != 1 else {}
    schedule = getattr(league,'schedule',[])
    previous_bye = bool(schedule) and week > 1 and not any(w == week-1 and abbr in (a,h)
        for w,a,h,ap,hp in schedule)
    # Judge the coming practice week, not the condition immediately after Sunday.
    # One exhausted player should receive protection without resting his whole unit.
    units, individual, reasons = {}, {}, []
    candidates = []
    for unit in UNITS:
        members = [p for p in players if _unit(p)==unit]
        healthy = []
        for p in members:
            c,j,saved = _health(league,runner,abbr,p)
            projected = H.recover_between_games(c,_fitness(p),7,j)
            if _rehab(runner,abbr,p) or c < 55 or j > .65:
                individual[p.pid] = 'rest'
                continue
            if bye and (projected < 95 or j > .08 or snaps.get(p.pid,0) >= 75):
                # Spend the break recovering worn players individually, while
                # healthy teammates can still develop with light work.
                individual[p.pid] = 'rest'
                continue
            if projected < 92 or j > .35 or snaps.get(p.pid,0) >= 75:
                individual[p.pid] = 'limited'
            healthy.append((p,projected,j,saved))
        regulars = [row for row in healthy if row[0].pid in starters or snaps.get(row[0].pid,0)>=30]
        exposed = regulars or healthy
        # Typical game loads build hundredths per week. Waiting for the UI's
        # severe-fatigue bands made a lighter week effectively unreachable.
        fatigue_limit = .06 if week > 18 else .08
        tired = sum(c < 95 or j > fatigue_limit for p,c,j,_ in exposed)/max(1,len(exposed))
        depleted = (len(members)-len(healthy))/max(1,len(members))
        young = [p for p,_,_,_ in healthy if p.age <= 25 and
                 p.pid not in starters and snaps.get(p.pid,0)<30 and p.pid not in individual]
        fresh = bool(healthy) and all(c >= 98.5 and j < .06 and
                    not (s.get('last_key')==f'{league.year}:{week-1}' and s.get('hard_streak',0))
                    for _,c,j,s in healthy)
        if bye:
            if healthy:
                intensity,reason = 'light','Bye week: light development work; tired or injured players rest.'
            else:
                intensity,reason = 'recovery','Bye week: this unit needs recovery; all players rest.'
        elif tired >= .30 or depleted >= .25:
            intensity,reason = 'light','Several regulars need a lighter week.'
        elif week <= 18 and (week == 1 or previous_bye) and fresh and depleted == 0 and len(young) >= max(2,len(members)*.35):
            intensity,reason = 'hard','Fresh unit after a break, with young depth to develop.'
        else:
            intensity,reason = 'standard','Normal preparation; protect tired players individually.'
        reps = 'development' if bye or intensity=='light' or (week<=18 and len(young)>=len(members)*.30) else 'balanced'
        units[unit] = dict(intensity=intensity,reps=reps)
        reasons.append(f'{unit.title()}: {reason}')
        # Focus can develop starters too; the reserve-only list is for deciding
        # unit reps, not eligibility for individual coaching attention.
        candidates.extend(p for p,_,_,_ in healthy)
    # Three focused players receive the full coaching attention factor.
    def focus_value(p):
        experience = max(0, int(league.year) - _entry_year(league, p))
        ceiling = WEEKLY_XP_CEILINGS[min(experience, len(WEEKLY_XP_CEILINGS)-1)]
        return ceiling * XP.modifier(p) * (.35 if individual.get(p.pid)=='limited' else 1.)
    candidates.sort(key=lambda p:(-focus_value(p),p.age,p.pid))
    return dict(units=units,individual=individual,
                focus=[p.pid for p in candidates[:3]],reasons=reasons)

def _plan(league,runner,abbr,week,plan,bye):
    base = recommend_plan(league,runner,abbr,week,bye=bye)
    if not isinstance(plan,dict): return base
    # Automatic advice cannot describe a manually overridden plan.
    base.pop('reasons',None)
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
        fitness=_fitness(p)
        after_j=max(0.,min(1.,j-shed + (.018*reps if intensity=='hard' else 0.)))
        if mode=='limited': after_j=max(0.,after_j-.008)
        if bye and not recovery_done: after_j=H.update_jadedness(after_j,0,fitness,bye=True)
        if mode=='rest' or rehab: after_j=max(0.,j-(.12 if bye and not recovery_done else .04))
        recovered=c if recovery_done else H.recover_between_games(c,fitness,7,after_j)
        after_c=max(0.,min(100.,recovered-burden*reps))
        streak=int(saved.get('hard_streak',0)) if saved.get('last_key')==f'{league.year}:{week-1}' else 0
        award=_xp_award(league,league.teams[abbr],p,reps,gain,
                        p.pid in plan['focus'],streak if intensity=='hard' else 0)
        # Reverse credit's common multipliers after calculating practice's own
        # normalized factors. Practice has no extra work-ethic multiplier.
        import personality as PT, staff as ST
        mult=PT.xp_mult(p)*ST.xp_mult(league.teams[abbr],p)
        risk=BASE_INJURY_RISK*reps*burden*H.condition_injury_multiplier(after_c)*(1+after_j)
        risk*= max(.6,min(1.5,(110-fitness)/40))*(.2 if unit=='special' else 1.)
        if duplicate: after_c,after_j=c,j
        rows.append(dict(pid=p.pid,name=p.name,pos=p.pos,unit=unit,condition=round(after_c,3),
                         before_condition=c,jaded=after_j,risk=risk,**award,
                         multiplier=mult,intensity=intensity,reps=reps,duplicate=duplicate,
                         rehab=rehab,hard_streak=streak+1 if intensity=='hard' and reps else 0))
    totals=dict(xp=round(sum(r['xp'] for r in rows),2),expected_injuries=sum(r['risk'] for r in rows),
                condition=round(sum(r['condition'] for r in rows)/max(1,len(rows)),1))
    return dict(plan=plan,players=rows,totals=totals,completed=False,injuries=[],
                summary=['Individual weekly XP ceilings decline with experience; coaching, development, reps and focus determine the award.'],
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
        p.xp_spent.setdefault('_practice_entry_year',_entry_year(league,p))
        # credit records the bounded award once, without reapplying modifiers.
        p._team_ref=league.teams[abbr]
        credited=XP.credit(p,row['xp']/max(.001,row['multiplier']),'practice')
        # Floating-point reversal of the common multipliers can overshoot by
        # a fraction of an XP. Keep both the balance and ledger within forecast.
        paid=min(row['xp'],credited)
        if paid != credited: p.xp_spent['_earned']['practice']-=credited-paid
        p.xp+=paid
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
    recap['summary']=[f"Practice complete: {round(recap['totals']['xp'])} XP earned across the team.",
                      f"Average condition: {recap['totals']['condition']}%."]
    recap['summary'] += [f"{i['name']}: {i['kind']}, estimated {i['weeks_out']} week(s)." for i in recap['injuries']] or ['No new practice injuries.']
    # Keep detailed results only for the user's report. CPU completion needs
    # totals, not a full duplicate of every player's weekly forecast.
    recap['players'] = ([{k:row[k] for k in ('pid','name','xp','condition','jaded',
                         'xp_ceiling','xp_experience','xp_factors','xp_explanation')}
                         for row in recap['players']] if abbr == getattr(league,'user_team',None) else [])
    state.setdefault('plans',{})[abbr]=copy.deepcopy(recap['plan'])
    state['completed'].setdefault(key,{})[abbr]=copy.deepcopy(recap)
    return recap
