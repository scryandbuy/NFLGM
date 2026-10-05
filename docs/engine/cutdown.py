"""
CUT-DOWN TO 53.

roster_construction was built and never called once, and almost every open
roster problem traced back to that: clubs finished an offseason with 47 men
and a minimum of 14, one club a year ended over the cap with nothing left to
move, and a team with seventeen players had no mechanism forcing it to go and
find thirty-six more.

WHAT THE ENGINE ALREADY DOES, and why it is worth using rather than writing a
simpler version:

  POSITIONAL MINIMUMS ARE NOT NEGOTIABLE. You cannot dress two offensive
  linemen because they happened to grade out below a fourth tight end.

  GROUP MINIMUMS BIND TOO. The per-position floors sum to five offensive
  linemen and no club in football carries fewer than nine, because five means
  one injury ends your game.

  EVERY OTHER SPOT COMPETES ON MARGINAL VALUE. A fourth receiver on a team
  with three good ones is worth less than a second corner on a team with one,
  and slot_value prices that directly - so the 53rd man is chosen against
  what the roster already has rather than by rating.

The output is a real shape: 2 QB, 3 HB, 7 WR, 4 TE, 9 OL, 11 DL, 4 LB, 10 DB
and 3 specialists.

CUTS COST MONEY, and that is the point of doing this after free agency rather
than before. Releasing a man accelerates his remaining signing bonus onto this
year's cap, so a club that overspent in March pays for it in August - which is
exactly when real teams discover the same thing.
"""
import numpy as np

import contracts as CT
import valuation as VAL

ROSTER_LIMIT = 53

# How deep a real 53 goes at each spot, from what roster_construction itself
# produces: 2 QB, 3 HB, 7 WR, 4 TE, 9 OL, 11 DL, 4 LB, 10 DB, 3 specialists.
POS_CAP = {'QB': 3, 'HB': 4, 'FB': 2, 'WR': 7, 'TE': 4,
           'LT': 3, 'LG': 3, 'C': 3, 'RG': 3, 'RT': 3,
           'LEDG': 4, 'REDG': 4, 'DT': 5,
           'MIKE': 3, 'WILL': 3, 'SAM': 3,
           'CB': 6, 'FS': 3, 'SS': 3, 'K': 1, 'P': 1, 'LS': 1}


def rows_for(team):
    """The shape roster_construction wants."""
    return [dict(pos=p.pos, ovr=p.ovr, pid=p.pid, name=p.name, dead=float(p.dead_if_cut(0)) if p.contract else 0.0, age=float(p.age))
            for p in team.active()]


def trim_specialists_for_team(league, team):
    """Release affordable healthy duplicate specialists on one CPU roster.

    Keep the best specialist and actual injury cover; do not take roster
    control from the user or discard protected investments.
    """
    import practice_squad as PS
    if team.abbr == getattr(league, 'user_team', None): return []
    cuts = []
    for pos in ('K', 'P', 'LS'):
        healthy = sorted((p for p in team.active() if p.pos == pos and p.out_until is None),
                         key=lambda p: (-p.ovr, p.pid))
        for p in healthy[1:]:
            if PS.locked(p, league.week) or PS.protected(team, p, league):
                continue
            saved, _, _ = CT.savings_if_cut(p, league.post_june1())
            if team.cap_space + saved < -.0005:
                continue
            league.release(p.pid)
            team.sync_cap()
            cuts.append((team.abbr, p))
    return cuts


def trim_specialists(league):
    """Run duplicate-specialist cleanup for each CPU team at cutdown."""
    return [cut for team in league.teams.values()
            for cut in trim_specialists_for_team(league, team)]


