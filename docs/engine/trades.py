from stable import stable_seed
"""
THE TRADE MARKET.

trade_engine was built and never called once. It already knows how to price an
asset through a club's own eyes and how to decide whether a deal is good for
both sides; what it never had was anybody to bring two clubs together.

WHY A TRADE HAPPENS HERE, which is the whole design:

  Both clubs have to believe they gained, and they can BOTH be right. Each
  prices the same asset through its own competitive window, its own general
  manager and its own season, so a rebuilding club and a contender genuinely
  value a 31-year-old differently. That disagreement is the mechanism rather
  than a rounding error - if everyone priced assets identically no trade would
  ever happen.

  PICKS HAVE TWO PRICES. What a pick is worth and what clubs pay for it are
  different numbers: pick 32 trades at 16.9% of pick 1 and RETURNS 55.3% of
  it. An analytics front office prices nearer the true value and a traditional
  one nearer the market, and `pick_lens` is exactly that axis. The gap is the
  edge, and it is the reason a smart club can win a trade without anyone being
  stupid.

  A GREAT PLAYER ON A TERRIBLE CONTRACT HAS NEGATIVE VALUE. trade_value is
  surplus - what he is worth minus what he costs - over the years you control
  him. That is why a club will attach a pick to move a bad deal.

THE PERSONA IS DERIVED, NOT DRAWN. trade_engine carries its own GM archetypes,
and giving a club a second, unrelated general manager for trades would mean a
patient man in free agency could be a gunslinger in July. The trade persona is
mapped off the GM the club already has, so there is one identity.
"""
import numpy as np

import trade_engine as TE
import valuation as VAL
from trade_calendar import TRADE_DEADLINE_WEEK, trading_open


def context(team):
    ctx = team.ctx()
    return ctx if 'games_played' in ctx else dict(ctx, **TE.race_context(team))


# How far apart two clubs can see the same man, in overall points. Real
# disagreement is scheme fit and it is not built yet; this stands in for it.
PERCEPTION_SPREAD = 1.2      # residual disagreement; scheme fit carries the rest

# A TRADE IS NOT AN EQUATION. Requiring both sides to clear a hard line meant
# deals died a tenth of a point apart - the seller at 5.97 against an offer of
# 5.84 - and nothing ever moved. Real front offices overpay and underpay, and
# a deal that is marginally bad for one side still happens when he wants the
# player. So a marginal deal gets a roll rather than a rejection.
ACCEPT_WINDOW = 1.2          # how far below even a club will still go
ACCEPT_FLOOR = 0.12          # ...and how often, at the very edge


def will_accept(gain, rng, aggression=0.5, selling=False):
    """
    A clear gain is taken; a marginal loss is a judgement call.

    THE SELLER IS HARDER TO MOVE, and he has to be. With one window for both
    sides a club handed over a starter for a single late pick at a small loss
    and 35 of 36 deals came out one-for-one, where real trades are two-thirds
    packages. A man giving up a player he uses wants to be paid; a man
    acquiring one is the motivated party. That asymmetry is what forces a
    buyer to add a second and third asset, so package size ends up scaling
    with the prize on its own rather than being imposed.
    """
    window = ACCEPT_WINDOW * (0.25 if selling else 1.0)
    if gain > (0.9 if selling else 0.5):
        return True
    if gain < -window:
        return False
    # linear from near-certain at break-even down to rare at the edge
    p = ACCEPT_FLOOR + (1.0 - ACCEPT_FLOOR) * (
        1.0 - (0.5 - gain) / (window + 0.5))
    return rng.random() < p * (0.7 + 0.6 * aggression)


def persona(gm):
    """
    The trade personality this club's general manager already implies.

    board_trust inverts into pick_lens: a man who trusts his own board prices
    picks near their true value, which is the analytics end of the axis.
    """
    if gm is None:
        return TE.GM_ARCHETYPES['balanced']
    return dict(
        pick_lens=float(np.clip(1.0 - getattr(gm, 'board_trust', 0.5), 0, 1)),
        aggression=float(np.clip(getattr(gm, 'aggression', 0.5), .05, .98)),
        own_bias=1.02 + 0.22 * (1.0 - float(getattr(gm, 'aggression', 0.5))),
        target_bias=0.95 + 0.35 * float(getattr(gm, 'aggression', 0.5)),
        patience=float(np.clip(getattr(gm, 'patience', 0.6), .05, .98)),
        contract_focus=float(np.clip(getattr(gm, 'contract_focus', 0.5), 0, 1)),
        archetype='derived')


