"""
THE WEEK'S GAME PLAN.

Before every game the assistants hand the coach a report on the opponent:
what they actually do (tendencies measured from their game logs this
season, next to their coach's identity), what they are good and bad at
(unit grades against the league, the men who matter, who is hurt), and
what to do about it on both sides of the ball. Each suggestion is a plan
change with a reason and the number behind it.

The coach's normal tendencies are the default. The user runs with them,
accepts some or all suggestions, or moves a lean himself within his coach's
range. AI coordinators read the same report and take suggestions by their
own adjustment skill and willingness, so AI plans become opponent-aware
rather than identity-only.

Nothing carries to the next week: the plan the game reads is base plus the
week's changes, and the state's plan resets when the game ends.
"""
import numpy as np, collections

TEND_KEYS = ('plays', 'passes', 'pa', 'motion', 'deep', 'fourth_go', 'fourth_opp', 'def_snaps', 'blitz', 'man', 'two_high', 'box8', 'shadow', 'bracket')
TWO_HIGH = {'cover_2', 'cover_4', 'cover_6', 'two_man', 'tampa_2', 'quarters'}


# ------------------------------------------------------------ tendencies, measured
def record_game(league, home, away, res):
    """What each club did in this game, into league.tendencies[year][abbr]."""
    T = league.tendencies.setdefault(league.year, {}) if hasattr(league, 'tendencies') else None
    if T is None:
        league.tendencies = {}; T = league.tendencies.setdefault(league.year, {})
    for abbr in (home, away):
        T.setdefault(abbr, collections.Counter())
    for pos, d in res['drives']:
        off = home if pos == 'home' else away; deff = away if pos == 'home' else home
        to, td = T[off], T[deff]
        for l in d.log:
            if not isinstance(l, dict) or l.get('type') not in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'interception', 'drop'): continue
            to['plays'] += 1; td['def_snaps'] += 1
            if l.get('is_pass'):
                to['passes'] += 1; to['pa'] += bool(l.get('play_action')); to['deep'] += l.get('depth') == 'deep'
            to['motion'] += bool(l.get('motion'))
            if l.get('down') == 4: to['fourth_opp'] += 1; to['fourth_go'] += 1
            td['blitz'] += bool(l.get('blitz')); td['man'] += bool(l.get('in_man')) if l.get('is_pass') else 0
            td['two_high'] += (l.get('shell') in TWO_HIGH); td['box8'] += (l.get('box') or 7) >= 8
            td['shadow'] += bool(l.get('travelled')); td['bracket'] += bool(l.get('bracketed'))
        # a punt or a kick on fourth down is a fourth-down opportunity declined
        if d.result in ('Punt', 'Field goal', 'Missed field goal'):
            to['fourth_opp'] += 1


def tendencies(league, abbr):
    """Rates for a club this season, or None before it has played."""
    T = getattr(league, 'tendencies', {}).get(league.year, {}).get(abbr)
    if not T or T.get('plays', 0) < 40: return None
    p, ps, ds = T['plays'], max(1, T['passes']), max(1, T['def_snaps'])
    return dict(pass_rate=T['passes'] / p, pa_rate=T['pa'] / ps, motion=T['motion'] / p, deep=T['deep'] / ps,
                fourth_go=T['fourth_go'] / max(1, T['fourth_opp']), blitz=T['blitz'] / ds, man=T['man'] / max(1, ds * 0.55),
                two_high=T['two_high'] / ds, box8=T['box8'] / ds, shadow=T['shadow'] / ds, bracket=T['bracket'] / ds, games=p / 62.0)


def league_rank(league, abbr, key, higher_is_more=True):
    vals = {a: (tendencies(league, a) or {}).get(key) for a in league.teams}
    vals = {a: v for a, v in vals.items() if v is not None}
    if abbr not in vals: return None
    order = sorted(vals, key=lambda a: -vals[a] if higher_is_more else vals[a])
    return order.index(abbr) + 1, len(order)


