"""Coach-aware roster needs shared by the AI's personnel decisions.

Saved positions remain canonical. A role may have several eligible positions,
but a player can cover only one starting job in any one package.
"""
from collections import Counter

import defense_roles as DR
import offense_roles as OR


POSITIONS = ('QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT',
             'LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS',
             'K', 'P', 'LS')
GROUPS = {
    'OL': ('LT', 'LG', 'C', 'RG', 'RT'),
    'DL': ('LEDG', 'REDG', 'DT'),
    'LB': ('MIKE', 'WILL', 'SAM'),
    'DB': ('CB', 'FS', 'SS'),
    'ST': ('K', 'P', 'LS'),
}

# Recruiting/depth value follows interchangeable football jobs. Keep these
# separate from roster_floors: roster construction/cutdown policy is unchanged.
EDGE_FAMILY = ('LEDG', 'REDG')
PLANNING_FAMILIES = tuple((EDGE_FAMILY if pos == 'LEDG' else (pos,))
                          for pos in POSITIONS if pos != 'REDG')


def planning_floor(floors, family):
    return sum(floors[pos] for pos in family)


def planning_shortages(counts, floors):
    """One shortage per job family, without a phantom vacant edge side."""
    for family in PLANNING_FAMILIES:
        yield family, max(0, planning_floor(floors, family) -
                          sum(counts.get(pos, 0) for pos in family))


def role_slots(team):
    """Starting jobs for this coach's base offense and defense."""
    gm = getattr(team, 'gm', None)
    offense = OR.PACKAGES[OR.base_package(gm)]
    slots = [('QB', ('QB',))]
    slots.extend((pos, (pos,) + tuple(p for p in OR.OL if p != pos)) for pos in OR.OL)
    skill_sources = {'HB': ('HB', 'FB', 'WR', 'TE'),
                     'FB': ('FB', 'HB', 'TE', 'WR'),
                     'TE': ('TE', 'FB', 'WR', 'HB'),
                     'WR': ('WR', 'TE', 'HB', 'FB')}
    for pos in ('HB', 'FB', 'TE', 'WR'):
        slots.extend((pos, skill_sources[pos]) for _ in range(offense[pos]))

    front = DR.coach_front(gm)
    defense = DR.shape(front, 'base')
    # In a 3-4, edge players fill outside linebacker jobs first. Assignment
    # follows the same priority as the game engine's defensive role selector.
    if front == '3-4':
        priority = {'LOLB': 0, 'ROLB': 0, 'NT': 1,
                    'LILB': 2, 'RILB': 2, '34LE': 3, '34RE': 3}
        roles = sorted(defense['lb'] + defense['dl'], key=lambda role: priority.get(role, 4))
    else:
        roles = defense['dl'] + defense['lb']
    slots.extend((role, DR.ROLE_SOURCES[role]) for role in roles)
    slots.extend((role, DR.ROLE_SOURCES[role]) for role in defense['db'])
    # Nickel is used often enough that a third corner is a starting job.
    if sum(role == 'CB' for role in defense['db']) < 3:
        slots.append(('CB', ('CB',)))
    slots.extend((pos, (pos,)) for pos in ('K', 'P', 'LS'))
    return slots


def _grade(player, team):
    from gm_engine import scheme_fit
    return float(player.ovr) + scheme_fit(player.ratings, player.pos, team)


