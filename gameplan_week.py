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
import numpy as np, collections, re

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
                two_high=T['two_high'] / ds, box8=T['box8'] / ds, shadow=T['shadow'] / ds, bracket=T['bracket'] / ds, games=sum(league.teams[abbr].record) if abbr in league.teams else 0)


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


def _offensive_line(team, healthy_only=True):
    """Use the field's unique assignments, preserving pins and injury replacements."""
    import offense_roles as OR
    depth = team.depth
    if healthy_only:
        try:
            return [(role, p) for role, p in OR.assign(depth, OR.base_package(team.gm)) if role in OR.OL]
        except ValueError:
            pass  # An incomplete preseason roster can still receive a report.
    used, line = set(), []
    for role in OR.OL:
        candidates = [p for pos in (role,) + tuple(x for x in OR.OL if x != role)
                      for p in depth.get(pos, ()) if p.pid not in used
                      and (not healthy_only or p.out_until is None)]
        if candidates:
            line.append((role, candidates[0])); used.add(candidates[0].pid)
    return line


def unit_grades(league, team, healthy_only=True):
    """Mean grade of the starters at each unit."""
    from plays import rate as _rate
    out = {}
    depth = team.depth
    for unit, poss in UNITS.items():
        men = [p for pos in poss for p in depth.get(pos, []) if (p.out_until is None or not healthy_only)]
        if unit in ('pass block', 'run block'):
            men = [p for _, p in _offensive_line(team, healthy_only)]
        else:
            men = sorted(men, key=lambda p: -p.ovr)[:UNIT_N[unit]]
        if not men: out[unit] = None; continue
        w = UNIT_WEIGHTS.get(unit)
        out[unit] = float(np.mean([_rate(p.ratings, w) * 100 if w else p.ovr for p in men]))
    return out


def season_underway(league):
    """Whether a game has been played this season: every club's record is reset to 0-0 at the New Year."""
    return any(sum(int(x) for x in (t.record or [0, 0, 0])[:3]) > 0 for t in league.teams.values())


def unit_ranks(league, team, all_grades=None):
    """Each unit against the league's 31 others, by grade. Hidden until the season's first game has been played,
    at the start of every year: before that every club shows the same ranks in every new game (same rosters),
    which read as carried over rather than earned."""
    if not season_underway(league):
        return {unit: None for unit in UNITS}
    allg = all_grades if all_grades is not None else {a: unit_grades(league, t) for a, t in league.teams.items()}
    mine = allg.get(team.abbr)
    if mine is None:
        mine = unit_grades(league, team)
    ranks = {}
    for unit, v in mine.items():
        if v is None: ranks[unit] = None; continue
        vals = sorted((g[unit] for g in allg.values() if g.get(unit) is not None), reverse=True)
        ranks[unit] = (vals.index(v) + 1 if v in vals else sum(1 for x in vals if x > v) + 1, len(vals), v)
    return ranks


def _recent_protection(league, abbr, week):
    """Last three completed games before this game, using recorded team affiliation.

    Blocking pressures are lost blocking reps, not unique pressured dropbacks;
    never sum them into a QB pressure percentage. Old books without team tags
    supply no evidence instead of assigning traded players to their new club.
    """
    games = []
    for key, book in (getattr(league, 'game_stats', {}) or {}).items():
        parts = key.split('-')
        if len(parts) != 4 or parts[0] != str(league.year): continue
        wk = int(parts[1])
        if wk >= week or abbr not in parts[2:]: continue
        lines = {pid: s for pid, s in book.items() if s.get('team') == abbr}
        if lines: games.append((wk, lines))
    games.sort(key=lambda x: x[0], reverse=True)
    dropbacks = sacks = sack_games = 0
    blocking = collections.defaultdict(collections.Counter)
    for _, lines in games[:3]:
        game_dropbacks = sum(s.get('pass_plays', 0) for s in lines.values())
        game_sacks = sum(s.get('sacked', 0) for s in lines.values())
        # Corroborating games may sit just below the aggregate 8% trigger;
        # require two of them so one outlier cannot carry the whole window.
        sack_games += game_dropbacks >= 20 and game_sacks / max(1, game_dropbacks) >= .07
        for pid, s in lines.items():
            dropbacks += s.get('pass_plays', 0); sacks += s.get('sacked', 0)
            blocking[pid]['reps'] += s.get('pb_snaps', 0)
            blocking[pid]['pressures'] += s.get('pressures_allowed', 0)
            reps = s.get('pb_snaps', 0)
            blocking[pid]['pressure_games'] += reps >= 20 and s.get('pressures_allowed', 0) / max(1, reps) >= .12
    return dict(games=min(3, len(games)), dropbacks=dropbacks, sacks=sacks,
                sack_games=sack_games, blocking=blocking)


