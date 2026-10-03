"""Finite, saved scouting work between regular-season games.

Only cross_checks earns information. Selecting priorities and reading reports
never roll evidence. Local random streams leave the simulation stream alone.
"""
import copy
import numpy as np
import scouting as SC
import character_assessment as CA
from stable import stable_seed

GROUPS = {
    'QB': ('QB',), 'Backs': ('HB', 'FB'), 'Receivers': ('WR',),
    'Tight Ends': ('TE',), 'Offensive Line': ('LT', 'LG', 'C', 'RG', 'RT'),
    'Edge': ('LEDG', 'REDG'), 'Interior DL': ('DT',),
    'Linebackers': ('MIKE', 'WILL', 'SAM'), 'Corners': ('CB',),
    'Safeties': ('FS', 'SS'), 'Specialists': ('K', 'P', 'LS'),
}
GROUP_LOOKS = 3
# Reuse the existing scouting ceiling; no new final-knowledge target is set.
INSEASON_CERT_MAX = SC.CERT_MAX


def _pool(league):
    return list(getattr(league, 'next_class', None) or
                getattr(league, 'draft_pool', None) or [])


def _class_id(pool):
    return str(stable_seed(('inseason-class-v1', tuple(sorted(p.pid for p in pool)))))


def _saved(league, pool):
    state = getattr(league, 'scouting_season', None) or {}
    return state if state.get('class_id') == _class_id(pool) else {}


def _choices(league, abbr, pool):
    views = (getattr(league, 'scouting', None) or {}).get(abbr, {})
    return [p for p in pool if p.pid in views]


def _pick_windows(league, abbr):
    """Upcoming draft ownership, including picks acquired from another club."""
    def projected(owner):
        record = getattr(league.teams.get(owner), 'record', (0, 0, 0))
        games = sum(record[:3])
        pct = (record[0] + .5 * (record[2] if len(record) > 2 else 0)) / games if games else .5
        return 1 + round(31 * pct)
    return [(int(pk.selection or (32 * (pk.round - 1) + projected(pk.original))), pk.round)
            for pk in league.teams[abbr].picks
            if pk.year == league.year and pk.owner == abbr and not pk.used_on]


def _defaults(league, abbr, pool):
    """Roster succession and saved football reads, never prospect hidden truth."""
    import draft_plan as DP
    positions = DP.assess(league, abbr)['positions']
    choices = _choices(league, abbr, pool)
    available = {p.pos for p in choices}
    groups = [g for g, ps in GROUPS.items() if available.intersection(ps)]
    cons = getattr(league, 'consensus', None) or {}
    mine = (getattr(league, 'scouting', None) or {}).get(abbr, {})
    windows = _pick_windows(league, abbr)
    history = _saved(league, pool).get('clubs', {}).get(abbr, {}).get('focus_history', [])
    scored = []
    for g in groups:
        pos = max(GROUPS[g], key=lambda pos: positions.get(pos, {}).get('need', 0))
        detail = positions.get(pos, {})
        need = detail.get('need', 0)
        focused = sum(g in (x['group1'], x['group2']) for x in history)
        candidates = [p for p in choices if p.pos in GROUPS[g]]
        opportunity = 0.
        near = set()
        for slot, rd in windows:
            strengths = []
            for p in candidates:
                distance = abs((cons.get(p.pid, {}).get('rank') or 999) - slot)
                if distance <= 20:
                    near.add(p.pid)
                    strengths.append((1 - distance / 21.) * min(1., max(0., (mine[p.pid]['ovr'] - 55) / 25.)))
            opportunity += max(strengths, default=0.) / rd ** .5
        score = (need + min(2., opportunity)) / (1. + .4 * focused)
        concern = ('Starting need' if detail.get('starter', 0) >= 4 else
                   'Succession or expiring contracts' if detail.get('future', 0) >= 4 else
                   'Backup depth' if detail.get('depth', 0) >= 3 else 'Depth and future flexibility')
        why = f'{concern} at {pos}. '
        why += (f'{len(near)} prospects near your {len(windows)} owned picks. ' if windows
                else 'No upcoming picks owned; maintain a trade-in and undrafted watchlist. ')
        why += f'Focused {focused} earlier cycle' + ('.' if focused == 1 else 's.')
        scored.append((score, g != 'Specialists', -list(GROUPS).index(g), g, why))
    scored.sort(reverse=True)
    suggestions = [dict(group=g, why=why) for _, _, _, g, why in scored[:2]]
    for g in GROUPS:
        if len(suggestions) >= 2: break
        if not any(s['group'] == g for s in suggestions):
            suggestions.append(dict(group=g, why='No scouted prospects available in this group yet.'))
    group1, group2 = [s['group'] for s in suggestions]
    candidates = [p for p in choices if p.pos in GROUPS[group1]]
    def target_key(p):
        rank = cons.get(p.pid, {}).get('rank') or 999
        distance = min((abs(rank - slot) + 4 * (rd - 1) for slot, rd in windows), default=abs(rank - 240))
        return (distance, -float(mine[p.pid].get('ovr', 0)), p.pid)
    prospect = min(candidates, key=target_key) if candidates else None
    return dict(group1=group1, group2=group2, prospect_pid=prospect.pid if prospect else None,
                suggestions=suggestions)


