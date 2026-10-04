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


def resolve(start, distance, returner, rng, rate, coverage=(), blockers=(), event='kick_return', weather=1.):
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
    if returner and coverage and 12 <= gain < start:
        skill = rate(returner, {'kick_ret_rating': .5, 'bcv_rating': .25, 'accel_rating': .25})
        chance = float(np.clip(.045 + .12 * (skill - .8) + .15 * (block - cov), .008, .09))
        if rng.random() < chance:
            import plays
            pursuers = sorted(coverage, key=lambda p: -rate(p, YAC['tackler']['angle']))[:2]
            chase = plays.resolve_yards_after(returner, pursuers, start, rng,
                                             contact_at=gain, in_space=True, track_tackler=True)
            gain = chase['yards']
            breakout = True
    # Pick the coverage player making contact before testing his impact.
    # Speed/tackling still govern return distance; impact governs ball security.
    tackler = coverage[int(rng.integers(len(coverage)))] if coverage else None
    impact = rate(tackler, YAC['tackler']['impact']) if tackler is not None else .70
    fum = events.fumble_check(returner, event, rng, rate, hit_power=impact, env_mult=weather) if returner else None
    result = dict(returner=returner.get('pid'), return_start=float(start), fumble=False, fumble_lost=False,
                  breakaway_opportunity=breakout)
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
