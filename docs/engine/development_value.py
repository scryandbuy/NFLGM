"""Bounded public development value; never reads a player's hidden ceiling."""


def development_credit(dev, age, overall, years, visible_range=None):
    """Return 0..1 growth credit, shared by trades and roster planning.

    Full age credit through 23, fading to zero at 29. One controlled year
    receives a quarter of the credit; four receive all of it. Unknown growth
    room receives a conservative allowance, never a hidden-potential lookup.
    """
    tier = {'star': .35, 'rare': .35, 'superstar': .65, 'epic': .65,
            'xfactor': 1., 'legendary': 1.}.get(str(dev).lower(), 0.)
    youth = max(0., min(1., (29. - float(age)) / 6.))
    control = max(0., min(1., float(years) / 4.))
    room = max(0., (sum(visible_range) / len(visible_range) if visible_range else
                    min(99., float(overall) + 3.)) - float(overall))
    return tier * youth * control * min(1., room / 10.)


def player_credit(player):
    from ceiling_knowledge import observed_range
    return development_credit(getattr(player, 'dev', 'normal'), player.age, player.ovr,
                              getattr(getattr(player, 'contract', None), 'years', 0),
                              observed_range(player))
