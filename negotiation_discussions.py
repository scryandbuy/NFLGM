"""Saved conversations around the existing contract and trade decision owners.

Dialogue never transfers an asset or signs a contract. Trade concessions remove
only part of a GM's attachment premium, only for the discussed target and the
promised form of compensation. Football, cap and portfolio checks still apply.
"""
import copy


def _choice(key, label):
    return dict(key=key, label=label)


def player_state(league, t):
    import contract_offer as CO
    p = league.player(t['pid'])
    if 'discussion' not in t:
        ready = bool(t.get('offers') or t['state'] != 'open')
        profile = CO.profile_for(p)
        opening = {
            'max_money': 'I want a deal that reflects my market. Where do you see this going?',
            'security': 'I want to know I have a future here. What are you thinking?',
            'ring_chaser': 'I want to win. Tell me where I fit in your plans.',
            'wants_the_ball': 'Playing time matters to me. What role do you have in mind?',
            'homebody': 'Staying settled matters to me, but the deal still has to work.',
            'balanced': 'I am willing to talk. What do you have in mind?',
        }
        t['discussion'] = dict(stage='proposal' if ready else 'talk', used=[], promises=[],
                               log=[dict(who='player', text=opening.get(profile['archetype'], opening['balanced']))])
    return t['discussion']


def player_view(league, t):
    d = player_state(league, t)
    choices = []
    if d['stage'] == 'talk':
        choices = [_choice(k, s) for k, s in [
            ('priorities', 'What Matters Most to You?'), ('price', 'What Number Do You Have in Mind?'),
            ('security', 'Would Earlier Pay Help?'), ('role', 'I Can Commit to a Starting Role'),
            ('home', 'I Can Commit to Keeping You Here'), ('pressure', 'You Need Us More Than We Need You')]
            if k not in d['used']]
        choices.append(_choice('finish', 'Let Me Put an Offer Together'))
    elif d['stage'] == 'ready':
        choices = [_choice('proposal', 'Open Proposal')]
    return dict(copy.deepcopy(d), choices=choices)


def player_reply(league, t, choice):
    import contract_offer as CO, negotiations as NG
    p = league.player(t['pid'])
    if t['state'] != 'open' or t.get('offers'):
        return dict(ok=False, why='The proposal is already under way.')
    d = player_state(league, t)
    options = {x['key']: x['label'] for x in player_view(league, t)['choices']}
    if choice not in options: return dict(ok=False, why='That part of the conversation has ended.')
    profile = CO.profile_for(p); archetype = profile['archetype']
    if choice == 'proposal':
        d['stage'] = 'proposal'
        return dict(ok=True)
    d['used'].append(choice); d['log'].append(dict(who='you', text=options[choice]))
    if choice == 'priorities':
        line = {
            'max_money': 'The total has to stack up against the market. A friendly conversation cannot replace that.',
            'security': 'Money early in the deal matters. I cannot count on every later salary being paid.',
            'ring_chaser': 'A competitive team and a real role matter. I still need the money to make sense.',
            'wants_the_ball': 'I want a starting role in writing. Do not promise it if you cannot follow through.',
            'homebody': 'I do not want to sign and then get traded. Put that commitment in the offer.',
            'balanced': 'Show me a fair total and a sensible payment schedule. I can work with that.',
        }[archetype]
        if profile['trust'] < .7: line += ' Your past promises make it harder to take your word for it.'
    elif choice == 'price':
        if archetype == 'max_money' or t['mood'] == 'firm':
            d['quote'] = t['ask']; line = f"Start at ${t['ask']:.2f}m a year over {t['years']} years. The structure matters too."
        elif profile['trust'] >= .7:
            d['range'] = [round(t['ask'] * .97, 2), round(t['ask'] * 1.03, 2)]
            line = f"Somewhere around ${d['range'][0]:.2f}m to ${d['range'][1]:.2f}m a year. Show me the full terms."
        else:
            line = 'Send a serious offer first. I am not giving you a number to negotiate down from.'
    elif choice == 'security':
        d['front_load'] = .85
        line = 'Put the earlier money in the offer and I will weigh it against the total.' if archetype != 'max_money' else 'I will look at the cash schedule, but do not lose sight of the total.'
    elif choice in ('role', 'home'):
        promise = 'starting_role' if choice == 'role' else 'no_trade'
        d['promises'].append(promise)
        line = 'Put that commitment in the proposal. I will hold you to it.' if profile['trust'] >= .7 else 'Put it in writing. After the broken promises, it is worth less to me.'
    elif choice == 'pressure':
        t['patience'] = max(1, t['patience'] - 1)
        d['stage'] = 'ready'
        line = 'That is not a reason to take less. Send your terms; I am done with the sales pitch.'
    else:
        d['stage'] = 'ready'; line = 'All right. Send the proposal and I will look at the full package.'
    d['log'].append(dict(who='player', text=line))
    return dict(ok=True, line=line)