def roster_floors(team):
    """Minimum depth for the coach's personnel and front within 53 places."""
    offense = OR.PACKAGES[OR.base_package(getattr(team, 'gm', None))]
    floors = {'QB': 2, 'HB': 2, 'FB': 0,
              'WR': max(4, offense['WR'] + 2),
              'TE': max(2, offense['TE'] + 1),
              'LT': 1, 'LG': 1, 'C': 1, 'RG': 1, 'RT': 1,
              'LEDG': 1, 'REDG': 1, 'DT': 4,
              'MIKE': 1, 'WILL': 1, 'SAM': 0,
              'CB': 4, 'FS': 1, 'SS': 1, 'K': 1, 'P': 1, 'LS': 1}
    # Odd-front edges live in saved LEDG/REDG slots. Standard nickel and dime
    # keep both on the rush line, while two off-ball linebackers start in base.
    # Reserve an extra front player in place of a fifth off-ball linebacker.
    groups = {'OL': 9, 'DL': 10, 'LB': 4, 'DB': 10, 'ST': 3}
    if offense['FB'] and hasattr(team, 'depth'):
        # A two-back coach may use a blocking TE as the second back. Keep that
        # TE even when his native TE grade puts him behind two receiving TEs.
        depth = team.depth
        rows = {pos: [dict(pid=p.pid, pos=p.pos, ovr=p.ovr, **p.ratings)
                      for p in group] for pos, group in depth.items() if pos in OR.OFFENSE}
        try:
            fb = next(p for role, p in OR.assign(rows, OR.base_package(getattr(team, 'gm', None)))
                      if role == 'FB')
        except (ValueError, StopIteration):
            fb = None
        if fb is not None and fb['pos'] == 'TE':
            rank = next((i for i, p in enumerate(depth.get('TE', ()), 1)
                         if p.pid == fb['pid']), 0)
            floors['TE'] = max(floors['TE'], rank)
    return floors, groups


def _base_assess(team, players=None, strict_roles=False, grades=None):
    """Return need (0..1) by saved position and uncovered starting jobs.

    This is a roster assessment, not a transaction: cap and dead money belong
    in the move decision. `players` allows callers to evaluate a proposed move.
    """
    players = list(team.active() if players is None else players)
    grades = grades if grades is not None else {p.pid: _grade(p, team) for p in players}
    by_pos = {pos: [] for pos in POSITIONS}
    for p in players:
        by_pos.setdefault(p.pos, []).append(p)
    for group in by_pos.values():
        group.sort(key=lambda p: -grades[p.pid])

    used = set()
    needs = {pos: 0.0 for pos in POSITIONS}
    uncovered = []
    assignments = []
    quality = 0.0
    slots = role_slots(team)
    offense_pids = ()
    try:
        proxy = {pos: [dict(pid=p.pid, pos=p.pos, ovr=p.ovr,
                            **(getattr(p, 'ratings', {}) or {})) for p in group]
                 for pos, group in by_pos.items() if pos in OR.OFFENSE}
        offense_pids = tuple(p['pid'] for _, p in OR.assign(proxy, OR.base_package(getattr(team, 'gm', None))))
    except ValueError:
        pass
    by_pid = {p.pid: p for p in players}
    if strict_roles and any(by_pid[pid].pos not in slots[i][1]
                            for i, pid in enumerate(offense_pids)):
        # Game-day emergency assignments can put a receiver at QB. Draft
        # planning must leave that job open and retain him for his own role.
        offense_pids = ()
    for index, (role, sources) in enumerate(slots):
        if index < len(offense_pids):
            chosen = by_pid[offense_pids[index]]
            choices = [(chosen, chosen.pos)]
        else:
            choices = [(p, source) for source in sources for p in by_pos.get(source, ())
                       if p.pid not in used]
        if not choices:
            assignments.append(dict(role=role, sources=sources, player=None, grade=None))
            uncovered.append(role)
            needs[sources[0]] = 1.0
            quality -= 20.0
            continue
        primary = [item for item in choices if item[1] == sources[0]]
        if primary:
            choices = primary
        # If the preferred position is empty, borrow from a position with
        # spare players before taking somebody needed for a later job.
        future = Counter(next_sources[0] for _, next_sources in slots[index + 1:])
        remaining = Counter(p.pos for p in players if p.pid not in used)
        player, source = max(choices, key=lambda item: (
            remaining[item[1]] - future[item[1]],
            OR.fullback_score(item[0]) if role == 'FB' else grades[item[0].pid]))
        used.add(player.pid)
        role_grade = OR.fullback_score(player) if role == 'FB' else grades[player.pid]
        grade = role_grade - (0.0 if source == sources[0] else 3.0)
        assignments.append(dict(role=role, sources=sources, player=player, grade=grade))
        quality += min(grade, 90.0) - 75.0
        bar = 81.0 if role == 'QB' else 76.0
        weakness = max(0.0, min(0.65, (bar - grade) / 18.0))
        needs[player.pos] = max(needs[player.pos], weakness)

    counts = Counter(p.pos for p in players)
    floors, group_floors = roster_floors(team)
    front = DR.coach_front(getattr(team, 'gm', None))
    for family, short in planning_shortages(counts, floors):
        if short:
            for pos in family:
                needs[pos] = max(needs[pos], min(1.0, 0.55 + 0.2 * short))
            quality -= 4.0 * short
    for group, floor in group_floors.items():
        short = max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
        if short:
            for pos in GROUPS[group]:
                needs[pos] = max(needs[pos], min(0.75, 0.2 + 0.13 * short))
            quality -= 3.0 * short
    return {'needs': needs, 'uncovered': uncovered, 'score': quality,
            'counts': counts, 'front': front, 'assignments': assignments}