def run(league, rng, verbose=False):
    """
    Every club to 53. Surplus players are released and reach the market.
    """
    import roster_needs as RN
    cuts, short = [], []
    for abbr, team in league.teams.items():
        # Session.blocking requires the user to make his own roster moves.
        if abbr == getattr(league, 'user_team', None): continue
        pool = rows_for(team)
        if len(pool) <= ROSTER_LIMIT:
            # Not a cut-down problem - he is SHORT, which free agency should
            # have solved and could not afford to.
            if len(pool) < ROSTER_LIMIT:
                short.append((abbr, len(pool)))
            continue
        kept = RN.select_cutdown(team, pool, ROSTER_LIMIT)
        for p in list(team.active()):
            if p.pid in kept:
                continue
            league.release(p.pid)
            cuts.append((abbr, p))
        team.sync_cap()

    # Cutting accelerates signing bonus, so a club can go over doing it - and
    # it must end with room for the men it still owes, not merely a positive
    # number.
    CT.enforce(league, rng, verbose, target=0.0, roster_target=ROSTER_LIMIT)

    if verbose:
        sizes = np.array([len(t.active()) for t in league.teams.values()])
        sp = np.array([t.cap_space for t in league.teams.values()])
        print(f'  {len(cuts)} cut to the limit | rosters min {sizes.min()} '
              f'mean {sizes.mean():.0f} max {sizes.max()} | '
              f'{len(short)} clubs short of 53 | over the cap {(sp < 0).sum()}')
    return cuts, short


def _sources(team, report, week=None):
    import roster_needs as RN
    import practice_squad as PS
    shortages = PS.essential_depth(team, week=week)['shortages']
    return ({pos for role, eligible in RN.role_slots(team)
             if role in report['uncovered'] for pos in eligible}
            | {pos for pos in POS_CAP if PS.GROUP_OF.get(pos, pos) in shortages})


def _replacement_pool(league, team, sources, essential=False, *, comps=None, only_sources=False):
    import practice_squad as PS
    import valuation as VAL
    from replacement_contracts import minimum_acceptance
    if comps is None: comps = VAL.pool_from_league(league)
    pool = [p for p in PS.available_free_agents(league)
            if (not only_sources or p.pos in sources)
            and minimum_acceptance(league, team, p, pool=comps)['accepts']] + [p for p in PS.squad(team)
            if not p.retired and p.out_until is None and (not only_sources or p.pos in sources)]
    # Search other squads for an otherwise unavailable starting role, not
    # simply to churn another club's developmental depth into our bench.
    absent = sources if essential else sources - {p.pos for p in pool}
    pool += [p for other in league.teams.values() if other is not team
             for p in PS.squad(other) if p.pos in absent
             and not p.retired and p.out_until is None]
    return pool


def _sign_replacement(league, team, player, contract, *, consent=False, comps=None):
    import practice_squad as PS
    if player.team == team.abbr:
        return PS.call_up(league, team.abbr, player.pid)
    if player.team:
        return PS.poach(league, team.abbr, player.pid, league.week)
    from replacement_contracts import minimum_acceptance
    if player not in PS.available_free_agents(league): return False
    if not consent and not minimum_acceptance(league, team, player, pool=comps)['accepts']: return False
    league.sign(player.pid, team.abbr, contract)
    return True


def _convert_long_snapper(league, team, report):
    """Last resort: train a reserve center/TE using the normal position tax.

    A legacy league can have fewer nonretired long snappers than clubs. Keep
    every required assignment and use existing ability, never create a player
    or alter his ratings to make the numbers fit.
    """
    import copy
    import roster_needs as RN
    import position_change as PC
    if 'LS' not in report['uncovered']: return False
    used = {row['player'].pid for row in report['package_assignments']
            if row['player'] is not None and row['weight'] >= .1}
    candidates = []
    for p in team.active():
        if p.pos not in ('C', 'TE') or p.pid in used or p.out_until is not None: continue
        if p.score_at('LS') - PC.COST['different'][0] < 50: continue
        trial = copy.copy(p)
        trial.pos = 'LS'
        after = RN.assess(team, [trial if q is p else q for q in team.active()])
        if len(after['uncovered']) >= len(report['uncovered']): continue
        candidates.append((after['score'] - RN.retention_value(team, p), p))
    if not candidates: return False
    _, p = max(candidates, key=lambda item: item[0])
    PC.change_position(league, p.pid, 'LS')
    return True


