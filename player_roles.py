"""Read-only recruiting labels; canonical positions and saved ratings never change.

These are primary football jobs, not the depth chart's emergency fallbacks.
A rush edge is not advertised as an interior end or an off-ball linebacker.
"""
import defense_roles as DR
from stable import stable_seed


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def team_front(team_or_gm):
    if isinstance(team_or_gm, str):
        return DR.front_family(team_or_gm)
    gm = _get(team_or_gm, 'gm', team_or_gm)
    if isinstance(gm, dict):
        front = gm.get('def_front', '4-3')
        return front if front in ('4-3', '3-4') else ('3-4' if float(gm.get('box', .5)) >= .5 else '4-3')
    return DR.coach_front(gm)


def fa_positions(player, team_or_gm):
    """Eligible recruiting filter keys, primary first, with no player mutation.

    Either side of an edge/interior/inside-LB pair is a recruiting possibility;
    actual assignment still respects the depth chart, availability and ratings.
    """
    pos = _get(player, 'pos', _get(player, 'madden_position', ''))
    odd = team_front(team_or_gm) == '3-4'
    if pos in ('LEDG', 'REDG'):
        roles = ('LOLB', 'ROLB') if odd else ('LEDG', 'REDG')
        return roles if pos == 'LEDG' else roles[::-1]
    if odd and pos == 'DT':
        ratings = _get(player, 'ratings', player)
        weight = _get(player, 'weight', _get(player, 'weight_lbs'))
        strength = _get(ratings, 'strength_rating')
        shedding = _get(ratings, 'block_shedding_rating')
        power = float(_get(ratings, 'power_moves_rating', 70) or 70)
        finesse = float(_get(ratings, 'finesse_moves_rating', 70) or 70)
        if weight is None and strength is None and shedding is None:
            return ('NT', 'LE', 'RE')  # legacy records without any profile
        strength, shedding = float(strength or 70), float(shedding or 70)
        mass = float(weight or 305)
        anchor = .55 * strength + .45 * shedding
        nose = mass >= 315 or (mass >= 300 and anchor >= max(power, finesse) + 5)
        can_nose = mass >= 305 or (mass >= 295 and strength >= 85 and shedding >= 78)
        # Side is interchangeable for recruiting; keep the label stable across loads.
        ends = ('LE', 'RE') if stable_seed(_get(player, 'pid', _get(player, 'name', ''))) % 2 == 0 else ('RE', 'LE')
        return ('NT',) + ends if nose else ends + (('NT',) if can_nose else ())
    if odd and pos in ('MIKE', 'WILL', 'SAM'):
        return ('LILB', 'RILB') if pos == 'MIKE' else ('RILB', 'LILB')
    return ('MLB' if pos == 'MIKE' else pos,)


def fa_position(player, team_or_gm):
    return fa_positions(player, team_or_gm)[0]


def fa_position_filters(team_or_gm):
    """OL/DL/LB/DB group payload; retain existing QB/HB/FB/WR/TE/K/P/LS chips."""
    odd = team_front(team_or_gm) == '3-4'
    groups = (
        ('OL', ('LT', 'LG', 'C', 'RG', 'RT')),
        ('DL', ('LE', 'NT', 'RE') if odd else ('LEDG', 'DT', 'REDG')),
        ('LB', ('LOLB', 'LILB', 'RILB', 'ROLB') if odd else ('WILL', 'MLB', 'SAM')),
        ('DB', ('CB', 'FS', 'SS')),
    )
    return [dict(group=group, positions=[dict(key=key, label=key) for key in keys])
            for group, keys in groups]
