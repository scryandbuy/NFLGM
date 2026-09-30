"""Pure on-field rush selection and protection matching, independent of list order."""

GROUPS = ('dl', 'lb', 'db')
EDGES = ('left_edge', 'right_edge')
INTERIOR = ('left_interior', 'nose', 'right_interior')


def player_key(p):
    """IDs survive fatigue/health copies. Anonymous test players retain identity."""
    return str(p['pid']) if p.get('pid') is not None else f'object:{id(p)}'


def _rush_grade(a):
    p = a['player']
    return max(float(p.get('power_moves_rating', 70)), float(p.get('finesse_moves_rating', 70))) + .1*float(p.get('speed_rating', 70))


def assignments(defense, call=None):
    """Bind metadata to final on-field copies; infer roles for direct callers."""
    call = call or {}
    live = {player_key(p): p for group in GROUPS for p in defense.get(group, []) if p}
    out, seen = [], set()
    for a in defense.get('defensive_assignments', []):
        p = a.get('player')
        if not p or player_key(p) not in live or player_key(p) in seen:
            continue
        p = live[player_key(p)]; seen.add(player_key(p))
        out.append(dict(a, player=p))
    # Older/direct resolver callers supply position groups without metadata.
    # Use the shared slots when available, matching canonical positions first.
    import defense_roles as DR
    slots = DR.role_slots(call.get('front_family', call.get('front', '4-3')),
                          call.get('personnel', 'nickel')) if hasattr(DR, 'role_slots') else []
    from collections import Counter
    represented = Counter((a.get('group'),a.get('role'),a.get('alignment')) for a in out)
    for slot in slots:
        key = (slot['group'],slot['role'],slot['alignment'])
        if represented[key]:
            represented[key] -= 1
            continue
        candidates = [p for p in defense.get(slot['group'], []) if player_key(p) not in seen]
        sources = DR.ROLE_SOURCES.get(slot['role'], (slot['role'],))
        candidates.sort(key=lambda p: (sources.index(p.get('pos')) if p.get('pos') in sources else 99, player_key(p)))
        if candidates:
            p = candidates[0]; seen.add(player_key(p)); out.append(dict(slot, player=p))
    for group in GROUPS:
        leftovers = sorted((p for p in defense.get(group, []) if player_key(p) not in seen), key=player_key)
        for i, p in enumerate(leftovers):
            pos = p.get('pos', '')
            alignment = {'LEDG':'left_edge', 'REDG':'right_edge', 'FS':'deep_left', 'SS':'deep_right',
                         'MIKE':'offball_middle', 'WILL':'offball_left', 'SAM':'offball_right'}.get(pos)
            if not alignment:
                alignment = ('left_interior' if i % 2 == 0 else 'right_interior') if group == 'dl' else (
                    'corner_left' if i == 0 else 'corner_right' if i == 1 else 'slot') if group == 'db' else 'offball_middle'
            out.append(dict(role=pos, group=group, alignment=alignment, player=p)); seen.add(player_key(p))
    return sorted(out, key=lambda a: (a.get('alignment', ''), a.get('role', ''), player_key(a['player'])))


