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
import json
import re

_ids = itertools.count(1)


def player_name(player, label=None):
    """An explicit mention for inbox composition; post stores plain text + spans."""
    if player is None:
        return label or 'Player'
    return '\x1e' + json.dumps([str(player.pid), label if label is not None else player.name], ensure_ascii=True) + '\x1f'


def _mentions(text):
    spans, parts, end, length = [], [], 0, 0
    for match in re.finditer(r'\x1e([^\x1f]*)\x1f', str(text)):
        prefix = str(text)[end:match.start()]
        parts.append(prefix)
        length += len(prefix.encode('utf-16-le')) // 2
        pid, label = json.loads(match[1])
        size = len(label.encode('utf-16-le')) // 2
        spans.append(dict(start=length, end=length+size, kind='player', id=pid, name=label))
        parts.append(label)
        length += size
        end = match.end()
    parts.append(str(text)[end:])
    return ''.join(parts), spans


def reference_spans(text, refs, existing=()):
    """Freeze reliable legacy/payload matches without replacing explicit occurrences."""
    spans = list(existing)
    names = {}
    for ref in refs:
        if ref['kind'] == 'player': names.setdefault(ref['name'], []).append(ref)
    for name, choices in names.items():
        if len({r['id'] for r in choices}) != 1: continue
        for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text):
            start = len(text[:match.start()].encode('utf-16-le')) // 2
            end = start + len(name.encode('utf-16-le')) // 2
            if not any(start < r['end'] and end > r['start'] for r in spans):
                spans.append(dict(start=start, end=end, **{k:choices[0][k] for k in ('kind','id','name')}))
    return sorted(spans, key=lambda r:r['start'])


def _box(league):
    if not hasattr(league, 'inbox') or league.inbox is None:
        league.inbox = []
    return league.inbox


def post(league, kind, subject, body, sender=None, payload=None, expires_week=None):
    subject, subject_refs = _mentions(subject)
    body, body_refs = _mentions(body)
    m = dict(id=next(_ids), year=league.year, week=league.week, kind=kind,
             sender=sender, subject=subject, body=body, payload=payload or {},
             status='unread', expires_week=expires_week)
    m['entities'] = entity_references(league, str(subject) + '\n' + str(body), payload)
    m['mentions'] = dict(subject=subject_refs, body=body_refs)
    for ref in subject_refs + body_refs:
        if not any(r['kind'] == ref['kind'] and r['id'] == ref['id'] for r in m['entities']):
            m['entities'].append({k: ref[k] for k in ('kind', 'id', 'name')})
    for field in ('subject', 'body'):
        m['mentions'][field] = reference_spans(m[field], m['entities'], m['mentions'][field])
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
    names = ', '.join(player_name(league.players[g]) for g in gets)
    body = (f"{league.teams[buyer].name if hasattr(league.teams[buyer], 'name') else buyer} would like "
            f"{names}. {why}")
    return post(league, 'trade_offer', f'Trade offer from {buyer} for {names}', body, sender=buyer,
                payload=dict(buyer=buyer, user_team=user_team, sends=[key(x) for x in sends], gets=list(gets)),
                expires_week=expires_week)


def _resolve(league, x, owner):
    if isinstance(x, str):
        return x
    for pk in league.teams[owner].picks:
        if pk.year == x['year'] and pk.round == x['round'] and pk.original == x['original'] and not pk.used_on and pk.owner == owner:
            return pk
    raise ValueError('pick no longer held')


def accept(league, msg_id, user_team):
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if m is None or m['kind'] != 'trade_offer' or m['status'] not in ('unread', 'open'):
        raise ValueError('no open offer with that id')
    p = m['payload']
    if p.get('user_team', user_team) != user_team or p['buyer'] == user_team:
        raise ValueError('this offer belongs to another team')
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


def counter(league, msg_id, user_team):
    """Resolve the original offer and retain a resumable, typed counter draft."""
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if not m or m.get('kind') != 'trade_offer' or m.get('status') not in ('unread', 'open', 'countered'):
        raise ValueError('no open offer to counter')
    pl = m['payload']
    if pl.get('user_team', user_team) != user_team or pl['buyer'] == user_team:
        raise ValueError('this offer belongs to another team')
    if m['status'] == 'countered':
        draft = pl.get('counter')
        if not draft or draft.get('state') not in ('draft', 'declined'):
            raise ValueError('this counter is already closed')
        return draft
    def asset(x):
        return dict(kind='player', id=x) if isinstance(x, str) else dict(kind='pick', id=f"{x['year']}-{x['round']}-{x['original']}")
    draft = dict(other=pl['buyer'], a=[asset(x) for x in pl['gets']],
                 b=[asset(x) for x in pl['sends']], state='draft')
    pl['counter'] = draft
    m['status'] = 'countered'
    return draft


