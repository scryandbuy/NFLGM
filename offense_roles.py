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
        if state is not None and rng is not None and role != 'QB':
            for rank, p in enumerate(candidates):
                gap = 0.75 if role == 'HB' and rank == 0 else 0.6 if rank == 0 else 0.3 if rank == 1 else 0.0
                if not state.cond.needs_rest(pid(p), position(p), rng,
                                            p.get('stamina_rating', 70.0), gap):
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
            if ((role == 'WR' and n >= 3 and len(own) > n and rng.random() < .23) or
                    (role == 'TE' and n == 1 and len(own) > 1 and rng.random() < .15)):
                i = n if role == 'WR' else 1
                own = list(own)
                own[n - 1], own[i] = own[i], own[n - 1]
                pools[role] = own
        for _ in range(spec[role]):
            pick(role, sources)
    return result


def field(roster, package, rng=None, state=None):
    rows = assign(roster_depth(roster), package,
                  excluded=(state.out if state is not None else ()), rng=rng, state=state)
    primary = next((p for role, p in rows if role == 'HB'), None)
    return dict(qb=next(p for role, p in rows if role == 'QB'), rb=primary,
                backs=([primary] if primary is not None else []),
                ol=[p for role, p in rows if role in OL],
                wr=[p for role, p in rows if role in ('FB', 'TE', 'WR')],
                extra_blockers=[p for role, p in rows if role in ('FB', 'TE')],
                te=[], offensive_assignments=rows)