def priorities(league, abbr):
    """Read-only public selection model. Defaults do not earn or save evidence."""
    if abbr not in league.teams:
        raise ValueError('Unknown team.')
    pool = _pool(league)
    valid = {p.pid for p in _choices(league, abbr, pool)}
    saved = _saved(league, pool).get('clubs', {}).get(abbr, {})
    default = _defaults(league, abbr, pool)
    prior = (getattr(league, 'scouting_season', None) or {}).get('clubs', {}).get(abbr, {})
    group1 = saved.get('group1', prior.get('group1'))
    if group1 not in GROUPS: group1 = default['group1']
    group2 = saved.get('group2', prior.get('group2'))
    if group2 not in GROUPS or group2 == group1:
        group2 = next(g for g in (default['group1'], default['group2']) if g != group1)
    pid = saved.get('prospect_pid')
    if pid not in valid:
        pid = default['prospect_pid']
    next_week = max((int(saved.get('last_week', 0)) // 2 + 1) * 2,
                    ((max(1, int(getattr(league, 'week', 1) or 1)) + 1) // 2) * 2)
    return dict(group1=group1, group2=group2, prospect_pid=pid, groups=list(GROUPS),
                suggestions=default['suggestions'], focus_history=copy.deepcopy(saved.get('focus_history', [])),
                last_report_week=int(saved.get('last_week', 0)),
                next_report_week=next_week if next_week <= 18 else None)


def _state(league, pool):
    state = _saved(league, pool)
    if not state:
        old = getattr(league, 'scouting_season', None) or {}
        state = dict(class_id=_class_id(pool), season_year=int(league.year), clubs={})
        for a, row in old.get('clubs', {}).items():
            if a in league.teams:
                state['clubs'][a] = {k: row[k] for k in ('group1', 'group2') if row.get(k) in GROUPS}
        league.scouting_season = state
    return state


def set_priorities(league, abbr, *, group1=None, group2=None, prospect_pid=None, use_scout=False):
    """Set the two priorities; no scouting work is performed here."""
    if abbr not in league.teams:
        raise ValueError('Unknown team.')
    current = priorities(league, abbr)
    if use_scout:
        group1, group2 = [s['group'] for s in current['suggestions']]
    group1 = current['group1'] if group1 is None else group1
    group2 = current['group2'] if group2 is None else group2
    prospect_pid = current['prospect_pid'] if prospect_pid is None else prospect_pid
    if group1 not in GROUPS or group2 not in GROUPS or group1 == group2:
        raise ValueError('Choose two different position groups.')
    pool = _pool(league)
    if prospect_pid not in {p.pid for p in _choices(league, abbr, pool)}:
        raise ValueError('Choose a prospect in the current scouted class.')
    row = _state(league, pool)['clubs'].setdefault(abbr, {})
    row.update(group1=group1, group2=group2, prospect_pid=prospect_pid)
    return priorities(league, abbr)


def _estimate(view):
    cert = SC.certainty(view)
    return dict(ovr=view['ovr'], pot_lo=view['pot_lo'], pot_hi=view['pot_hi'],
                confidence='Strong' if cert >= .75 else 'Moderate' if cert >= .5 else 'Limited')


def reports(league, abbr):
    """Safe report history for this class, detached from mutable save data."""
    return copy.deepcopy(_saved(league, _pool(league)).get('clubs', {}).get(abbr, {}).get('reports', []))


def background_coverage(league, abbr):
    """Safe coverage counts, separate from football certainty or hidden traits."""
    views = (getattr(league, 'scouting', None) or {}).get(abbr, {})
    candidates = _choices(league, abbr, _pool(league))
    counts = dict(total=len(candidates), assessed=0, limited=0, moderate=0, strong=0)
    for p in candidates:
        record = CA.assessments(views[p.pid]).get('work_ethic')
        if record is not None:
            counts['assessed'] += 1
            counts[CA.describe('work_ethic', record)['confidence'].lower()] += 1
    return counts


def _area_background(league, abbr, candidates, views, cons, room):
    """Finite background work across the class, without extra football looks.

    Around 7-9% of the class fits in a cycle's area-report workload, depending
    on scout quality. This is a workload setting, not an NFL coverage quota.
    Balance the proportion assessed across positions, then prioritize earlier
    consensus tiers. No hidden prospect ability determines who gets checked.
    """
    if room.get('character') == 'none' or not candidates:
        return 0
    quality = SC.scout_q(league.teams[abbr])
    budget = max(1, round(len(candidates) * (.07 + .02 * quality)))
    totals, known, queues = {}, {}, {}
    for p in candidates:
        totals[p.pos] = totals.get(p.pos, 0) + 1
        if 'work_ethic' in CA.assessments(views[p.pid]):
            known[p.pos] = known.get(p.pos, 0) + 1
        else:
            queues.setdefault(p.pos, []).append(p)
    def order(p):
        rank = cons.get(p.pid, {}).get('rank') or 999
        tier = 0 if rank <= 100 else 1 if rank <= 224 else 2
        return (tier, stable_seed(('area-coverage-v1', abbr, p.pid)), p.pid)
    for queue in queues.values():
        queue.sort(key=order, reverse=True)
    completed = 0
    for _ in range(budget):
        available = [pos for pos, queue in queues.items() if queue]
        if not available: break
        pos = min(available, key=lambda pos: (known.get(pos, 0) / totals[pos], pos))
        p = queues[pos].pop()
        if CA.area_report(p, abbr, views[p.pid], room, quality):
            known[pos] = known.get(pos, 0) + 1
            completed += 1
    return completed


def decision_resolved(league, week, abbr=None):
    """Read-only calendar marker, independent of deletable Inbox messages."""
    abbr = abbr or getattr(league, 'user_team', None)
    row = _saved(league, _pool(league)).get('clubs', {}).get(abbr, {})
    return f'{int(league.year)}:{int(week)}' in row.get('resolved_cycles', [])


def mark_decision_resolved(league, week, abbr=None):
    abbr = abbr or getattr(league, 'user_team', None)
    if abbr not in league.teams or isinstance(week, bool) or week not in range(19):
        raise ValueError('Unknown team or scouting decision week.')
    row = _state(league, _pool(league))['clubs'].setdefault(abbr, {})
    key = f'{int(league.year)}:{int(week)}'
    if key not in row.setdefault('resolved_cycles', []):
        row['resolved_cycles'].append(key)


def cross_checks(league, completed_week):
    """Earn one report batch after weeks 2,4,...18, at most once per club/week.

    The calendar calls this after the completed week while phase is regular.
    Old saves start with the current interval; missed weeks are not backfilled.
    Returns only newly earned, presentation-safe rows keyed by club.
    """
    if getattr(league, 'phase', None) != 'regular':
        return {}
    if isinstance(completed_week, bool) or completed_week not in range(2, 19, 2):
        return {}
    week = int(completed_week)
    pool = _pool(league)
    if not pool:
        return {}
    state = _state(league, pool)
    # Never reopen an old class's report calendar after the league-year roll.
    if state['season_year'] != int(league.year):
        return {}
    cons = getattr(league, 'consensus', None) or {}
    result = {}
    for abbr, team in league.teams.items():
        row = state['clubs'].setdefault(abbr, {})
        if int(row.get('last_week', 0)) >= week:
            continue
        choice = priorities(league, abbr)
        if abbr != getattr(league, 'user_team', None):
            choice['group1'], choice['group2'] = [s['group'] for s in choice['suggestions']]
        row.update(group1=choice['group1'], group2=choice['group2'], prospect_pid=choice['prospect_pid'])
        counts = row.setdefault('looks', {})
        views = (getattr(league, 'scouting', None) or {}).get(abbr, {})
        candidates = _choices(league, abbr, pool)
        def rank_key(p):
            return (cons.get(p.pid, {}).get('rank', 9999), p.pid)
        def rotate_key(p):
            return (counts.get(p.pid, 0), *rank_key(p))
        selected, kinds = {}, {}
        # Touch every actual position each cycle with very small gains. Rotate
        # prospects within the position; focus work is much more substantial.
        coverage = row.setdefault('baseline_positions', {})
        positions = sorted({p.pos for p in candidates}, key=lambda pos: (coverage.get(pos, 0), pos))
        for pos in positions:
            p = min((p for p in candidates if p.pos == pos), key=rotate_key)
            selected[p.pid] = p; kinds[p.pid] = 'Baseline'
            coverage[pos] = int(coverage.get(pos, 0)) + 1
        for g in (choice['group1'], choice['group2']):
            group = sorted((p for p in candidates if p.pos in GROUPS[g]), key=rank_key)[:12]
            # Focus grants additional reads beyond baseline coverage.
            extra = sorted((p for p in group if p.pid not in selected), key=rotate_key)[:GROUP_LOOKS]
            for p in extra:
                selected[p.pid] = p; kinds[p.pid] = 'Position Group'
        prospect = next((p for p in candidates if p.pid == choice['prospect_pid']), None)
        if prospect is not None:
            selected[prospect.pid] = prospect
            kinds[prospect.pid] = 'Prospect'
        batch = []
        for pid, p in selected.items():
            view = views[pid]
            before = _estimate(view)
            n = int(counts.get(pid, 0))
            room = SC.room(team)
            baseline_weight = .0125 + .0125 * SC.scout_q(team)
            weight = {'Prospect': .28, 'Position Group': .16, 'Baseline': baseline_weight}[kinds[pid]]
            weight *= room['looks_mult'] / (1 + .7 * n)
            room_gain = SC.cert_gain(team)
            weight = min(weight, max(0., INSEASON_CERT_MAX - SC.certainty(view)) / max(.001, room_gain))
            if weight > 0:
                # Fixed per evidence interval; a reload/toggle cannot draw again.
                rng = np.random.default_rng(stable_seed(('scouting-cross-check-v1', state['class_id'], abbr, pid, week)))
                SC.second_look(view, p, SC.error_sd(team.gm, team), rng,
                               weight=weight, R=room, team=team)
            CA.background(p, abbr, view, room, SC.error_sd(team.gm, team), n + 1)
            counts[pid] = n + 1
            batch.append(dict(year=int(league.year), week=week, pid=pid, name=p.name, pos=p.pos,
                              focus=kinds[pid],
                              before=before, after=_estimate(view), character=CA.report(view)))
        row['last_week'] = week
        _area_background(league, abbr, candidates, views, cons, SC.room(team))
        row.setdefault('focus_history', []).append(dict(week=week, group1=choice['group1'], group2=choice['group2']))
        if abbr == getattr(league, 'user_team', None):
            row.setdefault('reports', []).extend(batch)
        else:
            # CPU keeps cumulative knowledge/focus but only its latest verbose
            # report, avoiding thousands of redundant paragraphs in every save.
            row['reports'] = batch
        result[abbr] = copy.deepcopy(batch)
    if any(result.values()):
        SC.consensus(league)
    return result