_SKILL_SOURCES = {'HB': ('HB', 'FB', 'WR', 'TE'),
                  'FB': ('FB', 'HB', 'TE', 'WR'),
                  'TE': ('TE', 'FB', 'WR', 'HB'),
                  'WR': ('WR', 'TE', 'HB', 'FB')}


def _planning_depth(players, grades):
    """Projected availability includes returnees supplied by the caller."""
    depth = {pos: [] for pos in POSITIONS}
    for p in players:
        depth.setdefault(p.pos, []).append(dict(
            getattr(p, 'ratings', {}) or {}, pid=p.pid, pos=p.pos, ovr=float(p.ovr),
            weight=getattr(p, 'weight', None)))
    for men in depth.values():
        men.sort(key=lambda p: (-grades[p['pid']], str(p['pid'])))
    return depth


def _offensive_rows(depth, package):
    spec = OR.PACKAGES[package]
    slots = [('QB', ('QB',))] + [(p, (p,) + tuple(q for q in OR.OL if q != p)) for p in OR.OL]
    slots += [(p, _SKILL_SOURCES[p]) for p in ('HB', 'FB', 'TE', 'WR') for _ in range(spec[p])]
    try:
        chosen = OR.assign(depth, package)
        # Recruiting must not call a receiver an answer to a vacant QB/OL job.
        if any(p['pos'] not in sources for (_, p), (_, sources) in zip(chosen, slots)):
            chosen = None
    except ValueError:
        chosen = None
    used, rows, counts = set(), [], Counter()
    for i, (role, sources) in enumerate(slots):
        if chosen is not None:
            p = chosen[i][1]
        else:
            pool = [p for pos in sources for p in depth.get(pos, ()) if p['pid'] not in used]
            p = pool[0] if pool else None
            if role == 'FB' and p is not None and p['pos'] != 'FB':
                remaining = Counter(x['pos'] for men in depth.values() for x in men if x['pid'] not in used)
                spare = [x for x in pool if remaining[x['pos']] > spec.get(x['pos'], 0)]
                if spare: p = max(spare, key=OR.fullback_score)
        if p is not None: used.add(p['pid'])
        rows.append(dict(role=role, sources=sources, player=p, slot=counts[role]))
        counts[role] += 1
    return rows


def _defensive_rows(depth, variant, gm, role_grades, ranked=None):
    """Each package independently assigns eleven distinct physical players."""
    slots = variant['slots']
    used, rows = set(), []
    # Reserve specialist interior and deep jobs before interchangeable backups.
    priority = {'NT': 0, 'FS': 1, 'SS': 1, 'SLOT': 3, 'CB': 4}
    result = {}
    for i, slot in sorted(enumerate(slots), key=lambda pair: (priority.get(pair[1]['role'], 2), pair[0])):
        role = slot['role']; specialist = slot.get('specialist')
        sources = tuple(slot.get('sources', DR.ROLE_SOURCES[role]))
        def grade(p):
            key = (p['pid'], role, specialist)
            if key not in role_grades:
                role_grades[key] = DR.candidate_grade(p, role, specialist=specialist, gm=gm)
            return role_grades[key]
        if ranked is None:
            candidates = [p for pos in sources for p in depth.get(pos, ()) if p['pid'] not in used]
            player = max(candidates, key=lambda p: (grade(p), -sources.index(p['pos']), str(p['pid'])), default=None)
        else:
            # Variants repeat the same jobs. Rank each eligible pool once for
            # this projected roster; each package still reserves distinct men.
            job = (role, specialist, sources)
            if job not in ranked:
                candidates = [p for pos in sources for p in depth.get(pos, ())]
                ranked[job] = sorted(candidates, key=lambda p: (
                    grade(p), -sources.index(p['pos']), str(p['pid'])), reverse=True)
            player = next((p for p in ranked[job] if p['pid'] not in used), None)
        if player is not None: used.add(player['pid'])
        result[i] = dict(slot, sources=sources, player=player,
                         grade=grade(player) if player is not None else None)
    return [result[i] for i in range(len(slots))]