def player_asset(league, team, p, pool, rng, need=False, viewer=None):
    """
    Price him as he would be ON THE VIEWING CLUB'S ROSTER.

    Overall is not a property of a player, it is a property of a player in a
    scheme - position_score has always taken one and nothing used it here. So
    a man can be a 90 to you and a 95 to them, and neither club is wrong. You
    see YOUR number and never theirs, which is the whole of a negotiation:
    the disagreement IS the trade, not an error to be reconciled.
    """
    if not p.contract or p.contract_years_left <= 0 or p.fa_class == 'tendered':
        return None  # Unsigned rights are not a transferable playing contract.
    v = VAL.value_player(league, p, side='team', pool=pool, rng=rng)
    if not v:
        return None

    # PLACEHOLDER, and deliberately so. The real answer is scheme fit:
    # position_score already takes a scheme and SCHEME_SHIFT already defines
    # six of them - gap and zone blocking, one-gap and two-gap fronts, man and
    # zone coverage - so a player genuinely grades differently for different
    # clubs. But every team's scheme is None, so nothing set it and every club
    # sees the same number. That is on the tabled list with coach identity.
    #
    # Until then the disagreement is manufactured: a stable per-club, per-
    # player perception offset. A club sees ITS number and never the other's,
    # which is the part that matters - you think he is a 90, they think he is
    # a 95, and neither of you is wrong. The offset is noise standing in for a
    # reason, and it should be replaced rather than tuned.
    # SCHEME FIT IS THE REASON. A club sees a man through what it runs: a
    # 380-pound guard is worth more to a gap club than to a zone one, a
    # rangy free safety more to a two-high shell. That structural read plus
    # a small residual disagreement about the man replaces the manufactured
    # perception offset that stood in for it.
    seen = p.ovr
    if viewer is not None:
        from gm_engine import scheme_fit
        fit = scheme_fit(p.ratings, p.pos, viewer)
        seed = (stable_seed((getattr(viewer, 'abbr', ''), p.pid)) % 10000) / 10000.0
        seen = p.ovr + fit + (seed - 0.5) * 2.0 * PERCEPTION_SPREAD
        v = dict(v, apy=v['apy'] * (1.0 + 0.045 * (seen - p.ovr)))
    # THE CAP FACTS OF MOVING HIM. The seller eats every dollar of bonus
    # still prorated (dead money, this year); the buyer inherits only the
    # base and roster bonus. Both used to be ignored in favour of the APY.
    c = getattr(p, 'contract', None)
    if c:
        dead_now, dead_next, _s = c.release(0, league.post_june1())
        # what the seller feels: this year's charge in full, next year's at a
        # discount because it is a year away and a growing cap absorbs it
        dead = round(dead_now + 0.6 * dead_next, 2)
    else:
        dead_now, dead = 0.0, 0.0
    inherit = round(c.cap_hit(0) - c.annual_proration-c.earned_base-c.earned_roster, 2) if c else 0.0
    # WHAT THE BUYER WOULD ACTUALLY PAY. The bonus was paid by the club that
    # signed him and stays on its books; the buyer carries base and roster
    # bonus for the years left. So the same man is worth MORE to acquire the
    # more of his money has already been paid: a $36m-a-year player with a
    # $20m base is, to the buyer, a $20m-a-year player. His own club keeps
    # valuing him on the full contract, which is what it is paying.
    yrs = max(1, int(p.contract_years_left or 1))
    inherited_apy = (round(sum(c.cap_hit(i) - c.bonus_at(i) for i in range(yrs)) / yrs, 2)
                     if c else p.apy)
    from development_value import player_credit
    row = dict(age=p.age, apy=p.apy, ovr=float(seen),
               contract_years_left=p.contract_years_left, madden_position=p.pos,
               development_credit=player_credit(p))
    row_buyer = dict(row, apy=inherited_apy)
    tv_buyer = TE.trade_value(row_buyer, v)
    # THE STREET AND THE SQUAD ARE THE ALTERNATIVE. Why give a pick for a man when a comparable one is a free
    # agent for salary alone, or already on your practice squad? The buyer grades the best man available to
    # him at the spot the same way he grades the target; if the target is not clearly better, his trade value
    # collapses toward what the target has that the alternative does not: a cheaper deal, more years, a scheme fit.
    if viewer is not None and viewer is not team and getattr(viewer, 'abbr', None) != p.team:
        alt = _street_alternative(league, viewer, p)
        if alt is not None:
            alt_seen, alt_cost = alt
            edge = float(seen) - alt_seen                          # how much better the target grades to this club
            cheaper = max(0.0, alt_cost - inherited_apy)          # what the target saves against the alternative's price
            if edge <= 1.5: tv_buyer = min(tv_buyer, 0.15 * tv_buyer + 0.5 * cheaper)
            elif edge <= 4.0: tv_buyer = min(tv_buyer, 0.55 * tv_buyer + 0.5 * cheaper)
    return dict(kind='player', pid=p.pid, pos=p.pos, age=p.age, apy=p.apy,
                need=need, trade_value=TE.trade_value(row, v),
                trade_value_buyer=round(max(0.0, tv_buyer), 2),
                seen_ovr=round(float(seen), 1), obj=p, dead=dead, out_hit=(c.cap_hit(0)-c.earned_base-c.earned_roster if c else 0.0), dead_now=dead_now,
                inherit=inherit, inherited_apy=inherited_apy)


def _street_alternative(league, viewer, p):
    """The best player the viewing club could have at the target's position without a trade: a free agent (for his
    asking price) or a man on its own practice squad (for the minimum). Returns (graded overall, yearly cost) or None.
    The street is priced once a week and cached on the league; only the viewer's scheme fit is applied per call."""
    from gm_engine import scheme_fit
    import practice_squad as PSQ, valuation as VAL
    key = (league.year, league.week or 0, len(league.free_agents))
    cache = league.__dict__.setdefault('_street_cache', {})
    if cache.get('key') != key:
        by_pos = {}
        for pid in (getattr(league, 'free_agents', None) or [])[:400]:
            q = league.player(pid)
            if q is None or q.retired: continue
            by_pos.setdefault(q.pos, []).append(q)
        table = {}
        # Every quote in this table sees the same contracts and statistics.
        # Building comps per free agent repeatedly rescanned the entire season.
        # Keep this snapshot local: a later cache rebuild (including releases
        # after a trade) must price against the then-current league.
        quote_pool = None
        for pos, players in by_pos.items():
            top = sorted(players, key=lambda q: -q.ovr)[:4]
            rows = []
            for q in top:
                try:
                    if quote_pool is None:
                        quote_pool = VAL.pool_from_league(league)
                    vv = VAL.value_player(league, q, side='agent', rng=None, pool=quote_pool); cost = float(vv['apy']) if vv else 1.2
                except Exception: cost = 1.2
                rows.append((q, cost))
            table[pos] = rows
        cache.clear(); cache['key'] = key; cache['table'] = table
    best = None
    for q, cost in cache['table'].get(p.pos, []):
        g = q.ovr + scheme_fit(q.ratings, q.pos, viewer)
        if best is None or g > best[0]: best = (g, cost)
    for q in PSQ.squad(viewer):
        if q.pos != p.pos: continue
        g = q.ovr + scheme_fit(q.ratings, q.pos, viewer)
        if best is None or g > best[0]: best = (g, 1.0)
    return best


def through_buyer_eyes(asset, buyer, seller):
    """
    A surplus list is built once, through the SELLER's scheme. A buyer has
    to look at the same man through his own: the fit difference moves what
    he sees and what he would pay. Cheap, no re-valuation.
    """
    from gm_engine import scheme_fit
    p = asset.get('obj')
    if p is None or asset.get('kind') != 'player':
        return asset
    delta = scheme_fit(p.ratings, p.pos, buyer) - scheme_fit(p.ratings, p.pos, seller)
    if abs(delta) < 1e-9:
        return asset
    a = dict(asset)
    a['seen_ovr'] = round(float(asset['seen_ovr']) + delta, 1)
    scale = 1.0 + 0.045 * delta
    a['trade_value_buyer'] = round(float(asset.get('trade_value_buyer', asset['trade_value'])) * max(0.3, scale), 2)
    return a


def pick_asset(league, pk, need=False):
    # Picks name the season that earned them. The league has already rolled
    # forward when that season's draft is held, so the upcoming pick can be
    # one season behind league.year throughout the pre-draft offseason.
    base_year = int(league.year)
    closed = getattr(league, 'season_closed_year', None)
    last = getattr(league, 'last_draft', None) or {}
    if (league.phase in ('offseason', 'free_agency') and closed is not None
            and int(closed) == base_year - 1 and int(last.get('year', -1)) < base_year - 1):
        base_year -= 1
    return dict(kind='pick', pick=pk.selection or (pk.round - 1) * 32 + 16,
                years_out=max(0, pk.year - base_year), need=need,
                age=22, apy=0.0, trade_value=0.0, obj=pk)


# Clubs trade within a position GROUP, not a slot. A team short at left guard
# will take any interior lineman, and matching on the exact label meant 87
# surplus players and 32 clubs with holes produced zero deals.
GRP = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
       'LEDG': 'EDGE', 'REDG': 'EDGE', 'DT': 'DT',
       'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB',
       'CB': 'CB', 'FS': 'S', 'SS': 'S', 'HB': 'HB', 'FB': 'HB',
       'WR': 'WR', 'TE': 'TE', 'QB': 'QB', 'K': 'ST', 'P': 'ST', 'LS': 'ST'}


