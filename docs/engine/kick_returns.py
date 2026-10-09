"""Return outcomes shared by kickoffs and punts; all spots face the receiving goal."""
import numpy as np
import events
from matchups import YAC

KICKOFF_CONTAIN_LEVERAGE = .15
# Breaking the first wave is possible, but full-width lanes should be rare
# with the dynamic kickoff's coverage already spread across the field.
KICKOFF_BREAKAWAY_BASE = .025
KICKOFF_BREAKAWAY_UPPER = .060

def unit(roster, state, rate, blocking=False, exclude=None):
    """Healthy coverage/return personnel from existing depth, with unique players."""
    out = getattr(state, 'out', set())
    groups = (roster.get('depth') or {}).values() if roster.get('depth') else (
        roster.get(k, []) for k in ('wr', 'te', 'backs', 'lb', 'db'))
    players = {p['pid']: p for group in groups for p in group
               if p and p.get('pid') and p['pid'] not in out and p['pid'] != exclude
               and p.get('pos') in ('WR', 'TE', 'HB', 'FB', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS')}
    weights = {'run_block_rating': .55, 'speed_rating': .45} if blocking else {
        'tackle_rating': .55, 'speed_rating': .45}
    return sorted(players.values(), key=lambda p: (-rate(p, weights), p['pid']))[:10]


def _punt_intercept(runner_speed, defender_speed, ahead, lateral, reaction=0.):
    """Distance a straight-running carrier travels before a defender can reach him.

    Coordinates are relative to the runner: positive ahead is toward the goal.
    Solve the earliest reachable point, rather than requiring a defender who
    already has leverage to win a footrace from behind. None means no intercept.
    """
    from math import sqrt
    ahead -= runner_speed * reaction
    a = runner_speed ** 2 - defender_speed ** 2
    b = -2. * ahead * runner_speed
    c = ahead ** 2 + lateral ** 2
    if c < 1e-9:
        return runner_speed * reaction
    if abs(a) < 1e-9:
        time = -c / b if b < 0 else None
    else:
        disc = b * b - 4. * a * c
        if disc < 0: return None
        roots = [t for t in ((-b - sqrt(disc)) / (2. * a), (-b + sqrt(disc)) / (2. * a)) if t >= 0]
        time = min(roots) if roots else None
    return runner_speed * (time + reaction) if time is not None else None


def _punt_breakaway(start, gained, returner, coverage, punter, safety_spot, rng, rate):
    """An initial lane, with trailing coverage, outside contain, and a punter.

    This is coarse conditional geometry, not measured player coordinates.
    Clearing the first wave does not also erase both outside contain angles.
    Faster players can pursue from behind; slower players need existing leverage.
    The longer the initial return, the more likely it has passed contain too.
    """
    import plays
    speed_weights = {'speed_rating': .8, 'accel_rating': .2}
    runner_speed = 4. + 5. * rate(returner, speed_weights)
    lead = float(np.clip(gained * .35, 2., 10.)) * float(rng.uniform(.75, 1.25))
    lane_x = float(rng.uniform(-18., 18.))
    unique = {}
    for defender in coverage:
        key = defender.get('pid') or id(defender)
        if key == returner.get('pid') or (punter and key == punter.get('pid')): continue
        unique.setdefault(key, defender)
    # Two fastest coverage players represent the first wave. The next two
    # are the outside contain players; the rest pursue through the cleared lane.
    players = sorted(unique.values(), key=lambda p: (-rate(p, speed_weights), str(p.get('pid', ''))))
    contacts = []
    for index, defender in enumerate(players):
        speed = 4. + 5. * rate(defender, speed_weights)
        pursuit = rate(defender, {'pursuit_rating': .7, 'awareness_rating': .3})
        reaction = max(0., .6 * (1. - pursuit))
        if index in (2, 3):
            leverage = 'contain'
            side = -1. if index == 2 else 1.
            lateral = abs(side * float(rng.uniform(12., 18.)) - lane_x)
            ahead = float(rng.uniform(12., 30.)) - gained
        else:
            leverage = 'trail'
            lateral = 0.
            ahead = -lead * float(np.clip(1. + .8 * (.8 - pursuit), .6, 1.4))
        travel = _punt_intercept(runner_speed, speed, ahead, lateral, reaction)
        if travel is not None and gained + travel < start:
            contacts.append((gained + travel, defender, 'coverage', leverage, ahead, lateral))
    # The punter approaches from behind the original line, retaining his own
    # speed, angle and tackle ability rather than being an automatic final stop.
    safety = punter if punter is not None else {}
    ahead = float(start) - float(safety_spot if safety_spot is not None else 20.) - gained
    speed = 4. + 5. * rate(safety, speed_weights)
    pursuit = rate(safety, {'pursuit_rating': .7, 'awareness_rating': .3})
    travel = _punt_intercept(runner_speed, speed, ahead, abs(lane_x), max(0., .6 * (1. - pursuit)))
    if travel is not None and gained + travel < start:
        contacts.append((gained + travel, safety, 'punter', 'last', ahead, abs(lane_x)))
    contacts.sort(key=lambda row: (row[0], str(row[1].get('pid', ''))))
    attack = max(rate(returner, YAC['carrier']['elusive']), rate(returner, YAC['carrier']['power']))
    attack += .30 * (rate(returner, YAC['carrier']['vision']) - .70)
    trace = []
    for contact, defender, role, leverage, ahead, lateral in contacts:
        wrap = rate(defender, YAC['tackler']['wrap'])
        broken = rng.random() <= plays.logistic(plays.edge(attack, wrap) - .230, k=7.)
        trace.append(dict(pid=defender.get('pid'), role=role, leverage=leverage,
                          ahead=round(ahead, 1), lateral=round(lateral, 1),
                          at=round(contact, 1), missed=bool(broken)))
        if not broken:
            yards = min(float(start), contact + max(0., float(rng.normal(.9, .8))))
            return dict(yards=yards, tackler=defender, contacts=trace)
    return dict(yards=float(start), tackler=None, contacts=trace)


def _kickoff_breakaway(start, gained, returner, coverage, kicker, rng, rate):
    """Coarse lane geometry, not tracked coordinates: trailing wave, two
    outside contain players and the actual kicker. Contact requires an intercept.
    Dynamic-kickoff coverage starts at the receiving 40; outside players can
    retain leverage while the returner clears the inside wave.
    """
    import plays
    weights = {'speed_rating': .8, 'accel_rating': .2}
    runner_speed = 4. + 5. * rate(returner, weights)
    lane = float(rng.uniform(-18., 18.))
    lead = float(np.clip(gained * .35, 2., 10.))
    unique = {p.get('pid') or id(p): p for p in coverage
              if p.get('pid') != returner.get('pid') and
              (not kicker or p.get('pid') != kicker.get('pid'))}
    players = sorted(unique.values(), key=lambda p: (-rate(p, weights), str(p.get('pid', ''))))
    contacts = []
    for index, defender in enumerate(players):
        contain = index in (2, 3)
        ahead = float(rng.uniform(25., 40.)) - gained if contain else -lead
        lateral = abs((-1. if index == 2 else 1.) * 18. - lane) if contain else 0.
        contacts.append((defender, 'coverage', 'contain' if contain else 'trail', ahead, lateral))
    if kicker:
        contacts.append((kicker, 'kicker', 'last', start - 35. - gained, abs(lane)))
    reachable = []
    trace = []
    for defender, role, leverage, ahead, lateral in contacts:
        speed = 4. + 5. * rate(defender, weights)
        reaction = max(0., .6 * (1. - rate(defender, {'pursuit_rating': .7, 'awareness_rating': .3})))
        travel = _punt_intercept(runner_speed, speed, ahead, lateral, reaction)
        record = dict(pid=defender.get('pid'), role=role, leverage=leverage,
                      ahead=round(ahead, 1), lateral=round(lateral, 1), reachable=False)
        if travel is None or gained + travel >= start:
            trace.append(record)
        else:
            record.update(reachable=True, at=round(gained + travel, 1))
            reachable.append((gained + travel, defender, record))
    attack = max(rate(returner, YAC['carrier']['elusive']), rate(returner, YAC['carrier']['power']))
    attack += .30 * (rate(returner, YAC['carrier']['vision']) - .70)
    for contact, defender, record in sorted(reachable, key=lambda row: (row[0], str(row[1].get('pid', '')))):
        wrap = rate(defender, YAC['tackler']['wrap'])
        if record['leverage'] == 'contain':
            # A defender holding the outside lane can force the runner toward
            # help even when the returner has the better open-field skill.
            wrap = min(1., wrap + KICKOFF_CONTAIN_LEVERAGE)
        missed = rng.random() <= plays.logistic(plays.edge(attack, wrap) - .230, k=7.)
        record['missed'] = bool(missed)
        trace.append(record)
        if not missed:
            return dict(yards=min(float(start), contact + max(0., float(rng.normal(.9, .8)))),
                        tackler=defender, contacts=trace)
    return dict(yards=float(start), tackler=None, contacts=trace)


def resolve(start, distance, returner, rng, rate, coverage=(), blockers=(), event='kick_return', weather=1.,
            punt_safety=None, punt_safety_spot=None, kickoff_safety=None):
    """Resolve legal return yards, a potential fumble, and the end-zone boundary.

    start is the receiving team's yards to goal. Existing event-specific
    fumble rates include unforced handling errors as well as contact fumbles.
    Missing unit context is neutral for standalone/legacy callers.
    """
    coverage = list(coverage); blockers = list(blockers)
    cov = np.mean([rate(p, {'tackle_rating': .55, 'speed_rating': .45}) for p in coverage]) if coverage else .70
    block = np.mean([rate(p, {'run_block_rating': .55, 'speed_rating': .45}) for p in blockers]) if blockers else .70
    gain = min(float(start), max(0., float(distance) * float(np.clip(1 + .40 * (block - cov), .85, 1.15))))
    # Clearing a punt lane leaves outside contain to beat. A kickoff lane
    # also has to open before pursuit and containment decide the return.
    breakout = False
    punt_chase = None
    kickoff_chase = None
    if returner and coverage and 12 <= gain < start:
        skill = rate(returner, {'kick_ret_rating': .5, 'bcv_rating': .25, 'accel_rating': .25})
        base, upper = ((.080, .140) if event == 'punt_return' else
                       (KICKOFF_BREAKAWAY_BASE, KICKOFF_BREAKAWAY_UPPER))
        chance = float(np.clip(base + .12 * (skill - .8) + .15 * (block - cov), .008, upper))
        if rng.random() < chance:
            if event == 'punt_return':
                chase = _punt_breakaway(start, gain, returner, coverage, punt_safety, punt_safety_spot, rng, rate)
                punt_chase = chase
            else:
                chase = _kickoff_breakaway(start, gain, returner, coverage, kickoff_safety, rng, rate)
                kickoff_chase = chase
            gain = chase['yards']
            breakout = True
    # Pick the coverage player making contact before testing his impact.
    # Speed/tackling still govern return distance; impact governs ball security.
    tackler = coverage[int(rng.integers(len(coverage)))] if coverage else None
    if punt_chase is not None and punt_chase['tackler'] is not None:
        tackler = punt_chase['tackler']
    if kickoff_chase is not None and kickoff_chase['tackler'] is not None:
        tackler = kickoff_chase['tackler']
    impact = rate(tackler, YAC['tackler']['impact']) if tackler is not None else .70
    fum = events.fumble_check(returner, event, rng, rate, hit_power=impact, env_mult=weather) if returner else None
    result = dict(returner=returner.get('pid'), return_start=float(start), fumble=False, fumble_lost=False,
                  breakaway_opportunity=breakout)
    if punt_chase is not None:
        result['punt_pursuit'] = punt_chase['contacts']
    if kickoff_chase is not None:
        result['kickoff_pursuit'] = kickoff_chase['contacts']
    if fum:
        # Unforced handling errors occur at the catch. A contact fumble must
        # happen before crossing the goal; no fumble after a touchdown.
        gain = gain * float(rng.uniform(.15, .85)) if fum.get('forced') else 0.
        tackler = tackler or {}
        lost = bool(fum['lost'])
        result.update(fumble=True, fumble_lost=lost, fumble_by=returner.get('pid'),
                      fumble_forced=bool(fum.get('forced')), tackler=tackler.get('pid'))
        if lost: result['recoverer'] = tackler.get('pid')
    gain = round(gain, 1)
    spot = max(0., round(float(start) - gain, 1))
    result.update(ret=gain, display_ret=int(round(gain)), new_yardline=spot,
                  touchdown=spot == 0 and not result['fumble_lost'])
    return result


def enforce_return_flag(result, flag):
    """A return foul is measured from a modeled spot during the return.

    Once the kicking team recovers, decline a receiving-team foul and keep
    possession. An accepted return foul erases a return touchdown.
    """
    if not flag: return
    import penalty_players as PP
    if result.get('fumble_lost'):
        if result.get('declined_penalty'):
            result.setdefault('other_declined_penalties', []).append(result['declined_penalty'])
        result['declined_penalty'] = PP.decision(flag, False)
        return
    spot = max(result['new_yardline'], result.get('return_start', result['new_yardline']) - result.get('ret', 0) / 2)
    walk = min(float(flag['yards']), (100 - spot) / 2)
    result['ret'] = round(max(0., result.get('return_start', spot) - spot), 1)
    result['display_ret'] = int(round(result['ret']))
    result['new_yardline'] = min(99., spot + walk)
    result['touchdown'] = False
    result['penalty'] = PP.decision(dict(flag, yards=walk), True)


def book_return(book, kind, result):
    if book is None: return
    book.special(kind, result.get('returner'), ret=result.get('ret', 0), touchdown=result.get('touchdown'))
    if result.get('fumble'):
        book.record_fumble(result)
        if result.get('fumble_lost') and result.get('recoverer'):
            book._get(result['recoverer'])['fum_rec'] += 1
