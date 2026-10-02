"""Deterministic punt estimates and observed defensive form for fourth downs."""
import numpy as np

_NODES, _WEIGHTS = np.polynomial.hermite.hermgauss(17)
_NORMAL = tuple(zip(_NODES * np.sqrt(2), _WEIGHTS / np.sqrt(np.pi)))


def estimate(yardline, punter, returner, rate, rules, weather=1., snap_quality=0.):
    """Approximate game.punt's unblocked landing distribution without RNG draws.

    Power controls the full swing; accuracy/snap quality control pooch spread.
    Returns and goal-line bounces count, so a possible pin is never a sure pin.
    """
    power = rate(punter or {}, {'kick_power_rating': .70, 'kick_acc_rating': .30})
    accuracy = rate(punter or {}, {'kick_acc_rating': 1.})
    skill = rate(returner or {}, {'kick_ret_rating': .45, 'speed_rating': .30,
                                  'juke_move_rating': .25})
    spread = 1. - .5 * snap_quality
    mean = rules['full'] * (1 + .30 * (power - .70)) * weather
    aim_sd = rules['aim_sd'] * (1 - .6 * (accuracy - .70)) * spread
    # Same mean gamma return as game.punt; end-zone returns are negligible
    # in the short-field decisions for which the estimate matters.
    mean_return = 1.9 * 5.5 * (1 + .9 * (skill - .80))
    total = inside10 = inside20 = touchbacks = 0.
    def outcome(start, weight, touchback=False):
        nonlocal total, inside10, inside20, touchbacks
        start = float(max(1, min(99, start)))
        total += weight * start
        inside10 += weight * (start <= 10)
        inside20 += weight * (start < 20)
        touchbacks += weight * touchback
    def landing(land, weight):
        if land <= 0:
            outcome(20, weight, True)
        elif land < 10:
            bounce = .85 if land < 5 else .35
            outcome(land, weight * (1-bounce))
            for z, w in _NORMAL:
                end = land - max(0., rules['roll_mean'] + rules['roll_sd'] * z)
                outcome(20 if end <= 0 else end, weight * bounce * w, end <= 0)
        else:
            outcome(land, weight * (1-rules['return_rate']))
            outcome(land + mean_return, weight * rules['return_rate'])
    for z, w in _NORMAL:
        full = min(68., mean + rules['sd'] * spread * z)
        if yardline - full < rules['aim']:
            for za, wa in _NORMAL:
                gross = min(70., max(15., yardline - rules['aim'] + aim_sd * za))
                landing(yardline - gross, w * wa)
        else:
            landing(yardline - full, w)
    return dict(receiving_start=total, inside10=inside10,
                inside20=inside20, touchback=touchbacks)


def record_defense(state, drive):
    """Keep only completed, meaningful opposing possessions in this game."""
    if state is None or drive.result == 'End of half':
        return
    plays = [p for p in drive.log if not p.get('nullified') and
             p.get('type') in ('run', 'complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble')]
    if len(plays) < 3:
        return
    rows = getattr(state, '_fourth_defense', [])
    rows.append(dict(plays=len(plays), yards=sum(p.get('yards', 0) for p in plays),
                     stopped=drive.result in ('Punt', 'Turnover', 'Turnover on downs',
                                              'Safety', 'Defensive touchdown')))
    state._fourth_defense = rows


def confidence(state):
    rows = getattr(state, '_fourth_defense', []) if state is not None else []
    snaps = sum(r['plays'] for r in rows)
    if len(rows) < 3 or snaps < 12:
        return 0.
    ypp = sum(r['yards'] for r in rows) / snaps
    stops = sum(r['stopped'] for r in rows) / len(rows)
    form = .5 * np.clip((6. - ypp) / 3., 0, 1) + .5 * np.clip((stops - .55) / .45, 0, 1)
    return float(form * len(rows) / (len(rows) + 3.))


def flow_adjustment(aggression, defensive_confidence, pin_chance):
    """Confidence supports aggression or field position, following the coach."""
    preference = float(np.clip(aggression, 0, 1)) - .5
    confidence_ = float(np.clip(defensive_confidence, 0, 1))
    return .16 * confidence_ * preference * (1 if preference >= 0 else pin_chance)
