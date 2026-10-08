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


def mail_section(title, rows, columns=()):
    """Explicit display structure; strings may contain player_name mentions."""
    return dict(title=title, columns=list(columns),
                rows=[list(row) if isinstance(row, (list, tuple)) else [row] for row in rows])


def trade_sections(a, b, a_sends, b_sends):
    from stadium_names import TEAM_NAMES
    sections = []
    for team, received in ((a, b_sends), (b, a_sends)):
        section = mail_section(f'{TEAM_NAMES.get(team, team)} Receive', received or ['No assets'])
        section['team'] = team
        sections.append(section)
    return sections


def _coaching_mail_layout(payload):
    """Join recorded departures to hires; never guess an unrecorded former club."""
    import copy
    sections = payload.get('mail_sections') or []
    old = [s for s in sections if s.get('columns') == ['Team', 'Role', 'Coach', 'Details']]
    if not old: return payload
    def text(cell):
        return str(cell.get('text', '') if isinstance(cell, dict) else cell)
    def cell(value):
        return dict(text=value, mentions=[])
    hires, departures, vacancies = [], [], []
    seen = set()
    for section in old:
        for row in section.get('rows', []):
            values = tuple(text(c) for c in row)
            if values in seen: continue
            seen.add(values)
            team, role, name, detail = (list(values) + [''] * 4)[:4]
            if section['title'].startswith('Jobs still open'):
                vacancies.append([team, role])
            elif section['title'].startswith('Hired'):
                hires.append((team, role, name))
            else:
                departures.append((team, name, detail))
    rows, used = [], set()
    for team, role, name in hires:
        matches = [i for i, d in enumerate(departures) if d[1] == name]
        # Names alone cannot disambiguate multiple hires/departures.
        match = matches[0] if len(matches) == 1 and sum(h[2] == name for h in hires) == 1 else None
        origin = departures[match][0] if match is not None else 'Not recorded'
        if match is not None: used.add(match)
        rows.append([name, origin, team, role])
    out = []
    if rows:
        out.append(mail_section(f'Hired ({len(rows)})', sorted(rows, key=lambda r: (r[2], r[3], r[0])),
                                ['Coach', 'From', 'To', 'New Role']))
    left = [[name, team, detail.split(' (', 1)[0] or 'Departed']
            for i, (team, name, detail) in enumerate(departures) if i not in used]
    if left:
        out.append(mail_section(f'Departures ({len(left)})', sorted(left, key=lambda r: (r[1], r[0])),
                                ['Coach', 'Left', 'Outcome']))
    if vacancies:
        out.append(mail_section(f'Jobs still open ({len(vacancies)})', vacancies, ['Team', 'Role']))
    for section in out:
        section['rows'] = [[cell(value) for value in row] for row in section['rows']]
    # Preserve unrelated notes; drop only the obsolete market preview and
    # duplicated carousel announcements from older consolidated messages.
    for section in sections:
        if section in old or section.get('title') == 'Notable coaching candidates': continue
        preserved = copy.deepcopy(section)
        preserved['rows'] = [row for row in preserved.get('rows', []) if not (
            len(row) == 1 and (re.fullmatch(r'.+ moved on from its head coach\..*', text(row[0]))
            or re.fullmatch(r'\d+ clubs? making coaching changes\.', text(row[0]))
            or text(row[0]) == 'Coaching changes this offseason.'))]
        if preserved['rows']: out.append(preserved)
    return dict(payload, mail_sections=out, mail_intro=dict(text='', mentions=[]))