def protection_read(league, me, opp, week):
    """Scouting evidence, using the same move grades and side matching as the field.

    These are advice thresholds, not changes to play outcomes. A large mismatch
    can justify help alone; modest mismatches need repetition or recent trouble.
    Rankings remain a display feature and do not gate Week 1 advice.
    """
    import defense_roles as DR, defensive_rush as RUSH
    from matchups import PASS_RUSH
    from plays import rate
    line = _offensive_line(me)
    blockers = [dict(p.ratings, pid=p.pid, pos=role, name=p.name) for role, p in line]
    front = getattr(opp.gm, 'def_front', '4-3')
    fronts = ('4-3', '3-4') if front == 'multiple' else (front,)
    matchups = {}
    depth = opp.depth
    unavailable = {p.pid for men in depth.values() for p in men if p.out_until is not None}
    for family in fronts:
        for package in ('base', 'nickel'):
            rows = DR.assign(depth, family, package, pins=getattr(opp, 'depth_pins', None), excluded=unavailable)
            rush = [dict(r, player=dict(r['player'].ratings, pid=r['player'].pid, name=r['player'].name))
                    for r in rows if r.get('player') is not None
                    and r['alignment'] in RUSH.EDGES + RUSH.INTERIOR]
            pairs = RUSH.protection_pairs(blockers, rush)
            for assignment, blocker in zip(rush, pairs):
                if blocker is None: continue
                r = assignment['player']
                grades = {move: rate(r, PASS_RUSH['rusher'][move]) for move in ('power', 'finesse')}
                move = max(grades, key=grades.get)
                gap = 100 * (grades[move] - rate(blocker, PASS_RUSH['blocker'][move]))
                evidence = dict(pid=blocker['pid'], blocker=blocker['name'], role=blocker['pos'],
                                rusher=r['name'], move=move, gap=gap)
                if gap > matchups.get(blocker['pid'], {}).get('gap', -1000):
                    matchups[blocker['pid']] = evidence
    ordered = sorted(matchups.values(), key=lambda x: -x['gap'])
    worst = ordered[0] if ordered else None
    recent = _recent_protection(league, me.abbr, week)
    enough = recent['games'] >= 2 and recent['dropbacks'] >= 60
    sack_rate = recent['sacks'] / max(1, recent['dropbacks'])
    struggling = [x for x in ordered if x['gap'] >= 7
                  and recent['blocking'][x['pid']]['reps'] >= 40
                  and recent['blocking'][x['pid']]['pressure_games'] >= 2
                  and recent['blocking'][x['pid']]['pressures'] /
                      recent['blocking'][x['pid']]['reps'] >= .12]
    mismatch = worst is not None and (worst['gap'] >= 12 or sum(x['gap'] >= 9 for x in ordered) >= 2)
    recent_trouble = enough and recent['sack_games'] >= 2 and (sack_rate >= .12 or
                                 (sack_rate >= .08 and worst is not None and worst['gap'] >= 7))
    recommend = bool(mismatch or recent_trouble or (enough and struggling))
    reasons = []
    if recommend and worst and worst['gap'] >= 3:
        reasons.append(f"{worst['rusher']} has a {worst['move']}-rush advantage against {worst['blocker']} at {worst['role']}")
    if recommend and enough and sack_rate >= .08:
        reasons.append(f"{recent['sacks']:.0f} sacks on {recent['dropbacks']:.0f} dropbacks over our last {recent['games']} games")
    if recommend and enough and struggling:
        x = struggling[0]; b = recent['blocking'][x['pid']]
        reasons.append(f"{x['blocker']} allowed pressure on {b['pressures']:.0f} of {b['reps']:.0f} recent blocking reps")
    return dict(recommend=recommend, why='; '.join(reasons), matchups=ordered,
                recent_games=recent['games'], dropbacks=recent['dropbacks'], sacks=recent['sacks'])