def _cross_train_kicker(league, team, report, reserve=0.0):
    """A depleted kicker market can use a real punter with place-kicking skill.

    Use the normal position-change penalty, contracts and waivers. Never take
    another team's active player or a future draft prospect out of his pool.
    The existing starting punter must still have a job after this move.
    """
    import copy
    from types import SimpleNamespace
    import roster_needs as RN
    import practice_squad as PS
    import position_change as PC
    from cap_accounting import require_room
    if team.abbr == getattr(league, 'user_team', None) or 'K' not in report['uncovered']:
        return False
    if any(p.pos == 'K' for p in _replacement_pool(league, team, {'K'}, only_sources=True)):
        return False  # Exhaust normal kicker signings/poaches first.
    active = team.active()
    starters = {row['player'].pid for row in report['assignments'] if row['player'] is not None}
    recent = {row.get('pid') for row in league.transactions
              if row.get('year') == league.year and row.get('team') == team.abbr
              and row.get('kind') in ('sign', 'ps_callup', 'ps_poach')
              and 0 <= int(league.week or 0) - int(row.get('week') or 0) <= 3}
    pool = [p for p in active + _replacement_pool(league, team, {'P'}, only_sources=True)
            if p.pos == 'P' and not p.retired and p.out_until is None]
    best = None
    for p in pool:
        if p in active and p.pid in starters:
            continue
        trial = copy.copy(p)
        trial.team = team.abbr
        proxy = SimpleNamespace(player=lambda pid: trial, teams=league.teams)
        PC.change_position(proxy, p.pid, 'K', log=False)
        ratings = PC.effective_ratings(trial)
        # Require actual accuracy/power, including the learning penalty. A
        # strong leg alone cannot qualify a punter to fill the kicker slot.
        if (ratings.get('kick_acc_rating', 0) < 65
                or ratings.get('kick_power_rating', 0) < 70 or trial.ovr < 70):
            continue
        contract = None if p in active else PS.minimum_contract(league, team, p)
        departures = [None] if p in active or len(active) < ROSTER_LIMIT else [q for q in active
            if q.pid not in starters and q.pid not in recent and q.pos != 'QB'
            and q.out_until is None and not PS.locked(q, league.week)
            and not PS.protected(team, q, league)]
        for q in departures:
            after = RN.assess(team, [trial if r is p else r for r in active if r is not q]
                              + ([] if p in active else [trial]))
            if (len(after['uncovered']) >= len(report['uncovered'])
                    or set(after['uncovered']) - set(report['uncovered'])):
                continue
            dead = 0.0
            if contract is not None:
                saved = 0.0
                if q is not None:
                    saved, dead, _ = CT.savings_if_cut(q, league.post_june1())
                if team.cap_space + saved - contract.cap_hit(0) + .0005 < reserve: continue
                try: require_room(league, team, p.pid, contract, release_pid=q.pid if q else None)
                except ValueError: continue
            loss = (RN.departure_loss(team, q, report) + RN.retention_value(team, q)) if q else 0.0
            key = (p in active, trial.ovr, -loss-dead)
            if best is None or key > best[0]: best = (key, p, q, contract)
    if best is None: return False
    _, p, q, contract = best
    from replacement_contracts import minimum_acceptance
    if contract is not None and not minimum_acceptance(league, team, p)['accepts']:
        return False
    if q:
        league.release(q.pid)
    if contract is not None:
        if not _sign_replacement(league, team, p, contract, consent=True):
            raise RuntimeError('Validated kicker replacement became unavailable')
    PC.change_position(league, p.pid, 'K')
    team.sync_cap()
    return True


def fill_short(league, rng, verbose=False):
    """Fund every vacant spot; cover starting jobs before optional depth."""
    import roster_needs as RN
    import practice_squad as PS
    import min_salary as MS
    from cap_engine import CAP
    from cap_accounting import require_room
    signed = 0
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None): continue
        while len(team.active()) < ROSTER_LIMIT:
            report = RN.assess(team)
            remaining = ROSTER_LIMIT - len(team.active()) - 1
            # Preserve minimum funding for every spot still open after signing.
            reserve = remaining * MS.minimum_salary(0, CAP.get(league.year, 301.2)) * max(0,18-team.cap.paid_week)/18
            before = len(team.active())
            if _cross_train_kicker(league, team, report, reserve=reserve):
                signed += len(team.active()) - before
                continue
            sources = _sources(team, report, league.week)
            pool = _replacement_pool(league, team, sources)
            pool = [p for p in pool if len(team.by_pos(p.pos)) < POS_CAP.get(p.pos, 4)]
            pool.sort(key=lambda p: (p.pos in sources,
                      p.ovr + 25 * report['needs'].get(p.pos, 0)), reverse=True)
            pick = None
            for p in pool:
                contract = PS.minimum_contract(league, team, p)
                if team.cap_space - contract.cap_hit(0) + .0005 < reserve: continue
                try: require_room(league, team, p.pid, contract)
                except ValueError: continue
                pick = p
                break
            if pick is None: break
            if not _sign_replacement(league, team, pick, contract): break
            team.sync_cap()
            signed += 1
    return signed