def _transaction_mail_layout(message, payload):
    """Recover contract rows from saved wording without consulting current contracts."""
    import copy
    import re
    pattern = re.compile(r"^([A-Z]{2,4}) (sign|extend) (.+?) \(([^,]+), (\d+)\) for (?:a (\d+)-year deal averaging |(\d+) years? at )(\$[\d.]+m)(?: per year| a year)(?: \(.*?\))?\.$")
    sections = copy.deepcopy(payload.get('mail_sections') or [])
    if not sections:
        sections = [dict(title='', columns=[], rows=[[dict(text=line.strip(), mentions=[])]] )
                    for line in str(message.get('body') or '').splitlines() if line.strip()]
    result = []
    changed = False
    entities = message.get('entities') or []
    for section in sections:
        if section.get('columns'):
            if section.get('title') == 'Signings' and section['columns'][-1:] == ['Annual Average']:
                section['columns'][-1] = f"{message.get('year', '')} Cap Hit".strip()
                for saved_row in section['rows']:
                    saved_row[-1] = dict(text='—', mentions=[])
                changed = True
            result.append(section)
            continue
        for row in section.get('rows', []):
            cell = row[0] if len(row) == 1 else None
            text = cell.get('text', '') if isinstance(cell, dict) else str(cell or '')
            match = pattern.fullmatch(text)
            if not match:
                result.append(dict(section, rows=[row]))
                continue
            team, action, player, pos, ovr, years_new, years_old, annual = match.groups()
            title = 'Signings' if action == 'sign' else 'Extensions'
            columns = ['Team', 'Player', 'Pos', 'OVR', 'Years', 'Annual Average']
            if action == 'sign':
                columns[-1] = f"{message.get('year', '')} Cap Hit".strip()
                annual = '—'  # Old prose records average pay, not the year's cap charge.
            values = [team, player, pos, ovr, years_new or years_old, annual]
            cells = [dict(text=v, mentions=reference_spans(v, entities, [])) for v in values]
            if result and result[-1].get('title') == title and result[-1].get('columns') == columns:
                result[-1]['rows'].append(cells)
            else:
                result.append(dict(title=title, columns=columns, rows=[cells]))
            changed = True
    # Old digests converted the announcement prose into a second table while
    # retaining the authoritative structured row. Prefer its recorded cap hit.
    tables, normalized = {}, []
    for section in result:
        columns = section.get('columns') or []
        if section.get('title') not in ('Signings', 'Extensions') or len(columns) != 6:
            normalized.append(section)
            continue
        key = (section['title'], tuple(columns))
        target = tables.get(key)
        if target is None:
            target = dict(section, rows=[])
            tables[key] = target
            normalized.append(target)
        else:
            changed = True
        for row in section['rows']:
            def text(cell):
                return cell.get('text', '') if isinstance(cell, dict) else str(cell)
            match = next((old for old in target['rows'] if len(old) == len(row) == 6
                and [text(c) for c in old[:5]] == [text(c) for c in row[:5]]
                and (text(old[-1]) == text(row[-1]) or text(old[-1]) == '—' or text(row[-1]) == '—')), None)
            if match is None:
                target['rows'].append(row)
            else:
                if text(match[-1]) == '—': match[-1] = row[-1]
                changed = True
    intro = payload.get('mail_intro') or dict(text='', mentions=[])
    announcement = pattern.fullmatch(intro.get('text', '').strip())
    if announcement:
        team, action, player, pos, ovr, ny, oy, annual = announcement.groups()
        values = [team, player, pos, ovr, ny or oy]
        title = 'Signings' if action == 'sign' else 'Extensions'
        if any(s.get('title') == title and any(
                [c.get('text', '') if isinstance(c, dict) else str(c) for c in row[:5]] == values
                for row in s.get('rows', [])) for s in normalized):
            intro = dict(text='', mentions=[])
            changed = True
    if changed:
        return dict(payload, mail_sections=normalized, mail_intro=intro)
    return payload


