"""Position-aware rating targets for the initial and generated draft classes.

The rookie cohort supplies each position's baseline. A generated class may be
stronger or weaker, but a shared position roll should not promote most of a
large room across an overall threshold. The class tail is shaped within each
position so a top player in a weak room is not punished by his global rank.
"""
SPECIALISTS = frozenset(('K', 'P', 'LS'))
VARIATION_CAP = 2.0
SPECIALIST_VARIATION_CAP = 1.0
TAIL_DROP = 6.5
TAIL_KEEP_FRACTION = 0.20
TAIL_POWER = 0.80
TE_NEWGEN_TOP_BOOST = 6.0
TE_NEWGEN_TAIL_BOOST = 1.0


def newgen_position_targets(pos, curve):
    """Give future tight end classes a stronger top without inflating the tail.

    The seed's small rookie TE cohort tops out around 71, making every later
    class weak even in a strong TE year. Keep year-to-year variation while
    lifting a premium prospect roughly six points and the last slot one.
    """
    values = [float(value) for value in curve]
    if pos != 'TE':
        return values
    last = max(len(values) - 1, 1)
    return [value + TE_NEWGEN_TAIL_BOOST
            + (TE_NEWGEN_TOP_BOOST - TE_NEWGEN_TAIL_BOOST) * (1.0 - i / last)
            for i, value in enumerate(values)]


def variation_targets(pos, base_curve, class_shift, position_shift):
    """Apply a bounded strength roll, tapering its effect down the room.

    The caller draws class_shift and position_shift as before, preserving the
    class-to-class and position-to-position variation without promoting all
    thirty receivers or corners by the full shared roll.
    """
    base = [float(value) for value in base_curve]
    cap = SPECIALIST_VARIATION_CAP if pos in SPECIALISTS else VARIATION_CAP
    shift = max(-cap, min(cap, float(class_shift) + float(position_shift)))
    count = len(base)
    if count == 0:
        return []
    return [value + shift * (1.0 - 0.5 * i / max(count - 1, 1))
            for i, value in enumerate(base)]


def tail_target(pos, current_ovr, rank_index, position_count):
    """A position-rank target that preserves top prospects in weaker rooms.

    The top fifth at each nonspecialist position keeps its rating. The rest
    transitions smoothly to a 6.5-point reduction at the final slot.
    A negative or out-of-range rank is rejected rather than silently changing
    the wrong player.
    """
    current = float(current_ovr)
    count = int(position_count)
    rank = int(rank_index)
    if count < 1 or rank < 0 or rank >= count:
        raise ValueError('rank_index must be within position_count')
    if pos in SPECIALISTS:
        return current
    keep = max(1, round(count * TAIL_KEEP_FRACTION))
    if rank < keep:
        return current
    tail = (rank + 1 - keep) / max(count - keep, 1)
    reduction = TAIL_DROP * tail ** TAIL_POWER
    return min(current, max(20.0, current - reduction))
