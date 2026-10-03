"""Practice calendar, persistence and UI adapter. Calculations live in practice.py."""
import copy
import json


def week_of(session):
    if session.stop[0] == 'week': return int(session.stop[1])
    if session.stop[0] == 'playoffs' and int(session.stop[1]) < 4: return 19 + int(session.stop[1])
    return None


def eligible(league, abbr, week):
    if week is None or abbr not in league.teams: return False
    if 1 <= week <= 18: return True
    if not 19 <= week <= 22: return False
    post = getattr(league, '_post_ref', None)
    return bool(post and not getattr(post, 'champion', None) and abbr in post.alive_now())


def result(league, abbr, week):
    return (getattr(league, 'practice_state', None) or {}).get('completed', {}).get(f'{league.year}:{week}', {}).get(abbr)


def pending(session):
    week = week_of(session)
    state = getattr(session.L, 'practice_state', None) or {}
    if getattr(session, 'played', False) or state.get('auto', {}).get(session.user_team, False): return False
    return eligible(session.L, session.user_team, week) and result(session.L, session.user_team, week) is None


def migrate(self, saved):
    """Old saves already recovered; do not recover or train an ongoing game twice."""
    if saved.get('practice_state'): return
    week = week_of(self)
    state = self.L.practice_state = {'version': 1}
    if week is None: return
    state['recovery_already_applied'] = {f'{self.L.year}:{week}': list(self.L.teams)}
    finished = {a for w,a,h,ap,hp in self.L.schedule if w == week and hp is not None}
    finished |= {h for w,a,h,ap,hp in self.L.schedule if w == week and hp is not None}
    if finished:
        state['recovery_already_applied'][f'{self.L.year}:{week+1}'] = sorted(finished)
    if self.played or finished:
        state['completed'] = {f'{self.L.year}:{week}': {
            a: dict(legacy=True, summary=['This week was already underway when practice was added.'], players=[], injuries=[])
            for a in self.L.teams}}


def recover_week(runner, week, *, skip=(), skip_players=(), apply_bye=True):
    """Enter a decision week with one recovery per player, for every club."""
    import health as H
    import practice as PR
    league = runner.L
    week = int(week)
    key = f'{league.year}:{week}'
    state = league.__dict__.setdefault('practice_state', {})
    state['recovery_timing'] = 2
    ledger = state.setdefault('recovery_already_applied', {})
    for old in list(ledger):
        if int(old.split(':')[0]) < int(league.year)-1:
            del ledger[old]
    applied = set(ledger.get(key, []))
    skip, skip_players = set(skip), set(skip_players)
    health = state.setdefault('players', {})
    previous = week - 1
    for abbr, st in runner.states.items():
        st.defer_recovery = True
        if abbr in applied:
            continue
        had_game = any(w == previous and abbr in (a, h)
                       for w, a, h, ap, hp in league.schedule)
        bye = (apply_bye and 1 <= previous <= 22 and not had_game
               and (previous <= 18 or eligible(league, abbr, previous)))
        for p in PR._roster(league, abbr):
            c, j, saved = PR._health(league, runner, abbr, p)
            if (abbr not in skip and p.pid not in skip_players
                    and saved.get('last_recovery') != key and week > 1):
                if bye:
                    j = H.update_jadedness(j, 0, PR._fitness(p), bye=True)
                c = H.recover_between_games(c, PR._fitness(p), 7, j)
            st.cond.cond[p.pid] = c
            st.jaded[p.pid] = j
            health[p.pid] = dict(saved, condition=c, jaded=j, last_team=abbr,
                                 last_key=saved.get('last_key', f'{league.year}:0'),
                                 last_recovery=key)
        applied.add(abbr)
    ledger[key] = sorted(applied)


def migrate_recovery(session, saved):
    """Move unprocessed old-save recovery to the current week exactly once."""
    state = session.L.__dict__.setdefault('practice_state', {})
    if session.runner:
        for st in session.runner.states.values():
            st.defer_recovery = True
    if state.get('recovery_timing') == 2:
        return
    week = week_of(session)
    if session.runner is not None and week is not None and not session.played:
        key = f'{session.L.year}:{week}'
        # Practice under the old timing already recovered these players.
        skip = set(state.get('completed', {}).get(key, {}))
        skip.update(a for w, a, h, ap, hp in session.L.schedule if w == week and hp is not None)
        skip.update(h for w, a, h, ap, hp in session.L.schedule if w == week and hp is not None)
        live = saved.get('_live_pending') or {}
        skip.update(a for a in (live.get('home'), live.get('away')) if a)
        recover_week(session.runner, week, skip=skip,
                     skip_players=state.get('participants', {}).get(key, {}), apply_bye=False)
    state['recovery_timing'] = 2