def _cross_train_line(league, team, report):
    """Fill a missing native OL role from the club's own qualified surplus."""
    import copy
    from types import SimpleNamespace
    import offense_roles as OR
    import roster_needs as RN
    import position_change as PC
    if team.abbr == getattr(league, 'user_team', None): return False
    active = team.active()
    coverage = RN.essential_coverage(team, report=report)
    native_starters = {r['player'].pid for r in report['assignments']
                       if r['role'] in OR.OL and r['player'] is not None and r['player'].pos == r['role']}
    missing = {r['role'] for r in report['package_assignments']
               if r['role'] in OR.OL and (r['player'] is None or r['player'].pos != r['role'])}
    best = None
    for pos in sorted(missing):
        for p in active:
            if (p.pos not in OR.OL or p.pos == pos or p.out_until is not None
                    or p.pid in native_starters): continue
            trial = copy.copy(p)
            PC.change_position(SimpleNamespace(player=lambda _: trial, teams=league.teams), p.pid, pos, log=False)
            if trial.ovr < 55: continue
            after = RN.assess(team, [trial if q is p else q for q in active])
            next_coverage = RN.essential_coverage(team, report=after)
            if not RN.coverage_not_worse(coverage, next_coverage): continue
            improvement = sum(coverage['shortages'].values()) - sum(next_coverage['shortages'].values())
            if improvement <= 0: continue
            key = (improvement, after['score'])
            if best is None or key > best[0]: best = (key, p, pos)
    if best is None: return False
    _, p, pos = best
    PC.change_position(league, p.pid, pos)
    return True


def _market_kicker_recovery(league, team, report):
    """An empty kicker job can pay a willing street specialist above minimum.

    Try native kickers before qualified punters. Every offer funds its actual
    price and departure, preserves the punter and healthy depth, and applies
    the normal learning penalty when changing positions.
    """
    import copy
    from types import SimpleNamespace
    import practice_squad as PS
    import roster_needs as RN
    import position_change as PC
    from cap_accounting import require_room
    from replacement_contracts import minimum_acceptance
    if team.abbr == getattr(league, 'user_team', None) or 'K' not in report['uncovered']: return False
    active = team.active()
    coverage = RN.essential_coverage(team, report=report)
    depth = PS.essential_depth(team, active, league.week)['shortages']
    comps = VAL.pool_from_league(league)
    best = None
    for p in PS.available_free_agents(league):
        if p.pos not in ('K', 'P'): continue
        consent = minimum_acceptance(league, team, p, pool=comps)
        if consent['reason'] == 'recent_release': continue
        # At his own one-year reservation ask, the equal-cash comparison used
        # by minimum_acceptance is acceptable. Do not force a minimum deal.
        salary = max(float(consent.get('annual_offer', 0)), float(consent.get('annual_ask', 0)))
        if salary <= 0: continue
        contract = PS.minimum_contract(league, team, p)
        contract.base[0] = salary * max(0, 18-team.cap.paid_week)/18
        trial = copy.copy(p)
        if p.pos == 'P':
            PC.change_position(SimpleNamespace(player=lambda _: trial, teams=league.teams), p.pid, 'K', log=False)
            ratings = PC.effective_ratings(trial)
            if (ratings.get('kick_acc_rating', 0) < 65 or ratings.get('kick_power_rating', 0) < 70
                    or trial.ovr < 70): continue
        for q in active:
            if q.out_until is not None or PS.locked(q, league.week) or PS.protected(team, q, league, incoming=trial): continue
            proposed = [r for r in active if r is not q] + [trial]
            next_depth = PS.essential_depth(team, proposed, league.week)['shortages']
            if any(n > depth.get(g, 0) for g, n in next_depth.items()): continue
            try: require_room(league, team, p.pid, contract, release_pid=q.pid)
            except ValueError: continue
            after = RN.assess(team, proposed)
            next_coverage = RN.essential_coverage(team, report=after)
            if not RN.coverage_not_worse(coverage, next_coverage): continue
            if 'K' in after['uncovered']: continue
            if not PS._cpu_move_budget(league, team, trial, contract, q, essential=True): continue
            _, dead, _ = CT.savings_if_cut(q, league.post_june1())
            key = (p.pos == 'K', after['score']-dead-RN.retention_value(team, q), -contract.cap_hit(0))
            if best is None or key > best[0]: best = (key, p, q, contract)
    if best is None: return False
    _, p, q, contract = best
    league.release(q.pid)
    if not _sign_replacement(league, team, p, contract, consent=True):
        raise RuntimeError('Validated specialist recovery became unavailable')
    if p.pos != 'K': PC.change_position(league, p.pid, 'K')
    team.sync_cap()
    return True


