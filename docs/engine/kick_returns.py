"""Return outcomes shared by kickoffs and punts; all spots face the receiving goal."""
import numpy as np
import events
from matchups import YAC


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


def _punt_breakaway(start, gained, returner, coverage, punter, safety_spot, rng, rate):
    """A cleared punt lane: trailing coverage and the punter ahead of the ball.

    Coarse pursuit geometry, not tracked coordinates. The ordinary return and
    lane draw already decide whether the first wave is cleared. Do not place
    the unit's two best tacklers back in front for two fresh YAC contests.
    Speed determines closing time; pursuit changes the trailing player's angle.
    The estimated lead is a modeling assumption, not measured tracking data.
    """
    import plays
    runner_speed = 4. + 5. * rate(returner, {'speed_rating': .8, 'accel_rating': .2})
    lead = float(np.clip(gained * .35, 2., 10.)) * float(rng.uniform(.75, 1.25))
    contacts = []
    used = set()
    for defender in coverage:
        key = defender.get('pid') or id(defender)
        if key in used or key == returner.get('pid') or (punter and key == punter.get('pid')): continue
        used.add(key)
        speed = 4. + 5. * rate(defender, {'speed_rating': .8, 'accel_rating': .2})
        closing = speed - runner_speed
        if closing <= 0: continue
        pursuit = rate(defender, {'pursuit_rating': .7, 'awareness_rating': .3})
        gap = lead * float(np.clip(1. + .8 * (.8 - pursuit), .6, 1.4))
        contact = gained + runner_speed * gap / closing
        if contact < start:
            contacts.append((contact, defender, 'coverage'))
    # The punter starts behind his coverage. Use the original line of
    # scrimmage as his coarse containment depth after the kick, not a gunner's
    # immediate contact point. Legacy callers retain a neutral last defender.
    safety = punter if punter is not None else {}
    contact = max(gained, float(start) - float(safety_spot if safety_spot is not None else 20.))
    if contact < start and (not safety.get('pid') or safety.get('pid') not in used):
        contacts.append((contact, safety, 'punter'))
    contacts.sort(key=lambda row: (row[0], str(row[1].get('pid', ''))))
    attack = max(rate(returner, YAC['carrier']['elusive']), rate(returner, YAC['carrier']['power']))
    attack += .30 * (rate(returner, YAC['carrier']['vision']) - .70)
    trace = []
    for contact, defender, role in contacts:
        wrap = rate(defender, YAC['tackler']['wrap'])
        # Same first-contact contest as the existing open-field resolver.
        # A missed defender cannot reappear as a fresh tackle later.
        broken = rng.random() <= plays.logistic(plays.edge(attack, wrap) - .230, k=7.)
        trace.append(dict(pid=defender.get('pid'), role=role, at=round(contact, 1), missed=bool(broken)))
        if not broken:
            yards = min(float(start), contact + max(0., float(rng.normal(.9, .8))))
            return dict(yards=yards, tackler=defender, contacts=trace)
    return dict(yards=float(start), tackler=None, contacts=trace)


def resolve(start, distance, returner, rng, rate, coverage=(), blockers=(), event='kick_return', weather=1.,
            punt_safety=None, punt_safety_spot=None):
    """Resolve legal return yards, a potential fumble, and the end-zone boundary.

    start is the receiving team's yards to goal. Existing event-specific
    fumble rates include unforced handling errors as well as contact fumbles.
    Missing unit context is neutral for standalone/legacy callers.
    """
    coverage = list(coverage); blockers = list(blockers)
    cov = np.mean([rate(p, {'tackle_rating': .55, 'speed_rating': .45}) for p in coverage]) if coverage else .70
    block = np.mean([rate(p, {'run_block_rating': .55, 'speed_rating': .45}) for p in blockers]) if blockers else .70
    gain = min(float(start), max(0., float(distance) * float(np.clip(1 + .40 * (block - cov), .85, 1.15))))
    # Rare lanes expose the last covering defenders. Ordinary gains stay
    # unchanged; open-field chances use the existing tackle/pursuit engine.
    breakout = False
    punt_chase = None
    if returner and coverage and 12 <= gain < start:
        skill = rate(returner, {'kick_ret_rating': .5, 'bcv_rating': .25, 'accel_rating': .25})
        chance = float(np.clip(.045 + .12 * (skill - .8) + .15 * (block - cov), .008, .09))
        if rng.random() < chance:
            if event == 'punt_return':
                chase = _punt_breakaway(start, gain, returner, coverage, punt_safety, punt_safety_spot, rng, rate)
                punt_chase = chase
            else:
                import plays
                pursuers = sorted(coverage, key=lambda p: -rate(p, YAC['tackler']['angle']))[:2]
                chase = plays.resolve_yards_after(returner, pursuers, start, rng,
                                                 contact_at=gain, in_space=True, track_tackler=True)
            gain = chase['yards']
            breakout = True
    # Pick the coverage player making contact before testing his impact.
    # Speed/tackling still govern return distance; impact governs ball security.
    tackler = coverage[int(rng.integers(len(coverage)))] if coverage else None
    if punt_chase is not None and punt_chase['tackler'] is not None:
        tackler = punt_chase['tackler']
    impact = rate(tackler, YAC['tackler']['impact']) if tackler is not None else .70
    fum = events.fumble_check(returner, event, rng, rate, hit_power=impact, env_mult=weather) if returner else None
    result = dict(returner=returner.get('pid'), return_start=float(start), fumble=False, fumble_lost=False,
                  breakaway_opportunity=breakout)
    if punt_chase is not None:
        result['punt_pursuit'] = punt_chase['contacts']
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