def news(league, subject, body, payload=None):
    """A league-wide item: something that happened elsewhere and the GM should know. Read-only, tagged for the League filter."""
    return post(league, 'league', subject, body, sender='league', payload=payload)


DECISION_KINDS = {'trade_offer', 'match_request', 'gameplan', 'game_plan',
                  'offer_sheet', 'contract_year', 'injury_decision', 'roster', 'exit'}


def is_decision(message):
    """Whether this particular message still represents an action."""
    if message.get('status', 'unread') not in ('unread', 'open'):
        return False
    if message.get('resolved') or message.get('needs_decision') is False:
        return False
    kind = message.get('kind')
    if kind == 'staff':
        payload = message.get('payload') or {}
        return (payload.get('event') != 'retirement'
                and not message.get('subject', '').endswith(' is retiring')
                and bool(payload.get('poach') or payload.get('role')))
    return kind in DECISION_KINDS


def reconcile(league):
    """Repair legacy/stale mail from durable entity state; never perform its action.

    Session calls this after loading and before exposing or blocking on mail.
    Producers/actions also call it when their entity changes.
    """
    closed = 0
    user = getattr(league, 'user_team', None)
    team = getattr(league, 'teams', {}).get(user)
    year, week = getattr(league, 'year', None), getattr(league, 'week', None)
    for m in _box(league):
        if m.get('status', 'unread') not in ('unread', 'open'):
            continue
        pl = m.get('payload') or {}
        kind = m.get('kind')
        done = bool(m.get('resolved'))
        if kind == 'staff':
            if pl.get('poach'):
                request = next((r for r in getattr(league, 'poaches', []) or []
                                if r['id'] == pl['poach']), None)
                done = request is None or request.get('state') != 'open'
            elif pl.get('event') == 'retirement' or m.get('subject', '').endswith(' is retiring'):
                m['needs_decision'] = False
            elif pl.get('role') and team is not None:
                coach = (getattr(team, 'staff', {}) or {}).get(pl['role'])
                # Both a vacancy and an expired deal are settled by an employed,
                # contracted coach in the slot, including a replacement hire.
                done = coach is not None and coach.years > 0
                if pl.get('coach') or m.get('subject', '').endswith("'s contract is up"):
                    done = done or coach is None or (pl.get('coach') and coach.name != pl['coach'])
                done = done or (year is not None and m.get('year', year) < year)
            else:
                m['needs_decision'] = False
        elif kind == 'contract_year':
            p = league.player(pl.get('pid')) if pl.get('pid') else None
            done = (p is None or p.team != user or not p.contract or p.contract.years != 1
                    or (year is not None and m.get('year', year) < year))
        elif kind == 'exit':
            meetings = (getattr(league, 'exit_meetings', {}) or {}).get(str(m.get('year', year)))
            if meetings is not None:
                done = all(mt.get('answer') or league.player(mt.get('pid')) is None for mt in meetings)
            done = done or (year is not None and m.get('year', year) < year)
        elif kind == 'injury_decision':
            # Legacy listings were posted before the league clock rolled, so
            # their message week may be one week behind the actual decision.
            # Their expiry was target + 1; new listings use target for both.
            stored_week, expiry = m.get('week'), m.get('expires_week')
            if (isinstance(stored_week, int) and isinstance(expiry, int)
                    and expiry > stored_week):
                m['week'] = expiry - 1
                m['expires_week'] = expiry - 1
            done = ((year is not None and m.get('year', year) != year)
                    or (week is not None and m.get('week', week) < week))
            schedule = getattr(league, 'schedule', None)
            target_week = m.get('week', week)
            if schedule is not None and target_week is not None:
                done = done or not any(w == target_week and user in (away, home)
                                       for w, away, home, *_ in schedule)
        elif kind == 'offer_sheet':
            # Old saves may contain CPU-only requests in the shared inbox.
            if m.get('team', pl.get('team')) != user:
                m['needs_decision'] = False
            p = league.player(m.get('pid', pl.get('pid')))
            done = done or p is None or getattr(p, 'retired', False)
            if p is not None:
                done = done or p.team != m.get('team', pl.get('team')) or getattr(p, 'fa_class', None) != 'tendered'
        if done:
            m['status'] = 'done'
            closed += 1
    return closed