def _package_rows(team, players, grades, profile, role_grades, side=None, depth=None,
                  weight_cache=None):
    gm = getattr(team, 'gm', None)
    by_pid = {p.pid: p for p in players}
    depth = _planning_depth(players, grades) if depth is None else depth
    out = []
    if side in (None, 'offense'):
        for package, weight in OR.expected_package_weights(gm, depth, weight_cache).items():
            for row in _offensive_rows(depth, package):
                p = row['player']
                grade = None
                if p is not None:
                    grade = OR.role_grade(p, row['role'], package, row['slot']) + grades[p['pid']] - p['ovr']
                    if p['pos'] != row['sources'][0] and row['role'] != 'FB': grade -= 3
                out.append(dict(row, player=by_pid[p['pid']] if p else None, grade=grade,
                                side='offense', front=None, package=package, weight=weight,
                                variant='offense:' + package))
    if side in (None, 'defense'):
        ranked = {}
        for index, variant in enumerate(profile['variants']):
            for row in _defensive_rows(depth, variant, gm, role_grades, ranked):
                p = row['player']
                out.append(dict(row, player=by_pid[p['pid']] if p else None,
                                side='defense', front=variant['front'], package=variant['package'],
                                weight=variant['share'], big_nickel=variant.get('big_nickel', False),
                                variant='defense:' + str(index)))
    return out


def _quality(rows):
    return sum(row['weight'] * (min(row['grade'], 90.0) - 75.0
                                if row['grade'] is not None else -20.0) for row in rows)


def _depth_accounting(team, players, grades, floors_snapshot=None):
    from types import SimpleNamespace
    depth = {pos: [] for pos in POSITIONS}
    for p in players: depth.setdefault(p.pos, []).append(p)
    if floors_snapshot is None:
        for men in depth.values(): men.sort(key=lambda p: -grades[p.pid])
        projected = SimpleNamespace(gm=getattr(team, 'gm', None), depth=depth)
        floors, group_floors = roster_floors(projected)
    else:
        floors, group_floors = floors_snapshot
    counts = Counter(p.pos for p in players)
    needs = {pos: 0.0 for pos in POSITIONS}; score = 0.0
    for family, short in planning_shortages(counts, floors):
        if short:
            for pos in family:
                needs[pos] = min(1.0, .55 + .2 * short)
            score -= 4.0 * short
    for group, floor in group_floors.items():
        short = max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
        if short:
            for pos in GROUPS[group]: needs[pos] = max(needs[pos], min(.75, .2 + .13 * short))
            score -= 3.0 * short
    for pos in ('K', 'P', 'LS'):
        grade = max((grades[p.pid] for p in depth[pos]), default=None)
        score += min(grade, 90) - 75 if grade is not None else -20
        needs[pos] = max(needs[pos], 1.0 if grade is None else max(0.0, min(.65, (76-grade)/18)))
    return score, needs


def assessment_inputs(team, players):
    """Prepare fixed player/coach inputs for a single synchronous repair search.

    Discard after any roster, rating, position or coaching mutation. Callers
    still assign every proposed lineup and evaluate every coverage rule.
    """
    return dict(team=team, grades={p.pid: _grade(p, team) for p in players},
                profile=DR.planning_profile(getattr(team, 'gm', None)), role_grades={})