# ------------------------------------------------------------ units, graded
UNITS = {
    'QB': ('QB',), 'pass block': ('LT', 'LG', 'C', 'RG', 'RT'), 'run block': ('LT', 'LG', 'C', 'RG', 'RT'),
    'receivers': ('WR',), 'tight end': ('TE',), 'backs': ('HB',),
    'pass rush': ('LEDG', 'REDG', 'DT'), 'run front': ('LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM'),
    'corners': ('CB',), 'safeties': ('FS', 'SS'), 'linebackers': ('MIKE', 'WILL', 'SAM'),
}
UNIT_WEIGHTS = {
    'pass block': {'pass_block_rating': 1.0}, 'run block': {'run_block_rating': .6, 'run_block_power_rating': .2, 'run_block_finesse_rating': .2},
    'pass rush': {'power_moves_rating': .4, 'finesse_moves_rating': .4, 'speed_rating': .2},
    'run front': {'block_shed_rating': .5, 'tackle_rating': .3, 'strength_rating': .2},
    'corners': {'man_cover_rating': .35, 'zone_cover_rating': .35, 'speed_rating': .3},
    'safeties': {'zone_cover_rating': .4, 'play_rec_rating': .3, 'tackle_rating': .3},
    'linebackers': {'zone_cover_rating': .3, 'play_rec_rating': .3, 'tackle_rating': .4},
}
UNIT_N = {'QB': 1, 'pass block': 5, 'run block': 5, 'receivers': 3, 'tight end': 1, 'backs': 1, 'pass rush': 3, 'run front': 5, 'corners': 3, 'safeties': 2, 'linebackers': 2}


def unit_grades(league, team, healthy_only=True):
    """Mean grade of the starters at each unit."""
    from plays import rate as _rate
    out = {}
    for unit, poss in UNITS.items():
        men = [p for pos in poss for p in team.depth.get(pos, []) if (p.out_until is None or not healthy_only)]
        if unit in ('pass block', 'run block'):
            men = [team.depth[pos][0] for pos in poss if team.depth.get(pos)]
        else:
            men = sorted(men, key=lambda p: -p.ovr)[:UNIT_N[unit]]
        if not men: out[unit] = None; continue
        w = UNIT_WEIGHTS.get(unit)
        out[unit] = float(np.mean([_rate(p.ratings, w) * 100 if w else p.ovr for p in men]))
    return out


def unit_ranks(league, team):
    mine = unit_grades(league, team)
    allg = {a: unit_grades(league, t) for a, t in league.teams.items()}
    ranks = {}
    for unit, v in mine.items():
        if v is None: ranks[unit] = None; continue
        vals = sorted((g[unit] for g in allg.values() if g.get(unit) is not None), reverse=True)
        ranks[unit] = (vals.index(v) + 1 if v in vals else sum(1 for x in vals if x > v) + 1, len(vals), v)
    return ranks


