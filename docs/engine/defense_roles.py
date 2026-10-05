"""Shared defensive front, package, and depth-role definitions.

Roster positions stay canonical (LEDG/DT/REDG and MIKE/WILL/SAM). A 3-4
assigns those players to different on-field jobs without changing saves.
"""


ROLE_SOURCES = {
    'LE': ('LEDG', 'REDG'), 'DT': ('DT',),
    'RE': ('REDG', 'LEDG'),
    'MIKE': ('MIKE', 'WILL', 'SAM'), 'WILL': ('WILL', 'SAM', 'MIKE'),
    'SAM': ('SAM', 'WILL', 'MIKE'),
    'NT': ('DT',), '34LE': ('DT',), '34RE': ('DT',),
    'LOLB': ('LEDG', 'REDG'), 'ROLB': ('REDG', 'LEDG'),
    'LILB': ('MIKE', 'WILL', 'SAM'), 'RILB': ('WILL', 'MIKE', 'SAM'),
    'CB': ('CB',), 'FS': ('FS', 'SS'), 'SS': ('SS', 'FS'),
    'SLOT': ('SS', 'FS', 'CB'),
}

DEFENSE = frozenset(('LEDG', 'DT', 'REDG', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS'))

# Planning grades use the attributes the existing blocking, rush and coverage
# resolvers read. They are recruiting comparisons, not gameplay multipliers.
SPECIALIST_WEIGHTS = {
    'nose': {'strength': .35, 'block_shed': .35, 'tackle': .15, 'play_rec': .15},
    '34_end': {'block_shed': .30, 'strength': .25, 'power_moves': .20, 'pursuit': .15, 'play_rec': .10},
    'interior': {'block_shed': .25, 'power_moves': .25, 'finesse_moves': .20, 'strength': .20, 'acceleration': .10},
    'rush_edge': {'finesse_moves': .25, 'power_moves': .25, 'acceleration': .20, 'speed': .10, 'block_shed': .20},
    'offball': {'tackle': .25, 'play_rec': .25, 'pursuit': .20, 'zone_cover': .15, 'speed': .15},
    'tampa_middle': {'zone_cover': .35, 'speed': .25, 'play_rec': .20, 'awareness': .10, 'tackle': .10},
    'coverage_safety': {'zone_cover': .35, 'speed': .20, 'play_rec': .20, 'awareness': .15, 'man_cover': .10},
    'box_safety': {'tackle': .30, 'pursuit': .20, 'play_rec': .20, 'block_shed': .15, 'zone_cover': .15},
    'man_corner': {'man_cover': .40, 'speed': .25, 'press': .20, 'agility': .15},
    'zone_corner': {'zone_cover': .40, 'play_rec': .25, 'awareness': .15, 'speed': .20},
    'slot_corner': {'man_cover': .25, 'zone_cover': .25, 'agility': .20, 'speed': .15, 'tackle': .15},
    'big_nickel': {'zone_cover': .25, 'man_cover': .20, 'tackle': .20, 'agility': .15, 'speed': .20},
}


def _specialist(row, coverage='cover_3', under='zone', box=7):
    role = row['role']
    if role == 'NT': return 'nose'
    if role in ('34LE', '34RE'): return '34_end'
    if role == 'DT': return 'interior'
    if role in ('LE', 'RE', 'LOLB', 'ROLB'): return 'rush_edge'
    if role in ('MIKE', 'LILB') and coverage == 'tampa_2': return 'tampa_middle'
    if role in ('MIKE', 'WILL', 'SAM', 'LILB', 'RILB'): return 'offball'
    if role == 'SLOT': return 'big_nickel'
    if role == 'CB':
        if row['alignment'] == 'slot': return 'slot_corner'
        side = 1 if row['alignment'] == 'corner_left' else 0
        mode = under[side] if isinstance(under, (list, tuple)) else under
        return 'man_corner' if mode == 'man' else 'zone_corner'
    return 'box_safety' if role == 'SS' and box >= 8 else 'coverage_safety'


def candidate_grade(player, role, specialist=None, gm=None):
    """0..100 fit for one job; cross-family emergency substitutes score zero.

    Accepts engine player dictionaries or saved Player objects. No mutation,
    overall-rating bonus, development bonus or hidden positional conversion.
    """
    if position(player) not in ROLE_SOURCES.get(role, ()):
        return 0.0
    specialist = specialist or _specialist({'role': role, 'alignment': ''})
    weights = SPECIALIST_WEIGHTS[specialist]
    r = ratings(player)
    fallback = player.get('ovr', 50) if isinstance(player, dict) else getattr(player, 'ovr', 50)
    if callable(fallback): fallback = 50
    def value(key):
        val = r.get('accel_rating', r.get('acceleration_rating', fallback)) if key == 'acceleration' else r.get(key + '_rating', fallback)
        return max(0., min(100., float(val if val is not None else 50)))
    grade = sum(value(k)*w for k,w in weights.items())
    if specialist == 'nose':
        mass = player.get('weight', player.get('weight_lbs')) if isinstance(player, dict) else getattr(player, 'weight', None)
        if mass is not None:
            # Existing player_roles requires an anchor's mass/strength profile.
            grade -= max(0., min(12., (305-float(mass))*.3))
    return round(max(0., min(100., grade)), 4)


def planning_profile(gm=None, lean=None):
    """Pure reference demand, not a prediction of a particular opponent.

    Integrates the actual play caller over a fixed, bounded reference schedule.
    Local RNG never consumes franchise randomness. Neutral capable personnel
    express the installed playbook rather than hiding needs behind weak players.
    Big nickel assumes a third safety can be recruited; consumers assign eleven
    distinct players within each variant, never sum independently chosen stars.
    """
    import json, copy
    fields = ('def_front', 'box', 'aggression', 'board_trust', 'coverage', 'shell', 'blitz')
    values = {k: (gm.get(k) if isinstance(gm, dict) else getattr(gm, k, None)) for k in fields}
    values = {k:v for k,v in values.items() if v is not None}
    return copy.deepcopy(_planning_cached(json.dumps(values, sort_keys=True), json.dumps(lean or {}, sort_keys=True)))


from functools import lru_cache


@lru_cache(maxsize=128)
def _planning_cached(gm_json, lean_json):
    import json
    import numpy as np
    from types import SimpleNamespace
    from collections import defaultdict
    import schemes as S
    config = dict(def_front='4-3', box=.5, aggression=.5, board_trust=.5, coverage=.25, shell=.5, blitz=.35)
    config.update(json.loads(gm_json)); gm = SimpleNamespace(**config)
    fronts = {'4-3':['4-3 over','4-3 under','wide 9'], '3-4':['3-4 one','3-4 two','tite','mint'],
              'multiple':['4-3 over','3-4 one','tite','bear']}
    lean = dict(front_pref=fronts.get(gm.def_front, fronts['4-3']), coverage=gm.coverage, shell=gm.shell, blitz=gm.blitz)
    lean.update(json.loads(lean_json))
    rng = np.random.default_rng(718203)
    # First/second downs, short conversion, long third, goal line. Weights are
    # explicit planning assumptions; package/front probabilities come from S.
    situations = [(1,10,50,.35),(2,6,45,.25),(2,15,60,.10),(3,2,30,.10),(3,9,40,.15),(4,1,2,.05)]
    neutral = {g:[dict(pid=g+str(i), pos=p) for i,p in enumerate(ps)] for g,ps in
               [('dl',['LEDG','DT','DT','REDG']),('lb',['MIKE','WILL','SAM']),('db',['CB','CB','CB','FS','SS'])]}
    variants = defaultdict(float)
    for op, spec in S.PERSONNEL_OFF.items():
        for down, distance, ytg, sw in situations:
            for _ in range(16):
                call = S.call_defense(dict(personnel=op), down, distance, rng, gm=gm, yards_to_endzone=ytg,
                                      defense=neutral, rate_fn=lambda p,w:.75, lean=lean)
                package, family = call['personnel'], call['front_family']
                for big, bw in ([(False,.66),(True,.34)] if package=='nickel' else [(False,1.)]):
                    rows = role_slots(family, package, big)
                    jobs = tuple(_specialist(r, call['coverage'], call['under'], call['box']) for r in rows)
                    variants[(family,package,big,jobs)] += spec['rate']*sw*bw/16
    total = sum(variants.values()); packages = dict.fromkeys(('base','nickel','dime','heavy'),0.)
    demand = defaultdict(float); result=[]
    for (family,package,big,jobs),weight in sorted(variants.items()):
        share=weight/total; packages[package]+=share
        slots=[dict(r,specialist=job) for r,job in zip(role_slots(family,package,big),jobs)]
        result.append(dict(front=family,package=package,big_nickel=big,share=share,slots=slots))
        for r in slots: demand[(r['role'],r['specialist'])]+=share
    return dict(packages=packages,variants=result,roles=[dict(role=role,specialist=job,sources=ROLE_SOURCES[role],demand=value)
                for (role,job),value in sorted(demand.items())])
EDGE_ROLES = frozenset(('LE', 'RE', 'LOLB', 'ROLB'))
OFFBALL_ROLES = frozenset(('MIKE', 'WILL', 'SAM', 'LILB', 'RILB'))

PACKAGE_NAMES = ('Base', 'Nickel', 'Dime', 'Goal Line', 'Third Down', 'Two Minute')
PACKAGE_KEYS = {'Base': 'base', 'Nickel': 'nickel', 'Dime': 'dime',
                'Goal Line': 'heavy', 'Third Down': 'nickel', 'Two Minute': 'dime'}


def coach_front(gm):
    """Default chart for a coach; a multiple coach retains both game fronts."""
    front = getattr(gm, 'def_front', '4-3') if gm is not None else '4-3'
    if front in ('4-3', '3-4'):
        return front
    return '3-4' if float(getattr(gm, 'box', 0.5)) >= 0.5 else '4-3'


def front_family(front):
    if front in ('3-4', '3-4 one', '3-4 two', '3-4 sub', 'tite', 'mint'):
        return '3-4'
    return '4-3'


def package_key(package):
    return PACKAGE_KEYS.get(package, package if package in ('base', 'nickel', 'dime', 'heavy') else 'nickel')


def _parts(front, package):
    """Return role codes in display order; repeated codes are separate starters."""
    front = front_family(front)
    package = package_key(package)
    if package == 'heavy':
        dl = (['LOLB', '34LE', 'NT', '34RE', 'ROLB'] if front == '3-4' else
              ['LE', 'DT', 'DT', 'RE', 'DT'])
        lb = ['LILB', 'RILB', 'SAM'] if front == '3-4' else ['MIKE', 'WILL', 'SAM']
    elif front == '3-4' and package == 'base':
        dl = ['34LE', 'NT', '34RE']
        lb = ['LOLB', 'LILB', 'RILB', 'ROLB']
    elif front == '3-4':
        # Passing packages keep BOTH rush edges. The coach's base identity
        # does not require three interior linemen on every passing down.
        dl = ['LOLB', 'DT', 'DT', 'ROLB']
        lb = ['LILB', 'RILB'] if package == 'nickel' else ['LILB']
    else:
        dl = ['LE', 'DT', 'DT', 'RE']
        lb = (['MIKE', 'WILL', 'SAM'] if package == 'base' else
              ['MIKE', 'WILL'] if package == 'nickel' else ['MIKE'])
    cb = {'base': 2, 'nickel': 3, 'dime': 4, 'heavy': 2}[package]
    db = ['CB'] * cb + ['FS'] + ([] if package == 'heavy' else ['SS'])
    return dl, lb, db


def shape(front, package):
    dl, lb, db = _parts(front, package)
    return {'dl': dl, 'lb': lb, 'db': db}


def counts(front, package):
    return {group: len(roles) for group, roles in shape(front, package).items()}


def shape_label(front, package):
    c = counts(front, package)
    return f"{c['dl']}-{c['lb']}-{c['db']}"


def role_slots(front, package, big_nickel=False):
    """The formation's eleven jobs, independent of roster/list order.

    Left/right are defensive sides. Alignment survives rotation and is used
    by protection, rush selection and run fits instead of array indexes.
    """
    groups = shape(front, package)
    fixed = {'LE': 'left_edge', 'RE': 'right_edge', 'LOLB': 'left_edge',
             'ROLB': 'right_edge', '34LE': 'left_interior', 'NT': 'nose',
             '34RE': 'right_interior', 'MIKE': 'offball_middle',
             'WILL': 'offball_left', 'SAM': 'offball_right',
             'LILB': 'offball_left', 'RILB': 'offball_right',
             'FS': 'deep_left', 'SS': 'deep_right', 'SLOT': 'slot'}
    seen, out = {}, []
    for group, roles in groups.items():
        for role in roles:
            index = seen.get(role, 0); seen[role] = index + 1
            if role == 'CB':
                alignment = ('corner_left', 'corner_right', 'slot', 'slot')[index]
                if big_nickel and package_key(package) == 'nickel' and index == 2:
                    role = 'SLOT'
            elif role == 'DT':
                alignment = ('left_interior', 'right_interior', 'nose')[index]
            else:
                alignment = fixed[role]
            out.append(dict(group=group, role=role, alignment=alignment, slot=index))
    return out


def pid(player):
    return player.get('pid') if isinstance(player, dict) else player.pid


def position(player):
    return player.get('pos') if isinstance(player, dict) else player.pos


def ratings(player):
    return player.get('ratings', player) if isinstance(player, dict) else player.ratings


def needs_fallback(depth, front, package):
    """Whether a 4-3 club lacks a canonical player for a displayed job."""
    if front_family(front) != '4-3':
        return False
    required = {}
    for roles in shape(front, package).values():
        for role in roles:
            canonical = {'LE': 'LEDG', 'RE': 'REDG'}.get(role, role)
            required[canonical] = required.get(canonical, 0) + 1
    return any(len(depth.get(pos, ())) < amount for pos, amount in required.items())


def role_label(role, front=None):
    """Display the job in this front while keeping canonical roster/pin keys."""
    odd = front_family(front) == '3-4' if front is not None else role in ('34LE', '34RE')
    if role in ('LE', 'LEDG', '34LE'):
        return 'LE' if odd else 'LEDG'
    if role in ('RE', 'REDG', '34RE'):
        return 'RE' if odd else 'REDG'
    if role == 'MIKE' and not odd:
        return 'MLB'
    return role


def available_depth(depth, excluded=()):
    """Keep canonical ordering while excluding unavailable IDs in views/snaps."""
    excluded = set(excluded)
    return {pos: [p for p in men
                  if (p.get('pid') if isinstance(p, dict) else p.pid) not in excluded]
            for pos, men in depth.items()}


def role_candidates(depth, role, pins=None, excluded=()):
    """Eligible players in the user's role order, then canonical depth order."""
    excluded = set(excluded)
    players = [p for pos in ROLE_SOURCES[role] for p in depth.get(pos, ())]
    unique = []
    seen = set()
    for player in players:
        key = pid(player)
        if key not in seen and key not in excluded:
            unique.append(player); seen.add(key)
    if role in ('NT', '34LE', '34RE'):
        import player_roles as PR
        # The same body/ratings distinction drives recruiting and the chart.
        # Rank specialist fit within each physical tier; pins still win below.
        def profile_rank(p):
            if position(p) != 'DT': return 3
            roles = PR.fa_positions(p, '3-4')
            if role == 'NT':
                return 0 if roles[0] == 'NT' else 1 if 'NT' in roles else 2
            return int(roles[0] == 'NT')
        unique.sort(key=lambda p: (profile_rank(p), -candidate_grade(p, role)))
    elif role in OFFBALL_ROLES or role == 'SLOT':
        unique.sort(key=lambda p: -candidate_grade(p, role))
    order = {key: i for i, key in enumerate((pins or {}).get(role, ())) }
    return sorted(unique, key=lambda p: order.get(pid(p), 10**6))


def assign(depth, front, package, pins=None, excluded=(), big_nickel=False):
    """Unique starters for every role, plus available reserves for each role.

    Priority places edge defenders at 3-4 OLB before finding three interior
    linemen, so old roster positions become useful without a save migration.
    """
    depth = available_depth(depth, excluded)
    rows = role_slots(front, package, big_nickel)
    priority = {'LE': 0, 'RE': 0, 'LOLB': 0, 'ROLB': 0, 'NT': 1,
                'FS': 1, 'SS': 1, 'LILB': 2, 'RILB': 2, 'MIKE': 2,
                'WILL': 2, 'SAM': 2, '34LE': 3, '34RE': 3}
    # Generic specialist fit drives deployment; the established package policy
    # breaks equal grades. Coverage-call-specific assignments remain separate.
    import targets as TG
    offball = [p for pos in ('MIKE', 'WILL', 'SAM') for p in depth.get(pos, ())]
    preferred = [pid(p) for p, _ in TG.package_linebackers(
        offball, package_key(package), key=ratings)] if offball else []
    used = set(excluded)
    for row in sorted(rows, key=lambda r: priority.get(r['role'], 4)):
        role = row['role']
        candidates = role_candidates(depth, role, pins, used)
        if role in OFFBALL_ROLES and package_key(package) != 'base':
            pinned = {key: i for i, key in enumerate((pins or {}).get(role, ()))}
            candidates.sort(key=lambda p: (pid(p) not in pinned,
                pinned.get(pid(p), 1000), -candidate_grade(p, role),
                preferred.index(pid(p)) if pid(p) in preferred else 1000))
        row['player'] = candidates[0] if candidates else None
        if row['player'] is not None: used.add(pid(row['player']))
    # Only after every normal job has been filled do emergency substitutions
    # borrow another defensive position. Never steal another slot's starter.
    for row in rows:
        if row['player'] is None:
            sources = (('MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS', 'LEDG', 'REDG', 'DT')
                       if row['group'] == 'lb' else
                       ('CB', 'FS', 'SS', 'WILL', 'SAM', 'MIKE', 'LEDG', 'REDG', 'DT')
                       if row['group'] == 'db' else
                       ('DT', 'LEDG', 'REDG', 'SAM', 'MIKE', 'WILL', 'SS', 'FS', 'CB'))
            row['player'] = next((p for pos in sources for p in depth.get(pos, ())
                                  if pid(p) not in used), None)
            if row['player'] is not None: used.add(pid(row['player']))
    for row in rows:
        row['reserves'] = role_candidates(depth, row['role'], pins, used)
    return rows


def roster_depth(roster):
    """Support both full game rosters and older grouped calibration inputs."""
    depth = {pos: list(men) for pos, men in (roster.get('depth') or {}).items()
             if pos in DEFENSE}
    seen = {pid(p) for men in depth.values() for p in men}
    for group in ('dl', 'lb', 'db'):
        for p in roster.get(group, ()):
            if pid(p) not in seen:
                pos = position(p)
                # Older synthetic units use DL/LB labels.
                if pos == 'LB': pos = 'MIKE'
                elif pos == 'DL': pos = 'DT'
                if pos in DEFENSE:
                    depth.setdefault(pos, []).append(p); seen.add(pid(p))
    return depth


def rotation_choice(row, reserves, state, rng):
    """One condition decision, preserving depth order and every player's role.

    A starter's real advantage over available reserves earns more tolerance
    for fatigue. Passing downs can justify one more rep in a competitive game;
    neither consideration allows an exhausted player to bypass rest entirely.
    """
    starter = row['player']
    if state is None or rng is None or not reserves:
        return starter
    candidates = [starter] + reserves
    rested = getattr(state, 'resting_starters', set())
    candidates.sort(key=lambda p: pid(p) in rested)
    grades = [candidate_grade(p, row['role']) for p in candidates]
    context = getattr(state, 'rotation_context', {}) or {}
    important = (row['role'] in EDGE_ROLES and context.get('down', 1) >= 3
                 and context.get('to_go', 0) >= 5
                 and abs(context.get('score_diff', 0)) <= 16)
    condition = getattr(state.cond, 'get', lambda key: 100.0)
    for rank, p in enumerate(candidates):
        # Compare with the next eligible alternative, not a universal starter bonus.
        alternative = max(grades[rank + 1:], default=grades[rank])
        gap = max(-1.0, min(1.0, (grades[rank] - alternative) / 20.0))
        # Urgency shifts a few condition points, never the injury/health rules.
        gap += .25 if important and rank == 0 else 0.0
        if not state.cond.needs_rest(pid(p), position(p), rng,
                ratings(p).get('stamina_rating', 70), gap):
            return p
    # All failed their rest checks. Use the freshest eligible man, not the
    # original exhausted starter or an unrelated position.
    return max(candidates, key=lambda p: (condition(pid(p)), grades[candidates.index(p)]))


def field(roster, package, front=None, rng=None, state=None):
    """Final eleven with role metadata preserved through every substitution."""
    package = package_key(package)
    depth = available_depth(roster_depth(roster), state.out if state is not None else ())
    safety_count = len(depth.get('FS', ())) + len(depth.get('SS', ()))
    big = (package == 'nickel' and safety_count >= 3 and rng is not None
           and rng.random() < .34)
    rows = assign(depth, front or roster.get('front_family', '4-3'), package,
                  roster.get('depth_pins'), big_nickel=big)
    if any(row['player'] is None for row in rows):
        raise ValueError('Cannot field eleven unique healthy defensive players')
    used = {pid(row['player']) for row in rows}
    order = list(range(len(rows)))
    if rng is not None: rng.shuffle(order)
    for i in order:
        row = rows[i]; chosen = row['player']
        reserves = [p for p in row['reserves'] if pid(p) not in used]
        chosen = rotation_choice(row, reserves, state, rng)
        row['player'] = chosen; used.add(pid(chosen))
    on_field = {pid(row['player']): row['player'] for row in rows}
    if len(on_field) != 11:
        raise ValueError('Defensive assignment duplicated a player')
    if state is not None:
        everyone = {pid(p): p for men in depth.values() for p in men}
        for key, p in everyone.items():
            state.snap(p, position(p), key in on_field)
        transformed = {key: state.state(p, position(p)) for key, p in on_field.items()}
        for row in rows: row['player'] = transformed[pid(row['player'])]
    out = {group: [row['player'] for row in rows if row['group'] == group]
           for group in ('dl', 'lb', 'db')}
    out['defensive_assignments'] = [{key: value for key, value in row.items() if key != 'reserves'}
                                   for row in rows]
    return out