def body_rows(league, message):
    """Readable digest rows, including messages already stored in older saves.

    Preserve commas/semicolons inside player details, and do not split names,
    decimal salaries or ordinary sentences into fragments.
    """
    import re
    body = str(message.get('body') or '')
    explicit = (message.get('payload') or {}).get('body_rows')
    if isinstance(explicit, list):
        return [str(line) for line in explicit if str(line).strip()]
    names = {p.name for p in getattr(league, 'players', {}).values()
             if getattr(p, 'name', None) and p.name in body}
    positions = r'QB|HB|RB|FB|WR|TE|LT|LG|C|RG|RT|LEDG|REDG|LE|RE|DT|NT|MIKE|WILL|SAM|MLB|LOLB|ROLB|CB|FS|SS|K|P|LS|OC|DC|HC'
    record = r"[A-Z][A-Za-z’'.-]*(?:\s+[A-Z][A-Za-z’'.-]*){0,4}\s+\((?:" + positions + r")(?:\b)"
    starts = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    starts = '(?:' + (starts + '|' if starts else '') + record + ')'
    body = re.sub(r'(?<![A-Z]\.)(?<=[.,;:])\s+(?=' + starts + ')', '\n', body)
    body = re.sub(r'\s+and\s+(?=' + starts + ')', '\n', body)
    rows, chars, depth = [], [], 0
    for char in body:
        if char == '(': depth += 1
        elif char == ')': depth = max(0, depth - 1)
        # A semicolon in ordinary prose is punctuation, not a new digest row.
        # Player-list boundaries above already become newlines when appropriate.
        if char == '\n' or (depth == 0 and char in '·•'):
            line = ''.join(chars).strip().rstrip(',;')
            if line: rows.append(line)
            chars = []
        else:
            chars.append(char)
    line = ''.join(chars).strip().rstrip(',;')
    if line: rows.append(line)
    return rows

# Name navigation data is derived and never serialized as part of the league.
def entity_catalog(league, known=None):
    """One directory per roster generation; unchanged page reads return no payload."""
    players = getattr(league, 'players', {})
    key = f'{id(league)}:{getattr(league, "year", 0)}:{len(players)}'
    if known == key:
        return None
    cached = getattr(league, '_entity_catalog', None)
    if cached and cached['key'] == key:
        return cached['data']
    import re
    from views import CLUB_NAME, CLUB_DISPLAY_ABBR
    rows = [dict(kind='player', id=str(p.pid), name=p.name,
                 aliases=[p.name[0]+'. '+p.name.split(' ',1)[1]] if ' ' in p.name else [])
            for p in players.values() if getattr(p, 'name', None) and getattr(p, 'pid', None) is not None]
    rows += [dict(kind='team', id=a, name=CLUB_NAME.get(a, a),
                  aliases=list(dict.fromkeys([a, CLUB_DISPLAY_ABBR.get(a,a)]))) for a in getattr(league, 'teams', {})]
    names = {}
    for row in rows:
        names.setdefault(row['name'], []).append(row)
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True)) + r')(?!\w)') if names else None
    data = dict(key=key, entities=rows)
    league._entity_catalog = dict(key=key, data=data, names=names, pattern=pattern)
    return data


def entity_references(league, text, payload=None):
    """Persist unambiguous identities, using explicit payload IDs for namesakes."""
    entity_catalog(league)
    cache = league._entity_catalog
    if not cache['pattern']: return []
    explicit = set()
    def visit(value):
        if isinstance(value, dict):
            for v in value.values(): visit(v)
        elif isinstance(value, (list, tuple)):
            for v in value: visit(v)
        elif isinstance(value, str):
            explicit.add(value)
            if value.startswith('player:'): explicit.add(value[7:])
            if value.startswith('club:player:'): explicit.add(value[12:])
    visit(payload or {})
    result = []
    for name in dict.fromkeys(m.group() for m in cache['pattern'].finditer(text)):
        choices = cache['names'][name]
        selected = [r for r in choices if r['id'] in explicit]
        if len(choices) == 1: selected = choices
        if len(selected) == 1: result.append(dict(selected[0]))
    return result
