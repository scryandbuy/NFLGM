"""A QB can surrender available yards to finish before contact.

This is a stochastic opportunity model, not tracked sideline geometry. The
probability weights and yardage costs below are disclosed policy assumptions;
they are not estimates of NFL slide frequency. Call after final sack escape,
before contact injury, fumble, official stats and clock processing.
"""


def _clip(value, low, high):
    return max(low, min(high, float(value)))


def _period(quarter, playoffs=False):
    quarter = int(quarter)
    if quarter <= 4:
        return quarter
    return (quarter - 5) % 4 + 1 if playoffs else 4


def oob_stops_until_snap(out, quarter, seconds_after,
                         after_two_minute_warning=False, playoffs=False):
    """Runner OOB restart, excluding other reasons the clock might stop.

    seconds_after is time left in the half (regulation) or current OT period
    after live action. The caller may pass its effective clock period directly.
    Regular OT uses Q4 timing; postseason OT repeats the Q1..Q4 timing cycle.
    Fumble/penalty/score/change-of-possession precedence belongs to the caller.
    """
    if not out.get('out_of_bounds'):
        return False
    period = _period(quarter, playoffs)
    if period == 2:
        return bool(after_two_minute_warning or float(seconds_after) < 120.)
    return period == 4 and float(seconds_after) < 300.


def apply(out, qb, call, rng, rate_fn, coach=None, condition=100):
    """Mutate and return a final QB rushing outcome; repeated calls are inert.

    Adds run_end, contact_avoided, ended_without_contact, out_of_bounds and
    qb_contact evidence. Safe endings remove the terminal tackler, not QB
    workload or the possibility of an earlier non-contact loose ball. All
    ordinary/non-QB plays and already-scored outcomes remain untouched.
    """
    if out.get('run_end') is not None:
        return out
    kind = out.get('type')
    carrier = out.get('carrier_pid') or out.get('carrier')
    actual_qb = (carrier == qb.get('pid') if carrier is not None
                 else bool(out.get('qb_run') or call.get('qb_run')))
    if (kind not in ('run', 'scramble') or (kind == 'run' and not actual_qb)
            or out.get('sneak') or call.get('sneak') or out.get('touchdown')
            or out.get('defensive_td') or out.get('fumble') or out.get('fumble_lost')):
        return out
    if kind == 'scramble' and carrier is not None and carrier != qb.get('pid'):
        return out
    original = float(out.get('yards', 0.) or 0.)
    goal = out.get('yardline', call.get('yardline'))
    if goal is not None and (original >= float(goal) or round(original) >= float(goal)):
        return out  # The existing engine's whole-yard spot can already score.
    out.update(run_end='contact', contact_avoided=False,
               ended_without_contact=False, out_of_bounds=False)
    evidence = dict(version=1, original_yards=original, final_yards=original,
                    yards_given_up=0., reason='no_safe_space')
    out['qb_contact'] = evidence
    # A designed run already describes its first contact point. A safe ending
    # cannot keep its after-contact yards while pretending that hit vanished.
    clear = min(original, float(out.get('ybc', 0.) or 0.)) if kind == 'run' else original
    if clear < 3.:
        return out
    mobility = rate_fn(qb, {'speed_rating': .4, 'accel_rating': .3, 'agility_rating': .3})
    awareness = rate_fn(qb, {'awareness_rating': 1.})
    power = rate_fn(qb, {'break_tackle_rating': .6, 'strength_rating': .4})
    protection = _clip((coach or {}).get('starter_protection',
        1. - float(call.get('qb_run_aggression', .5))), 0., 1.)
    avoid = _clip(.38 + .28 * protection + .35 * (awareness - .7)
                  + .20 * (1. - _clip(condition, 0., 100.) / 100.)
                  - .18 * (power - .7), .1, .9)
    outside = out.get('scheme', call.get('scheme')) in ('outside_zone', 'toss', 'sweep')
    slide_chance = _clip(.30 + .035 * clear + .20 * (mobility - .7), .2, .8)
    boundary_chance = _clip(.12 + .018 * clear + .12 * outside
                           + .15 * (mobility - .7), .05, .55)
    slide_available = rng.random() < slide_chance
    boundary_available = rng.random() < boundary_chance
    # These are foregone gain, not extra distance supplied to reach a marker.
    slide_cost = .8 + 1.8 * rng.random()
    boundary_cost = .5 + 1.5 * rng.random()
    down = int(out.get('down', call.get('down', 1)))
    need = float(out.get('ydstogo', call.get('ydstogo', call.get('distance', 10.))))
    seconds = call.get('seconds')
    margin = float(call.get('score_diff', 0.))
    quarter = _period(call.get('clock_period', call.get('quarter', 1)), call.get('playoffs', False))
    late = seconds is not None and ((quarter == 2 and seconds <= 120.) or (quarter == 4 and seconds < 300.))
    save_clock = late and margin <= 0.
    keep_clock = quarter == 4 and late and margin > 0.
    choices = [('contact', original, 1. - avoid)]
    candidates = []
    for ending, available, cost in (('slide', slide_available, slide_cost),
                                    ('out_of_bounds', boundary_available, boundary_cost)):
        if not available:
            continue
        gain = round(max(0., clear - cost), 1)
        # Do not voluntarily concede fourth down because the caller asked for
        # safety. Contact still can fail; nothing grants the needed yardage.
        if down >= 4 and gain < need + .1:
            candidates.append(dict(ending=ending, yards=gain, accepted=False,
                                   reason='fourth_down_short'))
            continue
        weight = avoid
        if ending == 'out_of_bounds':
            weight *= 2. if save_clock else .08 if keep_clock else .65
        elif keep_clock:
            weight *= 1.3
        elif save_clock:
            weight *= .65
        if down == 3 and gain < need:
            weight *= .12 if original >= need else .55
        # Near a score, giving up ground has more value than between the 20s.
        if goal is not None and float(goal) <= 10.:
            weight *= .5
        candidates.append(dict(ending=ending, yards=gain, accepted=True,
                               weight=round(weight, 5)))
        choices.append((ending, gain, weight))
    evidence.update(reason='continued_for_yards', clear_yards=clear,
        slide_available=bool(slide_available), sideline_available=bool(boundary_available),
        avoid_weight=round(avoid, 5), save_clock=bool(save_clock),
        keep_clock=bool(keep_clock), candidates=candidates)
    if len(choices) == 1:
        return out
    draw = rng.random() * sum(c[2] for c in choices)
    chosen = choices[-1]
    for option in choices:
        draw -= option[2]
        if draw < 0.:
            chosen = option
            break
    ending, gain, _ = chosen
    if ending == 'contact':
        return out
    out.update(run_end=ending, contact_avoided=True, ended_without_contact=True,
               out_of_bounds=ending == 'out_of_bounds', yards=gain, touchdown=False)
    tackler = out.pop('tackler', None)
    if tackler is not None:
        evidence['pursuer_pid'] = tackler
    if 'broken_tackles' in out:
        out['broken_tackles'] = 0
    if 'ybc' in out:
        out['ybc'] = min(gain, float(out['ybc']))
    evidence.update(final_yards=gain, yards_given_up=round(original - gain, 1),
                    reason='save_clock' if ending == 'out_of_bounds' and save_clock else 'avoid_contact')
    return out
