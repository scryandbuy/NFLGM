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


# How far apart two clubs can see the same man, in overall points. Real
# disagreement is scheme fit and it is not built yet; this stands in for it.
PERCEPTION_SPREAD = 3.5

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
    seen = p.ovr
    if viewer is not None:
        seed = (hash((getattr(viewer, 'abbr', ''), p.pid)) % 10000) / 10000.0
        seen = p.ovr + (seed - 0.5) * 2.0 * PERCEPTION_SPREAD
        v = dict(v, apy=v['apy'] * (1.0 + 0.045 * (seen - p.ovr)))
    row = dict(age=p.age, apy=p.apy,
               contract_years_left=p.contract_years_left,
               madden_position=p.pos)
    return dict(kind='player', pid=p.pid, pos=p.pos, age=p.age, apy=p.apy,
                need=need, trade_value=TE.trade_value(row, v),
                seen_ovr=round(float(seen), 1), obj=p)


def pick_asset(league, pk, need=False):
    return dict(kind='pick', pick=pk.selection or (pk.round - 1) * 32 + 16,
                years_out=max(0, pk.year - league.year), need=need,
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
        by = {}
        for pos, men in t.depth.items():
            by.setdefault(GRP.get(pos, pos), []).extend(men)
        for grp, men in by.items():
            if men:
                tops.setdefault(grp, []).append(max(p.ovr for p in men))
    bar = {g: float(np.median(v)) for g, v in tops.items()}
    _BAR_CACHE.clear()
    _BAR_CACHE[key] = bar
    return bar


def surplus_and_needs(league, team, pool, rng, n=3):
    """
    Who a club can spare and where it is thin. Surplus is depth behind a
    starter who is clearly better; need is a spot with nobody.
    """
    surplus, needs = [], set()
    league_bar = starter_bar(league)
    depth = team.depth
    by_group = {}
    for pos, men in depth.items():
        by_group.setdefault(GRP.get(pos, pos), []).extend(men)
    for grp, men in by_group.items():
        men = sorted(men, key=lambda p: -p.ovr)
        # A man behind two better ones at his own group is expendable, and a
        # group with nobody spare is a hole.
        if len(men) >= 3:
            for p in men[2:4]:
                if men[0].ovr - p.ovr > 3:
                    a = player_asset(league, team, p, pool, rng,
                                     viewer=team)
                    if a:
                        a['grp'] = grp
                        surplus.append(a)
        # NEED IS QUALITY, NOT HEADCOUNT. Asking whether a group had one man
        # or fewer meant an offensive line of nine was never a need however
        # bad it was, and needs fired only at kicker and quarterback. A club
        # needs a tackle when its best tackle is a 72 and the league starts
        # 82s, which is also the only definition a trade can act on.
        if not men or men[0].ovr < league_bar.get(grp, 75.0) - NEED_GAP:
            needs.add(grp)
    surplus.sort(key=lambda a: -a['trade_value'])
    return surplus[:n], needs


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
        if pk.year < league.year or pk.used_on is not None:
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
             if pk.year >= league.year and pk.used_on is None]
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
MAX_PACKAGE = 4


def _negotiate(league, ta, tb, target, ga, gb, ctx_a, ctx_b, sa, sb, surplus,
               rng):
    """
    Build up an offer until the other club takes it.

    Start with the cheapest single asset and ADD to it rather than swapping to
    a dearer one. That is what the data shows - a club chasing a good player
    sends two or three things, and a club buying depth sends one - and it
    falls out naturally instead of being imposed: an expensive target simply
    needs more added before the seller says yes.

    A surplus PLAYER can go into the package too, which is where the 55% of
    real deals that are players plus picks come from.
    """
    bank = _picks_by_price(league, ta, ga, ctx_a, sa)
    bank += [x for x in surplus if x['pid'] != target.get('pid')]
    if not bank:
        return None, None

    pkg = []
    for _step in range(MAX_PACKAGE):
        best = None
        for cand in bank:
            if cand in pkg:
                continue
            o = dict(a_sends=pkg + [cand], a_gets=[target])
            r = TE.evaluate(o, ctx_a, ctx_b, sa, sb, ga, gb)
            if r['a_gain'] <= -ACCEPT_WINDOW:
                continue                    # paying this much stops paying off
            if (will_accept(r['a_gain'], rng, ga['aggression'])
                    and will_accept(r['b_gain'], rng, gb['aggression'],
                                    selling=True)):
                return o, r
            # not enough yet - keep the addition that moved him furthest
            if best is None or r['b_gain'] > best[0]:
                best = (r['b_gain'], cand)
        if best is None:
            return None, None
        pkg.append(best[1])
    return None, None


def run(league, rng, rounds=2, verbose=False):
    """
    Clubs shop their surplus. A deal goes through only when both sides price
    it as a gain through their own window.
    """
    pool = VAL.pool_from_league(league)
    cap_space = {a: t.cap_space for a, t in league.teams.items()}
    made = []
    teams = list(league.teams)

    for _r in range(rounds):
        rng.shuffle(teams)
        for a in teams:
            ta = league.teams[a]
            sa, na = surplus_and_needs(league, ta, pool, rng)
            if not sa:
                continue
            ga = persona(ta.gm)
            ctx_a = ta.ctx()
            for b in teams:
                if b == a:
                    continue
                tb = league.teams[b]
                sb, nb = surplus_and_needs(league, tb, pool, rng)
                if not sb:
                    continue
                gb = persona(tb.gm)
                ctx_b = tb.ctx()
                # MOST TRADES ARE A PLAYER FOR A PICK, not a swap of needs.
                # Requiring each club to want exactly what the other spares
                # produced four matched pairs in the whole league and no deals.
                # A pick is the currency that makes an uneven trade even.
                want_a = [x for x in sb if x.get('grp') in na]
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
                offer, res = _negotiate(league, ta, tb, target, ga, gb,
                                        ctx_a, ctx_b, cap_space[a],
                                        cap_space[b], sa, rng)
                if offer is None:
                    continue
                out = [x['obj'] if x['kind'] == 'pick' else x['pid']
                       for x in offer['a_sends']]
                league.trade(a, b, out, [offer['a_gets'][0]['pid']])
                made.append((a, b, offer['a_sends'], offer['a_gets'][0]['obj'],
                             res))
                ta.sync_cap(); tb.sync_cap()
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
