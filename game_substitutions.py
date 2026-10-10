"""Possession-level rest choices. Original depth charts and injury status stay intact."""
import math
import targets

STARTERS = {'QB': 1, 'HB': 1, 'WR': 2, 'TE': 1, 'LEDG': 1, 'REDG': 1,
            'DT': 2, 'MIKE': 1, 'WILL': 1, 'SAM': 1, 'CB': 2, 'FS': 1, 'SS': 1}


def opportunity(seconds, margin, playoffs=False):
    from late_game import rest_opportunity
    return rest_opportunity(seconds, margin, playoffs)


def rest_probability(starter, reserve, pos, state, chance):
    coach = getattr(state, 'coach', {}) or {}
    caution = float(coach.get('starter_protection', .5))
    age = starter.get('age')
    young = age is not None and float(age) <= 25
    condition = state.cond.get(starter['pid'])
    gap = max(0., targets.position_score(starter, pos) - targets.position_score(reserve, pos))
    # Experience still matters for a young starter; a weak reserve makes a
    # coach less willing to remove him. Neither uses hidden potential.
    willingness = .60 + .35 * caution - (.30 if young else 0.)
    willingness += min(.20, max(0., 85. - condition) / 100.)
    willingness -= min(.25, max(0., gap - 12.) / 60.)
    return max(0., min(.98, chance * willingness))


def season_probability(starter, reserve, pos, state, seconds, playoffs=False):
    """Optional late-season opportunities, using visible age and current ability."""
    context = getattr(state, 'season_rest', {}) or {}
    mode = context.get('mode')
    if playoffs or context.get('week', 0) < 15 or mode not in ('locked', 'eliminated'):
        return 0.
    age, reserve_age = starter.get('age'), reserve.get('age')
    if age is None or reserve_age is None:
        return 0.
    gap = max(0., targets.position_score(starter, pos) - targets.position_score(reserve, pos))
    if gap > 22 or state.cond.get(reserve['pid']) < 75:
        return 0.
    caution = max(0., min(1., float((getattr(state, 'coach', {}) or {}).get('starter_protection', .5))))
    tired = max(0., 90. - state.cond.get(starter['pid'])) / 100.
    if mode == 'eliminated':
        # Developing an established young starter remains valuable. No hidden
        # ceiling or development trait is used to select a replacement.
        if age <= 26 or reserve_age > 25 or reserve_age >= age or gap > 15:
            return 0.
        base = .18 + .22 * caution + min(.15, tired)
        # Give the veteran the opening half; evaluate reserves thereafter.
        phase = 0. if seconds > 1800 else (.65 if seconds > 900 else 1.)
    else:
        base = .40 + .35 * caution + min(.15, tired)
        if age <= 25:
            base *= .45
        phase = .30 if seconds > 2700 else (.65 if seconds > 1800 else 1.)
    readiness = max(.25, 1. - max(0., gap - 5.) / 22.)
    return min(.95, base * phase * readiness)


def for_possession(roster, state, seconds, margin, rng, playoffs=False):
    if state is None or getattr(state, 'engine_version', 2) < 2: return roster
    chance = opportunity(seconds, margin, playoffs)
    rested = set()
    promoted = {}
    depth = roster.get('depth') or {}
    draws = getattr(state, 'rest_draws', None)
    if draws is None: state.rest_draws = draws = {}
    season_active = not playoffs and (getattr(state, 'season_rest', {}) or {}).get('mode') in ('locked', 'eliminated')
    if chance or season_active:
        for pos, count in STARTERS.items():
            men = [p for p in depth.get(pos, []) if p['pid'] not in state.out]
            reserves = [p for p in men[count:] if state.cond.get(p['pid']) >= 65]
            for starter, reserve in zip(men[:count], reserves):
                pid = starter['pid']
                if pid not in draws: draws[pid] = float(rng.random())
                if draws[pid] < max(rest_probability(starter, reserve, pos, state, chance),
                                    season_probability(starter, reserve, pos, state, seconds, playoffs)):
                    rested.add(pid)
                    promoted.setdefault(pos, set()).add(reserve['pid'])
    state.resting_starters = rested
    if not rested: return roster
    # Keep everyone available as an emergency replacement. Rebuild the view
    # before play calling, audibles and personnel selection see the quarterback.
    import rosters
    ordered = {pos: sorted(men, key=lambda p: (p['pid'] in state.out, p['pid'] in rested, 0 if p['pid'] in promoted.get(pos, set()) else 1)) for pos, men in depth.items()}
    pins = {pos: [pid for pid in ids if pid not in rested]
            for pos, ids in (roster.get('depth_pins') or {}).items()}
    view = rosters._assemble(ordered, pins=pins, front=roster.get('front_family'))
    if view is None:
        state.resting_starters = set()
        return roster
    return dict(roster, **view)