def starting_offer(league, t):
    import contract_offer as CO, valuation as VAL
    from min_salary import demand_quote
    d = player_state(league, t); p = league.player(t['pid'])
    # Staff uses its own comps. No negotiation floor or hidden acceptance quote.
    value = VAL.value_player(league, p, side='team', rng=None, extension=t['kind'] == 'extension') or {}
    apy = float(value.get('apy', t['ask']))
    if d.get('quote') is not None: apy = d['quote']
    elif d.get('range'): apy = max(d['range'][0], min(d['range'][1], apy))
    apy = demand_quote(league, p, apy, t['years'], t['kind'])
    return CO.canonical(league, p, league.teams[t['team']], dict(apy=apy, years=t['years'],
        front_load=d.get('front_load', .5), promises=list(d['promises'])), t['kind'])


def _window(league):
    import negotiations as NG
    return [int(league.year), NG._clock(league)]


def trade_state(league, abbr, other):
    saved = getattr(league, 'trade_discussions', {}) or {}
    d = saved.get(abbr + ':' + other)
    return d if d and d.get('window') == _window(league) else None


def trade_view(league, abbr, other):
    d = trade_state(league, abbr, other)
    if not d: return dict(stage='topic', choices=[], log=[])
    choices = []
    if d['stage'] == 'talk':
        choices = [_choice(k, label) for k, label in [
            ('needs', 'What Would Help Your Team?'), ('price', 'What Would Make This Worthwhile?'),
            ('picks', 'Give Me Some Room and I Will Include Draft Capital'),
            ('players', 'Give Me Some Room and I Will Address a Roster Need'),
            ('pressure', 'You Will Not Get a Better Offer')]
            if k not in d['used'] and (k not in ('picks', 'players') or not d.get('commitment'))]
        choices.append(_choice('finish', 'Let Me Make You an Offer'))
    elif d['stage'] == 'ready': choices = [_choice('proposal', 'Open Proposal')]
    return dict(copy.deepcopy(d), choices=choices)


def start_trade(league, abbr, other, asset, direction):
    import views_personnel as VP, trades as TR
    from trade_calendar import trading_open
    if other not in league.teams or other == abbr or direction not in ('acquire', 'offer'):
        return dict(ok=False, why='Choose another team and an asset to discuss.')
    if not trading_open(league): return dict(ok=False, why='The trade window is closed.')
    owner = other if direction == 'acquire' else abbr
    try: ident = VP._trade_ids(league, owner, [asset])[0]
    except (ValueError, IndexError, TypeError): return dict(ok=False, why='That asset is no longer available.')
    old = trade_state(league, abbr, other)
    # Changing the subject does not replenish patience or a used concession.
    if old and old['stage'] == 'closed': return dict(ok=False, why=old['log'][-1]['text'])
    if old and old['topic'] == ident and old['direction'] == direction:
        return dict(ok=True)
    them = league.teams[other]; p = league.player(ident)
    pk = None if p else VP._find_pick(league, owner, ident)
    label = p.name if p else VP._pick_row(league, pk)['label']
    persona = TR.persona(them.gm)
    line = ('I will listen. What are you thinking?' if persona['aggression'] > .6 else
            'I am willing to hear an offer. Keeping what we have is still an option.')
    if p and direction == 'acquire':
        status = TR.seller_willingness(them, p)['seller_status']
        if status == 'core': line = 'He is part of our plans. I would need a package that covers the hole he leaves and makes us better overall.'
        elif status == 'requested_move': line = 'We are willing to find a move for him. The return still has to work for us.'
        # A no-trade promise is an actual existing commitment, not a rating veto.
        if any(x.get('pid') == p.pid and x.get('team') == other and x.get('kind') == 'no_trade' and x.get('status') == 'open' for x in getattr(league, 'promises', [])):
            line = 'We gave him our word that we would not trade him. I am not opening talks on him today.'
            return _save_trade(league, abbr, other, ident, direction, label, line, 'unavailable', old)
    elif p:
        line = f'I will look at {p.name}, but he has to justify his role and contract here. Who or what are you looking for in return?'
    return _save_trade(league, abbr, other, ident, direction, label, line, 'talk', old)