# ------------------------------------------------------------ the report
def opponent_report(league, me_abbr, opp_abbr, week, rng=None):
    import weather as W
    me, opp = league.teams[me_abbr], league.teams[opp_abbr]
    tr = tendencies(league, opp_abbr); tm = tendencies(league, me_abbr)
    ur_opp, ur_me = unit_ranks(league, opp), unit_ranks(league, me)
    n = len(league.teams)
    def rank_word(r): return 'elite' if r <= 5 else 'strong' if r <= 11 else 'average' if r <= 21 else 'weak' if r <= 27 else 'the worst in the league'
    strengths, weaknesses, suggestions = [], [], []
    def unit_line(unit, ranks):
        r = ranks.get(unit)
        return f"{unit} {rank_word(r[0])} ({r[0]} of {r[1]})" if r else None

    # their offence, our defence
    for unit in ('QB', 'pass block', 'run block', 'receivers', 'tight end', 'backs'):
        r = ur_opp.get(unit)
        if not r: continue
        (strengths if r[0] <= 8 else weaknesses if r[0] >= 24 else []).append(dict(side='their offence', unit=unit, rank=r[0], text=f"Their {unit_line(unit, ur_opp)}"))
    for unit in ('pass rush', 'run front', 'corners', 'safeties', 'linebackers'):
        r = ur_opp.get(unit)
        if not r: continue
        (strengths if r[0] <= 8 else weaknesses if r[0] >= 24 else []).append(dict(side='their defence', unit=unit, rank=r[0], text=f"Their {unit_line(unit, ur_opp)}"))

    # the men who matter
    stars = sorted([p for pos in ('WR', 'TE', 'HB', 'QB') for p in opp.depth.get(pos, [])[:1] if p.out_until is None], key=lambda p: -p.ovr)[:2]
    rushers = sorted([p for pos in ('LEDG', 'REDG') for p in opp.depth.get(pos, [])[:1] if p.out_until is None], key=lambda p: -p.ovr)[:1]
    hurt = [p for t_ in (opp,) for pos, ps in t_.depth.items() for p in ps[:1] if p.out_until is not None]

    # ---- suggestions on offence (against their defence)
    def sug(side, text, why, changes):
        suggestions.append(dict(side=side, text=text, why=why, changes=changes))
    rc = ur_opp.get('corners'); rr = ur_opp.get('pass rush'); rf = ur_opp.get('run front'); rs = ur_opp.get('safeties'); rl = ur_opp.get('linebackers')
    my_wr = ur_me.get('receivers'); my_ol = ur_me.get('pass block'); my_rb = ur_me.get('backs')
    if rc and rc[0] >= 22 and my_wr and my_wr[0] <= 16:
        sug('offence', 'Attack their corners: lean deep and outside', f"their corners rank {rc[0]} of {n}, our receivers {my_wr[0]}", {'depth_mix': (-0.08, +0.03, +0.05), 'pass_bias': +0.04})
    if rf and rf[0] >= 22:
        sug('offence', 'Run it: their front does not hold up', f"their run front ranks {rf[0]} of {n}", {'pass_bias': -0.06})
    if rr and rr[0] <= 8 and (my_ol is None or my_ol[0] >= 12):
        sug('offence', 'Protect: more six-man protection and the quick game', f"their pass rush ranks {rr[0]}; our pass blocking {my_ol[0] if my_ol else '?'}", {'protection': 'six', 'depth_mix': (+0.08, -0.05, -0.03)})
    if tr and tr['blitz'] >= 0.20:
        sug('offence', 'They bring pressure: screens and quick throws, less play action', f"blitz on {tr['blitz']*100:.0f}% of snaps", {'depth_mix': (+0.06, -0.04, -0.02), 'play_action_rate': -0.06, 'screen_boost': +0.03})
    if tr and tr['two_high'] >= 0.55:
        sug('offence', 'They live in two-high: run it and work underneath', f"two-high on {tr['two_high']*100:.0f}% of snaps", {'pass_bias': -0.05, 'depth_mix': (+0.05, +0.02, -0.07)})
    if tr and tr['two_high'] <= 0.30 and tr['box8'] >= 0.25:
        sug('offence', 'Single-high and a loaded box: take the shots outside', f"eight in the box on {tr['box8']*100:.0f}% of snaps", {'pass_bias': +0.05, 'depth_mix': (-0.05, 0.0, +0.05), 'play_action_rate': +0.05})
    if tr and tr['man'] >= 0.45 and my_rb and my_rb[0] <= 10:
        sug('offence', 'Man coverage: motion and the back out of the backfield', f"man on {tr['man']*100:.0f}% of pass snaps", {'motion_rate': +0.08})

    # ---- suggestions on defence (against their offence)
    oq = ur_opp.get('QB'); ob = ur_opp.get('pass block'); orb = ur_opp.get('run block'); owr = ur_opp.get('receivers')
    my_cb = ur_me.get('corners'); my_rush = ur_me.get('pass rush')
    if ob and ob[0] >= 22 and my_rush and my_rush[0] <= 14:
        sug('defence', 'Bring it: their line cannot block us', f"their pass blocking ranks {ob[0]}, our rush {my_rush[0]}", {'blitz_rate': +0.05})
    if oq and oq[0] >= 20:
        sug('defence', 'Load the box and make their quarterback beat us', f"their quarterback ranks {oq[0]} of {n}", {'box_bias': +0.12, 'man_rate': +0.08})
    if orb and orb[0] <= 8 and tr and tr['pass_rate'] <= 0.52:
        sug('defence', 'They want to run: heavier box, stay disciplined', f"pass rate {tr['pass_rate']*100:.0f}%, run blocking ranks {orb[0]}", {'box_bias': +0.12, 'blitz_rate': -0.03})
    if tr and tr['pa_rate'] >= 0.17:
        sug('defence', 'Play action heavy: safeties stay home', f"play action on {tr['pa_rate']*100:.0f}% of dropbacks", {'zone_aggression': -0.15, 'box_bias': -0.05})
    if tr and tr['deep'] >= 0.15:
        sug('defence', 'They take shots: two-high and carry the verticals', f"deep on {tr['deep']*100:.0f}% of throws", {'shell_lean': +0.15, 'zone_aggression': -0.10})
    if tr and tr['deep'] <= 0.09 and tr['pass_rate'] >= 0.58:
        sug('defence', 'Quick game: sit on the short routes', f"deep on only {tr['deep']*100:.0f}% of a pass-heavy offence", {'zone_aggression': +0.15})
    wrs = [p for p in opp.depth.get('WR', []) if p.out_until is None]
    if len(wrs) >= 2 and wrs[0].ovr >= 88 and wrs[0].ovr - wrs[1].ovr >= 5:
        sug('defence', f'Take away {wrs[0].name}: shadow him, bracket on the shots', f"a {wrs[0].ovr:.0f} with a {wrs[1].ovr:.0f} behind him", {'travel': True, 'bracket': wrs[0].pid})
    if owr and owr[0] >= 24 and my_cb and my_cb[0] <= 12:
        sug('defence', 'Our corners can hold them one-on-one: more man, more pressure', f"their receivers rank {owr[0]}, our corners {my_cb[0]}", {'man_rate': +0.10, 'blitz_rate': +0.04})

    # the sky
    home_abbr = opp_abbr if _is_home(league, opp_abbr, me_abbr, week) else me_abbr
    forecast = _forecast(home_abbr, week)
    if forecast.get('weather_risk', 0) >= 0.3:
        sug('offence', 'Weather coming: lean to the run, shorten the passing game', forecast['text'], {'pass_bias': -0.04, 'depth_mix': (+0.05, 0.0, -0.05)})

    return dict(week=week, me=me_abbr, opp=opp_abbr,
                coach=dict(name=opp.gm.name if opp.gm else None, prestige=round(getattr(opp.gm, 'prestige', 0)) if opp.gm else None,
                           tree=getattr(opp.gm, 'tree', '') if opp.gm else ''),
                tendencies=tr, my_tendencies=tm, units=ur_opp, my_units=ur_me,
                stars=[dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr)) for p in stars + rushers],
                injured=[dict(pid=p.pid, name=p.name, pos=p.pos, back=p.out_until) for p in hurt][:6],
                strengths=strengths, weaknesses=weaknesses, suggestions=suggestions, forecast=forecast)