def _roster_update_mail_layout(message, payload):
    """Tabulate saved announcements using only their original text and links."""
    import copy
    import re
    kind, subject = message.get('kind'), message.get('subject', '')
    injury = kind in ('injury', 'ir_ready') or subject == 'Injury Update'
    waiver = (kind == 'waiver_notice' and not subject.startswith('Available on waivers:')) or subject == 'Waiver Results'
    tags = kind == 'league'
    if not (injury or waiver or tags): return payload
    if injury and subject.startswith(('Short at ', 'Emergency at ')): return payload
    sections = copy.deepcopy(payload.get('mail_sections') or [])
    if not sections:
        lines = str(message.get('body') or '').splitlines()
        # A failed cap claim's player is recorded in its subject, not its body.
        if waiver and subject.startswith('Claim failed:'):
            lines = [subject + ' — ' + str(message.get('body') or '')]
        sections = [dict(title='', columns=[], rows=[[dict(text=line, mentions=[])] for line in lines if line.strip()])]
    result, changed = [], False
    entities = message.get('entities') or []
    for section in sections:
        if section.get('columns'):
            result.append(section); continue
        rows = section.get('rows', [])
        if injury and all(len(row) == 1 and isinstance(row[0], dict) for row in rows):
            rows = [[dict(text=line, mentions=[])] for row in rows
                    for line in row[0].get('text', '').splitlines() if line.strip()]
        for row in rows:
            cell = row[0] if len(row) == 1 else None
            text = cell.get('text', '') if isinstance(cell, dict) else str(cell or '')
            values = None
            if injury:
                match = re.fullmatch(r'(.+?) \(([^,)]+)(?:, \d+ overall)?\) (.+)', text)
                if match:
                    player, pos, detail = match.groups()
                    out = re.fullmatch(r'is out (.+?) \(([^)]+)\)(.*)', detail)
                    if out:
                        duration, condition, note = out.groups()
                        detail = condition + (note.rstrip('.') if note.startswith(';') else '')
                        values = [player, pos, detail, duration.removeprefix('for ')]
                    elif detail.startswith('is back from his injury'):
                        values = [player, pos, 'Cleared to play', 'Available']
                    else:
                        # Keep activation restrictions and medical details intact.
                        values = [player, pos, detail, '—']
                    title, columns = 'Injury Updates', ['Player', 'Pos', 'Status', 'Expected Return']
            elif waiver:
                patterns = [
                    (r'You were awarded (.+?) \(([^,]+), \d+\) off waivers from ([A-Z]+)\. (.+)', lambda m:[m[1],m[3],'Awarded',m[4]]),
                    (r'You claimed (.+?) \(([^)]+)\) and ([A-Z]+) held the higher priority\. He is theirs\.', lambda m:[m[1],m[3],'Claim lost','Higher waiver priority']),
                    (r'(.+?) \(([^)]+)\) was signed by ([A-Z]+) before the wire cleared\. Your claim did not go through\.', lambda m:[m[1],m[3],'Claim void','Signed before waivers cleared']),
                    (r'You waived (.+?) for the practice squad and ([A-Z]+) claimed him off the wire\. He is theirs\.', lambda m:[m[1],m[2],'Claimed','Claimed by another team']),
                    (r'(.+?) cleared waivers and is on your practice squad\.', lambda m:[m[1],'Your team','Cleared','Joined practice squad']),
                    (r'(.+?) cleared waivers but the squad had no room for him under its rules; he is a free agent\.', lambda m:[m[1],'—','Cleared','Free agent; practice squad full']),
                    (r'Claim failed: (.+?) — (.+)', lambda m:[m[1],'Your team','Claim failed',m[2]])]
                for pattern, convert in patterns:
                    match = re.fullmatch(pattern, text)
                    if match:
                        values = convert(match); break
                title, columns = 'Waiver Results', ['Player', 'Team', 'Outcome', 'Details']
            else:
                match = re.fullmatch(r'([A-Z]+) place the franchise tag on (.+?) \(([^,]+), \d+\)(?: at (\$[\d.]+m))?\.', text)
                if match: values = [match[1],match[2],match[3],match[4] or '—']
                if not values and section.get('title', '').lower() == 'franchise tags':
                    match = re.fullmatch(r'([A-Z]+) · (.+?) · ([^·]+) · (\$[\d.]+m)', text)
                    if match: values = list(match.groups())
                title, columns = 'Franchise Tags', ['Team', 'Player', 'Pos', 'Tag Amount']
            if values is None:
                result.append(dict(section, rows=[row])); continue
            cells = [dict(text=v, mentions=reference_spans(v, entities, [])) for v in values]
            if result and result[-1].get('title') == title and result[-1].get('columns') == columns:
                result[-1]['rows'].append(cells)
            else: result.append(dict(title=title, columns=columns, rows=[cells]))
            changed = True
    return dict(payload, mail_sections=result, mail_intro=payload.get('mail_intro') or dict(text='', mentions=[])) if changed else payload