# How far below the league's typical starter a club has to be before it counts
# as a hole worth trading for.
NEED_GAP = 4.0

# How much better than what he already has a man must be before it is worth a
# trade at all. A lateral move costs assets and changes nothing.
UPGRADE_GAP = 2.0


def package_trade_targets(team, assets, baseline=None, cache=None, minimum=UPGRADE_GAP):
    """Rank available players by marginal gain in this buyer's package mix."""
    import roster_needs as RN
    baseline = RN.assess(team) if baseline is None else baseline
    cache = {} if cache is None else cache
    unique = {a['pid']: a for a in assets if a.get('obj') is not None}
    missing = [a['obj'] for pid, a in unique.items() if pid not in cache]
    cache.update(RN.candidate_gains(team, missing, baseline=baseline))
    ranked = [dict(a, package_gain=cache[pid]) for pid, a in unique.items()
              if cache[pid] > minimum]
    return sorted(ranked, key=lambda a: (-a['package_gain'], -a.get('seen_ovr', 0), a['pid']))


def street_alternative(league, team, target, baseline, cache, comps):
    """A comparable affordable FA must leave a real reason to spend picks.

    Cache only within one roster decision. Test the target AFTER the possible
    signing, so another hole at the same broad position cannot block a trade.
    """
    import roster_needs as RN
    import market as MK
    from cap_engine import CAP
    from offer_reservations import held, raw_room
    player = target['obj']
    if player.contract is None:
        return False
    pos = player.pos
    group = frozenset(('CB', 'FS', 'SS')) if pos in ('CB', 'FS', 'SS') else frozenset(
        p for p in RN.POSITIONS if GRP.get(p,p) == GRP.get(pos,pos))
    key = tuple(sorted(group))
    if key not in cache:
        candidates = [league.player(pid) for pid in league.free_agents[:400]]
        candidates = [p for p in candidates if p is not None and p.team is None
                      and not p.retired and p.out_until is None and p.pos in group
                      and not MK.pending_offer_sheet(league, p.pid)]
        gains = RN.candidate_gains(team, candidates, baseline=baseline)
        # Keep affordable alternatives even when stronger, expensive players
        # lead the list. Quotes are cached and post-signing reports are built
        # only after contract and cap checks pass.
        cache[key] = [(p, gains[p.pid]) for p in sorted(candidates,
                      key=lambda p: -gains[p.pid])]
    cap = CAP.get(league.year, 301.2)
    for candidate, gain in cache[key]:
        if candidate.team is not None or candidate.pid not in league.free_agents:
            continue
        if gain < target['package_gain'] - UPGRADE_GAP:
            break  # the remaining candidates have still less package value
        quote_key = ('quote', candidate.pid)
        if quote_key not in cache:
            cache[quote_key] = VAL.value_player(league, candidate, side='agent', pool=comps)
        quote = cache[quote_key]
        if not quote:
            continue
        years = 1 if league.phase in ('regular','playoffs','playoffs_closed') else int(quote['years'])
        # Extra years or a much dearer FA are not equivalent contract terms.
        if years != player.contract_years_left or quote['apy'] > player.apy * 1.05:
            continue
        if MK.power(league, team, cap, years) < quote['apy'] * 1.05:
            continue
        terms = MK.signing_terms(league, candidate, team, quote['apy'], years, cap)
        room = raw_room(league, team) - held(league, team.abbr, exclude_pid=candidate.pid)
        if terms['cap_hits'][0] > min(room, target.get('inherit', player.apy)) + .0005:
            continue
        report_key = ('report', candidate.pid)
        if report_key not in cache:
            cache[report_key] = RN.assess(team, list(baseline['players']) + [candidate])
        if RN.move_gain(team, player, baseline=cache[report_key]) <= UPGRADE_GAP:
            return True
    return False


def package_trade_hole(report):
    """The group with the most actual package weakness, for occasional star pursuits."""
    needs = report['package_needs']
    eligible = {pos: need for pos, need in needs.items()
                if GRP.get(pos, pos) != 'ST' and need > .10}
    if not eligible:
        return None
    pos = max(eligible, key=eligible.get)
    return GRP.get(pos, pos)

_BAR_CACHE = {}


def starter_bar(league):
    """
    The median starter at each position group across the league - what 'good
    enough' actually means this season, rather than a fixed number that goes
    stale as the league changes.
    """
    key = id(league), league.year
    if key in _BAR_CACHE:
        return _BAR_CACHE[key]
    tops = {}
    for t in league.teams.values():
        for pos, men in t.depth.items():
            if men:
                tops.setdefault(pos, []).append(max(p.ovr for p in men))
    bar = {g: float(np.median(v)) for g, v in tops.items()}
    _BAR_CACHE.clear()
    _BAR_CACHE[key] = bar
    return bar


def _young_core(player):
    return (getattr(player, 'age', 99) <= 26
            and getattr(player, 'contract_years_left', 0) >= 2
            and player.ovr >= (78 if player.pos == 'QB' else 82))


def seller_veterans(league, team, baseline):
    """A lost-season club may shop replaceable veterans at normal market value.

    This never chooses a cap casualty or grants a liquidation discount. The
    existing fair-price negotiation and final cap checks still decide a trade.
    """
    if (getattr(league, 'phase', None) != 'regular' or not trading_open(league)
            or getattr(team, 'abbr', None) == getattr(league, 'user_team', None)
            or TE.window(context(team)) not in ('rebuilding', 'retooling')):
        return []
    import roster_needs as RN
    import cap_accounting as CA
    from offer_reservations import held
    candidates = [p for p in baseline['players']
                  if p.pos not in ('QB', 'K', 'P', 'LS') and p.age >= 28
                  and p.contract and 0 < p.contract_years_left <= 2
                  and p.fa_class != 'tendered' and p.out_until is None]
    candidates.sort(key=lambda p: (p.contract_years_left, -p.ovr, -p.age, p.pid))
    chosen, groups = [], set()
    # Bound the expensive package reassignments; this is a short shopping
    # list, not a sweep that attempts to dismantle a losing team's roster.
    for p in candidates[:6]:
        grp = GRP.get(p.pos, p.pos)
        if grp in groups or RN.departure_loss(team, p, baseline=baseline) > 6.0: continue
        remaining = [q for q in baseline['players'] if q.pid != p.pid]
        after = RN.assess(team, remaining)
        if set(after['uncovered']) - set(baseline['uncovered']): continue
        before_rows, after_rows = baseline['package_assignments'], after['package_assignments']
        if len(before_rows) != len(after_rows): continue
        # Check every package, including nickel/dime and the second TE/FB:
        # a nominal depth backup is not enough if he cannot fill the actual job.
        safe = True
        for old, new in zip(before_rows, after_rows):
            if old['player'] is None: continue
            if new['player'] is None or new['player'].pos not in new['sources']:
                safe = False; break
            if new['player'].pid != old['player'].pid and float(new['grade'] or 0) < 70:
                safe = False; break
        if not safe: continue
        projected = CA.trade_projection(league, team.abbr, [p.pid], [])
        if projected.space(team.phase) - held(league, team.abbr) < -.0005: continue
        chosen.append(p); groups.add(grp)
        if len(chosen) == 2: break
    return chosen


