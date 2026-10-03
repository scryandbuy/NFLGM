"""Eligible on-field foul exposure, separate from awareness and coaching."""
import numpy as np
from functools import lru_cache


TEAM_FOULS = {'Delay of Game', 'Defensive Too Many Men on Field', 'Illegal Formation'}
OL = {'LT', 'LG', 'C', 'RG', 'RT'}


def unit(roster, offense):
    if offense and roster.get('offensive_assignments'):
        rows = roster['offensive_assignments']
    elif not offense and roster.get('defensive_assignments'):
        rows = [(r['group'].upper(), r['player']) for r in roster['defensive_assignments']]
    elif offense:
        rows = [('QB', roster.get('qb')), ('HB', roster.get('rb'))]
        rows += [('OL', p) for p in roster.get('ol', [])[:5]]
        rows += [(p.get('pos', 'WR'), p) for p in roster.get('wr', [])[:4]]
    else:
        rows = [(k.upper(), p) for k in ('dl', 'lb', 'db') for p in roster.get(k, [])]
    return list({p['pid']: (role, p) for role, p in rows if p and p.get('pid')}.values())


def eligible(name, rows, out=None):
    """An ineligible/inactive roster member cannot alter a foul's probability."""
    if name in TEAM_FOULS:
        return []
    if name == 'Intentional Grounding':
        return [(r, p) for r, p in rows if r == 'QB']
    if name in ('Face Mask', 'Unnecessary Roughness') and out is not None:
        contact = {out.get(k) for k in ('carrier', 'carrier_pid', 'tackler', 'by', 'recoverer')}
        if out.get('type') == 'complete': contact.add(out.get('target'))
        for key in ('pb_reps', 'pr_reps', 'rb_reps'):
            contact.update(pid for pid, *_ in out.get(key, []))
        for block in out.get('run_support', []):
            contact.update((block.get('blocker'), block.get('defender')))
        # The run resolver records individual blockers but not every front
        # defender matched to them. Front-line jobs are the narrow fallback;
        # a remote safety is not a contact participant without evidence.
        if out.get('type') == 'run' and 'rb_reps' in out:
            contact.update(p['pid'] for role, p in rows if role == 'DL')
        if contact - {None}:
            return [(r, p) for r, p in rows if p['pid'] in contact]
        # Legacy/custom outcomes may omit all contact attribution.
        return [(r, p) for r, p in rows if r in OL | {'OL', 'HB', 'FB', 'TE', 'DL', 'LB'}]
    if name in ('Defensive Offside', 'Neutral Zone Infraction', 'Encroachment', 'Roughing the Kicker'):
        return [(r, p) for r, p in rows if r in ('DL', 'LB')]
    if name == 'Ineligible Downfield Pass':
        return [(r, p) for r, p in rows if r in OL or r == 'OL']
    if name in ('False Start', 'Illegal Shift'):
        return [(r, p) for r, p in rows if r != 'QB']
    if name == 'Offensive Pass Interference':
        blockers = {pid for pid, *_ in (out or {}).get('pb_reps', [])}
        return [(r, p) for r, p in rows if r not in OL | {'OL', 'QB'} and p['pid'] not in blockers]
    if name in ('Defensive Holding', 'Defensive Pass Interference', 'Illegal Contact'):
        evidence = (out or {}).get('coverage_evidence')
        if evidence is not None:
            covering = ({evidence.get('primary'), evidence.get('helper')} if name == 'Defensive Pass Interference'
                        else {item[0] for item in evidence.get('drops', [])})
            return [(r, p) for r, p in rows if p['pid'] in covering]
        rushers = {pid for pid, *_ in (out or {}).get('pr_reps', [])}
        return [(r, p) for r, p in rows if r in ('DB', 'LB') and p['pid'] not in rushers]
    if name == 'Roughing the Passer':
        if out is not None and 'pr_reps' in out:
            rushers = {pid for pid, *_ in out['pr_reps']}
            return [(r, p) for r, p in rows if p['pid'] in rushers]
        return [(r, p) for r, p in rows if r in ('DL', 'LB')]
    if name in ('Offensive Holding', 'Illegal Block Above the Waist') and out is not None:
        key = 'rb_reps' if 'rb_reps' in out else 'pb_reps'
        if key in out:
            blockers = {pid for pid, *_ in out[key]}
            return [(r, p) for r, p in rows if p['pid'] in blockers]
    return [(r, p) for r, p in rows if r != 'QB']


@lru_cache(maxsize=4096)
def _multiplier(value, name):
    import personality
    return float(personality.penalty_multiplier({'discipline': value}, name))


def profile(name, rows, out=None):
    players = eligible(name, rows, out)
    result = []
    for role, p in players:
        value = (p.get('traits') or {}).get('discipline', p.get('discipline', 50))
        try: hash(value)
        except TypeError: value = 50
        # The cache keys the immutable trait value, never a player/team id;
        # edits, moves and newly generated players cannot leave stale risk.
        result.append((role, p, 1. if value == 50 else _multiplier(value, name)))
    return result


def factor(profile):
    return sum(w for _, _, w in profile) / len(profile) if profile else 1.


def attribute(flag, profile, rng):
    if flag is None:
        return None
    flag = dict(flag)
    if profile:
        weights = np.array([w for _, _, w in profile], dtype=float)
        role, player, _ = profile[int(rng.choice(len(profile), p=weights / weights.sum()))]
        flag.update(offender_pid=player['pid'], offender_role=role, responsibility='player')
    else:
        flag.update(offender_pid=None, offender_role=None, responsibility='team')
    return flag


def decision(flag, accepted):
    flag.update(accepted=bool(accepted), declined=not accepted,
                enforced_yards=float(flag.get('yards', 0)) if accepted else 0.)
    return flag


def book_flag(book, flag):
    if book is None or not flag or not flag.get('offender_pid'):
        return
    line = book._get(flag['offender_pid'])
    line['penalties_committed'] = line.get('penalties_committed', 0) + 1
    line['penalties_accepted'] = line.get('penalties_accepted', 0) + int(flag.get('accepted', False))
    line['penalty_yards'] = line.get('penalty_yards', 0.) + flag.get('enforced_yards', 0.)


def book_opportunities(book, rows):
    if book is None:
        return
    for pid in sorted({p['pid'] for _, p in rows if p.get('pid')}):
        line = book._get(pid)
        line['penalty_opportunities'] = line.get('penalty_opportunities', 0) + 1
