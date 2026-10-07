"""Read-only news batched at the boundary of a single Advance."""
import copy
from collections import OrderedDict
import inbox as IB

TRANSACTION_TYPES = ('Trades', 'Signings', 'Extensions', 'Franchise Tags')


def split_saved_transactions(league):
    """Separate a saved mixed digest when every recorded section is identifiable."""
    box = getattr(league, 'inbox', None) or []
    for old in list(box):
        if old.get('kind') != 'league' or old.get('subject') != 'League Transactions':
            continue
        sections = (old.get('payload') or {}).get('mail_sections') or []
        if not sections:
            continue
        groups = OrderedDict()
        for section in sections:
            title = (section.get('title') or '').lower()
            if section.get('trade_group') is not None or (section.get('team') and title.endswith(' receive')):
                topic = 'Trades'
            elif title.startswith('signings'):
                topic = 'Signings'
            elif title.startswith('extensions'):
                topic = 'Extensions'
            elif title.startswith('franchise tags'):
                topic = 'Franchise Tags'
            else:
                topic = None
            if topic:
                groups.setdefault(topic, []).append(copy.deepcopy(section))
                continue
            # A pre-table announcement can contain one or several plain rows.
            # Classify each from its saved wording; never consult today's roster.
            if section.get('columns') or not section.get('rows'):
                groups = None
                break
            for row in section['rows']:
                if len(row) != 1:
                    groups = None
                    break
                text = row[0].get('text', '') if isinstance(row[0], dict) else str(row[0])
                topic = category(dict(kind='league', subject=text))
                if topic not in TRANSACTION_TYPES:
                    groups = None
                    break
                fragment = copy.deepcopy(section)
                fragment['rows'] = [copy.deepcopy(row)]
                groups.setdefault(topic, []).append(fragment)
            if groups is None:
                break
        if not groups:
            continue
        replacements = []
        for i, (topic, topic_sections) in enumerate(groups.items()):
            message = copy.deepcopy(old)
            if i:
                message['id'] = next(IB._ids)
            # Fresh IDs identify the split messages, while their inbox order
            # stays beside the historical message they came from.
            message['sort_id'] = old['id'] + i / len(groups)
            message['subject'] = topic
            message['payload']['mail_sections'] = topic_sections
            message['payload']['mail_intro'] = dict(text='', mentions=[])
            message['payload']['link'] = 'league:transactions'
            message['body'] = '\n\n'.join('\n'.join([s['title']] +
                [' | '.join(c.get('text', '') if isinstance(c, dict) else str(c) for c in row)
                 for row in s['rows']]).strip() for s in topic_sections)
            message['mentions'] = dict(subject=[], body=IB.reference_spans(
                message['body'], message.get('entities') or [], []))
            replacements.append(message)
        pos = next(i for i, message in enumerate(box) if message is old)
        box[pos:pos+1] = replacements


def category(message):
    kind = message.get('kind')
    subject = message.get('subject', '').lower()
    payload = message.get('payload') or {}
    if kind == 'contract_year': return 'Expiring Contracts'
    if kind == 'negotiation' and subject.endswith(' signs'): return 'Your Signings'
    if kind == 'negotiation' and subject.endswith(' extended'): return 'Your Extensions'
    if kind == 'ir_ready': return 'Injury Update'
    if IB.is_decision(message) or kind in ('negotiation', 'trade_request', 'morale', 'owner', 'ir_ready'):
        return None
    if kind == 'waiver_notice' and not subject.startswith('available on waivers:'):
        return 'Waiver Results'
    if kind == 'injury' and not ('short at ' in subject or 'emergency at ' in subject):
        return 'Injury Update'
    if kind == 'trade_done': return 'Your Trades'
    if kind == 'squad': return 'Practice Squad Moves'
    if kind == 'result' and any(s in subject for s in ('first start', 'th start', ' passes ', 'player of the week')):
        return 'Player Milestones'
    if kind == 'staff' and ('retiring' in subject): return 'Coaching Changes'
    if kind == 'league':
        if subject.startswith('free agency, round ') or subject == 'the market closes':
            return 'Signings'
        if 'make a trade' in subject: return 'Trades'
        if ' sign ' in subject or 'big signings' in subject: return 'Signings'
        if ' extend ' in subject or 'extensions ·' in subject: return 'Extensions'
        if ' tag ' in subject or 'franchise tags ·' in subject: return 'Franchise Tags'
        if any(s in subject for s in (' hire ', 'makes a change', 'coaching carousel summary', 'coaching market')):
            return 'Coaching Changes'
        if any(s in subject for s in ('may have found one', 'questions at ')):
            return 'Rookie Evaluation'
    if kind == 'club' and ('your scouts on ' in subject): return 'Rookie Evaluation'
    return None


