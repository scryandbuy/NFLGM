"""Read-only news batched at the boundary of a single Advance."""
import copy
import inbox as IB


def category(message):
    kind = message.get('kind')
    subject = message.get('subject', '').lower()
    payload = message.get('payload') or {}
    if kind == 'contract_year': return 'Expiring Contracts'
    if kind == 'negotiation' and subject.endswith((' signs', ' extended')): return 'Your Roster Moves'
    if kind == 'ir_ready': return 'Injury Update'
    if IB.is_decision(message) or kind in ('negotiation', 'trade_request', 'morale', 'owner', 'ir_ready'):
        return None
    if kind == 'waiver_notice' and not subject.startswith('available on waivers:'):
        return 'Waiver Results'
    if kind == 'injury' and not ('short at ' in subject or 'emergency at ' in subject):
        return 'Injury Update'
    if kind in ('trade_done', 'squad'): return 'Your Roster Moves'
    if kind == 'result' and any(s in subject for s in ('first start', 'th start', ' passes ', 'player of the week')):
        return 'Player Milestones'
    if kind == 'staff' and ('retiring' in subject): return 'Coaching Changes'
    if kind == 'league':
        if subject.startswith('free agency, round ') or subject == 'the market closes':
            return 'League Transactions'
        if any(s in subject for s in ('make a trade', ' sign ', ' extend ', ' tag ', 'extensions ·', 'franchise tags ·', 'big signings')):
            return 'League Transactions'
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
        # Coalesce ordinary one-line records into one compact section.
        merged = []
        for section in sections:
            if (topic in ('League Transactions', 'Injury Update', 'Waiver Results') and merged and section['columns']
                    and section['title'] == merged[-1]['title'] and section['columns'] == merged[-1]['columns']):
                merged[-1]['rows'].extend(section['rows'])
            elif not section['title'] and not section['columns'] and merged and not merged[-1]['title'] and not merged[-1]['columns']:
                merged[-1]['rows'].extend(section['rows'])
            else: merged.append(section)
        if topic == 'Expiring Contracts' and merged and all(s['columns'] == merged[0]['columns'] and s['columns'] for s in merged):
            merged = [dict(title='', columns=merged[0]['columns'], rows=[row for s in merged for row in s['rows']])]
        link = {'League Transactions':'league:transactions', 'Your Roster Moves':'club',
                'Waiver Results':'personnel:waivers', 'Injury Update':'club:depth',
                'Coaching Changes':'league:coaching', 'Rookie Evaluation':'draft:results',
                'Expiring Contracts':'personnel:extensions'}.get(topic)
        msg = IB.post(league, 'contract_year' if topic == 'Expiring Contracts' else 'league' if topic in ('League Transactions','Coaching Changes') else 'club',
                      topic, '', sender=messages[0].get('sender'),
                      payload=dict(link=link, digest_pids=pids))
        msg['payload'].update(mail_sections=merged, mail_intro=dict(text='These players are entering the final year of their contracts and can negotiate extensions.' if topic == 'Expiring Contracts' else '', mentions=[]))
        msg['entities'] = entities
        msg['body'] = '\n\n'.join('\n'.join([s['title']] + [' | '.join(c['text'] for c in row) for row in s['rows']]).strip() for s in merged)
        msg['mentions']['body'] = IB.reference_spans(msg['body'], entities, [])
        remove = {m['id'] for m in messages}
        league.inbox[:] = [m for m in league.inbox if m['id'] not in remove]
