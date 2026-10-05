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


def _coverage_grade(a, call):
    """Value the underneath job vacated by an exchange rusher."""
    p = a['player']
    man = call.get('under') == 'man' or call.get('coverage') in ('cover_0', 'cover_1')
    key = 'man_cover_rating' if man else 'zone_cover_rating'
    return (.65 * float(p.get(key, 40)) + .20 * float(p.get('play_rec_rating', 70))
            + .15 * float(p.get('speed_rating', 70)))


def _exchange_pair(front, replacements, call, rng):
    """Trade rush and underneath coverage jobs using information before the snap.

    A better coverage grade alone is not a reason to remove the best rusher.
    Some variation remains among plausible exchanges; named pressures are
    handled separately by select_rush and never overridden here.
    """
    import math
    choices = []
    for dropped in front:
        for sent in replacements:
            ds, ss = dropped['alignment'], sent['alignment']
            opposite = (('left' in ds and 'right' in ss) or
                        ('right' in ds and 'left' in ss))
            role_cost = (6.0 if opposite else 0.0) + (4.0 if ss == 'slot' else 0.0)
            score = (_rush_grade(sent) - _rush_grade(dropped)
                     + .4 * (_coverage_grade(dropped, call) - _coverage_grade(sent, call))
                     - role_cost)
            choices.append((score, dropped, sent))
    if not choices:
        return None
    choices.sort(key=lambda x: (player_key(x[1]['player']), player_key(x[2]['player'])))
    best = max(x[0] for x in choices)
    if rng is None:
        return max(choices, key=lambda x: x[0])[1:]
    weights = [math.exp((x[0] - best) / 4.0) for x in choices]
    total = sum(weights)
    return choices[int(rng.choice(len(choices), p=[w / total for w in weights]))][1:]


def select_rush(defense, call, rng=None):
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
    for a in preferred: add(a)
    exchange = None
    if explicit is None and not call.get('blitzer_ids') and call.get('sim_pressure'):
        front = [a for a in selected if a['alignment'] in EDGES]
        if not front:
            front = [a for a in selected if a['alignment'] in INTERIOR]
        replacements = [a for a in extra if a not in selected and
                        (a['alignment'].startswith('offball') or a['alignment'] == 'slot')]
        exchange = _exchange_pair(front, replacements, call, rng)
        if exchange:
            dropped, sent = exchange
            selected.remove(dropped); selected.append(sent)
    selected.sort(key=lambda a: (a['alignment'], player_key(a['player'])))
    rush_ids = {player_key(a['player']) for a in selected}
    coverage = dict(defense)
    for group in GROUPS:
        coverage[group] = [a['player'] for a in rows if a['group'] == group and player_key(a['player']) not in rush_ids]
    coverage['defensive_assignments'] = [a for a in rows if player_key(a['player']) not in rush_ids]
    if exchange:
        # The dropper fills the blitzer's underneath job. He is not a spare
        # unassigned coverage body still labelled as an edge on the rush line.
        dropped, sent = exchange
        coverage['defensive_assignments'] = [dict(a, role=sent['role'], alignment=sent['alignment'])
            if player_key(a['player']) == player_key(dropped['player']) else a
            for a in coverage['defensive_assignments']]
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


def protection_helpers(blockers, rush_assignments, matched, threats, protection='five'):
    """Assign spare blockers by reachable gap and known matchup before any rolls.

    Interior linemen help adjacent interior gaps; retained backs scan inside
    out in slide protection and edges first in man protection. Tight ends
    help an edge. Each blocker has one job, with diminishing stacked help.
    """
    engaged = {player_key(b) for b in matched if b is not None}
    spare = {player_key(b): b for b in blockers if b and player_key(b) not in engaged}
    help_by = [[] for _ in rush_assignments]
    # A spare man must account for an uncovered rush before doubling anybody.
    # Usually protection_pairs has already used him; keep direct callers safe.
    if any(b is None for b in matched):
        return help_by
    reach = {'C': INTERIOR, 'LG': ('right_interior', 'nose', 'right_edge'),
             'RG': ('left_interior', 'nose', 'left_edge'),
             'LT': ('right_edge', 'right_interior'), 'RT': ('left_edge', 'left_interior'),
             'TE': EDGES}
    order = {'C': 0, 'LG': 1, 'RG': 1, 'LT': 2, 'RT': 2, 'TE': 3, 'HB': 4, 'FB': 4}
    for b in sorted(spare.values(), key=lambda b: (order.get(b.get('pos'), 5), player_key(b))):
        pos = b.get('pos')
        allowed = reach.get(pos, EDGES + INTERIOR + ('offball_left', 'offball_right', 'offball_middle', 'slot'))
        candidates = [i for i, a in enumerate(rush_assignments)
                      if matched[i] is not None and a['alignment'] in allowed]
        if not candidates:
            continue
        def priority(i):
            alignment = rush_assignments[i]['alignment']
            preference = 0.0
            if pos in ('HB', 'FB'):
                slide = protection in ('six_slide', 'half_slide')
                preference = .06 if alignment in (INTERIOR if slide else EDGES) else 0.0
            # Inside penetration has a shorter path. Treat each helper as
            # reducing that matchup's remaining urgency, not as permission
            # to keep stacking bodies on the highest-rated player.
            inside = .045 if alignment in INTERIOR else 0.
            return (float(threats[i]) + inside + preference - .16 * len(help_by[i]),
                    rush_assignments[i]['alignment'], player_key(rush_assignments[i]['player']))
        chosen = max(candidates, key=priority)
        help_by[chosen].append(b)
    return help_by
