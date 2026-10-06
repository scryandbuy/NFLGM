"""Shared late-game competitive outlook, not a calibrated win probability."""
import math


def rest_opportunity(seconds, margin, playoffs=False):
    lead = abs(margin)
    if seconds <= 0 or seconds > 900 or lead <= 16:
        return 0.
    cushion = math.ceil(lead / 8.) - seconds / 240.
    value = max(0., min(1., (cushion - 1.) / 2.))
    return value * (.65 if playoffs else 1.)


def pursuing_comeback(seconds, deficit, coach=None):
    if seconds <= 0:
        return False
    if deficit <= 16 or seconds > 900:
        return True
    coach = coach or {}
    aggression = max(0., min(1., .5 * float(coach.get('fourth_down', .5))
                            + .5 * float(coach.get('adjust_willingness', .5))))
    # Reserve a narrow path for aggressive coaches without treating every
    # mathematically possible sequence as a reason to prolong a blowout.
    return 1. - rest_opportunity(seconds, deficit) > .55 - .30 * aggression