def surplus_and_needs(league, team, pool, rng, n=3):
    """
    Who a club can spare and where it is thin. Surplus is depth behind a
    starter who is clearly better; need is a spot with nobody.
    """
    import roster_needs as RN
    surplus, needs = [], {}
    roster_report = RN.assess(team, [p for p in team.active() if getattr(p, 'out_until', None) is None])
    roster_needs = roster_report['needs']
    league_bar = starter_bar(league)
    depth = team.depth
    by_group = {}
    for pos, men in depth.items():
        # WHO IS ACTUALLY AVAILABLE. Depth counts everyone on the roster, hurt
        # or not, so a club whose starter is out for the season registered no
        # hole at all - which is the one case where trading for a lesser
        # player is plainly right.
        fit = [p for p in men if p.out_until is None]
        by_group.setdefault(GRP.get(pos, pos), []).extend(fit)
    # SURPLUS is a GROUP question: a fourth healthy lineman is spare whatever
    # slot he is listed at.
    for grp, men in by_group.items():
        if grp == 'ST': continue                 # kickers, punters and snappers are signed off the street, not traded for; the ST group (K + P + LS) is not a depth chart
        men = sorted(men, key=lambda p: -p.ovr)
        if len(men) >= 3:
            for p in men[2:4]:
                if _young_core(p): continue
                if men[0].ovr - p.ovr > 3:
                    if RN.departure_loss(team, p, baseline=roster_report) > 6.0:
                        continue  # he is needed for a job this coach actually runs
                    a = player_asset(league, team, p, pool, rng, viewer=team)
                    if a:
                        a['grp'] = grp
                        surplus.append(a)

    # NEED is a SLOT question, and a SIZE rather than a flag.
    #
    # By slot because a group hides exactly the hole worth trading for: lose
    # your right tackle for the season and the line still contains a
    # 90-overall left tackle, so the group looks fine while the spot is empty.
    #
    # A size because a club with a 74 where the league starts 82s and a club
    # with a 60 are not the same, and treating them alike meant both chased
    # the same 71 when only one of them is improved by him.
    wk_now = int(getattr(league, 'week', 0) or 0)
    street = {}
    for pid_ in (getattr(league, 'free_agents', None) or [])[:400]:
        q_ = league.player(pid_)
        if q_ is not None and not q_.retired and q_.out_until is None: street[q_.pos] = max(street.get(q_.pos, 0.0), q_.ovr)
    for pos in set(depth) | set(RN.POSITIONS):
        men = depth.get(pos, ())
        # a man out two weeks or less still counts as the club's man at the spot: nobody trades a pick to cover a fortnight
        fit = [p for p in men if p.out_until is None or (int(p.out_until) < 99 and int(p.out_until) - wk_now <= 2)]
        have = max((p.ovr for p in fit), default=0.0)
        # the street counts too: a club does not trade for a spot a free agent fills as well
        have = max(have, street.get(pos, 0.0) - 2.0)
        # a hole worth a trade: a real weakness at the premium spots, a gaping one on the interior line, where
        # clubs live with a 72 and sign a veteran rather than pay a pick
        gap = NEED_GAP + (5.0 if pos in ('C', 'LG', 'RG') else 2.0 if pos in ('LT', 'RT', 'SS', 'FS', 'MIKE', 'WILL', 'SAM', 'TE') else 0.0)
        if have < league_bar.get(pos, 75.0) - gap or roster_needs.get(pos, 0.0) >= 0.75:
            grp = GRP.get(pos, pos)
            if grp == 'ST': continue                 # a club short a kicker signs one; it does not trade for one
            if grp not in needs or have < needs[grp]:
                needs[grp] = have

    have = {a['pid'] for a in surplus}
    for p in seller_veterans(league, team, roster_report):
        if p.pid in have: continue
        a = player_asset(league, team, p, pool, rng, viewer=team)
        if a and a['trade_value'] > 0:
            a['grp'] = GRP.get(p.pos, p.pos)
            a['seller_veteran'] = True
            surplus.append(a); have.add(p.pid)
    surplus.sort(key=lambda a: (not a.get('seller_veteran', False), -a['trade_value']))
    # A MAN WHO ASKED OUT is shopped like surplus, at his market value: his
    # club is willing where it was not, and buyers see him in the flow
    import morale as MO
    have = {x['pid'] for x in surplus}
    for pos, men in depth.items():
        for p in men:
            if MO.wants_out(p) and p.pid not in have and p.out_until is None:
                a = player_asset(league, team, p, pool, rng)
                if a:
                    a['grp'] = GRP.get(pos, pos); a['wants_out'] = True
                    surplus.insert(0, a)
    return surplus[:n + sum(1 for x in surplus if x.get('wants_out'))], needs


STAR_ASK = {'contending': 1.60, 'win_now': 1.45, 'middling': 1.30, 'retooling': 1.15, 'rebuilding': 1.05}


def stars_at(league, team, pool, rng, grp, viewer=None):
    """
    The men a club is NOT trying to move: its best one or two at a group.
    They are available the way anyone is available - at a price. A
    contending club asks 60% over what it thinks he is worth and will not
    move its quarterback; a rebuilding one asks a little over and listens.
    """
    out = []
    men = sorted((p for pos, ps in team.depth.items() if GRP.get(pos, pos) == grp for p in ps
                  if p.out_until is None), key=lambda p: -p.ovr)[:2]
    wdw = TE.window(context(team))
    import morale as MO
    for p in men:
        wants_out = MO.wants_out(p)
        # A MAN WHO ASKED OUT is available where he was untouchable, and his
        # club takes a fair offer where it wanted a premium. The price does
        # not move: buyers pay what he is worth, they just get to buy him.
        if not wants_out:
            if _young_core(p): continue
            if p.pos == 'QB' and wdw in ('contending', 'win_now'):
                continue                              # the one man not for sale
            if p.ovr >= 95 and p.age < 30 and wdw in ('contending', 'win_now'):
                continue                              # nor is a 95 in his prime
        a = player_asset(league, team, p, pool, rng, viewer=viewer or team)
        if a:
            a['grp'] = grp; a['star'] = True; a['ask'] = 1.0 if wants_out else STAR_ASK[wdw]
            if wants_out: a['wants_out'] = True
            out.append(a)
    return out


