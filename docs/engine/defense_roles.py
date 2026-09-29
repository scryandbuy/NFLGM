"""Shared defensive front, package, and depth-role definitions.

Roster positions stay canonical (LEDG/DT/REDG and MIKE/WILL/SAM). A 3-4
assigns those players to different on-field jobs without changing saves.
"""


ROLE_SOURCES = {
    'LE': ('LEDG', 'REDG', 'DT'), 'DT': ('DT', 'LEDG', 'REDG'),
    'RE': ('REDG', 'LEDG', 'DT'),
    'MIKE': ('MIKE', 'WILL', 'SAM'), 'WILL': ('WILL', 'SAM', 'MIKE'),
    'SAM': ('SAM', 'WILL', 'MIKE'),
    'NT': ('DT',), '34LE': ('DT', 'LEDG'), '34RE': ('DT', 'REDG'),
    'LOLB': ('LEDG', 'SAM'), 'ROLB': ('REDG', 'SAM'),
    'LILB': ('MIKE', 'WILL', 'SAM'), 'RILB': ('WILL', 'MIKE', 'SAM'),
    'CB': ('CB',), 'FS': ('FS',), 'SS': ('SS',),
}

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
        dl = ['LE', 'DT', 'DT', 'RE', 'DT']
        lb = ['MIKE', 'WILL', 'SAM']
    elif front == '3-4':
        dl = ['34LE', 'NT', '34RE']
        lb = (['LOLB', 'LILB', 'RILB', 'ROLB'] if package == 'base' else
              ['LOLB', 'LILB', 'ROLB'] if package == 'nickel' else ['LILB', 'ROLB'])
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


def role_label(role):
    return {'LE': 'LEDG', 'RE': 'REDG', '34LE': 'LEDG', '34RE': 'REDG'}.get(role, role)


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
        pid = player.get('pid') if isinstance(player, dict) else player.pid
        if pid not in seen and pid not in excluded:
            unique.append(player); seen.add(pid)
    order = {pid: i for i, pid in enumerate((pins or {}).get(role, ())) }
    return sorted(unique, key=lambda p: order.get(p.get('pid') if isinstance(p, dict) else p.pid, 10**6))


def assign(depth, front, package, pins=None, excluded=()):
    """Unique starters for every role, plus available reserves for each role.

    Priority places edge defenders at 3-4 OLB before finding three interior
    linemen, so old roster positions become useful without a save migration.
    """
    groups = shape(front, package)
    entries = [(group, role, index) for group, roles in groups.items()
               for index, role in enumerate(roles)]
    priority = {'LOLB': 0, 'ROLB': 0, 'NT': 1, 'LILB': 2, 'RILB': 2,
                '34LE': 3, '34RE': 3}
    selection = {}
    used = set(excluded)
    for group, role, index in sorted(entries, key=lambda item: (priority.get(item[1], 4), item[2])):
        candidates = role_candidates(depth, role, pins, used)
        chosen = candidates[0] if candidates else None
        selection[(group, index)] = chosen
        if chosen is not None:
            used.add(chosen.get('pid') if isinstance(chosen, dict) else chosen.pid)
    starters = set(used) - set(excluded)
    out = []
    for group, role, index in entries:
        chosen = selection[(group, index)]
        reserves = role_candidates(depth, role, pins, starters | set(excluded))
        out.append(dict(group=group, role=role, player=chosen, reserves=reserves))
    return out