def record_health(runner, clubs):
    state = runner.L.__dict__.setdefault('practice_state', {})
    health = state.setdefault('players', {})
    for abbr in clubs:
        st = runner.states[abbr]
        for p in runner.L.teams[abbr].roster:
            if p.pid in st.cond.cond:
                health.setdefault(p.pid, {}).update(condition=st.cond.get(p.pid),
                    jaded=st.jaded.get(p.pid, 0.0), last_team=abbr)


def restore_transfers(runner, abbr):
    """A player joining a team after its practice keeps his existing health."""
    health = (getattr(runner.L, 'practice_state', None) or {}).get('players', {})
    team = runner.L.teams[abbr]
    st = runner.states[abbr]
    for p in list(team.roster) + list(getattr(team, 'practice_squad', [])):
        saved = health.get(p.pid)
        if saved and str(saved.get('last_key', f'{runner.L.year}:0')).split(':')[0] == str(runner.L.year) and saved.get('last_team') not in (None, abbr):
            st.cond.cond[p.pid] = saved.get('condition', 100.)
            st.jaded[p.pid] = saved.get('jaded', 0.)
            saved['last_team'] = abbr


def prepare(runner, week, clubs=None):
    import practice as PR
    league = runner.L
    week = int(week)
    direct_playoff = clubs is not None and 19 <= week <= 22 and getattr(league, '_post_ref', None) is None
    clubs = list(league.teams) if clubs is None else list(clubs)
    selected = [a for a in clubs if (eligible(league, a, week) or direct_playoff) and result(league, a, week) is None]
    if not selected: return {}
    runner.week = week
    league.week = week
    # Medical designations are established once before practice. New practice
    # injuries are then unavailable; do not reroll their designation at kickoff.
    if getattr(runner, '_listed_week', None) != week:
        runner.injury_week(week)
        runner._listed_week = week
    out = {}
    for abbr in selected:
        state = getattr(league, 'practice_state', None) or {}
        plan = state.get('plans', {}).get(abbr)
        if abbr != getattr(league, 'user_team', None) or state.get('auto', {}).get(abbr, False): plan = None
        bye = not any(w == week and abbr in (a,h) for w,a,h,ap,hp in league.schedule)
        previous_injuries = {p.pid:p.out_until for p in league.teams[abbr].roster}
        recap = PR.resolve(league, runner, abbr, week, plan, bye=bye)
        desk = runner.desks.get(abbr)
        if desk:
            for p in league.teams[abbr].roster:
                if p.out_until is not None and p.out_until != previous_injuries.get(p.pid):
                    desk.pending.pop(p.pid, None)
                    desk.playing_hurt.pop(p.pid, None)
                    desk.status[p.pid] = 'out'
        runner.refresh(abbr)
        out[abbr] = recap
        if abbr == getattr(league, 'user_team', None):
            import inbox_events as IE
            lines = summary(recap)
            # The displayed recap stays plain; only inbox composition carries IDs.
            import inbox as IB
            for injury in recap.get('injuries', []):
                p = league.player(injury.get('pid'))
                name = injury.get('name')
                if p is not None and name:
                    for i, line in enumerate(lines):
                        if line.startswith(name + ':'):
                            lines[i] = IB.player_name(p, name) + line[len(name):]
                            break
            IE.post(league, f'practice:{league.year}:{week}:{abbr}', 'practice',
                    f'{__import__("club_notes")._period(week)} practice report', '\n\n'.join(lines),
                    sender='assistant coaches', payload={'link':'gameplan:practice'})
    return out


def summary(recap):
    if not recap: return []
    if recap.get('summary'): return list(recap['summary'])
    players = recap.get('players') or []
    if isinstance(players, dict): players = list(players.values())
    injuries = recap.get('injuries') or []
    lines = [f'Practice complete. {len(players)} players reviewed.']
    for injury in injuries:
        if isinstance(injury, dict): lines.append(f"{injury.get('name', injury.get('pid','Player'))}: {injury.get('kind','injury')}.")
    if not injuries: lines.append('No new practice injuries.')
    lines.append('Review your depth chart and game plan before kickoff.')
    return lines


