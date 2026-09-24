"""
REGRESSION.

Progression is not here. By decision it is continuous - XP earned every game,
one scheduled practice a week, extra drills at minicamp - and a player or the
AI spends it whenever. What belongs to the offseason is the other direction:
the year a man gets slower.

BUILT ON THE REAL AGING CURVES, which were already in the project and never
called. aging_curves.json holds a delta-method curve per position: the same
player at age t compared to himself at t+1, which controls for quality
entirely. That matters because cross-sectional averages are badly biased by
survivorship - the only 34-year-olds still playing are the good ones, so a
naive curve looks flat when it is not.

What the curves say, and it is not subtle:

    plateau ends at 26 for a back, a receiver, a linebacker and a defensive
    back; 27 for a tight end and both lines; 36 for a quarterback.

    a back at 29 produces at 0.838 of his previous year and at 0.774 by 30.
    a receiver falls to 0.574 by 33 and 0.489 by 34.
    an offensive lineman holds to 0.997 at 26 and is at 0.684 by 32.
    a quarterback never declines at all inside the measured range.

TWO THINGS THE CURVE CANNOT BE USED FOR DIRECTLY:

1. It measures PRODUCTION, not ability. Production swings harder than the man
   does - a receiver losing his job loses nearly all of it while still being
   most of the player he was. So the drop is damped before it reaches a
   rating, and the damping is the one constant here that is fitted rather
   than measured.

2. It is a single number for a whole player, and a player is not one thing.
   Speed goes first and awareness does not go at all - a 34-year-old is
   slower than he was and knows more. So the decline is spent on physical
   attributes, mental ones are held, and a few of them still creep up.

LONGEVITY is already on every Player, drawn at creation and hidden: at 29 the
10th percentile held 74% of his baseline and the 90th held 125%. Some men are
finished at 28 and some play to 38, and nothing about their ratings says
which in advance.
"""
import json
import os

import numpy as np

_D = os.path.dirname(os.path.abspath(__file__))
CURVES = json.load(open(os.path.join(_D, 'aging_curves.json')))

POS_GROUP = {
    'QB': 'QB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE',
    'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
    'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL',
    'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB',
    'CB': 'DB', 'FS': 'DB', 'SS': 'DB',
    'K': 'QB', 'P': 'QB', 'LS': 'QB',      # specialists barely decline
}

# Production swings harder than ability does. A 16% production drop is not a
# 16% worse football player, so the curve is damped before it touches a
# rating. This is the only fitted constant in the file: it is set so a back
# past thirty loses two to three points of overall a year, which is the shape
# every football game uses.
#
# It has to be aggressive, and here is why. The curve says a receiver at 33
# produces at 0.574 of his previous year. If overall mapped to production
# quadratically that is a 24% drop in ability - twenty rating points in a
# single season, which no football game does and no scout would recognise.
# The gap is role: a 33-year-old who loses his job produces almost nothing
# while remaining most of the player he was. Damping IS that correction, so it
# is set by what a year of decline should look like on a rating sheet rather
# than by the curve's face value.
DAMPING = 0.17

# HOW PHYSICAL EACH ATTRIBUTE IS, 0 to 1.
#
# A binary physical/mental split does not survive contact with real positions.
# A tackle's overall is carried almost entirely by his blocking ratings, so
# calling blocking "mental" left him flat from 24 to 36; a back's is carried by
# speed and elusiveness, so calling those purely physical dropped him from 85
# to 56 in eleven years. Neither is right, because neither kind of attribute is
# one thing: blocking is leverage and hand placement as much as it is strength,
# and route running is timing as much as it is burst.
#
# So every rating carries a weight instead. 1.0 leaves with the legs, 0.0 never
# leaves at all, and the ones in between decay at their own pace.
PHYS_WEIGHT = {
    # pure athleticism - the first thing to go
    'speed_rating': 1.00, 'accel_rating': 1.00, 'agility_rating': 0.95,
    'change_of_direction_rating': 0.95, 'jump_rating': 0.90,
    'stamina_rating': 0.75, 'strength_rating': 0.55,
    # skills that lean athletic
    'juke_move_rating': 0.85, 'spin_move_rating': 0.75, 'truck_rating': 0.70,
    'break_tackle_rating': 0.75, 'pursuit_rating': 0.80, 'press_rating': 0.65,
    'release_rating': 0.65, 'man_cover_rating': 0.70, 'kick_ret_rating': 0.85,
    'power_moves_rating': 0.60, 'finesse_moves_rating': 0.65,
    'hit_power_rating': 0.55, 'bcv_rating': 0.45, 'spec_catch_rating': 0.45,
    'throw_power_rating': 0.45, 'kick_power_rating': 0.55,
    'throw_on_run_rating': 0.55, 'break_sack_rating': 0.80,
    # BLENDS. This is the correction: blocking and route running are technique
    # and leverage as much as they are athleticism, so they decay slowly
    # rather than either falling off a cliff or holding forever.
    'pass_block_rating': 0.40, 'pass_block_power_rating': 0.50,
    'pass_block_finesse_rating': 0.35, 'run_block_rating': 0.40,
    'run_block_power_rating': 0.50, 'run_block_finesse_rating': 0.35,
    'impact_block_rating': 0.45, 'lead_block_rating': 0.45,
    'block_shed_rating': 0.45, 'tackle_rating': 0.40,
    'route_run_short_rating': 0.30, 'route_run_med_rating': 0.35,
    'route_run_deep_rating': 0.45, 'zone_cover_rating': 0.30,
    'catch_rating': 0.20, 'cit_rating': 0.20, 'carry_rating': 0.15,
    'stiff_arm_rating': 0.55,
    # the head. None of this leaves, and some of it grows.
    'awareness_rating': 0.00, 'play_rec_rating': 0.00,
    'throw_acc_short_rating': 0.10, 'throw_acc_mid_rating': 0.15,
    'throw_acc_deep_rating': 0.25, 'play_action_rating': 0.00,
    'throw_under_pressure_rating': 0.10, 'kick_acc_rating': 0.10,
}
DEFAULT_PHYS = 0.50

