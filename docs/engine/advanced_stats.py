"""
ADVANCED STATS.

Expected points (EP) for any down, distance and spot, from the real
nflfastR shape: about -1.6 at your own one on first and ten, 0.6 at the 25,
2.0 at midfield, 4.0 at their 25, 6.0 at their one, with a penalty for
down and distance. EPA per play is EP after minus EP before, with scores
and turnovers valued the real way. Booked by player: passers, rushers,
receivers, and the defence that allowed it.

Completion percentage over expectation (CPOE) uses the engine's own
expectation for each throw: the completion probability it computed from
depth, separation, pressure, the read and the coverage before the roll.
Actual minus expected, summed by passer, is the cleanest CPOE there is.

Pass-rush win rate is the rusher's side of the block-win rep: he wins a
rep when he beats his man inside 2.5 seconds, the same clock the block win
rate reads from the other side. Separation per target is the receiver's.

Nothing here changes a game; it is bookkeeping in the box score, rolled up
to season lines by league.record_stats like every other stat.
"""
import numpy as np

# first-and-ten EP by yards to the goal (100 = own goal line), real shape
_EP_PTS = [(99, -1.4), (90, -0.5), (80, 0.4), (75, 0.9), (65, 1.6), (50, 2.4), (35, 3.4), (25, 4.1), (15, 4.8), (10, 5.3), (5, 5.8), (1, 6.3), (0, 6.6)]
_XS = np.array([x for x, _ in _EP_PTS][::-1], float); _YS = np.array([y for _, y in _EP_PTS][::-1], float)
DOWN_PEN = {1: 0.0, 2: 0.35, 3: 0.95, 4: 1.7}
TD_VALUE = 6.95          # a touchdown and the point after, less the kickoff


def ep(down, ydstogo, yards_to_goal):
    """Expected points for the offence with the ball here."""
    ytg = float(np.clip(yards_to_goal, 0, 100))
    base = float(np.interp(ytg, _XS, _YS))
    pen = DOWN_PEN.get(int(down), 0.0) * (1.0 + 0.06 * max(0.0, float(ydstogo) - 10.0)) * (0.5 + 0.5 * min(1.0, float(ydstogo) / 10.0))
    return base - pen


def epa(out, before_down, before_togo, before_ytg, after_down, after_togo, after_ytg, result=None):
    """EPA of one play for the offence."""
    before = ep(before_down, before_togo, before_ytg)
    t = out.get('type')
    if out.get('touchdown'):
        return TD_VALUE - before
    if t in ('interception', 'fumble') or result == 'Turnover':
        spot = 100.0 - float(after_ytg if after_ytg is not None else before_ytg)     # the other side's spot
        return -ep(1, 10, spot) - before
    if result == 'Turnover on downs':
        return -ep(1, 10, 100.0 - float(after_ytg)) - before
    if result == 'Safety':
        return -2.0 - before
    if after_ytg is None:
        return 0.0
    return ep(after_down, after_togo, after_ytg) - before


def book_play(book, out, off, deff, epa_val):
    """Credit the men: the passer or rusher, the target, and the defence allowing it."""
    if book is None: return
    t = out.get('type')
    qb = off['qb'].get('pid')
    if t in ('complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble'):
        s = book._get(qb); s['pass_epa'] += epa_val; s['pass_plays'] += 1
        if t in ('complete', 'incomplete', 'drop', 'interception'):
            if out.get('xcomp') is not None:
                s['xcomp'] += float(out['xcomp']); s['cpoe_att'] += 1
            tgt = out.get('target')
            if tgt:
                w = book._get(tgt); w['rec_epa'] += epa_val; w['sep_total'] += float(out.get('separation') or 0.0); w['sep_n'] += 1
    elif t == 'run':
        rb = out.get('carrier_pid') or off['rb'].get('pid')
        s = book._get(rb); s['rush_epa'] += epa_val; s['rush_plays'] += 1
    # the defence: the men on the field share what they allowed, by unit
    for d in (deff.get('dl') or []) + (deff.get('lb') or []) + (deff.get('db') or []):
        pid = d.get('pid')
        if pid:
            x = book._get(pid); x['def_epa'] -= epa_val / 11.0; x['def_plays'] += 1
    # pass-rush reps
    for pid, won in (out.get('pr_reps') or []):
        x = book._get(pid); x['pr_reps'] += 1; x['pr_wins'] += bool(won)


def book_special(book, dr, last, offense):
    """The punt or the kick: from the fourth-down state to what it produced."""
    before = ep(4, dr.togo, dr.yardline)
    if dr.result == 'Field goal':
        v = 3.0 - before; pid = (offense.get('k') or {}).get('pid')
    elif dr.result == 'Missed field goal':
        v = -ep(1, 10, 100.0 - max(20.0, dr.yardline + 7.0)) - before; pid = (offense.get('k') or {}).get('pid')
    else:
        spot = float(last.get('new_yardline', 60.0)) if isinstance(last, dict) else 60.0   # the other side's yards to goal
        v = -ep(1, 10, spot) - before; pid = (offense.get('p') or {}).get('pid')
    if isinstance(last, dict): last['epa'] = round(v, 3)
    if book is not None and pid:
        s = book._get(pid); s['st_epa'] = s.get('st_epa', 0.0) + v


# ------------------------------------------------------------ readouts
def line_metrics(line):
    """Derived metrics from a season line."""
    m = {}
    if line.get('pass_plays'): m['epa_per_dropback'] = line['pass_epa'] / line['pass_plays']
    if line.get('rush_plays'): m['epa_per_rush'] = line['rush_epa'] / line['rush_plays']
    if line.get('cpoe_att'): m['cpoe'] = (line.get('pass_cmp', 0) - line['xcomp']) / line['cpoe_att'] * 100.0
    if line.get('pr_reps'): m['pass_rush_win_rate'] = line['pr_wins'] / line['pr_reps'] * 100.0
    reps = line.get('pb_reps') or line.get('pb_snaps')             # the book records blocking snaps as pb_snaps
    if reps: m['pass_block_win_rate'] = line.get('pb_wins', 0) / reps * 100.0
    if line.get('sep_n'): m['separation'] = line['sep_total'] / line['sep_n']
    if line.get('def_plays'): m['def_epa_per_play'] = line['def_epa'] / line['def_plays']
    if line.get('tgt'): m['rec_epa_per_target'] = line.get('rec_epa', 0.0) / line['tgt']
    return m


def leaders(league, year, metric, min_n=1, top=10, pos=None):
    """League leaders on a derived metric with a floor on the denominator."""
    floor_key = {'epa_per_dropback': 'pass_plays', 'cpoe': 'cpoe_att', 'epa_per_rush': 'rush_plays',
                 'pass_rush_win_rate': 'pr_reps', 'pass_block_win_rate': 'pb_reps', 'separation': 'sep_n',
                 'def_epa_per_play': 'def_plays', 'rec_epa_per_target': 'tgt'}[metric]
    rows = []
    for pid, line in league.stats.get(year, {}).items():
        p = league.player(pid)
        n = line.get(floor_key, 0) or (line.get('pb_snaps', 0) if floor_key == 'pb_reps' else 0)
        if p is None or (pos and p.pos not in pos) or n < min_n: continue
        m = line_metrics(line)
        if metric in m: rows.append((p, m[metric], n))
    rows.sort(key=lambda r: -r[1])
    return rows[:top]
