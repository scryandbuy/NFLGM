"""Visible offseason stops and compatibility with the original saved indices."""
VERSION = 1
STEPS = [
    ('Season Awards', 'step_awards'),  # internal close-season compatibility
    ('Retirements and Development', 'step_development_roll'),
    ('Coaching Carousel', 'step_coaching'),
    ('Re-sign: Tags and Tenders', 'step_extensions'),
    ('Free Agency: Round 1', 'step_fa_1'),
    ('Free Agency: Round 2', 'step_fa_2'),
    ('Free Agency: Round 3', 'step_fa_3'),
    ('Free Agency: Market Closes', 'step_fa_close'),
    ('The Spring: Combine and Pro Days', 'step_spring'),
    ('The Spring: Private Visits', 'step_visits'),
    ('The Draft', 'step_draft'),
    ("Camp and Next Year's Class", 'step_camp'),
    ('Cut-Down to 53', 'step_cutdown'),
]
# Calendar anchors retain their original meaning; birthdays do not move when
# two UI stops are combined. Rollover still crosses March 10/11 after retirement.
AGE_INDICES = (0, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)


def saved_progress(saved):
    stop = tuple(saved.get('_stop', ('week', 1)))
    if saved.get('_offseason_calendar_version') == VERSION:
        return stop, dict(saved.get('_offseason_progress') or {})
    if stop[0] != 'offseason':
        return stop, {}
    old = int(stop[1])
    year = int(saved['year']) - (old >= 4)
    # Earlier saves already ran their carousel before retirement. Do not fire,
    # hire, age staff or resolve the same season twice when adopting this order.
    progress = dict(year=year, development_done=old >= 3,
                    development_market_done=old >= 3,
                    roll_done=old >= 4, coaching_done=old >= 2)
    index = 1 if old <= 3 else 2 if old == 4 else old - 2
    return ('offseason', index), progress


def team_context(league):
    """Completed-season decision evidence, retained after records reset to 0-0."""
    return dict(records={a: list(t.record) for a, t in league.teams.items()},
                histories={a: t.hist() for a, t in league.teams.items()})