def mail_layout(message):
    """Display old structured regression mail and legacy CPU trades consistently."""
    import copy
    import re
    payload = dict(message.get('payload') or {})
    if message.get('kind') == 'league':
        payload = _transaction_mail_layout(message, payload)
    payload = _roster_update_mail_layout(message, payload)
    if message.get('kind') == 'contract_year':
        # Render saved announcements from their original contract snapshot.
        # Never substitute today's player ratings or salary into old mail.
        pattern = r"([^\n|]+?) \(([^,]+), (\d+), age (\d+)\) is in the last year of his deal at (\$[\d.]+m)\. He can be extended now; his agent will price him at the market\."
        records = re.findall(pattern, str(message.get('body') or ''))
        if records:
            rows = [[dict(text=value.strip(), mentions=reference_spans(value.strip(), message.get('entities') or [], []))
                     for value in record] for record in records]
            payload.update(mail_sections=[dict(title='', columns=['Player', 'Pos', 'OVR', 'Age', 'Annual Salary'], rows=rows)],
                           mail_intro=dict(text='These players are entering the final year of their contracts and can negotiate extensions.', mentions=[]))
    coaching = (str(message.get('subject', '')).startswith('Coaching carousel summary')
                or message.get('subject') == 'Coaching Changes')
    if coaching and payload.get('mail_sections'):
        return _coaching_mail_layout(payload)
    if str(message.get('subject', '')).startswith('Coaching carousel summary') and not payload.get('mail_sections'):
        lines = payload.get('body_rows') or str(message.get('body') or '').splitlines()
        sections = []
        section = None
        for line in lines:
            line = str(line).strip()
            if re.fullmatch(r'(Hired|Fired / released / replaced|Other departures|Jobs still open) \(\d+\)', line):
                title = line.replace('Fired / released / replaced', 'Departures').replace('Other departures', 'Other Changes')
                section = dict(title=title, columns=['Team', 'Role', 'Coach', 'Details'], rows=[])
                sections.append(section)
            elif section is not None and line and line != 'None':
                cells = line.split(' — ', 3)
                cells += [''] * (4-len(cells))
                if section['title'].startswith('Hired'):
                    cells[3] = re.sub(r'^Hired(?: \((.*)\))?$', lambda m: m.group(1) or '', cells[3])
                    if cells[3] == 'from the pool': cells[3] = ''
                section['rows'].append([dict(text=value, mentions=reference_spans(value, message.get('entities') or [], [])) for value in cells])
        if sections:
            payload.update(mail_sections=[s for s in sections if s['rows']],
                           mail_intro=dict(text='Coaching changes this offseason.' if any(s['rows'] for s in sections) else 'No coaching changes this offseason.', mentions=[]))
            return _coaching_mail_layout(payload)
    if payload.get('link') == 'league:bracket' and not payload.get('mail_sections'):
        # Older playoff letters used single newlines, which the prose renderer
        # correctly treats as wrapping. Recover only that exact saved format.
        intro, marker, fixtures = (message.get('body') or '').partition('The round\n')
        rows = []
        for line in fixtures.splitlines() if marker else []:
            match = re.fullmatch(r'(The \d+ seed .+? \([\d-]+\)|.+? \([\d-]+\)) at '
                                 r'(The \d+ seed .+? \([\d-]+\)|.+? \([\d-]+\)), (.+)', line)
            if not match: break
            rows.append([re.sub(r'^The (\d+) seed ', r'No. \1 ', cell) for cell in match.groups()])
        else:
            if rows:
                intro = intro.strip()
                intro = re.sub(r'^Your (.+) game: vs (.+) at home\. They finished ([\d-]+)\.$',
                               r'You host \2 (\3) in the \1.', intro)
                intro = re.sub(r'^Your (.+) game: at (.+?), .+\. They finished ([\d-]+)\.$',
                               r'You visit \2 (\3) in the \1.', intro)
                section = mail_section('Round Matchups', rows, ('Away Team', 'Home Team', 'Venue'))
                section['rows'] = [[dict(text=value, mentions=[]) for value in row] for row in rows]
                payload.update(mail_sections=[section], mail_intro=dict(text=intro, mentions=[]))
                return payload
    regression = payload.get('link') == 'club:regression' and payload.get('mail_sections')
    if regression: payload['mail_sections'] = copy.deepcopy(payload['mail_sections'])
    for section in (payload.get('mail_sections') or []) if regression else []:
        columns = section.get('columns') or []
        keep = [i for i, name in enumerate(columns) if name.lower() != 'ovr lost']
        if len(keep) != len(columns):
            section['columns'] = [columns[i] for i in keep]
            section['rows'] = [[row[i] for i in keep if i < len(row)] for row in section['rows']]
    if message.get('kind') == 'trade_offer' and not payload.get('mail_sections'):
        refs = message.get('entities') or []
        def saved_asset(item):
            if isinstance(item, dict) and item.get('pick'):
                from views import draft_year
                return f"{draft_year(item['year'])} R{item['round']} ({item['original']})"
            return next((r['name'] for r in refs if r.get('kind') == 'player' and r.get('id') == item), None)
        sends = [saved_asset(x) for x in payload.get('sends', [])]
        gets = [saved_asset(x) for x in payload.get('gets', [])]
        if sends and gets and all(x is not None for x in sends + gets) and payload.get('buyer') and payload.get('user_team'):
            sections = trade_sections(payload['buyer'], payload['user_team'], sends, gets)
            for section in sections:
                section['rows'] = [[dict(text=value, mentions=reference_spans(value, refs, [])) for value in row] for row in section['rows']]
            payload.update(mail_sections=sections, mail_intro=dict(text='', mentions=[]), mail_layout='trade')
            return payload
    if message.get('kind') == 'trade_done' and not payload.get('mail_sections'):
        old = re.fullmatch(r'You send (.+) to ([A-Z]+) for (.+)\.', message.get('body') or '')
        if old:
            sent, other, received = old.groups()
            sides = []
            for text in (sent, received):
                assets = re.findall(r'(?:^|, )(.+?\([^)]*\)|\d{4} R\d+)(?=, |$)', text)
                if ', '.join(assets) != text: return payload
                sides.append(assets)
            sections = [mail_section('You Send', sides[0]), mail_section('You Receive', sides[1])]
            for section in sections:
                section['rows'] = [[dict(text=value, mentions=reference_spans(value, message.get('entities') or [], [])) for value in row] for row in section['rows']]
            payload.update(mail_sections=sections, mail_intro=dict(text='', mentions=[]), mail_layout='trade')
            return payload
    if message.get('kind') != 'league' or payload.get('mail_sections'): return payload
    match = re.fullmatch(r'([A-Z]+) and ([A-Z]+) make a trade', message.get('subject', ''))
    if not match: return payload
    a, b = match.groups()
    body = message.get('body') or ''
    parts = re.fullmatch(re.escape(a) + r' send (.+) to ' + re.escape(b) + r' for (.+)\.', body)
    if not parts: return payload
    sides = []
    for side in parts.groups():
        if side == 'nothing': sides.append([]); continue
        assets = re.findall(r'(?:^|, )(.+?\([^)]*\)|a \d{4} [^,]+?-round pick)(?=, |$)', side)
        if ', '.join(assets) != side: return payload
        sides.append(assets)
    sections = trade_sections(a, b, *sides)
    for section in sections:
        section['rows'] = [[dict(text=value, mentions=reference_spans(value, message.get('entities') or [], [])) for value in row] for row in section['rows']]
    payload.update(mail_sections=sections, mail_intro=dict(text='', mentions=[]), mail_layout='trade')
    return payload