def repair_shape(league):
    """Swap genuine surplus for a missing job without creating another hole."""
    import roster_needs as RN
    import practice_squad as PS
    from cap_accounting import require_room
    fixed = 0
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None): continue
        for _ in range(ROSTER_LIMIT):
            report = RN.assess(team)
            coverage = RN.essential_coverage(team, report=report)
            if not coverage['shortages'] or len(team.active()) != ROSTER_LIMIT: break
            sources = _sources(team, report, league.week) | {pos for eligible in coverage['sources'].values() for pos in eligible}
            pool = _replacement_pool(league, team, sources, only_sources=True)
            if not any(p.pos == 'LS' for p in pool) and _convert_long_snapper(league, team, report):
                fixed += 1
                continue
            candidates = [p for pos in sorted(sources) for p in sorted(
                (q for q in pool if q.pos == pos), key=lambda q: -q.ovr)[:4]]
            prepared = RN.assessment_inputs(team, list(team.active()) + candidates)
            best = None
            for p in candidates:
                contract = PS.minimum_contract(league, team, p)
                for q in team.active():
                    if PS.locked(q, league.week) or PS.protected(team, q, league, incoming=p): continue
                    saved, dead, _ = CT.savings_if_cut(q, league.post_june1())
                    if team.cap_space + saved - contract.cap_hit(0) < -.0005: continue
                    try: require_room(league, team, p.pid, contract, release_pid=q.pid)
                    except ValueError: continue
                    after = RN.assess(team, [r for r in team.active() if r is not q] + [p], prepared=prepared)
                    next_coverage = RN.essential_coverage(team, report=after)
                    if not RN.coverage_not_worse(coverage, next_coverage): continue
                    improvement = sum(coverage['shortages'].values()) - sum(next_coverage['shortages'].values())
                    if improvement <= 1e-9: continue
                    gain = after['score'] - report['score'] - dead - RN.retention_value(team, q)
                    if gain <= 0: continue
                    key = (improvement, gain)
                    if best is None or key > best[0]: best = (key, p, q, contract)
            if best is None:
                if (_cross_train_line(league, team, report)
                        or _cross_train_kicker(league, team, report)
                        or _market_kicker_recovery(league, team, report)):
                    fixed += 1
                    continue
                break
            _, p, q, contract = best
            from replacement_contracts import minimum_acceptance
            if not minimum_acceptance(league, team, p)['accepts']: break
            league.release(q.pid)
            if not _sign_replacement(league, team, p, contract, consent=True):
                raise RuntimeError('Validated roster replacement became unavailable')
            team.sync_cap()
            fixed += 1
    return fixed


