"""Scrimmage loose-ball adjudication, in the original offense's coordinates.

Zero is the opponent goal line; 100 is the offense's goal line. A recovery
spot is distinct from where possession was lost. This module does not decide
whether a fumble occurs or grant a fumble after a touchdown/dead ball.
"""


def resolve(spot, recovery_spot, side, *, same_player=False, restricted=False,
            out_of_bounds=False):
    spot, recovery_spot = float(spot), float(recovery_spot)
    result = dict(fumble_spot=spot, fumble_recovery_spot=recovery_spot,
                  fumble_out_of_bounds=bool(out_of_bounds),
                  fumble_advancement_restricted=False, touchdown=False,
                  defensive_td=False, safety=False, touchback=False)
    if out_of_bounds:
        if recovery_spot <= 0:
            result.update(fumble_lost=True, touchback=True, end_spot=20.0)
            return result
        dead = max(spot, recovery_spot)  # no forward gain via the boundary
        result.update(fumble_lost=False, fumble_dead_spot=min(100.0, dead),
                      safety=dead >= 100)
        return result
    if side == 'defense':
        result.update(fumble_lost=True, return_start=recovery_spot)
        return result  # defensive_return resolves recovery/advance/touchback
    dead = recovery_spot
    if restricted and not same_player:
        dead = max(spot, recovery_spot)
        result['fumble_advancement_restricted'] = True
    result.update(fumble_lost=False, fumble_dead_spot=max(0.0, min(100.0, dead)),
                  touchdown=dead <= 0, safety=dead >= 100,
                  offensive_fumble_td=dead <= 0)
    return result


def near_goal_recovery(spot, rng):
    """Small loose-ball displacement near either goal; frequency is a model choice.

Keep ordinary field recoveries at their existing spot. This bounded first
model avoids turning a goal-line correction into a global return-yard retune.
No sideline geometry is available: the boundary branch represents a rare
loose ball leaving the field, not a claimed exact pylon trajectory.
"""
    if 5 < spot < 95:
        return float(spot), False
    recovery = float(spot) + float(max(-4.0, min(4.0, rng.normal(0, 1.5))))
    return recovery, bool(rng.random() < .06)