def post(league, kind, subject, body, sender=None, payload=None, expires_week=None):
    payload = dict(payload or {})
    sections = payload.get('mail_sections')
    if sections:
        # Preserve the plain body for exports, search, and older readers. Store
        # mention offsets within each cell as well as within that full body.
        def cell(value):
            text, refs = _mentions(str(value))
            return dict(text=text, mentions=refs)
        payload['mail_intro'] = cell(body)
        chunks = [body] if body else []
        normalized = []
        for section in sections:
            rows = section.get('rows') or []
            chunks.append('\n'.join([section.get('title') or ''] +
                                     [' | '.join(str(value) for value in row) for row in rows]))
            normalized.append(dict(title=section.get('title') or '', columns=section.get('columns') or [],
                                   rows=[[cell(value) for value in row] for row in rows]))
            if section.get('team'): normalized[-1]['team'] = section['team']
        payload['mail_sections'] = normalized
        body = '\n\n'.join(chunks)
    subject, subject_refs = _mentions(subject)
    body, body_refs = _mentions(body)
    m = dict(id=next(_ids), year=league.year, week=league.week, phase=league.phase, kind=kind,
             sender=sender, subject=subject, body=body, payload=payload or {},
             status='unread', expires_week=expires_week)
    m['entities'] = entity_references(league, str(subject) + '\n' + str(body), payload)
    m['mentions'] = dict(subject=subject_refs, body=body_refs)
    for ref in subject_refs + body_refs:
        if not any(r['kind'] == ref['kind'] and r['id'] == ref['id'] for r in m['entities']):
            m['entities'].append({k: ref[k] for k in ('kind', 'id', 'name')})
    for field in ('subject', 'body'):
        m['mentions'][field] = reference_spans(m[field], m['entities'], m['mentions'][field])
    if sections:
        cells = [payload['mail_intro']] + [c for s in payload['mail_sections'] for row in s['rows'] for c in row]
        for c in cells:
            c['mentions'] = reference_spans(c['text'], m['entities'], c['mentions'])
    _box(league).append(m)
    import inbox_digest
    return inbox_digest.append_draft_trade(league, m)


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
    import trades as TR
    if TR.trade_was_rejected(league, buyer, user_team, sends, gets): return None
    def key(x):
        return x if isinstance(x, str) else dict(pick=True, year=x.year, round=x.round,
                                                  original=x.original, selection=x.selection)
    names = ', '.join(player_name(league.players[g]) for g in gets)
    body = (f"{league.teams[buyer].name if hasattr(league.teams[buyer], 'name') else buyer} would like "
            f"{names}. {why}")
    def asset(x):
        if isinstance(x, str):
            p = league.player(x)
            return f'{player_name(p)} ({p.pos})' if p is not None else x
        from views import draft_year
        return f'{draft_year(x.year)} R{x.round} ({x.original})'
    body = why
    sections = trade_sections(buyer, user_team, [asset(x) for x in sends], [asset(x) for x in gets])
    return post(league, 'trade_offer', f'Trade offer from {buyer} for {names}', body, sender=buyer,
                payload=dict(buyer=buyer, user_team=user_team, sends=[key(x) for x in sends], gets=list(gets), mail_sections=sections, mail_layout='trade'),
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
    reconcile(league)
    if m['status'] not in ('unread', 'open'):
        raise ValueError('this offer is no longer valid')
    p = m['payload']
    if p.get('user_team', user_team) != user_team or p['buyer'] == user_team:
        raise ValueError('this offer belongs to another team')
    sends = [_resolve(league, x, p['buyer']) for x in p['sends']]
    import trades as TR
    decision = TR.cpu_trade_check(league, league.teams[p['buyer']], league.teams[user_team],
                                   sends, p['gets'], buyer=p['buyer'])
    if not decision['approved']:
        raise ValueError(decision['why'])
    # An old offer is not permission to spend a now-depleted pick portfolio.
    # Reuse the fresh effective margin; accepting mail never rerolls GM taste.
    margin = (decision.get('portfolio_gains') or {}).get(p['buyer'])
    cost = (decision.get('portfolio_costs') or {}).get(p['buyer'], 0.)
    if cost > 1e-9 and margin is not None and margin < -TR.ACCEPT_WINDOW - 1e-9:
        raise ValueError('This offer no longer justifies giving up those future roster options.')
    league.trade(p['buyer'], user_team, sends, p['gets'])
    m['status'] = 'accepted'
    league.log('inbox_trade', buyer=p['buyer'], gets=p['gets'],
               sent=[x if isinstance(x, str) else x.selection or f"R{x.round} {x.year}" for x in sends])
    return m


def decline(league, msg_id):
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if m is not None and m['status'] in ('unread', 'open'):
        if m.get('kind') == 'trade_offer':
            import trades as TR
            p = m.get('payload') or {}
            if all(k in p for k in ('buyer', 'user_team', 'sends', 'gets')):
                TR.remember_trade_rejection(league, p['buyer'], p['user_team'], p['sends'], p['gets'])
        m['status'] = 'declined'
    return m


def counter(league, msg_id, user_team):
    """Resolve the original offer and retain a resumable, typed counter draft."""
    m = next((m for m in _box(league) if m['id'] == msg_id), None)
    if not m or m.get('kind') != 'trade_offer' or m.get('status') not in ('unread', 'open', 'countered'):
        raise ValueError('no open offer to counter')
    from trade_calendar import offer_expired
    if offer_expired(league, m):
        m['status'] = 'expired'
        raise ValueError('This trade offer has expired.')
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
                  'offer_sheet', 'contract_year', 'injury_decision', 'roster', 'exit',
                  'scouting_focus'}


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
    for message in getattr(league, 'inbox', []) or []:
        report = (message.get('payload') or {}).get('report')
        if message.get('kind') == 'game_plan' and report:
            from gameplan_week import report_summary
            message['body'] = report_summary(report)
            message['subject'] = message['subject'].replace('Game plan: week ', 'Game Plan · Week ')
            message['mentions'] = dict(subject=reference_spans(message['subject'], message.get('entities') or [], []),
                                       body=reference_spans(message['body'], message.get('entities') or [], []))
    from inbox_digest import split_saved_transactions
    split_saved_transactions(league)
    from game_recap import combine_saved_reports
    combine_saved_reports(league)
    from league_notes import combine_saved_eliminations, combine_saved_clinches
    combine_saved_eliminations(league)
    combine_saved_clinches(league)
    from free_agency import fa_class
    for player in league.players.values():
        if (not player.retired and not player.contract
                and player.fa_class in (None, 'under_contract', 'signed')
                and player.team in league.teams
                and player.pid not in league.free_agents):
            player.fa_class = fa_class(player.accrued, 0)
    closed = 0
    user = getattr(league, 'user_team', None)
    team = getattr(league, 'teams', {}).get(user)
    year, week = getattr(league, 'year', None), getattr(league, 'week', None)
    for m in _box(league):
        from trade_calendar import offer_expired
        if (m.get('kind') == 'trade_offer'
                and m.get('status', 'unread') in ('unread', 'open', 'countered')
                and offer_expired(league, m)):
            m['status'] = 'expired'
            closed += 1
        if m.get('status', 'unread') not in ('unread', 'open'):
            continue
        pl = m.get('payload') or {}
        kind = m.get('kind')
        done = bool(m.get('resolved'))
        if kind == 'trade_offer':
            if (not m.get('phase') and league.phase == 'offseason'
                    and m.get('year') == league.year
                    and (getattr(league, 'season_closed_year', None) or league.year) < league.year):
                m['phase'] = 'offseason'
            for owner, assets in ((pl.get('buyer'), pl.get('sends', [])),
                                  (pl.get('user_team', user), pl.get('gets', []))):
                for asset in assets:
                    if isinstance(asset, str):
                        player = league.player(asset)
                        if (player is None or player.team != owner or not player.contract
                                or player.contract_years_left <= 0 or player.fa_class == 'tendered'):
                            done = True
                    else:
                        try: _resolve(league, asset, owner)
                        except (ValueError, KeyError): done = True
        elif kind == 'staff':
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
            pids = pl.get('digest_pids') or [pl.get('pid')]
            players = [league.player(pid) for pid in pids if pid]
            current = [p for p in players if p is not None and p.team == user
                       and not getattr(p, 'retired', False) and p.contract and p.contract.years == 1]
            done = (not current or (year is not None and m.get('year', year) < year))
            if not done:
                # This is an open roster reminder, not a historical transaction.
                # Keep its membership current after trades, releases and extensions.
                pl['digest_pids'] = [p.pid for p in current]
                pl.pop('pid', None)
                pl['link'] = 'personnel:extensions'
                names = ', '.join(p.name for p in current[:3])
                extra = f" and {len(current)-3} others" if len(current) > 3 else ''
                m['body'] = f"{names}{extra}: expiring contracts to review."
                m['subject'] = 'Expiring Contracts'
                entities = [dict(kind='player', id=p.pid, name=p.name) for p in current]
                m['entities'] = entities
                pl['mail_sections'] = [dict(title='', columns=['Player', 'Pos', 'OVR', 'Age', 'Annual Average'],
                    rows=[[dict(text=value, mentions=reference_spans(value, entities, [])) for value in
                           [p.name, p.pos, str(round(p.ovr)), str(int(p.age)), f"${p.apy:.1f}m"]] for p in current])]
                pl['mail_intro'] = dict(text='These players are entering the final year of their contracts and can negotiate extensions.', mentions=[])
                m['payload'] = pl
                m.setdefault('mentions', {})['body'] = reference_spans(m['body'], entities, [])
        elif kind == 'exit':
            meetings = (getattr(league, 'exit_meetings', {}) or {}).get(str(m.get('year', year)))
            if meetings is not None:
                done = all(mt.get('answer') or league.player(mt.get('pid')) is None for mt in meetings)
            done = done or (year is not None and m.get('year', year) < year)
        elif kind == 'injury_decision':
            import injury_status as IS
            injured = league.player(pl.get('pid'))
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
            if injured is not None and IS.concussion_restricted(injured):
                done = True  # Medical clearance is not a GM play-or-sit decision.
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
    if '\n' in body:
        # Producers already chose the boundaries. Do not separate a labeled
        # injury status or recommendation from the player it describes.
        return [line.strip() for line in body.splitlines() if line.strip()]
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


def date_label(message):
    year, week = message.get('year'), message.get('week')
    if message.get('phase') in ('offseason', 'free_agency', 'draft', 'camp'):
        return f'Offseason {year}'
    label = {19:'Wild Card', 20:'Divisional Round', 21:'Conference Championship',
             22:'Championship Game'}.get(week, f'Week {week}' if week else '')
    return f'{year} · {label}' if label else str(year or '')
