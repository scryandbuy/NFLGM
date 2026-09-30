"""Offensive personnel shared by the chart and game-day assignments."""

PACKAGES = {
    '11': dict(HB=1, FB=0, TE=1, WR=3),
    '12': dict(HB=1, FB=0, TE=2, WR=2),
    '13': dict(HB=1, FB=0, TE=3, WR=1),
    '21': dict(HB=1, FB=1, TE=1, WR=2),
    '22': dict(HB=1, FB=1, TE=2, WR=1),
    '10': dict(HB=1, FB=0, TE=0, WR=4),
    '00': dict(HB=0, FB=0, TE=0, WR=5),
}
OL = ('LT', 'LG', 'C', 'RG', 'RT')
OFFENSE = frozenset(('QB', 'HB', 'FB', 'TE', 'WR') + OL)


def pid(player):
    return player.get('pid') if isinstance(player, dict) else player.pid


def position(player):
    return player.get('pos') if isinstance(player, dict) else player.pos


def base_package(gm):
    key = str(getattr(gm, 'off_personnel', '11'))
    return key if key in PACKAGES else '11'


def package_weights(gm=None):
    """Normal-situation mix shared by coaching and roster planning.

    The installed base is the plurality, not a promise to use it every down.
    The play caller still adjusts these weights for personnel and situation.
    A fresh mapping prevents callers from changing the shared defaults.
    """
    keys = ('11', '12', '13', '21', '22', '10', '00')
    mixes = {
        '11': (.62, .20, .035, .065, .02, .05, .01),
        '12': (.30, .50, .10, .04, .035, .02, .005),
        '13': (.18, .28, .46, .025, .04, .01, .005),
        '21': (.25, .10, .025, .50, .10, .02, .005),
        '22': (.10, .16, .035, .23, .46, .01, .005),
        '10': (.29, .10, .015, .025, .01, .52, .04),
        '00': (.18, .04, .005, .01, .005, .25, .51),
    }
    return dict(zip(keys, mixes[base_package(gm)]))


# A fixed set of ordinary situations for roster planning. The play caller
# still makes the actual choice on each snap; these shares only estimate how
# often a job is available when the GM compares players.
_PLANNING_SITUATIONS = (
    (1, 10, 50, 0, None, .35),
    (2, 6, 45, 0, None, .23),
    (2, 15, 60, 0, None, .10),
    (3, 2, 30, 0, None, .10),
    (3, 9, 40, 0, None, .14),
    (1, 3, 4, 0, None, .04),
    (2, 10, 50, -7, 90, .02),
    (2, 4, 50, 7, 90, .02),
)


def expected_package_weights(gm, depth):
    """Expected calls for a projected roster, with the coach's intent retained.

    Use the same roster and situational adjustments as the game caller. Half
    the estimate uses neutral roster strengths so a missing TE or fourth WR
    remains a recruiting need instead of making that package disappear.
    ``depth`` contains projected player dictionaries ordered by team fit.
    """
    import identity as ID
    from plays import rate

    base = package_weights(gm)
    backs = depth.get('HB') or depth.get('FB') or []
    offensive_line = [depth[pos][0] for pos in OL if depth.get(pos)]
    projected = dict(qb=(depth.get('QB') or [None])[0],
                     rb=backs[0] if backs else None, backs=backs,
                     ol=offensive_line,
                     wr=(depth.get('WR') or [])[:6] + (depth.get('TE') or [])[:3] + backs[:1])
    identity = ID.read_identity(projected, rate)
    adjusted = ID.personnel_weights(identity, base)
    estimate = dict.fromkeys(base, 0.0)
    for down, distance, yards_to_endzone, score_diff, seconds_left, share in _PLANNING_SITUATIONS:
        for source in (base, adjusted):
            situational = ID.situational_weights(source, down, distance,
                                                 yards_to_endzone, score_diff, seconds_left)
            total = sum(situational.values())
            for package, weight in situational.items():
                estimate[package] += .5 * share * weight / total
    return estimate


def role_grade(player, role, package='11', slot=0):
    """Grade the job actually performed; extra heavy-package TEs must block."""
    if role == 'FB':
        return fullback_score(player)
    overall = float(player.get('ovr', 70) if isinstance(player, dict)
                    else getattr(player, 'ovr', 70))
    if role != 'TE' or str(package) not in ('12', '13', '22') or slot == 0:
        return overall
    ratings = player.get('ratings', player) if isinstance(player, dict) else getattr(player, 'ratings', {})
    def mean(keys):
        return sum(float(ratings.get(key, overall)) for key in keys) / len(keys)
    blocking = mean(('run_block_rating', 'impact_block_rating', 'strength_rating'))
    receiving = mean(('catch_rating', 'route_run_short_rating', 'cit_rating'))
    return .55 * overall + .30 * blocking + .15 * receiving


def fullback_score(player):
    """Blocking grade for a fullback role, including an HB or TE fill-in."""
    ratings = player if isinstance(player, dict) else getattr(player, 'ratings', {})
    if any(key in ratings for key in ('run_block_rating', 'lead_block_rating', 'impact_block_rating')):
        import targets as TG
        return TG.position_score(ratings, 'FB')
    return float(player.get('ovr', 70.0) if isinstance(player, dict)
                 else getattr(player, 'ovr', 70.0))