def _save_trade(league, abbr, other, ident, direction, label, line, stage, old):
    if not getattr(league, 'trade_discussions', None): league.trade_discussions = {}
    d = dict(window=_window(league), topic=ident, direction=direction, label=label, stage=stage,
             used=[], concession=0., patience=(old or {}).get('patience', 2),
             spent=(old or {}).get('spent', False), log=[dict(who='you', text=f"{'I am interested in' if direction == 'acquire' else 'I would like to discuss moving'} {label}."), dict(who='gm', text=line)])
    d['refused_topics'] = list((old or {}).get('refused_topics', []))
    if stage == 'unavailable' and ident not in d['refused_topics']: d['refused_topics'].append(ident)
    league.trade_discussions[abbr + ':' + other] = d
    return dict(ok=True, line=line)


def trade_refusal(league, abbr, other, b_sends):
    d = trade_state(league, abbr, other)
    if d and any((x.get('id') if isinstance(x, dict) else x) in d.get('refused_topics', []) for x in b_sends):
        return 'We already said we are honoring our commitment to keep that player. He is not available in this negotiating window.'
    return None


def trade_reply(league, abbr, other, choice):
    import trades as TR, trade_engine as TE
    d = trade_state(league, abbr, other)
    options = {x['key']: x['label'] for x in trade_view(league, abbr, other)['choices']}
    if choice not in options: return dict(ok=False, why='That part of the conversation has ended.')
    if choice == 'proposal': d['stage'] = 'proposal'; return dict(ok=True)
    them = league.teams[other]; gm = TR.persona(them.gm)
    needs = sorted(TR.roster_need_labels(them, int(league.week or 0)))
    window = TE.window(them.ctx())
    d['used'].append(choice); d['log'].append(dict(who='you', text=options[choice]))
    if choice == 'needs':
        d['needs_known'] = True
        line = ('We could use help at ' + ', '.join(needs) + '. It needs to be someone who can actually do the job.' if needs else
                'There is no obvious hole I need you to fill. Future value would have to justify a move.')
    elif choice == 'price':
        line = ('I value keeping our draft options open. One attractive name will not make up for losing several useful picks.' if gm['patience'] > .65 else
                'I will pay attention to someone who helps us now, but I need a usable replacement for anyone we send out.')
        line += ' Put the complete package in front of me before we talk exact terms.'
    elif choice in ('picks', 'players'):
        credible = (choice == 'picks' and (window in ('rebuilding', 'retooling') or gm['patience'] > .6)) or (choice == 'players' and bool(needs) and gm['aggression'] > .45)
        if credible and not d['spent']:
            d['commitment'] = choice; d['needs'] = needs
            d['concession'] = min(.035, (gm['own_bias'] - 1) * (.15 + .15 * gm['aggression']))
            d['spent'] = True
            line = 'All right. Include ' + ('draft capital' if choice == 'picks' else 'a player who addresses those needs') + ' and I can ease my asking price a little. I still need the whole deal to work.'
        else:
            line = 'That is not enough reason for me to lower the price. You can still put a package together.'
    elif choice == 'pressure':
        d['patience'] -= 2 if gm['patience'] < .5 else 1
        d['concession'] = 0.
        line = 'You have not even sent the offer. Do not tell me what my alternatives are.'
        if d['patience'] <= 0: d['stage'] = 'closed'; line += ' We are done for today.'
    else:
        d['stage'] = 'ready'; line = 'Okay, I am willing to look. Send me the offer.'
    d['log'].append(dict(who='gm', text=line))
    return dict(ok=True, line=line)


def trade_persona(league, abbr, other, a_sends, b_sends):
    import trades as TR, views_personnel as VP
    gm = dict(TR.persona(league.teams[other].gm))
    d = trade_state(league, abbr, other)
    if not d or d['stage'] not in ('ready', 'proposal') or not d.get('concession'): return gm
    def ident(x): return x.get('id') if isinstance(x, dict) else x
    outgoing, incoming = list(map(ident, a_sends)), list(map(ident, b_sends))
    if d['topic'] not in (incoming if d['direction'] == 'acquire' else outgoing): return gm
    kept = (d.get('commitment') == 'picks' and any(VP._find_pick(league, abbr, x) for x in outgoing))
    if d.get('commitment') == 'players':
        current = set(TR.roster_need_labels(league.teams[other], int(league.week or 0)))
        kept = bool(current.intersection(d.get('needs', []))) and any(league.player(x) and TR.receiving_need(league.teams[other], league.player(x), int(league.week or 0)) for x in outgoing)
    if kept: gm['own_bias'] = max(1., gm['own_bias'] - d['concession'])
    return gm