def repair_depth(league):
    """Fund essential backups with a net improvement, including full camp rosters.

    Use the same prepared move as weekly repairs: price and approve the exact
    departure before releasing anyone, then recompute actual depth after arrival.
    """
    import practice_squad as PS
    import valuation as VAL
    comps = VAL.pool_from_league(league)
    fixed = 0
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None): continue
        for _ in range(ROSTER_LIMIT):
            before = PS.essential_depth(team, week=league.week)['shortages']
            if not before: break
            sources = {pos for pos in POS_CAP if PS.GROUP_OF.get(pos, pos) in before}
            pool = sorted(_replacement_pool(league, team, sources, essential=True, comps=comps, only_sources=True),
                          key=lambda p: (not PS.minimum_fits(league, team, p, essential=True, pool=comps),
                                         bool(p.team and p.team != abbr), -p.ovr, str(p.pid)))
            moved = False
            for p in pool:
                if p.pos not in sources: continue
                if p.team == abbr:
                    moved = PS.call_up(league, abbr, p.pid, emergency=True)
                elif p.team:
                    moved = PS.poach(league, abbr, p.pid, league.week, essential=True)
                else:
                    moved = PS.sign_minimum(league, abbr, p, essential=True, pool=comps)
                if moved:
                    after = PS.essential_depth(team, week=league.week)['shortages']
                    if sum(after.values()) >= sum(before.values()):
                        raise RuntimeError('Roster depth repair did not improve actual coverage')
                    fixed += 1
                    break
            if not moved: break
    return fixed


def violations(league):
    """Final CPU season-opening constraints, independent of the user's choices."""
    import roster_needs as RN
    import practice_squad as PS
    problems = []
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None): continue
        team.sync_cap()
        report = RN.assess(team)
        missing = report['uncovered']
        essential = {k: v for k, v in RN.essential_coverage(team, report=report)['shortages'].items() if v >= 1.0}
        depth = PS.essential_depth(team, week=league.week)['shortages']
        if len(team.active()) != ROSTER_LIMIT or team.cap_space < -.0005 or missing or depth or essential:
            problems.append(dict(team=abbr, size=len(team.active()),
                                 cap=round(team.cap_space, 3), missing=list(missing), depth=depth, essential=essential))
    return problems


def emergency_fill(league, rng, verbose=False):
    """Compatibility entry point: urgency never waives cap accounting."""
    CT.enforce(league, rng, roster_target=ROSTER_LIMIT, target=0.0)
    return fill_short(league, rng, verbose)


@VAL.comparison_batch()
def finalize(league, rng, verbose=False, passes=3):
    """Resolve roster size, replacement funding and starting roles together.

    Leave an impossible state visible for the calendar gate; never manufacture
    cap room or sign replacements on an unfunded emergency exception.
    """
    # Batch and interactive callers must both price all 53, while the league
    # calendar still controls the offseason post-June 1 departure treatment.
    for team in league.teams.values(): team.phase = 'season'
    total_cut, total_signed = trim_specialists(league), 0
    for _ in range(passes):
        transaction_count = len(getattr(league, 'transactions', ()))
        cuts, _ = run(league, rng)
        total_cut += cuts
        signed = fill_short(league, rng)
        total_signed += signed
        shape = repair_shape(league)
        depth = repair_depth(league)
        if not violations(league): break
        # These searches are deterministic. Repeating an unchanged, failed
        # pass cannot find a new solution; leave its violations for the gate.
        if (not cuts and not signed and not shape and not depth
                and len(getattr(league, 'transactions', ())) == transaction_count):
            break
    if verbose:
        print(f'  {len(total_cut)} cut, {total_signed} signed; unresolved: {violations(league)}')
    return total_cut, total_signed


if __name__ == '__main__':
    import league as LG, season as SN, retirement as RT
    import regression as RG, tags as TG, market as MK
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)
    L.roll_year(rng)
    L.advance_contracts()
    CT.run(L, rng)
    CT.enforce(L, rng)
    TG.run(L, rng)
    CT.enforce(L, rng)
    MK.run(L, rng)
    sizes = np.array([len(t.active()) for t in L.teams.values()])
    print(f'before cut-down: rosters min {sizes.min()} mean {sizes.mean():.0f} '
          f'max {sizes.max()}')
    finalize(L, rng, verbose=True)
    import collections
    t = L.teams['KC']
    GRP = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
           'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL', 'MIKE': 'LB', 'WILL': 'LB',
           'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'K': 'ST',
           'P': 'ST', 'LS': 'ST'}
    print('\nKC final roster:',
          dict(collections.Counter(GRP.get(p.pos, p.pos) for p in t.active())))