def roster_depth(roster):
    """Older callers can still supply the assembled groups without depth."""
    depth = {pos: list(men) for pos, men in (roster.get('depth') or {}).items() if pos in OFFENSE}
    seen = {pid(p) for men in depth.values() for p in men}
    pool = [roster.get('qb'), roster.get('rb')]
    for group in ('qbs', 'backs', 'fullbacks', 'ol', 'wr', 'extra_blockers'):
        pool.extend(roster.get(group) or [])
    for p in pool:
        if p is not None and position(p) in OFFENSE and pid(p) not in seen:
            depth.setdefault(position(p), []).append(p)
            seen.add(pid(p))
    return depth


def assign(depth, package, excluded=(), rng=None, state=None):
    """Select eleven unique players, using healthy depth for missing roles.

    With no RNG this is the chart's starting lineup. Game-day rotation can
    replace a receiver, tight end or back, but never duplicates a player.
    """
    spec = PACKAGES.get(str(package), PACKAGES['11'])
    excluded = set(excluded or ())
    pools = {}
    for pos, men in depth.items():
        pools[pos] = [p for p in men if pid(p) not in excluded and
                      (isinstance(p, dict) or p.out_until is None)]
    used, result = set(), []

    def pick(role, sources):
        slot = sum(assigned_role == role for assigned_role, _ in result)
        candidates, seen = [], set()
        # Preferred position first, then compatible emergency replacements.
        for source in sources:
            for p in pools.get(source, []):
                key = pid(p)
                if key not in used and key not in seen:
                    candidates.append(p); seen.add(key)
        if not candidates:
            candidates = [p for men in pools.values() for p in men if pid(p) not in used]
        if not candidates:
            raise ValueError('Cannot field eleven unique healthy offensive players')
        chosen = candidates[0]
        if role == 'TE' and slot > 0 and str(package) in ('12', '13', '22'):
            own = [p for p in candidates if position(p) == 'TE']
            if own:
                chosen = max(own, key=lambda p: role_grade(p, role, package, slot))
                candidates = [chosen] + [p for p in candidates if pid(p) != pid(chosen)]
        if role == 'FB' and position(chosen) != 'FB':
            # A blocking TE can be the better second back. Preserve the lead
            # TE and receivers needed later in the package when choosing one.
            remaining = {pos: sum(position(p) == pos and pid(p) not in used
                                  for p in pools.get(pos, ())) for pos in ('HB', 'TE', 'WR')}
            spare = [p for p in candidates if position(p) in remaining and
                     remaining[position(p)] > {'HB': 0, 'TE': spec['TE'],
                                                'WR': spec['WR']}[position(p)]]
            if spare:
                chosen = max(spare, key=fullback_score)
                candidates = [chosen] + [p for p in candidates if pid(p) != pid(chosen)]
        if state is not None and rng is not None and role != 'QB':
            for rank, p in enumerate(candidates):
                gap = 0.75 if role == 'HB' and rank == 0 else 0.6 if rank == 0 else 0.3 if rank == 1 else 0.0
                needs_rest = state.cond.needs_rest(pid(p), position(p), rng,
                                                   p.get('stamina_rating', 70.0), gap)
                # Keep the lead TE in both single- and multiple-TE packages.
                # In 12 personnel the first slot could otherwise pass over
                # TE1 while the second slot almost always kept TE2.
                if needs_rest and rank == 0 and slot == 0 and role == 'TE':
                    needs_rest = rng.random() >= 0.92
                # The top two wideouts should not both rotate away so often
                # that a three-WR package fields its fourth WR on half its snaps.
                if needs_rest and rank == 0 and slot < 2 and role == 'WR':
                    needs_rest = rng.random() >= 0.65
                if not needs_rest:
                    chosen = p; break
        used.add(pid(chosen)); result.append((role, chosen))

    # Keep the quarterback and offensive line out of emergency skill pools.
    pick('QB', ('QB',))
    for role in OL:
        pick(role, (role,) + tuple(pos for pos in OL if pos != role))
    for role in ('HB', 'FB', 'TE', 'WR'):
        sources = {'HB': ('HB', 'FB', 'WR', 'TE'),
                   'FB': ('FB', 'HB', 'TE', 'WR'),
                   'TE': ('TE', 'FB', 'WR', 'HB'),
                   'WR': ('WR', 'TE', 'HB', 'FB')}[role]
        # Retain the established occasional WR3 / TE1 rotation, with each
        # candidate represented once even when older assembled pools overlap.
        if rng is not None and role in ('TE', 'WR'):
            n = spec[role]
            own = pools.get(role, [])
            if ((role == 'WR' and n >= 3 and len(own) > n and rng.random() < .20) or
                    (role == 'TE' and n == 1 and len(own) > 1 and rng.random() < .05)):
                i = n if role == 'WR' else 1
                own = list(own)
                own[n - 1], own[i] = own[i], own[n - 1]
                pools[role] = own
        for _ in range(spec[role]):
            pick(role, sources)
    return result


def field(roster, package, rng=None, state=None, depth=None):
    rows = assign(depth if depth is not None else roster_depth(roster), package,
                  excluded=(state.out if state is not None else ()), rng=rng, state=state)
    primary = next((p for role, p in rows if role == 'HB'), None)
    return dict(qb=next(p for role, p in rows if role == 'QB'), rb=primary,
                backs=([primary] if primary is not None else []),
                ol=[p for role, p in rows if role in OL],
                wr=[p for role, p in rows if role in ('FB', 'TE', 'WR')],
                extra_blockers=[p for role, p in rows if role in ('FB', 'TE')],
                te=[], offensive_assignments=rows)
