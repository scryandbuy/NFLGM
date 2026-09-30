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


def assess(team, players=None, strict_roles=False):
    """Return need (0..1) by saved position and uncovered starting jobs.

    This is a roster assessment, not a transaction: cap and dead money belong
    in the move decision. `players` allows callers to evaluate a proposed move.
    """
    players = list(team.active() if players is None else players)
    grades = {p.pid: _grade(p, team) for p in players}
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
    for pos, floor in floors.items():
        if counts[pos] < floor:
            needs[pos] = max(needs[pos], min(1.0, 0.55 + 0.2 * (floor - counts[pos])))
            quality -= 4.0 * (floor - counts[pos])
    for group, floor in group_floors.items():
        short = max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
        if short:
            for pos in GROUPS[group]:
                needs[pos] = max(needs[pos], min(0.75, 0.2 + 0.13 * short))
            quality -= 3.0 * short
    return {'needs': needs, 'uncovered': uncovered, 'score': quality,
            'counts': counts, 'front': front, 'assignments': assignments}


def move_gain(team, arrival, departure=None):
    """Roster improvement from adding a player and optionally replacing one."""
    before = assess(team)
    after = [p for p in team.active()
             if p.pid != arrival.pid and (departure is None or p.pid != departure.pid)]
    after.append(arrival)
    return assess(team, after)['score'] - before['score']


def lineup_strength(team, players):
    """Grade the actual base-package starters selected by the game."""
    import targets as TG
    depth = {pos: [] for pos in POSITIONS}
    for player in players:
        depth.setdefault(player.pos, []).append(player)
    for pos, group in depth.items():
        group.sort(key=lambda player: -TG.position_score(player.ratings, pos,
                                                          getattr(team, 'scheme', None)))
    try:
        offense = OR.assign(depth, OR.base_package(getattr(team, 'gm', None)))
        offense_grade = sum(OR.fullback_score(p) if role == 'FB' else p.ovr
                            for role, p in offense)
        missing = 0
    except ValueError:
        offense_grade, missing = 0.0, 1
    defense = DR.assign(depth, DR.coach_front(getattr(team, 'gm', None)), 'base')
    defense_grade = sum(row['player'].ovr for row in defense if row['player'])
    missing += sum(row['player'] is None for row in defense)
    missing += sum(not depth[pos] for pos in ('K', 'P', 'LS'))
    return missing, offense_grade + defense_grade


def select_cutdown(team, rows, limit=53):
    """Choose 53 with coach-aware depth and a playable-lineup safeguard."""
    import roster_construction as RC
    floors, group_floors = roster_floors(team)
    selected, _ = RC.allocate(rows, team.ctx(), team.gm, limit=limit,
                              minimums=floors, group_minimums=group_floors)
    row_ids = {row['pid'] for row in rows}
    pool = [p for p in team.active() if p.pid in row_ids]
    selected_ids = improve_cutdown(team, (row['pid'] for row in selected),
                                    limit=limit, available=pool)
    baseline, _ = RC.allocate(rows, team.ctx(), team.gm, limit=limit)
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

    def shortage(players):
        counts = Counter(p.pos for p in players)
        return (sum(max(0, floor - counts[pos]) for pos, floor in floors.items())
                + sum(max(0, floor - sum(counts[pos] for pos in GROUPS[group]))
                      for group, floor in group_floors.items()))

    for _ in range(3):
        kept = [p for p in pool if p.pid in keep_ids]
        base = assess(team, kept)['score']
        missing = shortage(kept)
        best = None
        arrivals = [(assess(team, kept + [p])['score'] - base, p)
                    for p in pool if p.pid not in keep_ids]
        arrivals = [p for gain, p in sorted(arrivals, key=lambda row: -row[0])[:8]
                    if gain > 1.0]
        departures = sorted(kept,
                            key=lambda p: base - assess(team, [q for q in kept if q.pid != p.pid])['score'])[:16]
        for arrival in arrivals:
            for departure in departures:
                proposed = [p for p in kept if p.pid != departure.pid] + [arrival]
                if shortage(proposed) > missing:
                    continue
                dead_delta = max(0.0, departure.dead_if_cut(0) - arrival.dead_if_cut(0))
                gain = assess(team, proposed)['score'] - base - 0.5 * dead_delta
                if gain > 2.0 and (best is None or gain > best[0]):
                    best = (gain, arrival.pid, departure.pid)
        if best is None:
            break
        _, incoming, outgoing = best
        keep_ids.remove(outgoing)
        keep_ids.add(incoming)
    return keep_ids
