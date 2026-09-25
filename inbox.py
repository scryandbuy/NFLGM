"""
THE INBOX. Every message to the user lands here, the way Football Manager
does it: a trade offer in week 7, a note that a class has been scouted, a
contract about to expire. Each message has a kind, a sender, a subject, a
body, a payload the screen can act on, a status and an expiry.

Trade offers carry the offer itself in the payload; accept() executes it
through league.trade with the cap checks the trade engine already applies,
decline() closes it, and anything left past its expiry is expired on the
next advance. The AI never sees the inbox; it only writes to it.
"""
import itertools

_ids = itertools.count(1)


def _box(league):
    if not hasattr(league, 'inbox') or league.inbox is None:
        league.inbox = []
    return league.inbox


def post(league, kind, subject, body, sender=None, payload=None, expires_week=None):
    m = dict(id=next(_ids), year=league.year, week=league.week, kind=kind,
             sender=sender, subject=subject, body=body, payload=payload or {},
             status='unread', expires_week=expires_week)
    _box(league).append(m)
    return m


def pending(league, kind=None):
    return [m for m in _box(league) if m.get('status', 'unread') in ('unread', 'open')
            and (kind is None or m.get('kind') == kind)]


def expire(league, week):
    """Close anything past its expiry. Called at every advance."""
    n = 0
    for m in _box(league):
        if m.get('status', 'unread') in ('unread', 'open') and m.get('expires_week') is not None \
                and (week > m['expires_week'] or m['year'] < league.year):
            m['status'] = 'expired'; n += 1
    return n


def read(league, msg_id):
    for m in _box(league):
        if m['id'] == msg_id and m['status'] == 'unread':
            m['status'] = 'open'
            return m
    return next((m for m in _box(league) if m['id'] == msg_id), None)


# ------------------------------------------------------------ trade offers
def post_trade_offer(league, buyer, user_team, sends, gets, why, expires_week):
    """
    sends: assets the buyer gives (pids or DraftPick objects); gets: pids the
    buyer wants from the user. Stored as ids so the inbox survives a save.
    """
    def key(x):
        return x if isinstance(x, str) else dict(pick=True, year=x.year, round=x.round,
                                                  original=x.original, selection=x.selection)
    names = ', '.join(league.players[g].name for g in gets)
    body = (f"{league.teams[buyer].name if hasattr(league.teams[buyer], 'name') else buyer} would like "
            f"{names}. {why}")
    return post(league, 'trade_offer', f'Trade offer from {buyer} for {names}', body, sender=buyer,
                payload=dict(buyer=buyer, sends=[key(x) for x in sends], gets=list(gets)),
                expires_week=expires_week)


def _resolve(league, x, owner):
    if isinstance(x, str):
        return x
    for pk in league.teams[owner].picks:
        if pk.year == x['year'] and pk.round == x['round'] and pk.original == x['original']:
            return pk
    raise ValueError('pick no longer held')


def accept(league, msg_id, user_team):
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if m is None or m['kind'] != 'trade_offer' or m['status'] not in ('unread', 'open'):
        raise ValueError('no open offer with that id')
    p = m['payload']
    sends = [_resolve(league, x, p['buyer']) for x in p['sends']]
    league.trade(p['buyer'], user_team, sends, p['gets'])
    m['status'] = 'accepted'
    league.log('inbox_trade', buyer=p['buyer'], gets=p['gets'],
               sent=[x if isinstance(x, str) else x.selection or f"R{x.round} {x.year}" for x in sends])
    return m


def decline(league, msg_id):
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if m is not None and m['status'] in ('unread', 'open'):
        m['status'] = 'declined'
    return m


def news(league, subject, body, payload=None):
    """A league-wide item: something that happened elsewhere and the GM should know. Read-only, tagged for the League filter."""
    return post(league, 'league', subject, body, sender='league', payload=payload)
