"""Read-only recruiting labels; canonical positions and saved ratings never change.

These are primary football jobs, not the depth chart's emergency fallbacks.
A rush edge is not advertised as an interior end or an off-ball linebacker.
"""
import defense_roles as DR


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
        return ('NT', 'LE', 'RE')
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