def protection_suggestion(league, me, opp, week, read=None, opponent_tendencies=None):
    """Choose one protection recommendation from observed risk and matchups."""
    read = protection_read(league, me, opp, week) if read is None else read
    rows = read['matchups']
    if read['recommend']:
        interior = [r for r in rows if r['role'] in ('LG', 'C', 'RG') and r['gap'] >= 7]
        distributed = sum(r['gap'] >= 7 for r in rows) >= 2
        slide = bool(interior and distributed)
        return dict(side='offence',
            text='Full Slide: coordinate protection against their interior rush' if slide else
                 'Protect: more six-man protection and the quick game',
            why=read['why'], changes=dict(protection='full_slide' if slide else 'six',
                                         depth_mix=(+.08, -.05, -.03)))
    # Absence of trouble is insufficient: require clean recent protection,
    # favorable line matchups, low observed blitzing and a useful extra target.
    tape = opponent_tendencies if opponent_tendencies is not None else tendencies(league, opp.abbr)
    if not tape or tape['blitz'] > .15 or len(_offensive_line(me)) != 5:
        return None
    if not rows or max(r['gap'] for r in rows) > -5:
        return None
    if read['recent_games'] < 2 or read['dropbacks'] < 60 or read['sacks'] / read['dropbacks'] > .04:
        return None
    from plays import rate
    backs = [p for p in me.depth.get('HB', ()) if p.out_until is None]
    back = 100 * rate(backs[0].ratings, {'catch_rating': .45, 'route_run_short_rating': .35, 'speed_rating': .20}) if backs else None
    coverage = unit_grades(league, opp).get('linebackers')
    if back is None or coverage is None or back < coverage + 5:
        return None
    return dict(side='offence', text='Empty: release the extra receiver with five-man protection',
        why=f"our line has favorable rush matchups; {read['sacks']:.0f} sacks on {read['dropbacks']:.0f} recent dropbacks, "
            f"they blitz on {tape['blitz']*100:.0f}% of snaps, and our back grades above their coverage linebackers",
        changes=dict(protection='empty', depth_mix=(+.05, -.02, -.03)))


def scouting_suggestions(league, me, opp, all_grades=None):
    """Cautious roster and coach reads before the opponent has current-season tape.

    Keep these distinct from measured tendencies and performance rankings.
    They use current, healthy personnel and known coaching preferences only.
    """
    mine = (all_grades.get(me.abbr) if all_grades is not None else
            unit_grades(league, me) if me.depth else {})
    theirs = (all_grades.get(opp.abbr) if all_grades is not None else
              unit_grades(league, opp) if opp.depth else {})
    suggestions = []

    def edge(our_unit, their_unit):
        a, b = mine.get(our_unit), theirs.get(their_unit)
        return None if a is None or b is None else a - b

    def add(side, text, why, changes):
        suggestions.append(dict(side=side, text=text,
                                why=f'Pregame projection: {why}; current-season tape is not available yet',
                                changes=changes, basis='projection'))

    receiver_edge = edge('receivers', 'corners')
    run_edge = edge('run block', 'run front')
    if receiver_edge is not None and receiver_edge >= 7 and (run_edge is None or receiver_edge >= run_edge):
        add('offence', 'Test their corners with more outside throws',
            f'our current receivers grade {mine["receivers"]:.0f} against their corners at {theirs["corners"]:.0f}',
            {'pass_bias': +0.03, 'depth_mix': (-0.04, 0.0, +0.04)})
    elif run_edge is not None and run_edge >= 7:
        add('offence', 'Lean on the run blocking matchup',
            f'our current line grades {mine["run block"]:.0f} against their run front at {theirs["run front"]:.0f}',
            {'pass_bias': -0.04})

    gm = getattr(opp, 'gm', None)
    if gm is not None and not any(s['side'] == 'offence' for s in suggestions):
        shell = float(getattr(gm, 'shell', .5))
        coverage = float(getattr(gm, 'coverage', .5))
        if shell >= .56 and coverage <= .35:
            add('offence', 'Expect two-high zones: work underneath and test the run',
                'their coach leans toward a two-high shell and zone coverage',
                {'pass_bias': -0.03, 'depth_mix': (+0.05, +0.02, -0.07)})
        elif shell <= .40 and coverage >= .60:
            add('offence', 'Expect single-high man: use motion and outside shots',
                'their coach leans toward a single-high shell and man coverage',
                {'motion_rate': +0.06, 'depth_mix': (-0.04, 0.0, +0.04)})

    receiving_threat = theirs.get('receivers')
    our_corners = mine.get('corners')
    if receiving_threat is not None and our_corners is not None and receiving_threat - our_corners >= 7:
        add('defence', 'Protect the deep routes against their receivers',
            f'their current receivers grade {receiving_threat:.0f} against our corners at {our_corners:.0f}',
            {'shell_lean': +0.10, 'zone_aggression': -0.08})
    return suggestions