# Experience is worth something, on the attributes that are mostly head. Small,
# and it never outruns the physical loss.
MENTAL_GAIN = 0.40

# Injury and toughness are availability, not ability, and sit outside this
# entirely - the same reason they sit outside any future XP budget.
UNTOUCHED = ('injury_rating', 'tough_rating')


def curve_factor(pos, age):
    """
    The real year-over-year production multiplier for this man's position at
    this age. Above 1.0 before the plateau, below it after.
    """
    c = CURVES.get(POS_GROUP.get(pos, 'LB'), CURVES['LB'])
    tbl = c.get('curve') or {}
    if not tbl:
        return 1.0
    a = int(round(age))
    ks = sorted(int(k) for k in tbl)
    if a < ks[0]:
        a = ks[0]
    elif a > ks[-1]:
        a = ks[-1]
    return float(tbl[str(a)])


def plateau_end(pos):
    c = CURVES.get(POS_GROUP.get(pos, 'LB'), CURVES['LB'])
    return int(c.get('plateau_end') or 27)


def decline(player, rng):
    """
    One year older. Returns how much overall he lost, and mutates his ratings.

    Nothing here touches a stored overall, because there isn't one - ovr is
    computed from these ratings. Move the ratings and the overall follows, and
    the play engine feels it on the field the same season.
    """
    before = player.ovr
    f = curve_factor(player.pos, player.age)
    if f >= 1.0:
        # still on the plateau: no decline, and no free improvement either,
        # since gains are XP and XP is earned rather than handed out
        return 0.0

    # damp production into ability, then let the hidden longevity draw decide
    # whether this is the man who falls off at 28 or the one still going at 38
    drop = (1.0 - f) * DAMPING / max(0.35, player.longevity)
    drop *= float(np.clip(rng.normal(1.0, 0.35), 0.15, 2.2))

    for k in list(player.ratings):
        if k in UNTOUCHED:
            continue
        w = PHYS_WEIGHT.get(k, DEFAULT_PHYS)
        v = player.ratings[k]
        if w > 0:
            v *= 1.0 - drop * w
        if w < 0.5:
            # he knows more than he did, right up until the end, and the more
            # of an attribute is head the more it keeps growing
            v *= 1.0 + MENTAL_GAIN * drop * (1.0 - 2.0 * w)
        player.ratings[k] = float(np.clip(v, 20.0, 99.0))
    return before - player.ovr


def run(league, rng, verbose=False):
    """
    Age the league a year and take what age takes. Called after retirement -
    a man who has just retired does not need to get slower first.
    """
    moved = []
    for p in league.players.values():
        if p.retired:
            continue
        p.age += 1.0
        lost = decline(p, rng)
        if lost:
            moved.append((p, lost))
            league.log('regress', pid=p.pid, pos=p.pos,
                       age=round(p.age, 1), lost=round(lost, 2))
    if verbose and moved:
        print(f'  {len(moved)} declined, mean {np.mean([m for _p, m in moved]):.2f} ovr')
    return moved


if __name__ == '__main__':
    import collections
    import league as LG
    rng = np.random.default_rng(7)
    L = LG.build_league(rng=rng)

    print('one offseason, mean overall lost by age:')
    by = collections.defaultdict(list)
    snapshot = {p.pid: p.ovr for p in L.players.values()}
    run(L, rng)
    for p in L.players.values():
        if p.retired:
            continue
        by[int(p.age)].append(snapshot[p.pid] - p.ovr)
    for a in sorted(by):
        if a < 23 or a > 37 or len(by[a]) < 10:
            continue
        print('  age %2d  n=%4d  %+.2f' % (a, len(by[a]), -np.mean(by[a])))

    print('\nthe same man, aged from 24 to 36:')
    L2 = LG.build_league(rng=np.random.default_rng(7))
    for pos in ('HB', 'WR', 'LT', 'QB'):
        p = next((x for x in L2.players.values()
                  if x.pos == pos and 23 <= x.age <= 25), None)
        if p is None:
            continue
        p.age = 24.0
        row = []
        for _ in range(12):
            row.append(p.ovr)
            p.age += 1
            decline(p, np.random.default_rng(3))
        print('  %-3s %s' % (pos, ' '.join('%.0f' % v for v in row)))