def assess(team, players=None, strict_roles=False, *, prepared=None, score_only=False):
    """Shared base chart, weighted package quality, and reserve-depth needs.

    Package weights sum to one separately for each side of the ball. A player
    may appear in multiple alternatives, never twice in one package. Callers
    may reuse this snapshot for candidate_gains until roster/coach/ratings change.
    score_only returns the identical numeric score without building chart and
    needs summaries that a cutdown candidate search never consumes.
    """
    players = tuple(team.active() if players is None else players)
    if prepared is not None and prepared['team'] is not team:
        raise ValueError('Assessment inputs belong to another team')
    grades = ({p.pid: prepared['grades'][p.pid] for p in players} if prepared is not None
              else {p.pid: _grade(p, team) for p in players})
    report = None if score_only else _base_assess(team, players, strict_roles, grades)
    profile = prepared['profile'] if prepared is not None else DR.planning_profile(getattr(team, 'gm', None))
    role_grades = prepared['role_grades'] if prepared is not None else {}
    depth = _planning_depth(players, grades)
    rows = _package_rows(team, players, grades, profile, role_grades, depth=depth)
    depth_score, needs = _depth_accounting(team, players, grades)
    scores = {side: _quality([row for row in rows if row['side']==side]) for side in ('offense','defense')}
    if score_only:
        return depth_score + sum(scores.values())
    # The summary chart must describe the same choices as the package planner.
    # Preserve specialist rows and the extra nickel corner without reranking LBs
    # by their saved MIKE/WILL label.
    base_off = OR.base_package(getattr(team, 'gm', None))
    base_def = [v for v in profile['variants'] if v['package'] == 'base']
    representative = max(base_def or profile['variants'], key=lambda v: v['share'])
    def_index = next(i for i, v in enumerate(profile['variants']) if v is representative)
    base_rows = [dict(r) for r in rows if r['variant'] in
                 ('offense:' + base_off, 'defense:' + str(def_index))]
    old_extra = [r for r in report['assignments'] if r['role'] in ('K', 'P', 'LS')]
    if sum(r['role'] == 'CB' for r in base_rows) < 3:
        used = {r['player'].pid for r in base_rows if r['player'] is not None}
        corners = [p for p in players if p.pos == 'CB' and p.pid not in used]
        corner = max(corners, key=lambda p: grades[p.pid], default=None)
        old_extra.insert(0, dict(role='CB', sources=('CB',), player=corner,
                                grade=grades[corner.pid] if corner else None))
    report['assignments'] = base_rows + old_extra
    report['uncovered'] = [r['role'] for r in report['assignments'] if r['player'] is None]
    package_needs = {pos: 0.0 for pos in POSITIONS}
    demand = {pos: 0.0 for pos in POSITIONS}
    for row in rows:
        pos = row['sources'][0]
        if row['role'] == 'FB' and row['player'] is not None: pos = row['player'].pos
        demand[pos] += row['weight']
        bar = 81.0 if row['role'] == 'QB' else 76.0
        weakness = 1.0 if row['grade'] is None else max(0.0, min(.65, (bar-row['grade'])/18))
        package_needs[pos] += row['weight'] * weakness
    # Summed weak jobs can warrant attention, but many rare jobs cannot
    # produce more than one fully vacant everyday position's urgency.
    for pos in needs:
        package_needs[pos] = min(1.0, package_needs[pos])
        needs[pos] = max(needs[pos], package_needs[pos])
    report.update(needs=needs, score=depth_score+sum(scores.values()), players=players,
                  package_assignments=rows, package_needs=package_needs, package_demand=demand,
                  _grades=grades, _role_grades=role_grades, _profile=profile, _package_scores=scores,
                  _planning_depth=depth)
    return report



def essential_coverage(team, players=None, report=None):
    """Normal starter coverage, independent of preferred reserve depth.

    Stable side:role:slot keys permit before/after comparisons. Severity is
    2 for an empty job, at least 1 for a non-native OL starter, and (65-grade)/65
    for a weak starter. Compatible FB and defensive roles remain legitimate.
    Quality is the same complete-package score consumed by move_gain.
    """
    report = assess(team, players) if report is None else report
    shortages, sources = {}, {}
    base = OR.base_package(getattr(team, 'gm', None))
    occurrences = Counter()
    for row in report['package_assignments']:
        index = occurrences[(row['variant'], row['role'])]
        occurrences[(row['variant'], row['role'])] += 1
        # Every callable package needs eleven qualified bodies. Low-share
        # packages still do not impose quality or preferred-depth floors.
        if row['weight'] < .1 and not (row['package'] == 'base' or row['side'] == 'offense' and row['package'] == base):
            if row['weight'] <= 0 or row['player'] is not None:
                continue
        key = f"{row['side']}:{row['role']}:{index}"
        p, grade = row['player'], row['grade']
        severity = 2.0 if p is None else max(0.0, (65.0 - grade) / 65.0)
        eligible = tuple(row['sources'])
        if row['side'] == 'offense' and row['role'] in OR.OL:
            eligible = (row['role'],)
            if p is not None and p.pos != row['role']:
                severity = max(1.0, severity)
        if severity > 0:
            shortages[key] = max(shortages.get(key, 0.0), severity)
            sources[key] = eligible
    for row in report['assignments']:
        if row['role'] in ('K', 'P', 'LS') and row['player'] is None:
            key = 'special:' + row['role'] + ':0'
            shortages[key] = 2.0; sources[key] = tuple(row['sources'])
    return dict(shortages=shortages, sources=sources, quality=report['score'])