# ------------------------------------------------------------ the report
def opponent_report(league, me_abbr, opp_abbr, week, rng=None):
    import weather as W
    me, opp = league.teams[me_abbr], league.teams[opp_abbr]
    tr = tendencies(league, opp_abbr); tm = tendencies(league, me_abbr)
    # This snapshot lasts only for this report: roster changes are visible next time.
    all_grades = {a: unit_grades(league, t) for a, t in league.teams.items()} if season_underway(league) else None
    ur_opp, ur_me = unit_ranks(league, opp, all_grades), unit_ranks(league, me, all_grades)
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
    protection = protection_suggestion(league, me, opp, week, opponent_tendencies=tr)
    if protection:
        suggestions.append(protection)
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

    if tr is None:
        suggestions.extend(scouting_suggestions(league, me, opp, all_grades))

    # the sky
    home_abbr = opp_abbr if _is_home(league, opp_abbr, me_abbr, week) else me_abbr
    forecast = game_forecast(league, home_abbr, week)
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
RANGE = {'pass_bias': 0.10, 'play_action_rate': 0.12, 'motion_rate': 0.15, 'tempo': 0.15, 'blitz_rate': 0.10, 'box_bias': 0.25,
         'man_rate': 0.20, 'shell_lean': 0.25, 'zone_aggression': 0.25}


def apply_changes(plan, base, changes):
    """A week's changes onto the plan, each lean kept inside the coach's range of his base."""
    for k, v in changes.items():
        if k == 'depth_mix':
            d = np.array(plan.depth_mix, float) + np.array(v, float)
            if d.shape != (3,) or not np.all(np.isfinite(d)): continue
            d = np.clip(d, 0.05, 0.9); plan.depth_mix = tuple(d / d.sum())
        elif k == 'protection':
            plan.protection = v
            plan.protection_locked = True
        elif k in ('travel', 'bracket', 'travel_target'):
            setattr(plan, k, v)
        elif k == 'screen_boost':
            plan.screen_boost = getattr(plan, 'screen_boost', 0.0) + v
        elif k in ('sub_lean', 'heavy_lean'):
            setattr(plan, k, float(np.clip(getattr(plan, k, 0.0) + v, -1.0, 1.0)))
        elif k in RANGE:
            b = float(getattr(base, k, getattr(plan, k)))
            if not np.isfinite(float(v)): continue
            lo, hi = b - RANGE[k], b + RANGE[k]
            if k not in ('pass_bias', 'box_bias'): lo, hi = max(0.0, lo), min(1.0, hi)
            setattr(plan, k, float(np.clip(getattr(plan, k) + v, lo, hi)))
    return plan