def _picks_by_price(league, team, gm, ctx, space):
    """
    Every pick this club holds, cheapest first, as it prices them itself.

    Which one it parts with is the decision: a club that prices picks near
    their true value guards them, one that prices them at market spends them
    freely. That is `pick_lens`, and it is why two front offices can both walk
    away happy.
    """
    out = []
    for pk in team.picks:
        if pk.year < league.year or pk.year > league.year + 2 or pk.used_on is not None:      # this draft and the next two
            continue
        a = pick_asset(league, pk)
        out.append((TE.team_price(a, ctx, space, gm, owns=True), a))
    out.sort(key=lambda x: x[0])
    return [a for _c, a in out]


def _pick_to_offer(league, team, target, gm, ctx, space):
    """
    The cheapest pick this club holds that the other side would take for him.

    A pick is the currency of an uneven trade, and which one you part with is
    the decision: a club that prices picks near their true value guards them,
    and one that prices them at market spends them freely. That is `pick_lens`
    and it is why two front offices can both be happy.
    """
    owned = [pk for pk in team.picks
             if league.year <= pk.year <= league.year + 2 and pk.used_on is None]
    if not owned:
        return None
    want = TE.team_price(target, ctx, space, gm, owns=False)
    best = None
    for pk in sorted(owned, key=lambda k: (k.year, k.round)):
        a = pick_asset(league, pk)
        cost = TE.team_price(a, ctx, space, gm, owns=True)
        if cost >= want * 0.55:
            if best is None or cost < best[0]:
                best = (cost, a)
    return best[1] if best else None


# WHAT A REAL TRADE LOOKS LIKE, from 1,077 deals across fifteen seasons:
#   only 34% are one asset for one asset - 41% move three, 16% four, 9% five
#     or more, averaging 3.04 assets a deal
#   55% are players PLUS picks, 39% picks only, and just 6% are player for
#     player straight up
#   82% of player acquisitions headline a day-three pick, and a first-rounder
#     changes hands for a player in only 5% of deals
#   package size scales with the prize: a first-round headline comes with 2.59
#     picks on average, a sixth-rounder with 1.03
#
# So a package is the normal shape and a single pick is the cheap end of it.
MAX_PACKAGE = 5


def _financial_trade(league, ta, tb, outgoing, incoming, cache=None):
    """Price both complete rosters, including any cuts needed for this trade."""
    import cap_accounting as CA
    import financial_plan as FP
    import roster_needs as RN
    # One negotiation can compare many pick combinations for the same player
    # exchange. Reuse its roster math, never cache beyond that negotiation.
    cache = {} if cache is None else cache
    key = (ta.abbr, tb.abbr, tuple(sorted(x for x in outgoing if isinstance(x, str))),
           tuple(sorted(x for x in incoming if isinstance(x, str))))
    if key not in cache:
        try:
            releases = league._trade_roster_releases(ta.abbr, tb.abbr, outgoing, incoming)
            CA.require_trade_room(league, ta.abbr, tb.abbr, outgoing, incoming, releases)
        except ValueError:
            cache[key] = None
            return False
        if 'retention_market' not in cache:
            cache['retention_market'] = FP.retention_market(league)
        market = cache['retention_market']
        states = {}
        for team, sent, received in ((ta, outgoing, incoming), (tb, incoming, outgoing)):
            if team.abbr == getattr(league, 'user_team', None):
                continue
            removed = [x for x in sent if isinstance(x, str)] + list(releases.get(team.abbr, ()))
            arrivals = [league.player(x) for x in received if isinstance(x, str)]
            arrivals = [p for p in arrivals if p is not None and p.contract]
            trial = CA.trade_projection(league, team.abbr, removed, received)
            contracts = {pid: c for pid, c, _ in trial.contracts}
            projected = [p for p in team.active() if p.pid not in removed] + arrivals
            gain = RN.assess(team, projected)['score'] - RN.assess(team)['score']
            states[team.abbr] = dict(additions=[(p, contracts[p.pid]) for p in arrivals],
                removals=removed, trial_cap=trial, gain=gain, market=market,
                before=FP.snapshot(league, team, market=market))
        cache[key] = states
    if cache[key] is None:
        return False
    for team, sent, received in ((ta, outgoing, incoming), (tb, incoming, outgoing)):
        if team.abbr == getattr(league, 'user_team', None):
            continue
        sent_picks = {id(x) for x in sent if not isinstance(x, str)}
        picks = [pk for pk in team.picks if id(pk) not in sent_picks]
        picks += [x for x in received if not isinstance(x, str)]
        decision = FP.evaluate(league, team, **cache[key][team.abbr], action='trade', picks=picks)
        if not decision['approved']:
            return False
    return True


MAX_PACKAGE_SEARCH = 50000  # fail closed on pathological pick-hoarding banks
MAX_PACKAGE_ROSTER_CHECKS = 64  # also bound costly role assignments


def _upgrade_budget(gain):
    """Small upgrades receive 40% of the ceiling; gains of six receive all.

    Smoothstep avoids a spending jump at either end. This is a roster gain,
    not an OVR difference: package usage and reserve depth already enter it.
    """
    t = min(1.0, max(0.0, (float(gain) - UPGRADE_GAP) / 4.0))
    return .4 + .6 * t * t * (3.0 - 2.0 * t)


def _market_floor(target):
    """A pick philosophy cannot erase most of a controlled player's value.

    Rentals and an explicit request to leave allow a larger concession. A
    decided cap casualty has its own shop_cap_casualty path; merely being
    over the cap does not turn every player into a forced-sale exception.
    """
    player = target.get('obj')
    years = getattr(player, 'contract_years_left', 2)
    fraction = .5 if years <= 1 or target.get('wants_out') else .75
    return max(0.0, float(target.get('trade_value', 0) or 0)) * fraction