def view(session):
    import practice as PR
    import views
    week = week_of(session)
    league = session.L
    abbr = session.user_team
    state = getattr(league, 'practice_state', None) or {}
    can = eligible(league, abbr, week) and not session.played
    # Opening a page must not build a runner, list injuries, or consume RNG.
    runner = session.runner
    done = result(league, abbr, week)
    bye = not any(w == week and abbr in (a,h) for w,a,h,ap,hp in league.schedule)
    plan = (done or {}).get('plan') or state.get('plans', {}).get(abbr)
    if not plan or (state.get('auto', {}).get(abbr) and not done):
        plan = PR.recommend_plan(league, runner, abbr, week or 1, bye=bye)
    preview = PR.preview(league, runner, abbr, week or 1, plan,
        bye=bye) if can and not done else {}
    plan = preview.get('plan', plan)
    projections = {row['pid']: row for row in (done or preview).get('players', [])}
    players = []
    roster = {p.pid:p for p in league.teams[abbr].roster}
    roster.update((p.pid,p) for p in getattr(league.teams[abbr], 'practice_squad', []))
    for p in roster.values():
        if p.retired: continue
        st = runner.states.get(abbr) if runner else None
        health = state.get('players', {}).get(p.pid, {})
        if str(health.get('last_key', f'{league.year}:0')).split(':')[0] != str(league.year): health = {}
        condition = st.cond.get(p.pid) if st and p.pid in st.cond.cond else health.get('condition', 100)
        jaded = st.jaded.get(p.pid, 0) if st else health.get('jaded', 0)
        unit = 'special' if p.pos in ('K','P','LS') else 'offense' if p.pos in ('QB','HB','FB','TE','WR','LT','LG','C','RG','RT') else 'defense'
        projection = projections.get(p.pid, {})
        players.append(dict(pid=p.pid, name=p.name, pos=p.pos, unit=unit,
                            practice_xp=projection.get('xp'), xp_ceiling=projection.get('xp_ceiling'),
                            xp_explanation=projection.get('xp_explanation', ''),
                            condition=f'{condition:.0f}%',jaded=('High' if jaded >= .65 else 'Moderate' if jaded >= .3 else 'Low'),
                            injured=p.out_until is not None or bool(runner and p.pid in runner.desks[abbr].playing_hurt)))
    return dict(rail=views.rail(session, league, abbr),week=week,eligible=can,
                note=('Your practice results are saved.' if done else 'Practice opens before each eligible game week.' if not can else None),
                completed=done is not None,auto=bool(state.get('auto',{}).get(abbr)),
                plan=copy.deepcopy(plan),players=players,preview=preview,
                result=dict(done or {},summary=summary(done)) if done else None)


def action(session, action, plan_json=None, enabled=None):
    import practice as PR
    league = session.L
    week = week_of(session)
    abbr = session.user_team
    if action == 'auto':
        league.__dict__.setdefault('practice_state', {}).setdefault('auto', {})[abbr] = bool(enabled)
        return dict(ok=True,line='Practice management updated.')
    if not eligible(league, abbr, week) or session.played:
        return dict(ok=False,why='Practice is not available at this point in your season.')
    if result(league, abbr, week) is not None:
        return dict(ok=action == 'run',line='Practice is already complete.',why='Practice is already complete.')
    if action == 'save':
        try:
            plan = json.loads(plan_json)
            if not isinstance(plan, dict): raise ValueError('Expected a practice plan.')
            units = plan.get('units', {})
            for unit in ('offense','defense','special'):
                row = units.get(unit, {})
                if row.get('intensity') not in ('recovery','light','standard','hard') or row.get('reps') not in ('starters','balanced','development'):
                    raise ValueError('Choose a valid intensity and rep allocation for each unit.')
            roster = {p.pid for p in league.teams[abbr].roster} | {p.pid for p in getattr(league.teams[abbr],'practice_squad',[])}
            focus = plan.get('focus', [])
            if not isinstance(focus,list) or len(set(focus)) != len(focus) or len(focus)>3 or any(pid not in roster for pid in focus):
                raise ValueError('Choose up to three different players on your team.')
            individual = plan.get('individual', {})
            if not isinstance(individual,dict) or any(pid not in roster or mode not in ('limited','rest') for pid,mode in individual.items()):
                raise ValueError('Choose valid individual workloads.')
            plan = dict(units=units,individual=individual,focus=focus)
        except (TypeError,ValueError) as error: return dict(ok=False,why=str(error))
        league.__dict__.setdefault('practice_state', {}).setdefault('plans', {})[abbr] = plan
        return dict(ok=True,line='Practice plan saved.')
    if action == 'run':
        if session.runner is None:
            from season import SeasonRunner
            session.runner = SeasonRunner(league, session.rng)
        prepare(session.runner, week, (abbr,))
        return dict(ok=True,line='Practice complete. Review your roster before kickoff.')
    return dict(ok=False,why='Unknown practice action.')
