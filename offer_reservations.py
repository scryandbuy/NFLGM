"""Cap room temporarily committed by unanswered user free-agent offers.

These are planning holds, not signed contracts. They are derived from the
negotiation threads so saving, loading, withdrawing and resolving an offer all
update the available room without a second ledger to synchronize.
"""

from cap_engine import CAP


LIVE_STATES = frozenset(('waiting', 'match_requested'))
FA_KINDS = frozenset(('fa_offseason', 'fa_inseason'))


def offer_hit(league, team, player, offer):
    """First cap-year charge of the deal currently offered to a free agent."""
    from market import signing_terms

    terms = signing_terms(
        league, player, team, float(offer['apy']), int(offer['years']),
        CAP.get(league.year, 301.2), offer.get('front_load'), offer.get('bonus'),
    )
    return float(terms['cap_hits'][0])


def pending_offers(league, abbr, exclude_thread=None, exclude_pid=None):
    """The latest outstanding offer per player for this club, with cap holds."""
    team = league.teams[abbr]
    rows = []
    for thread in getattr(league, 'negotiations', None) or ():
        if (thread.get('id') == exclude_thread or thread.get('pid') == exclude_pid
                or thread.get('team') != abbr):
            continue
        if thread.get('kind') not in FA_KINDS or thread.get('state') not in LIVE_STATES:
            continue
        player = league.player(thread.get('pid'))
        if player is None or player.pid not in league.free_agents or not thread.get('offers'):
            continue
        offer = thread['offers'][-1]
        try:
            hit = offer_hit(league, team, player, offer)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue  # an older malformed saved offer must not hide the market
        rows.append(dict(thread=thread['id'], pid=player.pid, name=player.name,
                         apy=float(offer['apy']), years=int(offer['years']),
                         cap_hit=round(hit, 3), state=thread['state']))
    return rows


def held(league, abbr, exclude_thread=None, exclude_pid=None):
    return sum(row['cap_hit'] for row in pending_offers(league, abbr, exclude_thread, exclude_pid))


def raw_room(league, team):
    """Room in the cap year shown by the UI, before pending offers."""
    from cap_accounting import next_year_ledger, pre_roll

    if pre_roll(league):
        limit, committed, _, _ = next_year_ledger(league, team)
        return float(limit - committed)
    return float(team.cap_space)


def available(league, abbr, exclude_thread=None):
    return raw_room(league, league.teams[abbr]) - held(league, abbr, exclude_thread)


def check_offer(league, abbr, thread, apy, years, bonus=None, front_load=None):
    """Check one proposed FA offer against room left after other live offers."""
    if thread.get('kind') not in FA_KINDS:
        return None
    player = league.player(thread.get('pid'))
    if player is None or player.pid not in league.free_agents:
        return 'This player is no longer available.'
    offer = dict(apy=apy, years=years, bonus=bonus, front_load=front_load)
    try:
        hit = offer_hit(league, league.teams[abbr], player, offer)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return str(exc)
    room = available(league, abbr, exclude_thread=thread.get('id'))
    if hit > room + 0.0005:
        return f'Not enough available cap room after outstanding offers (${max(0.0, room):.1f}m left).'
    return None