def _negotiate(league, ta, tb, target, ga, gb, ctx_a, ctx_b, sa, sb, surplus,
               rng, needs_b=None):
    """Find the cheapest acceptable complete offer, up to five assets.

    Prices and willingness are fixed for this negotiation. Compare alternate
    combinations instead of adding an expensive pick to a failed offer.
    Positive costs, suffix value bounds and a node budget bound the work. If
    the budget is exhausted, decline rather than return an unproven overpay.
    ``needs_b`` remains for caller compatibility; actual recipient roles decide
    whether an outgoing player helps, including combinations of players.
    """
    import roster_needs as RN
    from types import SimpleNamespace

    market = float(target.get('trade_value', 0.0) or 0.0)
    wdw = TE.window(ctx_a)
    prem = (1.40 if target.get('star') else 1.25) if wdw in ('contending', 'win_now') else (1.25 if target.get('star') else 1.10)
    gain = target.get('package_gain')
    if gain is None:
        gain = RN.move_gain(ta, target['obj'])
    ceiling = (market * prem + .35) * _upgrade_budget(gain)
    floor = _market_floor(target)
    if ceiling <= 0 or ceiling + 1e-9 < floor:
        return None, None

    raw = _picks_by_price(league, ta, ga, ctx_a, sa)
    candidates = {x['pid']: x for x in surplus
                  if x['pid'] != target.get('pid') and x.get('obj') is not None
                  and 0 < float(x.get('trade_value', 0) or 0) <= ceiling}
    # Assess the receiving roster AFTER the target leaves. A replacement can
    # help even when he would have sat behind the traded player beforehand.
    recipient = [p for p in tb.active() if p.pid != target.get('pid')]
    roster_scores, exhausted = {}, False
    def roster_score(ids):
        nonlocal exhausted
        ids = tuple(sorted(ids))
        if ids not in roster_scores:
            if len(roster_scores) >= MAX_PACKAGE_ROSTER_CHECKS:
                exhausted = True
                return float('-inf')
            roster_scores[ids] = RN.assess(tb, recipient + [candidates[i]['obj'] for i in ids])['score']
        return roster_scores[ids]

    if candidates:
        base = roster_score(())
        raw += [x for pid, x in candidates.items()
                if roster_score((pid,)) > base + 1e-6]
        if exhausted:
            return None, None

    bank, seen = [], set()
    for asset in raw:
        if asset['kind'] == 'pick':
            pk = asset['obj']
            key = ('pick', pk.year, pk.round, pk.original)
            paid = float(TE.pick_value_dollars(asset['pick'], asset.get('years_out', 0)))
        else:
            key = ('player', asset['pid'])
            paid = float(asset.get('trade_value', 0.0) or 0.0)
        if key in seen:
            continue
        seen.add(key)
        buyer = TE.team_price(asset, ctx_a, sa, ga, owns=True)
        seller = TE.team_price(asset, ctx_b, sb, gb, owns=False)
        # Salary dumps and negative-value sweeteners need a separate market;
        # this ordinary upgrade search spends only useful, positive assets.
        if 0 < paid <= ceiling and buyer >= 0 and seller > 0:
            bank.append((paid, buyer, seller, key, asset))
    bank.sort(key=lambda row: (row[0], row[3]))
    if not bank:
        return None, None

    # Reusing each draw prevents repeated counteroffers from turning a low
    # acceptance chance into a near-certain sale by trying many combinations.
    draw_a, draw_b = float(rng.random()), float(rng.random())
    roll_a = SimpleNamespace(random=lambda: draw_a)
    roll_b = SimpleNamespace(random=lambda: draw_b)
    value_in = TE.team_price(target, ctx_a, sa, ga, owns=False)
    ask = TE.team_price(target, ctx_b, sb, gb, owns=True)
    def accepts_a(cost):
        margin = round(value_in - cost, 2)
        return margin > -ACCEPT_WINDOW and will_accept(margin, roll_a, ga['aggression'])
    def accepts_b(value):
        return will_accept(round(value - ask, 2), roll_b, gb['aggression'], selling=True)

    # Upper bound on what any remaining k assets could bring the seller.
    # Ignoring their costs/cap/role fit is optimistic and therefore safe for
    # pruning: no valid cheaper package is removed by this bound.
    n = len(bank)
    upper = [[0.0] * (MAX_PACKAGE + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for k in range(1, MAX_PACKAGE + 1):
            upper[i][k] = max(upper[i+1][k], bank[i][2] + upper[i+1][k-1])
    valid_players = {}
    financial_cache = {}
    best, nodes = None, 0

    def legal(items):
        ids = tuple(sorted(x['pid'] for x in items if x['kind'] == 'player'))
        if ids not in valid_players:
            offer = dict(a_sends=[candidates[i] for i in ids], a_gets=[target])
            valid = TE.cap_blocks(offer, sa, sb, ga, gb) is None
            if valid and ids:
                total = roster_score(ids)
                valid = all(total > roster_score(tuple(j for j in ids if j != i)) + 1e-6
                            for i in ids)
            valid_players[ids] = valid
        if not valid_players[ids]:
            return False
        if league is not None:
            sent = [x['obj'] if x['kind'] == 'pick' else x['pid'] for x in items]
            return _financial_trade(league, ta, tb, sent, [target['pid']], financial_cache)
        return True  # Standalone valuation/search probes have no league ledger.

    def visit(start, chosen, paid, cost, value):
        nonlocal best, nodes, exhausted
        nodes += 1
        if nodes > MAX_PACKAGE_SEARCH:
            exhausted = True
            return
        if not accepts_a(cost):
            return  # every remaining asset has a nonnegative buyer cost
        if chosen and paid + 1e-9 >= floor and accepts_b(value):
            items = [bank[i][4] for i in chosen]
            if legal(items):
                rank = (paid, len(chosen), cost, tuple(bank[i][3] for i in chosen))
                if best is None or rank < best[0]:
                    best = (rank, items)
                return  # any superset costs more
            if exhausted:
                return
        left = MAX_PACKAGE - len(chosen)
        if not left or not accepts_b(value + upper[start][left]):
            return
        limit = min(ceiling, best[0][0] if best else ceiling)
        for i in range(start, n):
            row = bank[i]
            if paid + row[0] > limit + 1e-9:
                break
            visit(i + 1, chosen + (i,), paid + row[0], cost + row[1], value + row[2])
            if exhausted:
                return
            limit = min(ceiling, best[0][0] if best else ceiling)

    visit(0, (), 0.0, 0.0, 0.0)
    if exhausted or best is None:
        return None, None
    offer = dict(a_sends=best[1], a_gets=[target])
    result = TE.evaluate(offer, ctx_a, ctx_b, sa, sb, ga, gb)
    result['search'] = dict(
        target_gain=round(float(gain), 3), target_market=round(market, 3),
        market_floor=round(floor, 3), market_ceiling=round(ceiling, 3),
        package_market=round(best[0][0], 3), candidates=n, nodes=nodes,
        buyer_target_price=round(value_in, 3), seller_ask=round(ask, 3))
    return offer, result


# THE CALENDAR. Real player trades run roughly 40 to 60 across the
# offseason and 20 to 25 in season, most of those in the two weeks before
# the deadline. Nothing after the deadline until the season is over.
IN_SEASON_ACTIVITY = {w: 0.04 for w in range(1, 7)}
IN_SEASON_ACTIVITY.update({7: 0.15, 8: 0.35, 9: 0.60})


def shop_cap_casualty(league, seller, player, rng, june1=None):
    """Last chance for ONE player already selected for release by contracts.

    Never selects a casualty or searches the seller's roster. Picks only:
    receiving salary would undermine the already-decided cap move. Buyers
    retain their roster, contract and price checks. Only an over-cap seller
    may take less than its normal ask, because its alternative is this cut.
    """
    from itertools import combinations
    import roster_needs as RN
    import cap_accounting as CA

    user = getattr(league, 'user_team', None)
    if (seller.abbr == user or player.team != seller.abbr
            or player not in seller.active() or not player.contract
            or player.out_until is not None):
        return False
    if not trading_open(league):
        return False
    offseason = league.phase in ('offseason', 'free_agency')
    if CA.pre_roll(league):
        CA.settle_week(league, 18)
    seller.sync_cap()
    before = seller.cap.charges(seller.phase)
    trial = CA.trade_projection(league, seller.abbr, [player.pid], [])
    relief = before - trial.charges(seller.phase)
    # The emergency June-1 release can differ from a regular-season trade.
    # Do not trade if it would free less room than the cut already selected.
    cut_now, _, _ = player.contract.release(
        0, league.post_june1() if june1 is None else june1)
    trade_now, _, _ = player.contract.release(0, league.post_june1())
    if relief <= .0005 or trade_now > cut_now + .0005:
        return False
    forced = before > seller.cap.limit + .0005
    pool = VAL.pool_from_league(league)
    own = player_asset(league, seller, player, pool, rng, viewer=seller)
    if own is None:
        return False
    ctx_s, gm_s = context(seller), persona(seller.gm)
    ask = TE.team_price(own, ctx_s, seller.cap_space, gm_s, owns=True)
    bids = []
    for abbr, buyer in sorted(league.teams.items()):
        if abbr in (seller.abbr, user):
            continue
        buyer.sync_cap()
        # Accounting phase becomes 'season' at cutdown, even while the
        # calendar still says offseason. Never force a buyer to cut a man.
        limit = 90 if offseason and buyer.phase != 'season' else 53
        if len(buyer.active()) >= limit or RN.move_gain(buyer, player) <= .5:
            continue
        target = player_asset(league, seller, player, pool, rng,
                              need=True, viewer=buyer)
        if target is None:
            continue
        try:
            CA.require_trade_room(league, seller.abbr, abbr, [player.pid], [])
        except ValueError:
            continue
        ctx_b, gm_b = context(buyer), persona(buyer.gm)
        # A clear buyer gain and the ordinary market ceiling are required;
        # cap desperation never persuades the buyer to overpay.
        budget = TE.team_price(target, ctx_b, buyer.cap_space, gm_b) - .5
        premium = 1.25 if TE.window(ctx_b) in ('contending', 'win_now') else 1.10
        ceiling = max(0.0, float(target['trade_value']),
                      float(target['trade_value_buyer'])) * premium + .35
        bank = []
        for pk in buyer.picks:
            asset = pick_asset(league, pk)
            # pick_asset handles the game's previous-season draft labels.
            if (pk.owner != abbr or pk.used_on is not None
                    or pk.year > league.year + 2
                    or pk.year < league.year - (1 if offseason else 0)):
                continue
            if pk.year < league.year and (
                    getattr(league, 'season_closed_year', None) != league.year - 1
                    or int((getattr(league, 'last_draft', None) or {}).get('year', -1)) >= pk.year):
                continue
            cost = TE.team_price(asset, ctx_b, buyer.cap_space, gm_b, owns=True)
            market = TE.pick_value_dollars(asset['pick'], asset['years_out'])
            value = TE.team_price(asset, ctx_s, seller.cap_space, gm_s)
            if 0 < cost <= budget and 0 < market <= ceiling:
                bank.append((pk, cost, market, value))
        best = None
        # Compare every affordable picks-only package (same five-asset limit
        # as ordinary negotiations), then compare buyers. No first low bid.
        for count in range(1, min(MAX_PACKAGE, len(bank)) + 1):
            for package in combinations(bank, count):
                cost = sum(x[1] for x in package)
                market = sum(x[2] for x in package)
                value = sum(x[3] for x in package)
                if cost > budget or market > ceiling or (not forced and value <= ask + .9):
                    continue
                rank = (value, market, -count)
                if best is None or rank > best[0]:
                    best = (rank, [x[0] for x in package])
        if best is not None:
            bids.append((best[0], abbr, best[1]))
    for rank, abbr, picks in sorted(bids, key=lambda bid: bid[0], reverse=True):
        if not _financial_trade(league, seller, league.teams[abbr], [player.pid], picks):
            continue
        try:
            league.trade(seller.abbr, abbr, [player.pid], picks)
        except ValueError:
            continue
        league.log('cap_casualty_trade', team=seller.abbr, buyer=abbr,
                   pid=player.pid, relief=round(relief, 3),
                   discounted=rank[0] <= ask + .9)
        return True
    return False


def run(league, rng, rounds=2, verbose=False, activity=1.0, exclude=(), offers_to_user=True):
    """
    Clubs shop their surplus. A deal goes through only when both sides price
    it as a gain through their own window.

    activity: the share of clubs that pick up the phone this window (1.0 in
    the offseason, a trickle early in the season, most of the league in
    deadline week). exclude: clubs that do not trade on their own, which is
    the user's team.
    """
    if not trading_open(league): return []
    pool = VAL.pool_from_league(league)
    cap_space = {a: t.cap_space for a, t in league.teams.items()}
    made = []
    moved = set()          # nobody changes hands twice in one window
    teams = [a for a in league.teams if a not in set(exclude)]

    for _r in range(rounds):
        rng.shuffle(teams)
        # every club's surplus and needs once a round, not once per pairing:
        # the old loop re-valued the whole league 32 times over and a weekly
        # in-season window took minutes
        active = [a for a in teams if activity >= 1.0 or rng.random() <= activity]
        if not active:
            continue
        sn = {b: surplus_and_needs(league, league.teams[b], pool, rng) for b in teams}
        import roster_needs as RN
        target_reports, target_gains, street_cache = {}, {}, {}
        for a in active:
            ta = league.teams[a]
            sa, _ = sn[a]
            ga = persona(ta.gm)
            ctx_a = context(ta)
            if a not in target_reports: target_reports[a] = RN.assess(ta)
            gain_cache = target_gains.setdefault(a, {})
            for b in teams:
                if b == a:
                    continue
                tb = league.teams[b]
                sb, nb = sn[b]
                if not sb:
                    continue
                gb = persona(tb.gm)
                ctx_b = context(tb)
                # MOST TRADES ARE A PLAYER FOR A PICK, not a swap of needs.
                # Requiring each club to want exactly what the other spares
                # produced four matched pairs in the whole league and no deals.
                # A pick is the currency that makes an uneven trade even.
                # He only wants a man who IMPROVES the hole, not merely one
                # who plays the position. Otherwise a club trades for a 71 to
                # sit behind its own 74, which nobody does.
                # the seller's surplus, seen through the BUYER's scheme
                sb_seen = [through_buyer_eyes(x, ta, tb) for x in sb]
                want_a = [x for x in sb_seen if x['pid'] not in moved]
                # NOT ONLY SURPLUS. A club that is good everywhere but one
                # spot goes and gets someone's starter there and pays for
                # him. Contenders do it most, aggressive GMs do it most, and
                # it is rare enough that a window is still mostly depth
                # deals: the seller's asking price on a star (stars_at) is
                # what keeps it rare, not a rule.
                wdw_a = TE.window(ctx_a)
                selling = ctx_a.get('phase') == 'regular' and wdw_a in ('rebuilding', 'retooling')
                if selling:
                    want_a = [x for x in want_a if x.get('age', 30) < 28]
                chase = (0.35 if wdw_a in ('contending', 'win_now') else 0.10) * (0.5 + ga['aggression'])
                hole = package_trade_hole(target_reports[a])
                if hole and not selling and rng.random() < chase:
                    for x in stars_at(league, tb, pool, rng, hole, viewer=ta):
                        if x['pid'] not in moved:
                            want_a.append(x)
                want_a = package_trade_targets(ta, want_a, target_reports[a], gain_cache)
                want_a = [x for x in want_a if not street_alternative(
                    league, ta, x, target_reports[a], street_cache.setdefault(a, {}), pool)]
                if not want_a:
                    continue
                target = want_a[0]
                target['need'] = True
                # SWEETEN UNTIL HE TAKES IT. A single cheapest-pick offer came
                # within a tenth of a point on deal after deal - the seller
                # valued his man at 5.97 and the pick at 5.84 - and every one
                # of them failed. A buyer who wants a player improves the
                # offer; he does not shrug and walk. He stops when the deal
                # stops being worth it to him, which is what makes the price
                # real rather than arbitrary.
                # The package search checks both clubs' actual contract and
                # rookie funding after the complete exchange.
                # a man already sent away in an earlier deal this window is
                # not in the bank any more (the surplus list was built once)
                sa_live = [x for x in sa if x['pid'] not in moved
                           and getattr(x.get('obj'), 'team', a) == a]
                offer, res = _negotiate(league, ta, tb, target, ga, gb,
                                        ctx_a, ctx_b, cap_space[a],
                                        cap_space[b], sa_live, rng, needs_b=nb)
                if offer is None:
                    continue
                # A man just acquired is not surplus the following round.
                # Without this the same player went to Washington and straight
                # back to Las Vegas inside one window.
                moved.add(offer['a_gets'][0]['pid'])
                for x in offer['a_sends']:
                    if x['kind'] != 'pick':
                        moved.add(x['pid'])
                out = [x['obj'] if x['kind'] == 'pick' else x['pid']
                       for x in offer['a_sends']]
                try: league.trade(a, b, out, [offer['a_gets'][0]['pid']])
                except ValueError: continue
                league.log('ai_trade_decision', buyer=a, seller=b,
                           target_pid=target['pid'],
                           buyer_gain=res['a_gain'], seller_gain=res['b_gain'],
                           offered=[str(x) for x in out],
                           **res.get('search', {}))
                made.append((a, b, offer['a_sends'], offer['a_gets'][0]['obj'],
                             res))
                ta.sync_cap(); tb.sync_cap()
                for changed in (a,b):
                    target_reports.pop(changed, None); target_gains.pop(changed, None)
                    street_cache.pop(changed, None)
                    sn[changed] = surplus_and_needs(league, league.teams[changed], pool, rng)
                cap_space[a], cap_space[b] = ta.cap_space, tb.cap_space
                break

    if verbose:
        print(f'  {len(made)} trades')
        import collections as _c
        print('    package size: %s' % dict(sorted(
            _c.Counter(len(x[2]) for x in made).items())))
        for a, b, outs, inn, res in made[:6]:
            lbl = ' + '.join(
                (f"{o['obj'].year} rd{o['obj'].round}" if o['kind'] == 'pick'
                 else f"{o['obj'].name}") for o in outs)
            print(f'    {a} sends {lbl} '
                  f'for {b} {inn.name} ({inn.pos} {inn.ovr:.0f})  '
                  f'gains {res["a_gain"]:+.1f}/{res["b_gain"]:+.1f}')
    # OFFERS TO THE USER. Clubs come to the user unprompted with the same
    # logic they use on each other: a man in the user's surplus who improves
    # a real hole, priced up until a balanced front office would take it.
    # The offer goes to the inbox and waits; nothing moves until the user
    # says so. Not during the draft (draft_day handles that) and never more
    # than one live offer per club at a time.
    user = [t for t in exclude if t and t in league.teams]
    if user and offers_to_user:
        u = user[0]; tu = league.teams[u]
        import inbox as IB
        live = {m['sender'] for m in IB.pending(league, 'trade_offer')}
        su, nu = surplus_and_needs(league, tu, pool, rng)
        gu, ctx_u = TE.GM_ARCHETYPES['balanced'], context(tu)
        active_now = [a for a in teams if activity >= 1.0 or rng.random() <= activity * 0.6]
        for a in active_now:
            if a in live or not su:
                continue
            ta = league.teams[a]
            sa, _ = surplus_and_needs(league, ta, pool, rng)
            ga, ctx_a = persona(ta.gm), context(ta)
            su_seen = [through_buyer_eyes(x, ta, tu) for x in su]
            import roster_needs as RN
            report = RN.assess(ta)
            candidates = list(su_seen)
            wdw_a = TE.window(ctx_a)
            selling = ctx_a.get('phase') == 'regular' and wdw_a in ('rebuilding', 'retooling')
            if selling: candidates = [x for x in candidates if x.get('age', 30) < 28]
            chase = (0.35 if wdw_a in ('contending', 'win_now') else 0.10) * (0.5 + ga['aggression'])
            hole = package_trade_hole(report)
            if hole and not selling and rng.random() < chase:
                candidates.extend(stars_at(league, tu, pool, rng, hole, viewer=ta))
            want = package_trade_targets(ta, candidates, report)
            alternatives = {}
            want = [x for x in want if not street_alternative(league, ta, x, report, alternatives, pool)]
            if not want:
                continue
            target = dict(want[0]); target['need'] = True
            offer, res = _negotiate(league, ta, tu, target, ga, gu, ctx_a, ctx_u,
                                    cap_space[a], cap_space[u], sa, rng)
            if offer is None:
                continue
            sends = [x['obj'] if x['kind'] == 'pick' else x['pid'] for x in offer['a_sends']]
            why = (('They want him as their starter at ' if target.get('star') else 'They see him as an upgrade at ') + str(target.get('grp')) +
                   ' and are offering ' + ', '.join(
                       (f"their {x['obj'].year} round {x['obj'].round} pick" if x['kind'] == 'pick'
                        else x['obj'].name) for x in offer['a_sends']) + '.')
            IB.post_trade_offer(league, a, u, sends, [target['pid']], why,
                                expires_week=(league.week or 0) + 1)
            live.add(a)
    return made


if __name__ == '__main__':
    import league as LG, season as SN, retirement as RT
    import regression as RG, contracts as CT, tags as TG, market as MK
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)
    L.roll_year(rng)
    L.advance_contracts()
    CT.run(L, rng); CT.enforce(L, rng)
    TG.run(L, rng); CT.enforce(L, rng)
    MK.run(L, rng)
    print('trade window:')
    run(L, rng, verbose=True)
