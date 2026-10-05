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

    The current offseason can straddle a league-year rollover. Its old logs
    carry week 22; the last played season separates them from older recruits.
    A trade or waiver claim is a commitment too.
"""
    ids = set()
    offseason = league.phase not in ('regular', 'playoffs')
    for tx in reversed(getattr(league, 'transactions', ())):
        year = int(tx.get('year', league.year))
        during_season = tx.get('phase') in ('regular', 'playoffs')
        if during_season:
            if offseason or year != league.year:
                break
            if not 0 <= week - int(tx.get('week') or 0) <= 3:
                continue
        elif year < league.year - 1 or (not offseason and week > 3):
            break
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


def _performance(league, player, cache):
    """Role-relative evidence; missing/short samples are not poor performance."""
    import dev_evaluation as DE
    if 'performance_rows' not in cache:
        book = (getattr(league, 'stats', {}) or {}).get(league.year, {})
        # Rollover creates an empty new-season book, not new evidence about
        # the incumbent. Use the latest completed season until play supplies
        # a current book; never blend an older good season into current form.
        if not book:
            completed = getattr(league, 'season_closed_year', None)
            if completed is not None and int(completed) < int(league.year):
                book = (getattr(league, 'stats', {}) or {}).get(int(completed), {})
        rows = {pid: row for pid, line in book.items()
                if (p := league.player(pid)) is not None
                and (row := DE.assessment(p, line)) is not None}
        DE.calibrate_coverage(rows)
        cache['performance_rows'] = rows
    rows = cache['performance_rows']
    row = rows.get(player.pid)
    if row is None:
        return .5, 0.
    peers = [r['score'] for pid, r in rows.items() if pid != player.pid
             and r['group'] == row['group'] and r['confidence'] >= .25]
    if len(peers) < 4:
        return .5, row['confidence']
    percentile = sum((v < row['score']) + .5 * (v == row['score']) for v in peers) / len(peers)
    return percentile, row['confidence']


def _service_view(league, player, contract=None):
    """Public retention/aging view with calendar stubs removed, without mutation."""
    view = copy.copy(player)
    c = player.contract if contract is None else contract
    if c is not None:
        view.contract = copy.copy(c)
        start = max(int(getattr(c, 'start_offset', 0) or 0),
                    int(getattr(league, 'season_closed_year', None) == league.year))
        view.contract.years = max(0, c.years-start)
    return view


def replacement_read(league, team, incoming, outgoing, contract, gain, report,
                     quote, *, cache=None):
    """Preference for a complete replacement versus standing pat, in roster points.

    Reuse public development, neutral aging, role evidence and trade valuation.
    The asset estimate is an opportunity cost, NOT a promised bid. This route
    never invents a trade or gives a non-cap casualty a discounted trade floor.
    Coefficients below are GM decision weights, not measured probabilities.
    """
    if outgoing is None:
        return dict(approved=True, net_gain=gain, immediate_gain=gain,
                    reason='open_roster_place')
    import regression as REG
    from types import SimpleNamespace
    from trade_calendar import trading_open
    cache = {} if cache is None else cache
    gm = team.gm.shift(team.ctx())
    trait = lambda k: max(0., min(1., float(getattr(gm, k, .5))))
    youth, patience, aggression = trait('youth'), trait('patience'), trait('aggression')
    share = min(1., _shares(report).get(outgoing.pid, 0.))
    signed = _service_view(league, incoming, contract)
    incumbent = _service_view(league, outgoing)
    roster_key = ('service_roster', team.abbr, tuple(p.pid for p in report['players']))
    if roster_key not in cache:
        cache[roster_key] = [_service_view(league, p) for p in report['players']]
    retained_players = cache[roster_key]
    retention = (RN.retention_value(team, signed, retained_players)
                 - RN.retention_value(team, incumbent, retained_players))
    def age_loss(p):
        key = ('aging', p.pid)
        if key not in cache:
            q = copy.copy(p); q.ratings = dict(p.ratings); q.longevity = 1.
            cache[key] = REG.decline(q, SimpleNamespace(normal=lambda *a: 1.), age=p.age + 1)
        return cache[key]
    # Expiring players have only a renewal option, not guaranteed future control.
    horizon = 1. if max(signed.contract.years,
                       incumbent.contract.years if incumbent.contract else 0) > 1 else .25
    aging = (age_loss(incoming) - age_loss(outgoing)) * share * horizon * (.5 + youth)
    key = ('performance', outgoing.pid)
    if key not in cache: cache[key] = _performance(league, outgoing, cache)
    percentile, confidence = cache[key]
    continuity = share * confidence * (.5 + percentile) * (1. + 2.*patience + trait('loyalty'))
    # Price the incumbent through the existing deterministic trade model. Free
    # agents at the same job reduce the likely recoverable value of his rights.
    key = ('asset', outgoing.pid)
    if key not in cache:
        v = MK.VAL.value_player(league, outgoing, side='team', rng=None, pool=cache.get('quote_pool'))
        if v and outgoing.contract:
            # Use the same remaining-service, actual annual pay and public
            # development quote as a trade. This is an option value, not an
            # invented buyer or a promise that the club can recover it.
            import trades as TR
            asset = TR.player_asset(league, team, outgoing, cache.get('quote_pool'), None)
            cache[key] = max(0., asset['trade_value']) if asset else 0., float(v['apy'])
        else:
            cache[key] = 0., float(quote['apy'])
    asset, old_quote = cache[key]
    # Use the same 4.5%-per-grade valuation sensitivity as trade scheme pricing.
    dollars_per_point = max(.25, .045 * max(old_quote, float(quote['apy'])))
    street_factor = .15 if incoming.pos == outgoing.pos and incoming.ovr >= outgoing.ovr - 1.5 else .55
    asset_cost = asset / dollars_per_point * street_factor * (.5 + patience) * (1. - .5*aggression)
    if not trading_open(league): asset_cost = 0.
    c = outgoing.contract
    saved = c.release(0, league.post_june1())[2] if c else 0.
    # Both are unearned, current-year cap amounts. Future funding and dead
    # charges remain subject to the authoritative joint financial preview.
    cap_change = contract.cap_hit(0) - saved
    remaining = max(0., (18. - float(league.week or 0)) / 18.) if league.phase == 'regular' else 1.
    immediate = gain * remaining * (.75 + .5*aggression)
    # Do not charge the new salary twice: acquisition_read already compares
    # the full commitment to this role's benefit, and FP checks the joint
    # release/signing against current and future books.
    net = immediate + retention * (.5 + youth) - aging - continuity - asset_cost
    return dict(approved=net > 1., reason='worthwhile_replacement' if net > 1. else 'prefer_keep_or_trade',
        net_gain=round(net, 4), immediate_gain=round(immediate, 4),
        retention_change=round(retention, 4), aging_cost=round(aging, 4),
        continuity_cost=round(continuity, 4), performance_percentile=round(percentile, 4),
        performance_confidence=round(confidence, 4), released_asset_value=round(asset, 3),
        asset_cost=round(asset_cost, 4), current_cap_change=round(cap_change, 4))


def _proposal(league, team, player, quote, report, recent, budget, comparisons, *, cache=None):
    """Prepare an entire funded move before accepting or releasing anybody."""
    price = round(max(.70 * quote['apy'], MS.minimum_salary(player.accrued or 0,
                                                          CAP.get(league.year, 301.2))), 3)
    # A full roster considers coverage-safe replacements at the relevant job.
    departures = (q for q in PS._room_candidates(league, team, player) if q.pid not in recent) \
        if len(team.active()) >= 53 else iter((None,))
    old_shares = _shares(report)
    best = None
    cache = {} if cache is None else cache
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
            replacement = replacement_read(league, team, player, outgoing, contract,
                                           gain, report, quote, cache=cache)
            if not replacement['approved']:
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
            if best is None or replacement['net_gain'] > best[3]['net_gain']:
                best = offer, outgoing, gain, replacement
    return best


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
    # One review sees unchanged season evidence. Keep this ephemeral; a later
    # review must reprice contracts and never reuse stale player assessments.
    cache = {'quote_pool': comps}
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
                                 report, recent, budget, comparisons, cache=cache)
            if proposal:
                bidders.append(proposal)
        if not bidders:
            continue
        winner = MK.best_offer(league, player, [x[0] for x in bidders], quote['apy'])
        _, outgoing, gain, replacement = next(x for x in bidders if x[0] is winner)
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
                          planning_gain=round(gain, 3), replacement_assessment=replacement)
                break
        moves.append((team.abbr, player.pid, outgoing.pid if outgoing else None))
        del teams[team.abbr]
    notes['_veteran_market'] = dict(year=league.year, done=done + [key])
    return moves