def select_rush(defense, call):
    rows = assignments(defense, call)
    by_id = {player_key(a['player']): a for a in rows}
    cov = call.get('coverage', call.get('shell', 'cover_3'))
    safeties = [a for a in rows if a['alignment'].startswith('deep_')]
    corners = [a for a in rows if a['alignment'].startswith('corner_')]
    # Preserve the shell's designated deep bodies; explicit pressures may
    # exchange underneath players, not silently erase a deep half/quarter.
    deep = ([] if cov == 'cover_0' else safeties[:1] if cov in ('cover_1','cover_1_robber','cover_3','cover_3_mable') else safeties)
    if cov in ('cover_3','cover_3_mable','cover_4'):
        deep += corners[:2]
    elif cov == 'cover_6':
        # zones.cover_6 puts the outside quarter on offensive left.
        deep += [a for a in corners if a['alignment'] == 'corner_right']
    protected = {player_key(a['player']) for a in deep}
    drops = {str(x) for x in call.get('dropper_ids', [])}
    eligible = [a for a in rows if player_key(a['player']) not in protected | drops]
    count = min(max(0, int(call.get('rushers', 4))), len(eligible))
    rank = lambda a: (-_rush_grade(a), player_key(a['player']))
    interiors = sorted([a for a in eligible if a['alignment'] in INTERIOR], key=rank)
    edges = sorted([a for a in eligible if a['alignment'] in EDGES], key=rank)
    extra = sorted([a for a in eligible if a not in interiors+edges],
                   key=lambda a: (0 if a['alignment'].startswith('offball') else 1 if a['alignment']=='slot' else 2, *rank(a)))
    odd_base = call.get('personnel', 'base') == 'base' and (
        call.get('front_family') == '3-4' or any(a.get('role') == 'NT' for a in rows))
    preferred = (interiors[:3]+edges) if odd_base else (edges+interiors)
    preferred += extra
    selected = []
    def add(a):
        if a in eligible and a not in selected and len(selected) < count:
            selected.append(a)
    explicit = call.get('rusher_ids')
    if explicit is not None:
        for pid in explicit:
            if str(pid) in by_id: add(by_id[str(pid)])
    for pid in call.get('blitzer_ids', []):
        if str(pid) in by_id: add(by_id[str(pid)])
    if explicit is None and call.get('sim_pressure') and extra and preferred:
        # A deliberate four-man exchange: the best dropping edge (or interior
        # if no edge) replaces his rush with a second-level pressure.
        front = preferred[:count]
        droppers = [a for a in front if a['alignment'] in EDGES] or front
        dropped = max(droppers, key=lambda a: (float(a['player'].get('zone_cover_rating', 40)), player_key(a['player'])))
        add(extra[0])
        preferred = [a for a in preferred if a is not dropped]+[dropped]
    for a in preferred: add(a)
    selected.sort(key=lambda a: (a['alignment'], player_key(a['player'])))
    rush_ids = {player_key(a['player']) for a in selected}
    coverage = dict(defense)
    for group in GROUPS:
        coverage[group] = [a['player'] for a in rows if a['group'] == group and player_key(a['player']) not in rush_ids]
    coverage['defensive_assignments'] = [a for a in rows if player_key(a['player']) not in rush_ids]
    return dict(rushers=[a['player'] for a in selected], assignments=selected, coverage=coverage)


def protection_pairs(blockers, rush_assignments):
    """Defensive left faces offensive right. Edges get tackles before helpers."""
    unique = {player_key(b): b for b in blockers if b}
    used, pairs = set(), {}
    preferences = {'left_edge':('RT','TE','HB','FB','RG','C','LG','LT'),
                   'right_edge':('LT','TE','HB','FB','LG','C','RG','RT'),
                   'left_interior':('RG','C','RT','LG','LT'),
                   'right_interior':('LG','C','LT','RG','RT'),
                   'nose':('C','RG','LG','RT','LT'),
                   'offball_left':('HB','FB','TE','RG','C','RT','LG','LT'),
                   'offball_right':('HB','FB','TE','LG','C','LT','RG','RT'),
                   'offball_middle':('C','HB','FB','TE','RG','LG','RT','LT'),
                   'slot':('HB','FB','TE','RT','LT','RG','LG','C')}
    order = sorted(enumerate(rush_assignments), key=lambda pair: (
        0 if pair[1]['alignment'] in EDGES else 1 if pair[1]['alignment'] in INTERIOR else 2,
        pair[1]['alignment'], player_key(pair[1]['player'])))
    for i, a in order:
        pref = preferences.get(a['alignment'], ('HB','FB','TE','C','RG','LG','RT','LT'))
        remaining = [b for key,b in unique.items() if key not in used]
        remaining.sort(key=lambda b: (pref.index(b.get('pos')) if b.get('pos') in pref else 99, player_key(b)))
        b = remaining[0] if remaining else None
        pairs[i] = b
        if b: used.add(player_key(b))
    return [pairs[i] for i in range(len(rush_assignments))]
