"""Bounded execution effects for motion and play-action fakes."""
import numpy as np


def recognition(defense, rate):
    men = (defense.get('lb') or []) + (defense.get('db') or [])
    return float(np.mean([rate(p, {'awareness_rating': .5, 'play_rec_rating': .5}) for p in men])) if men else .7


def motion_run_bonus(offense, defense, rate):
    movers = [p for p in offense.get('wr', []) if p.get('pos') in ('WR','TE','HB','FB')]
    if not movers:
        return 0.
    execution = float(np.mean([rate(p, {'awareness_rating': .45, 'agility_rating': .35, 'accel_rating': .20}) for p in movers]))
    # A well-coordinated defense can absorb the movement. This does not
    # manufacture a mishap or penalize merely attempting motion.
    return float(np.clip(.20 * (execution - recognition(defense, rate)), 0., .06))


def play_action_effect(qb, defense, rate, shotgun=False):
    execution = rate(qb, {'play_action_rating': .75, 'awareness_rating': .25})
    read = recognition(defense, rate)
    benefit = float(np.clip(.08 + .65 * (execution - read), 0., .22))
    if shotgun: benefit *= .65
    # A quick gun fake costs less than turning away under center. Better
    # execution trims the exchange, without eliminating its time cost.
    delay = float(np.clip((.18 if shotgun else .32) + .25 * (.7-execution), .10, .42))
    return delay, benefit
