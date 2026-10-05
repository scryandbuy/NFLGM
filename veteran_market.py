"""Recurring, negotiated veteran acquisitions after the main FA market.

Reuse football assignments, player consent, release protections and cap planning.
Reviews are calendar actions, never page reads. The saved checkpoint prevents a
reload/repeated advance from becoming another shopping opportunity.
"""
import copy

import market as MK
import roster_needs as RN
import practice_squad as PS
import financial_plan as FP
import contract_offer as CO
import min_salary as MS
from cap_engine import CAP
from cap_accounting import require_room


def recent_commitments(league, team, week):
    """Keep offseason recruits through camp/early games and new in-season men.

Old offseason logs carry week 22. Treat that as preseason, not as a future
regular-season acquisition. A trade is a commitment too.
"""
    ids = set()
    for tx in league.transactions:
        if tx.get('year') != league.year:
            continue
        during_season = tx.get('phase') in ('regular', 'playoffs')
        if during_season:
            if not 0 <= week - int(tx.get('week') or 0) <= 3:
                continue
        elif week > 3:
            continue
        if tx.get('kind') in ('sign', 'udfa_sign', 'waiver_claim', 'ps_callup', 'ps_poach', 'emergency_sign') and tx.get('team') == team.abbr:
            ids.add(tx.get('pid'))
        if tx.get('kind') == 'trade':
            if tx.get('a') == team.abbr: ids.update(tx.get('b_sends', ()))
            if tx.get('b') == team.abbr: ids.update(tx.get('a_sends', ()))
    return ids


def _shares(report):
    shares = {}
    for row in report['package_assignments']:
        p = row['player']
        if p is not None:
            shares[p.pid] = shares.get(p.pid, 0.) + row['weight']
    for row in report['assignments']:
        if row['role'] in ('K', 'P', 'LS') and row['player']:
            shares[row['player'].pid] = 1.
    return shares


def _proposal(league, team, player, quote, report, recent, budget, comparisons):
    """Prepare an entire funded move before accepting or releasing anybody."""
    price = round(max(.70 * quote['apy'], MS.minimum_salary(player.accrued or 0,
                                                          CAP.get(league.year, 301.2))), 3)
    # A full roster considers coverage-safe replacements at the relevant job.
    departures = (q for q in PS._room_candidates(league, team, player) if q.pid not in recent) \
        if len(team.active()) >= 53 else iter((None,))
    old_shares = _shares(report)
    for outgoing in departures:
        players = [p for p in report['players'] if p is not outgoing] + [player]
        after = RN.assess(team, players)
        gain = after['score'] - report['score']
        if gain <= 1.:
            continue
        # Native-position depth bonuses must not justify weakening the lineup
        # that will actually play. Real healthy-coverage repairs can trade
        # some quality for a playable roster; specialist quality is accounted
        # for outside the offensive/defensive package scores.
        package_gain = sum(after['_package_scores'].values()) - sum(report['_package_scores'].values())
        if outgoing and player.pos not in ('K', 'P', 'LS') and package_gain < -.0001:
            old_short = PS.essential_depth(team, report['players'], league.week)['shortages']
            new_short = PS.essential_depth(team, players, league.week)['shortages']
            if sum(new_short.values()) >= sum(old_short.values()):
                continue
        shares = _shares(after)
        if any(old_shares.get(pid, 0.) >= .15 and
               shares.get(pid, 0.) < .5 * old_shares[pid] for pid in recent):
            continue  # don't bury the starter we just recruited, either
        # Use existing late-market economics. Security-seeking players may
        # prefer two years; both schedules must fit the club's future books.
        for years in range(1, min(2, max(1, int(quote.get('years', 1)))) + 1):
            offer = MK.Offer(team.abbr, player.pid, price, years, phase=MK.PHASES + 1)
            contract = MK.offer_contract(league, player, offer)
            if not MK.acquisition_read(league, team, player, offer, gain, quote['apy'],
                    report, after_package_rows=after['package_assignments'])['approved']:
                continue
            try:
                require_room(league, team, player.pid, contract,
                             release_pid=outgoing.pid if outgoing else None)
            except ValueError:
                continue
            decision = FP.evaluate(league, team, additions=[(player, contract)],
                removals=[outgoing.pid] if outgoing else [], gain=gain,
                action='veteran_market', before=budget, market=comparisons)
            if not decision['approved']:
                continue
            ask = max(.55 * quote['apy'], MS.minimum_salary(player.accrued or 0,
                                                           CAP.get(league.year, 301.2)))
            # Consent is a preview: don't initialize hidden preferences merely
            # because a team considered the player.
            preview = copy.copy(player)
            preview.xp_spent = dict(player.xp_spent or {})
            profile = CO.profile_for(preview)
            if not CO.assess(league, player, team, offer.as_dict(), ask,
                             min(2, max(1, int(quote.get('years', 1)))),
                             profile=profile)['acceptable']:
                continue
            return offer, outgoing, gain
    return None