def consolidate(league, before):
    groups = {}
    for message in list(getattr(league, 'inbox', [])):
        if message['id'] in before: continue
        topic = category(message)
        if topic: groups.setdefault(topic, []).append(message)
    for topic, messages in groups.items():
        if len(messages) < 2: continue
        sections = []
        entities = []
        pids = []
        sources = messages
        if topic == 'Coaching Changes':
            summaries = [m for m in messages if m.get('subject', '').startswith('Coaching carousel summary')]
            if summaries:
                # The completed ledger includes hires and exits. Earlier market
                # previews and club announcements repeat it and may be stale.
                sources = summaries[-1:]
        for message in sources:
            layout = IB.mail_layout(message)
            entities.extend(message.get('entities') or [])
            pid = (message.get('payload') or {}).get('pid')
            if pid: pids.append(pid)
            if layout.get('mail_sections'):
                intro = layout.get('mail_intro')
                if intro and intro.get('text') and topic != 'Expiring Contracts':
                    sections.append(dict(title='', columns=[], rows=[[copy.deepcopy(intro)]]))
                for section in layout['mail_sections']:
                    section = copy.deepcopy(section)
                    if layout.get('mail_layout') == 'trade':
                        # Keep the two received-asset lists together without
                        # repeating the announcement over each team's list.
                        section['trade_group'] = str(message['id'])
                    sections.append(section)
            else:
                sections.append(dict(title='', columns=[], rows=[[dict(
                    text=(message['subject'] + ' — ' + message.get('body', '') if message.get('kind') == 'negotiation' else message.get('body') or message['subject']),
                    mentions=IB.reference_spans(message['subject'] + ' — ' + message.get('body', ''), message.get('entities') or [], []) if message.get('kind') == 'negotiation' else copy.deepcopy((message.get('mentions') or {}).get('body', [])))]]))
        # Keep each announcement's wording, then one combined table for its
        # transaction type. The source messages alternate prose and tables.
        if topic in ('Signings', 'Extensions', 'Franchise Tags', 'Your Signings', 'Your Extensions'):
            sections = [s for s in sections if not s['columns']] + [s for s in sections if s['columns']]
        # Coalesce ordinary one-line records into one compact section.
        merged = []
        for section in sections:
            if (topic in ('Signings', 'Extensions', 'Franchise Tags', 'Your Signings',
                          'Your Extensions', 'Injury Update', 'Waiver Results') and merged and section['columns']
                    and section['title'] == merged[-1]['title'] and section['columns'] == merged[-1]['columns']):
                merged[-1]['rows'].extend(section['rows'])
            elif not section['title'] and not section['columns'] and merged and not merged[-1]['title'] and not merged[-1]['columns']:
                merged[-1]['rows'].extend(section['rows'])
            else: merged.append(section)
        if topic == 'Expiring Contracts' and merged and all(s['columns'] == merged[0]['columns'] and s['columns'] for s in merged):
            merged = [dict(title='', columns=merged[0]['columns'], rows=[row for s in merged for row in s['rows']])]
        link = {'Trades':'league:transactions', 'Signings':'league:transactions',
                'Extensions':'league:transactions', 'Franchise Tags':'league:transactions',
                'Your Trades':'personnel:trades', 'Your Signings':'club',
                'Your Extensions':'personnel:extensions', 'Practice Squad Moves':'club',
                'Waiver Results':'personnel:waivers', 'Injury Update':'club:depth',
                'Coaching Changes':'league:coaching', 'Rookie Evaluation':'draft:results',
                'Expiring Contracts':'personnel:extensions'}.get(topic)
        msg = IB.post(league, 'contract_year' if topic == 'Expiring Contracts' else 'league' if topic in ('Trades', 'Signings', 'Extensions', 'Franchise Tags', 'Coaching Changes') else 'club',
                      topic, '', sender=messages[0].get('sender'),
                      payload=dict(link=link, digest_pids=pids))
        msg['payload'].update(mail_sections=merged, mail_intro=dict(text='These players are entering the final year of their contracts and can negotiate extensions.' if topic == 'Expiring Contracts' else '', mentions=[]))
        msg['entities'] = entities
        msg['body'] = '\n\n'.join('\n'.join([s['title']] + [' | '.join(c['text'] for c in row) for row in s['rows']]).strip() for s in merged)
        msg['mentions']['body'] = IB.reference_spans(msg['body'], entities, [])
        remove = {m['id'] for m in messages}
        league.inbox[:] = [m for m in league.inbox if m['id'] not in remove]


def append_draft_trade(league, message):
    """One growing draft ledger, including user trades across separate clicks."""
    year = (getattr(league, 'league_notes_sent', None) or {}).get('_draft_trade_mail_active')
    if year is None or category(message) not in ('Trades', 'Your Trades'):
        return message
    layout = IB.mail_layout(message)
    if not layout.get('mail_sections'):
        return message
    sections = copy.deepcopy(layout['mail_sections'])
    for section in sections:
        section['trade_group'] = str(message['id'])
    box = league.inbox
    existing = next((m for m in box if m is not message and
        (m.get('payload') or {}).get('draft_trade_digest') == year), None)
    if existing is None:
        existing = message
        existing.update(subject='Draft Day Trades', kind='league', sender='league')
        existing['payload'] = dict(draft_trade_digest=year, link='league:transactions',
            mail_sections=sections, mail_intro=dict(text='', mentions=[]))
    else:
        existing['payload']['mail_sections'].extend(sections)
        existing.setdefault('entities', []).extend(message.get('entities') or [])
        existing['status'] = 'unread'
        box.remove(message)
    existing['body'] = '\n\n'.join('\n'.join([s['title']] +
        [' | '.join(c.get('text', '') for c in row) for row in s['rows']]).strip()
        for s in existing['payload']['mail_sections'])
    existing['mentions'] = dict(subject=[], body=IB.reference_spans(
        existing['body'], existing.get('entities') or [], []))
    return existing