def ai_plan(league, state, me_abbr, opp_abbr, week, rng):
    """An AI coordinator takes the report's suggestions by his skill and willingness."""
    rep = opponent_report(league, me_abbr, opp_abbr, week)
    will = float(state.coach.get('adjust_willingness', 0.5))
    team = league.teams[me_abbr]
    import staff as ST
    taken = []
    for s in rep['suggestions']:
        # the coordinator on that side of the ball decides how much of the report he sees
        skill = ST.plan_skill(team, s.get('side', 'offence')) if getattr(team, 'staff', None) else float(state.coach.get('adjust_skill', 0.5))
        if rng.random() < 0.35 + 0.5 * skill * (0.6 + 0.8 * will):
            apply_changes(state.plan, state.base_plan, s['changes']); taken.append(s['text'])
    state.week_plan_taken = taken
    return rep, taken


def user_plan(league, state, week):
    """The user's saved week: changes he accepted or made, applied to the plan the game reads."""
    wp = getattr(league, 'user_week_plan', None)
    if not wp or wp.get('week') != week or wp.get('year') != league.year: return []
    ch = wp.get('changes', {})
    apply_changes(state.plan, state.base_plan, ch)
    # the game-week calls the GM made himself are his: kickoff does not re-decide them
    state.plan.travel_locked = 'travel' in ch
    state.plan.bracket_locked = 'bracket' in ch
    if ch.get('travel_target'): state.plan.travel_target = ch['travel_target']
    return list(ch.keys())


def set_user_plan(league, week, changes, taken=None):
    """From the UI: the changes for this week (a merged dict of param -> delta or value),
    and the report suggestions taken, by their text, so the pages can mark them."""
    prev = getattr(league, 'user_week_plan', None) or {}
    keep = list(prev.get('taken', [])) if (prev.get('week') == week and prev.get('year') == league.year) else []
    league.user_week_plan = dict(year=league.year, week=week, changes=dict(changes), taken=(list(taken) if taken is not None else keep), skipped=(list(prev.get('skipped', [])) if prev.get('week') == week and prev.get('year') == league.year else []))
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
    body = f"{__import__('club_notes')._period(week)} against {opp}. " + (f"Their coach: {rep['coach']['name']}, prestige {rep['coach']['prestige']}. " if rep['coach']['name'] else '')
    if rep['strengths']: body += 'Strengths: ' + '; '.join(s['text'] for s in rep['strengths'][:3]) + '. '
    if rep['weaknesses']: body += 'Weaknesses: ' + '; '.join(s['text'] for s in rep['weaknesses'][:3]) + '. '
    count = len(rep['suggestions'])
    body += f"Forecast: {rep['forecast']['text']}. {count} suggestion{'s' if count != 1 else ''} from the assistants."
    IB.post(league, 'game_plan', f"Game plan: week {week} at {opp}" if not _is_home(league, user, opp, week) else f"Game plan: week {week} vs {opp}",
            body, sender='assistants', payload=dict(report=rep, link=f'gameplan:{week}'), expires_week=week)   # gone once the week is played
    league.game_plan_reports = getattr(league, 'game_plan_reports', {}); league.game_plan_reports[week] = rep
    return rep


def refresh_open_report(league, week):
    """Repair an empty current-week report saved before scouting projections existed.

    Preserve the original message, its read state, and historical reports. The
    count is at the end of the body, so existing entity offsets stay valid.
    """
    user = getattr(league, 'user_team', None)
    if not user:
        return False
    for mail in reversed(getattr(league, 'inbox', None) or []):
        old = (mail.get('payload') or {}).get('report') or {}
        if (mail.get('kind') != 'game_plan' or mail.get('year') != league.year
                or old.get('week') != week or old.get('me') != user):
            continue
        if old.get('suggestions') or old.get('opp') not in league.teams:
            return False
        report = opponent_report(league, user, old['opp'], week)
        if not report['suggestions']:
            return False
        mail['payload']['report'] = report
        count = len(report['suggestions'])
        ending = f"{count} suggestion{'s' if count != 1 else ''} from the assistants."
        body, n = re.subn(r'0 suggestions from the assistants\.$', ending, mail.get('body') or '')
        mail['body'] = body if n else (mail.get('body') or '') + f' Scouting update: {ending}'
        league.game_plan_reports = getattr(league, 'game_plan_reports', {})
        league.game_plan_reports[week] = report
        return True
    return False


