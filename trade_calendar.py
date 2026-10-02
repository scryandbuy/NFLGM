"""Shared transaction calendar, independent of UI and AI scheduling."""
TRADE_DEADLINE_WEEK = 9
OPEN_PHASES = frozenset(('offseason', 'free_agency', 'draft', 'camp', 'preseason'))


def trading_open(league):
    phase = getattr(league, 'phase', None)
    if phase in OPEN_PHASES:
        return True
    return phase == 'regular' and 1 <= int(getattr(league, 'week', 0) or 0) <= TRADE_DEADLINE_WEEK


def require_open(league):
    if not trading_open(league):
        raise ValueError('The trade deadline has passed. Trades reopen after the season.')


def offer_expired(league, message):
    if not trading_open(league) or message.get('year', league.year) != league.year:
        return True
    phase = message.get('phase')
    if phase == 'regular' and league.phase != 'regular':
        return True
    if league.phase == 'regular':
        expiry = message.get('expires_week')
        return expiry is not None and int(league.week or 0) > int(expiry)
    return False