def _is_home(league, a, b, week):
    for wk, away, home, *_ in league.schedule:
        if wk == week and home == a and away == b: return True
    return False


def _forecast(home_abbr, week):
    import weather as W
    if home_abbr in W.DOMES: return dict(text='Indoors', weather_risk=0.0)
    m = W.WEEK_MONTH(week); c = W.CLIMATE.get(home_abbr, W.DEFAULT_CLIMATE)
    rain = c['rain'][m]; snow = c['snow'][m - 2] * 1.7 if m >= 2 else 0.0; wind = c['wind']
    parts = [f"around {c['temp'][m]}°F"]
    if snow >= 0.15: parts.append(f"snow {snow*100:.0f}%")
    if rain >= 0.12: parts.append(f"rain {rain*100:.0f}%")
    if wind >= 0.15: parts.append(f"wind likely")
    return dict(text=', '.join(parts), weather_risk=float(rain + snow + 0.5 * wind), temp=c['temp'][m])


# ------------------------------------------------------------ applying it
RANGE = {'pass_bias': 0.10, 'play_action_rate': 0.12, 'motion_rate': 0.15, 'blitz_rate': 0.10, 'box_bias': 0.25,
         'man_rate': 0.20, 'shell_lean': 0.25, 'zone_aggression': 0.25}


