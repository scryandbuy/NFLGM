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
    if front in ('3-4', '3-4 one', '3-4 two', 'tite', 'mint'):
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
        # Keep the team's depth order within each physical role category.
        def profile_rank(p):
            if position(p) != 'DT': return 3
            roles = PR.fa_positions(p, '3-4')
            if role == 'NT':
                return 0 if roles[0] == 'NT' else 1 if 'NT' in roles else 2
            return int(roles[0] == 'NT')
        unique.sort(key=profile_rank)
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
    # Reuse the established package-specific off-ball policy. An excellent
    # covering SAM can earn the nickel/dime job without becoming a rush OLB.
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
                pinned.get(pid(p), preferred.index(pid(p)) if pid(p) in preferred else 1000)))
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
        candidates = [chosen] + reserves
        if state is not None and rng is not None:
            for rank, p in enumerate(candidates):
                if not state.cond.needs_rest(pid(p), position(p), rng,
                        ratings(p).get('stamina_rating', 70), .6 if rank == 0 else .3):
                    chosen = p; break
        rotation = .30 if row['role'] in EDGE_ROLES else .32 if row['group'] == 'dl' else 0.0
        if chosen is row['player'] and reserves and rng is not None and rng.random() < rotation:
            chosen = reserves[0]
            if len(reserves) > 1 and rng.random() >= (.78 if row['role'] in EDGE_ROLES else .68):
                chosen = reserves[1]
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
