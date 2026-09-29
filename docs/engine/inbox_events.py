"""Notification identities survive deleting mail and saving/loading the league."""
import inbox as IB


def ledger(league):
    if getattr(league, 'notes_sent', None) is None:
        league.notes_sent = {}
    return league.notes_sent.setdefault('_inbox_events', {})


def seen(league, key):
    sent = ledger(league)
    if key in sent:
        return True
    # Adopt keys from old saves before their messages can be cleared.
    if any((m.get('payload') or {}).get('key') == key for m in getattr(league, 'inbox', [])):
        sent[key] = True
        return True
    return False


def remember(league):
    sent = ledger(league)
    for m in getattr(league, 'inbox', []):
        key = (m.get('payload') or {}).get('key')
        if key and not key.startswith('roster-'):
            sent[key] = True


def post(league, key, kind, subject, body, **kwargs):
    if seen(league, key):
        return None
    payload = dict(kwargs.pop('payload', None) or {})
    payload['key'] = key
    msg = IB.post(league, kind, subject, body, payload=payload, **kwargs)
    ledger(league)[key] = True
    return msg