def coverage_not_worse(before, after):
    """Reject newly opened or worsened essential jobs, not existing weaknesses."""
    return all(value <= before['shortages'].get(key, 0.0) + 1e-9
               for key, value in after['shortages'].items())

def _changed_depth(before, grades, arrival=None, departure=None):
    """Copy only changed position groups from one caller-owned roster read."""
    saved = before.get('_planning_depth')
    if saved is None:
        saved = _planning_depth(before['players'], before['_grades'])
    removed = {p.pid for p in (arrival, departure) if p is not None}
    depth = dict(saved)
    for pos, men in saved.items():
        if any(p['pid'] in removed for p in men):
            depth[pos] = [p for p in men if p['pid'] not in removed]
    if arrival is not None:
        row = dict(getattr(arrival, 'ratings', {}) or {}, pid=arrival.pid,
                   pos=arrival.pos, ovr=float(arrival.ovr), weight=getattr(arrival, 'weight', None))
        depth[arrival.pos] = list(depth.get(arrival.pos, ())) + [row]
        depth[arrival.pos].sort(key=lambda p: (-grades[p['pid']], str(p['pid'])))
    return depth


def move_gain(team, arrival, departure=None, baseline=None, *,
              _floors_snapshot=None, _weight_cache=None, return_package_rows=False):
    """Marginal package/depth value; optionally return recalculated package rows.

    Those rows belong only to the changed side of the ball. The caller may
    combine them with unchanged rows from the same current baseline, but must
    discard them after any roster, rating, or coach change.
    """
    before = assess(team) if baseline is None else baseline
    players = [p for p in before['players'] if p.pid != arrival.pid
               and (departure is None or p.pid != departure.pid)] + [arrival]
    grades = dict(before['_grades']); grades[arrival.pid] = _grade(arrival, team)
    role_grades = {key: value for key, value in before['_role_grades'].items() if key[0] != arrival.pid}
    affected = {arrival.pos} | ({departure.pos} if departure is not None else set())
    scores = dict(before['_package_scores'])
    depth = _changed_depth(before, grades, arrival, departure)
    changed_rows = []
    for side, positions in (('offense', OR.OFFENSE), ('defense', DR.DEFENSE)):
        if affected & positions:
            rows = _package_rows(team, players, grades, before['_profile'],
                                 role_grades, side, depth, _weight_cache)
            scores[side] = _quality(rows)
            if return_package_rows:
                changed_rows.extend(rows)
    depth_score, _ = _depth_accounting(team, players, grades, _floors_snapshot)
    gain = depth_score + sum(scores.values()) - before['score']
    return (gain, changed_rows) if return_package_rows else gain


def departure_loss(team, departure, baseline=None):
    """Exact removal score using one caller-owned, current roster snapshot.

    Reuse player/role grades, but allocate every package again: emergency
    replacements can cross positions, and removing a back can change the
    offensive personnel mix. Nothing is cached beyond this assessment.
    """
    before = assess(team) if baseline is None else baseline
    players = [p for p in before['players'] if p.pid != departure.pid]
    grades = before['_grades']
    role_grades = dict(before['_role_grades'])
    depth = _changed_depth(before, grades, departure=departure)
    rows = _package_rows(team, players, grades, before['_profile'], role_grades, depth=depth)
    depth_score, _ = _depth_accounting(team, players, grades)
    scores = {side: _quality([row for row in rows if row['side'] == side])
              for side in ('offense', 'defense')}
    return before['score'] - (depth_score + sum(scores.values()))


