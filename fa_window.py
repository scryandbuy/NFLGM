"""League-wide pause between the closed FA market and the finished draft."""
MESSAGE = 'Free Agency reopens after the draft, once undrafted rookies join the pool.'

def closed(league):
    return (getattr(league, 'league_notes_sent', None) or {}).get('_fa_closed_until_draft') == league.year and league.phase in ('offseason','draft','free_agency')

def set_closed(league, value):
    if getattr(league, 'league_notes_sent', None) is None: league.league_notes_sent = {}
    league.league_notes_sent['_fa_closed_until_draft'] = league.year if value else None

def sync(session):
    stop = session.stop
    if stop[0] != 'offseason': return
    names = [s[1] for s in session.OFFSEASON]
    draft_finished = bool(getattr(getattr(session, 'draft', None), 'done', False))
    set_closed(session.L, names.index('step_fa_close') < stop[1] <= names.index('step_draft') and not draft_finished)

def require_open(league):
    if closed(league): raise ValueError(MESSAGE)