@MK.VAL.comparison_batch()
def review(league, rng, stage, week=0, user_team=None):
    """One considered acquisition per club per review, not a signing quota.

Camp and cleared cutdown waivers review every CPU club. In season the existing
monthly review cadence is staggered by club; real coverage holes get an earlier
look. Injuries and minimum/squad emergency routes remain available each week.
"""
    if stage not in ('camp', 'wire', 'weekly'):
        raise ValueError('Unknown veteran-market checkpoint')
    if stage == 'weekly' and (league.phase != 'regular' or not 1 <= week <= 17):
        return []
    notes = league.__dict__.setdefault('notes_sent', {})
    saved = notes.get('_veteran_market', {})
    done = list(saved.get('done', ())) if saved.get('year') == league.year else []
    key = f'{stage}:{week}'
    if key in done:
        return []
    protected = {user_team, getattr(league, 'user_team', None)}
    pool = [p for p in PS.available_free_agents(league)
            if p.ovr >= MK.REPLACEMENT_GRADE or p.pos in ('K', 'P', 'LS')]
    # Preserve a user's active negotiations rather than settling behind them.
    import negotiations as NG
    held = {t['pid'] for t in NG._threads(league) if t.get('team') in protected and
            t.get('state') in ('open', 'waiting', 'countered', 'match_requested')}
    pool = [p for p in pool if p.pid not in held and not MK.pending_offer_sheet(league, p.pid)]
    teams = {}
    comparisons = FP.retention_market(league)
    for abbr, team in league.teams.items():
        if abbr in protected or team.gm is None:
            continue
        report = RN.assess(team)
        if stage == 'weekly':
            if getattr(team, '_moved_week', None) == week:
                continue
            short = PS.essential_depth(team, week=week + 1)['shortages']
            if (week + sum(map(ord, abbr))) % 4 != 0 and not any(short.values()):
                continue
        teams[abbr] = (report, RN.candidate_gains(team, pool, baseline=report),
                       recent_commitments(league, team, week), FP.snapshot(league, team, market=comparisons))
    comps = MK.VAL.pool_from_league(league)
    moves = []
    for player in sorted(pool, key=lambda p: (-p.ovr, p.pid)):
        if not teams:
            break
        bidders = []
        quote = None
        for abbr, (report, gains, recent, budget) in teams.items():
            if gains.get(player.pid, 0.) <= 1. or PS.shunned(player, abbr, league):
                continue
            if quote is None:
                quote = MK.VAL.value_player(league, player, pool=comps, rng=rng)
            if not quote:
                continue
            proposal = _proposal(league, league.teams[abbr], player, quote,
                                 report, recent, budget, comparisons)
            if proposal:
                bidders.append(proposal)
        if not bidders:
            continue
        winner = MK.best_offer(league, player, [x[0] for x in bidders], quote['apy'])
        _, outgoing, gain = next(x for x in bidders if x[0] is winner)
        # Final legal preview is before either mutation. Signing uses exactly
        # the frozen terms that passed player consent and the joint budget.
        team = league.teams[winner.team]
        require_room(league, team, player.pid, MK.offer_contract(league, player, winner),
                     release_pid=outgoing.pid if outgoing else None)
        if outgoing:
            league.release(outgoing.pid)
        MK.sign(league, player, winner, CAP.get(league.year, 301.2), market_apy=quote['apy'])
        # Other acquisition routes use this saved marker as well. Camp's old
        # offseason week-22 log must not lose its protection at cutdown week 0.
        player.xp_spent['_cpu_added'] = [league.year, week]
        if stage != 'camp':
            team._moved_week = week
        # Enrich the ordinary signing record; don't create a second league
        # transaction/email for the same acquisition.
        for tx in reversed(league.transactions):
            if tx.get('kind') == 'sign' and tx.get('pid') == player.pid and tx.get('team') == team.abbr:
                tx.update(market_stage=stage, replaced_pid=outgoing.pid if outgoing else None,
                          planning_gain=round(gain, 3))
                break
        moves.append((team.abbr, player.pid, outgoing.pid if outgoing else None))
        del teams[team.abbr]
    notes['_veteran_market'] = dict(year=league.year, done=done + [key])
    return moves