def candidate_gains(team, players, baseline=None):
    """Evaluate a candidate pool against one explicit, short-lived snapshot."""
    baseline = assess(team) if baseline is None else baseline
    players = tuple(players)
    floors_snapshot = None
    weight_cache = {}
    if any(p.pos not in OR.OFFENSE for p in players):
        # A defensive or special-teams arrival cannot change which back or
        # tight end fills this coach's offensive FB job. Reuse those floors
        # only within this candidate pass; the next roster/coach read starts
        # with a fresh baseline and a fresh snapshot.
        from types import SimpleNamespace
        projected_depth = {pos: [] for pos in POSITIONS}
        for p in baseline['players']:
            projected_depth.setdefault(p.pos, []).append(p)
        for men in projected_depth.values():
            men.sort(key=lambda p: -baseline['_grades'][p.pid])
        projected = SimpleNamespace(gm=getattr(team, 'gm', None), depth=projected_depth)
        floors_snapshot = roster_floors(projected)
    return {p.pid: move_gain(team, p, baseline=baseline,
                             _floors_snapshot=(floors_snapshot if p.pos not in OR.OFFENSE else None),
                             _weight_cache=weight_cache)
            for p in players}


def lineup_strength(team, players):
    """Protect a playable base lineup, then compare the full package mix."""
    players = list(players)
    import targets as TG
    depth = {pos: [] for pos in POSITIONS}
    for player in players:
        depth.setdefault(player.pos, []).append(player)
    for pos, group in depth.items():
        group.sort(key=lambda player: -TG.position_score(player.ratings, pos,
                                                          getattr(team, 'scheme', None)))
    try:
        OR.assign(depth, OR.base_package(getattr(team, 'gm', None)))
        missing = 0
    except ValueError:
        missing = 1
    defense = DR.assign(depth, DR.coach_front(getattr(team, 'gm', None)), 'base')
    missing += sum(row['player'] is None for row in defense)
    missing += sum(not depth[pos] for pos in ('K', 'P', 'LS'))
    # The cutdown's final comparison must not undo a package-aware exchange
    # merely because WR4/TE2/CB4 does not belong to the displayed base chart.
    report = assess(team, players)
    return missing, _quality(report['package_assignments']) + 22 * 75.0


def retention_value(team, player, players=None):
    """Bounded value of keeping a controlled young successor off waivers.

    This is a planning preference, never a roster/cap exemption. Use the
    visible potential range, not the hidden ceiling. A weak early pick can
    still lose his place to a useful veteran or a required position.
    """
    age = float(getattr(player, 'age', 30))
    accrued = int(getattr(player, 'accrued', 3) or 0)
    contract = getattr(player, 'contract', None)
    years = int(getattr(contract, 'years', 0) or 0)
    from development_value import player_credit
    dev_credit = 2.0 * player_credit(player)
    if age > 26 or accrued > 2 or years < 2:
        return dev_credit
    readiness = max(0.0, min(1.0, (float(player.ovr) - 60.0) / 18.0))
    from ceiling_knowledge import observed_range
    visible = observed_range(player)
    growth = min(6.0, max(0.0, sum(visible) / 2 - player.ovr)) if visible else 0.0
    belief = float(getattr(getattr(team, 'gm', None), 'dev_belief', .5))
    # Ready young players are unlikely to be safely stashed. Early draft
    # investment supplies modest patience, rather than permanent protection.
    rd = getattr(player, 'draft_round', None)
    investment = max(0.0, (5 - int(rd)) / 4) if rd else 0.0
    exposure = readiness * (1.0 + investment) / (1.0 + .5 * accrued)
    men = list(team.active() if players is None else players)
    incumbents = [q for q in men if q.pid != player.pid and q.pos == player.pos
                  and q.ovr >= player.ovr]
    succession = any(getattr(q, 'age', 25) >= (33 if player.pos == 'QB' else 29)
                     or getattr(getattr(q, 'contract', None), 'years', 3) <= 1
                     for q in incumbents)
    return min(6.0, readiness * growth * (.35 + .25 * belief)
               + exposure + (1.0 if succession else 0.0) * readiness + dev_credit)