# Season performance is separate from the roster grades used by scouting.
def record_team_performance(league, home, away, week, res):
    rows = {a: dict(pass_yds=0.0, rush_yds=0.0) for a in (home, away)}
    for side, drive in res['drives']:
        row = rows[home if side == 'home' else away]
        for play in drive.log:
            if not isinstance(play, dict) or play.get('nullified'): continue
            kind = play.get('type')
            yards = float(play.get('yards', 0) or 0)
            if kind in ('complete', 'sack'): row['pass_yds'] += yards
            elif kind in ('run', 'scramble', 'kneel'): row['rush_yds'] += yards
    store = league.__dict__.setdefault('team_game_stats', {})
    store[f'{league.year}-{week}-{home}-{away}'] = rows


def performance_table(league, mine, theirs):
    """NFL-style regular-season rates; never infer missing net yards from ratings."""
    from fractions import Fraction
    totals = {a: dict(games=0, known=0, passing=0, rushing=0,
                     pass_allowed=0, rush_allowed=0, points=0, points_allowed=0)
              for a in league.teams}
    store = getattr(league, 'team_game_stats', {}) or {}
    for week, away, home, ap, hp in league.schedule:
        if not 1 <= week <= 18 or ap is None or hp is None: continue
        rows = store.get(f'{league.year}-{week}-{home}-{away}', {})
        for a, b, points, allowed in ((home, away, hp, ap), (away, home, ap, hp)):
            t = totals[a]; t['games'] += 1
            t['points'] += points; t['points_allowed'] += allowed
            if a not in rows or b not in rows: continue
            t['known'] += 1
            for key, source, field in (('passing', a, 'pass_yds'), ('rushing', a, 'rush_yds'),
                                       ('pass_allowed', b, 'pass_yds'), ('rush_allowed', b, 'rush_yds')):
                t[key] += Fraction(str(rows[source][field]))
    specs = [('Total Offense', 'total', False), ('Pass Offense', 'passing', False),
             ('Run Offense', 'rushing', False), ('Scoring Offense', 'points', False),
             ('Total Defense', 'total_allowed', True), ('Pass Defense', 'pass_allowed', True),
             ('Run Defense', 'rush_allowed', True), ('Scoring Defense', 'points_allowed', True)]
    # A partial league sample cannot honestly be labelled a league-wide yardage rank.
    complete = all(t['known'] == t['games'] for t in totals.values())
    out = []
    for label, key, lower in specs:
        values = {}
        for a, t in totals.items():
            if not t['games'] or (key not in ('points', 'points_allowed') and not complete): continue
            value = (t['passing'] + t['rushing'] if key == 'total' else
                     t['pass_allowed'] + t['rush_allowed'] if key == 'total_allowed' else t[key])
            values[a] = Fraction(value) / t['games']
        def rank(a):
            if a not in values: return None
            return 1 + sum(v < values[a] if lower else v > values[a] for v in values.values())
        metric = ('Points allowed/game' if lower else 'Points/game') if key.startswith('points') else (
            ('Net passing yards' if key in ('passing', 'pass_allowed') else 'Rushing yards' if key in ('rushing', 'rush_allowed') else 'Net total yards') + (' allowed/game' if lower else '/game'))
        out.append(dict(label=label, mine=rank(mine), theirs=rank(theirs), metric=metric,
                        mine_value=round(float(values[mine]), 1) if mine in values else None,
                        theirs_value=round(float(values[theirs]), 1) if theirs in values else None))
    return out


def game_forecast(league, home_abbr, week):
    """Use the same championship host as the game weather draw."""
    if int(week) == 22:
        import postseason as PS
        home_abbr = PS.sb_venue(league)['abbr']
    return _forecast(home_abbr, week)
