"""Support blocks by the selected eleven, after the line engages the front."""
import math
from defensive_rush import player_key
from matchups import RUN_BLOCK

SUPPORT_YARDS = 1.25
OL = frozenset(('LT', 'LG', 'C', 'RG', 'RT'))


def contact_execution(blocks, scheme, sigma, spread):
    """Use the same block executions for penetration and recorded wins.

    Interior blocks matter most inside; edge blocks matter most outside.
    Support jobs retain their existing relevance weights. Normalizing the
    independent Gaussian rolls preserves the contact-noise variance as the
    number of blockers changes, without granting heavy personnel free yards.
    These are coarse path weights, not tracked left/right player coordinates.
    """
    wide = scheme in ('outside_zone', 'stretch', 'toss', 'sweep')
    weighted = square = 0.
    for block in blocks:
        if block.get('front'):
            edge = block['alignment'] in ('left_edge', 'right_edge')
            weight = 2. if edge == wide else 1.
        else:
            weight = block['weight']
        block['contact_weight'] = weight
        weighted += weight * block['execution']
        square += weight * weight
    return spread * weighted / (sigma * math.sqrt(square)) if square else 0.


def support_blocks(offense, defense_roles, engaged_blockers, engaged_defenders,
                   scheme, rate, carrier=None):
    """Match free linemen/lead/attached/perimeter blockers with unique defenders.

    Equal blocking and shedding grades add zero yards. Extra personnel alone
    do not create a free bonus; their actual ability changes the contest.
    Role metadata matters when a TE or HB fills the fullback assignment.
    """
    role_by_id = {player_key(p): role for role, p in offense.get('offensive_assignments', ())}
    carrier = carrier or offense.get('rb') or offense.get('qb') or {}
    qb_carry = player_key(carrier) == player_key(offense.get('qb') or {})
    excluded = set(engaged_blockers) | {player_key(carrier)}
    if offense.get('qb'): excluded.add(player_key(offense['qb']))
    pool = {}
    for group in ('ol', 'wr', 'te', 'extra_blockers', 'backs'):
        for p in offense.get(group) or ():
            if p and player_key(p) not in excluded:
                pool[player_key(p)] = p
    role = lambda p: role_by_id.get(player_key(p), p.get('pos', ''))
    priority = lambda p: (0 if role(p) in OL else 1 if role(p) in ('FB', 'HB') else 2 if role(p) == 'TE' else 3, player_key(p))
    defenders = {player_key(a['player']): a for a in defense_roles
                 if player_key(a['player']) not in engaged_defenders}
    wide = scheme in ('outside_zone', 'stretch')
    blocks = []
    for blocker in sorted(pool.values(), key=priority):
        job = role(blocker)
        if job not in OL | {'FB', 'TE', 'WR'} | ({'HB'} if qb_carry else set()) or not defenders:
            continue
        def proximity(a):
            alignment = a.get('alignment', '')
            if job == 'WR':
                near = 0 if alignment.startswith(('corner', 'slot')) else 1
            else:
                near = 0 if alignment.startswith('offball') else 1
            return near, alignment, player_key(a['player'])
        assignment = min(defenders.values(), key=proximity)
        defender = assignment['player']
        del defenders[player_key(defender)]
        second = rate(blocker, RUN_BLOCK['blocker']['second'])
        base = rate(blocker, {'run_block_rating': 1.0})
        if job in OL:
            attack, weight = second, 1.0
        elif job in ('FB', 'HB'):
            attack = rate(blocker, {'lead_block_rating': .50, 'impact_block_rating': .20,
                                   'run_block_rating': .20, 'strength_rating': .10})
            weight = 1.0
        elif job == 'TE':
            attack, weight = .65 * base + .35 * second, .8
        else:
            attack, weight = .75 * base + .25 * second, .65 if wide else .20
        resistance = rate(defender, RUN_BLOCK['defender']['shed'])
        blocks.append(dict(blocker=player_key(blocker), defender=player_key(defender),
                           role=job, edge=attack-resistance, weight=weight))
    delta = max(-1.25, min(1.25, SUPPORT_YARDS * sum(b['edge'] * b['weight'] for b in blocks)))
    return delta, blocks