def select_cutdown(team, rows, limit=53):
    """Choose 53 with coach-aware depth and a playable-lineup safeguard."""
    import roster_construction as RC
    raw_rows = rows
    by_pid = {p.pid: p for p in team.active()}
    retention = {pid: retention_value(team, p) for pid, p in by_pid.items()}
    # Only the allocation proxy changes; displayed ratings and game grades
    # are untouched. Carry the same preference through the final safeguard.
    rows = [dict(row, ovr=row['ovr'] + retention.get(row['pid'], 0.0)) for row in rows]
    floors, group_floors = roster_floors(team)
    selected, _ = RC.allocate(rows, team.ctx(), team.gm, limit=limit,
                              minimums=floors, group_minimums=group_floors)
    row_ids = {row['pid'] for row in rows}
    pool = [p for p in team.active() if p.pid in row_ids]
    selected_ids = improve_cutdown(team, (row['pid'] for row in selected),
                                    limit=limit, available=pool)
    baseline, _ = RC.allocate(raw_rows, team.ctx(), team.gm, limit=limit)
    baseline_ids = {row['pid'] for row in baseline}

    def chosen(ids):
        return [p for p in pool if p.pid in ids]

    def shortage(players):
        counts = Counter(p.pos for p in players)
        return (sum(max(0, floor - counts[pos]) for pos, floor in floors.items())
                + sum(max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
                      for group, floor in group_floors.items()))

    new, old = chosen(selected_ids), chosen(baseline_ids)
    new_missing, new_grade = lineup_strength(team, new)
    old_missing, old_grade = lineup_strength(team, old)
    new_grade += sum(retention[p.pid] for p in new)
    old_grade += sum(retention[p.pid] for p in old)
    # A reserve-depth floor is valuable, but it must not cost a substantially
    # stronger starter. An uncovered job always takes precedence.
    if (old_missing < new_missing or
            (old_missing == new_missing and
             old_grade - 4.0 * shortage(old) >
             new_grade - 4.0 * shortage(new) + 0.1)):
        return baseline_ids
    return selected_ids


def improve_cutdown(team, keep_ids, limit=53, available=None):
    """Exchange marginal camp players when a cut weakens the playable lineup."""
    pool = list(team.active() if available is None else available)
    keep_ids = set(keep_ids)
    if len(keep_ids) != limit:
        return keep_ids
    floors, group_floors = roster_floors(team)
    retention = {p.pid: retention_value(team, p, pool) for p in pool}

    def shortage(players):
        counts = Counter(p.pos for p in players)
        return (sum(max(0, floor - counts[pos]) for pos, floor in floors.items())
                + sum(max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
                      for group, floor in group_floors.items()))

    prepared = assessment_inputs(team, pool)
    for _ in range(3):
        kept = [p for p in pool if p.pid in keep_ids]
        base = assess(team, kept, prepared=prepared, score_only=True)
        missing = shortage(kept)
        best = None
        arrivals = [(assess(team, kept + [p], prepared=prepared, score_only=True) - base + retention[p.pid], p)
                    for p in pool if p.pid not in keep_ids]
        arrivals = [p for gain, p in sorted(arrivals, key=lambda row: -row[0])[:8]
                    if gain > 1.0]
        departures = sorted(kept,
                            key=lambda p: base - assess(team, [q for q in kept if q.pid != p.pid], prepared=prepared, score_only=True)
                            + retention[p.pid])[:16]
        for arrival in arrivals:
            for departure in departures:
                proposed = [p for p in kept if p.pid != departure.pid] + [arrival]
                if shortage(proposed) > missing:
                    continue
                dead_delta = max(0.0, departure.dead_if_cut(0) - arrival.dead_if_cut(0))
                gain = (assess(team, proposed, prepared=prepared, score_only=True) - base - 0.5 * dead_delta
                        + retention[arrival.pid] - retention[departure.pid])
                if gain > 2.0 and (best is None or gain > best[0]):
                    best = (gain, arrival.pid, departure.pid)
        if best is None:
            break
        _, incoming, outgoing = best
        keep_ids.remove(outgoing)
        keep_ids.add(incoming)
    return keep_ids