def apply_changes(plan, base, changes):
    """A week's changes onto the plan, each lean kept inside the coach's range of his base."""
    for k, v in changes.items():
        if k == 'depth_mix':
            d = np.array(plan.depth_mix, float) + np.array(v, float)
            d = np.clip(d, 0.05, 0.9); plan.depth_mix = tuple(d / d.sum())
        elif k == 'protection':
            plan.protection = v
        elif k in ('travel', 'bracket'):
            setattr(plan, k, v)
        elif k == 'screen_boost':
            plan.screen_boost = getattr(plan, 'screen_boost', 0.0) + v
        elif k in RANGE:
            b = float(getattr(base, k, getattr(plan, k)))
            setattr(plan, k, float(np.clip(getattr(plan, k) + v, b - RANGE[k], b + RANGE[k])))
    return plan


def ai_plan(league, state, me_abbr, opp_abbr, week, rng):
    """An AI coordinator takes the report's suggestions by his skill and willingness."""
    rep = opponent_report(league, me_abbr, opp_abbr, week)
    skill = float(state.coach.get('adjust_skill', 0.5)); will = float(state.coach.get('adjust_willingness', 0.5))
    taken = []
    for s in rep['suggestions']:
        if rng.random() < 0.35 + 0.5 * skill * (0.6 + 0.8 * will):
            apply_changes(state.plan, state.base_plan, s['changes']); taken.append(s['text'])
    state.week_plan_taken = taken
    return rep, taken


def user_plan(league, state, week):
    """The user's saved week: changes he accepted or made, applied to the plan the game reads."""
    wp = getattr(league, 'user_week_plan', None)
    if not wp or wp.get('week') != week or wp.get('year') != league.year: return []
    apply_changes(state.plan, state.base_plan, wp.get('changes', {}))
    return list(wp.get('changes', {}).keys())


def set_user_plan(league, week, changes):
    """From the UI: the changes for this week (a merged dict of param -> delta or value)."""
    league.user_week_plan = dict(year=league.year, week=week, changes=dict(changes))
    return league.user_week_plan


def post_report(league, week):
    """The assistants' report into the user's inbox before the week."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if not user: return None
    opp = None
    for wk, away, home, *_ in league.schedule:
        if wk == week and user in (home, away): opp = away if home == user else home
    if opp is None: return None
    rep = opponent_report(league, user, opp, week)
    body = f"Week {week} against {opp}. " + (f"Their coach: {rep['coach']['name']}, prestige {rep['coach']['prestige']}. " if rep['coach']['name'] else '')
    if rep['strengths']: body += 'Strengths: ' + '; '.join(s['text'] for s in rep['strengths'][:3]) + '. '
    if rep['weaknesses']: body += 'Weaknesses: ' + '; '.join(s['text'] for s in rep['weaknesses'][:3]) + '. '
    body += f"Forecast: {rep['forecast']['text']}. {len(rep['suggestions'])} suggestions from the assistants."
    IB.post(league, 'game_plan', f"Game plan: week {week} at {opp}" if not _is_home(league, user, opp, week) else f"Game plan: week {week} vs {opp}",
            body, sender='assistants', payload=dict(report=rep, link=f'gameplan:{week}'), expires_week=week + 1)
    league.game_plan_reports = getattr(league, 'game_plan_reports', {}); league.game_plan_reports[week] = rep
    return rep
