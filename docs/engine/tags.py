"""
THE RE-SIGN PHASE.

Runs before the market opens, and it is where every club decides what to do
about its OWN pending free agents.

  Tag one man, if he is worth it.
  Tender the restricted ones you want to keep.
  Offer the minimum to your exclusive-rights men.
  Everyone you pass on becomes an unrestricted free agent.

A TENDER IS NOT A SIGNING. This used to take a tendered player off the market
entirely, which is wrong: a tendered restricted free agent negotiates with
whoever he likes, and his own club holds a right to match. So a tendered man
goes into the free agent list alongside everybody else and can be bid on. The
difference between tendering and not is who gets the last word, not whether
the player is available.

Tagging is the exception, and that IS what keeps a man off the market. Every club sorts its expiring contracts into classes, decides whether to
spend its one tag, and tenders the restricted men it wants to keep.

WHAT IS MODELLED, AND WHAT IS NOT:

  ONE TAG PER CLUB, priced as the non-exclusive tag. The real rules offer an
  exclusive version too, and the only thing separating them is that a
  non-exclusive player may sign an offer sheet elsewhere - at a price of TWO
  FIRST-ROUND PICKS. That price is prohibitive by design and clubs do not pay
  it, so modelling both would be a choice with no consequence. The tag here
  simply removes him from the market.

  THE ESCALATOR IS IN, and it is the most important rule on the list. A club
  may tag the same man three times: the second costs 120% of the previous
  year and the third 144%. Without it a front office franchises its best
  player forever and free agency never sees anybody worth having.

  THE 120% FLOOR IS IN. The tag pays the greater of the positional figure or
  120% of his prior salary, which is why a club tags a rising player rather
  than one it has already paid.

  TENDERS ARE RIGHT OF FIRST REFUSAL ONLY, by decision. The real game has four
  levels carrying draft compensation, and they are deterrents rather than
  prices anyone expects to pay - the sources are blunt that the vast majority
  of offer sheets get matched, and that a player's only leverage is finding an
  offer his club will not match, which is hardest at exactly the tender levels
  meant to stop it. When a club genuinely wants another team's restricted man
  it trades for him instead; that is how Wes Welker moved in 2007. So the
  compensation tiers are gone, every tender is a right to match, and acquiring
  a restricted player is a trade.

  EXCLUSIVE RIGHTS PLAYERS, fewer than three accrued seasons, cannot negotiate
  at all if their club offers the minimum. They are not really free agents and
  are handled here so they do not leak into the market.

  THE JULY 15 DEADLINE is a window rather than an event: between the tag and
  the deadline a club may convert it into a long-term deal. After it, he plays
  the year on the tag.
"""
import numpy as np

import free_agency as FA
import min_salary as MS
from cap_engine import CAP, Contract

# A club may tag the same man three times and no more. The raise is on his own
# previous tag, which is what makes the third one unaffordable.
TAG_ESCALATOR = {1: 1.00, 2: 1.20, 3: 1.44}
MAX_TAGS = 3

# The tender that survives: a right to match, no compensation. Real 2026 value
# is $3.52M against a $301.2M cap, which is the share free_agency carries.
TENDER_KIND = 'right_of_first'


def classify(league):
    """
    Sort every man into UFA, RFA, ERFA or under contract. Accrued seasons
    decide it: four or more and he is free, three and he is restricted, fewer
    and his club holds exclusive rights.
    """
    out = {'UFA': [], 'RFA': [], 'ERFA': [], 'under_contract': []}
    for p in league.players.values():
        if p.retired:
            continue
        c = FA.fa_class(p.accrued, p.contract_years_left)
        p.fa_class = c
        out[c].append(p)
    return out


def value_over_replacement(league, team, player):
    """
    How much the club loses if he walks.

    NOT the gap to his own backup. A club carries exactly one kicker and one
    punter, so a team-only comparison made their replacement zero and handed
    them a value equal to their entire rating - six of the first eight
    franchise tags in the league went to specialists. The honest comparison is
    to what the club could go and sign at that spot, which is a league-median
    player, not an empty roster slot.
    """
    grp = team.by_pos(player.pos)
    if len(grp) > 1:
        return player.ovr - grp[1].ovr
    pool = [p.ovr for p in league.players.values()
            if not p.retired and p.pos == player.pos]
    if not pool:
        return 0.0
    return player.ovr - float(np.median(pool))


def tag_price(player, cap):
    """
    The greater of the positional figure and 120% of his prior salary, then
    escalated by how many times this club has already done it.
    """
    positional = FA.tag_value(player.pos, cap)
    prior = player.apy if player.contract else 0.0
    base = max(positional, 1.20 * prior)
    step = TAG_ESCALATOR.get(min(player.tag_count + 1, MAX_TAGS), 1.44)
    return round(base * step, 3)


def tender_price(player, cap):
    """A right to match, nothing more. Never below his own minimum."""
    return round(max(FA.tender_value(TENDER_KIND, cap),
                     MS.minimum_salary(p_accrued(player), cap)), 3)


def p_accrued(player):
    return int(player.accrued or 0)


def _one_year(value, year):
    """A tag or tender is a one-year deal with no proration."""
    return Contract(years=1, base=[value], signing_bonus=0.0, signed=year)


def power(league, team, cap):
    """Space minus what the club still owes the bodies it has not signed. A
    tag or a tender is a real commitment and has to clear the same bar as any
    other signing."""
    return team.spending_power(cap, MS.minimum_salary(2, cap))


def run(league, rng, verbose=False):
    """
    Tag, tender, and let everyone else reach the market. Called after cuts and
    restructures, because a club has to know its cap room before it commits a
    tag - and before free agency, because that is the whole point of a tag.
    """
    cap = CAP.get(league.year, 301.2)
    groups = classify(league)
    tagged, tendered, reserved, to_market = [], [], [], []
    league.tags_done_year = league.year

    for abbr, team in league.teams.items():
        team.sync_cap()
        roster = set(p.pid for p in team.active())

        # ---- the one tag ------------------------------------------------
        mine = [p for p in groups['UFA'] if p.pid in roster]
        best = None
        if abbr == getattr(league, 'user_team', None) and getattr(league, 'user_tag_choice', None) is not None:
            # the user decided from the Extensions page: a man, or 'none'
            mine = []          # the AI does not tag for a club whose GM has spoken
        if mine:
            # spend it on the man the club can least afford to lose: value
            # over the next man at his spot, not raw rating
            def worth(p):
                return value_over_replacement(league, team, p)
            cand = max(mine, key=worth)
            price = tag_price(cand, cap)
            if (cand.tag_count < MAX_TAGS and worth(cand) >= 5.0
                    and price <= power(league, team, cap)):
                cand.contract = _one_year(price, league.year)
                cand.tag_count += 1
                cand.tagged_year = league.year
                cand.fa_class = 'tagged'
                best = cand
                tagged.append((abbr, cand, price))
                league.log('franchise_tag', pid=cand.pid, team=abbr,
                           price=price, times=cand.tag_count)
                team.sync_cap()

        # ---- restricted men ---------------------------------------------
        for p in [x for x in groups['RFA'] if x.pid in roster]:
            price = tender_price(p, cap)
            if price > power(league, team, cap):
                to_market.append((abbr, p))     # cannot afford to keep him
                continue
            p.contract = _one_year(price, league.year)
            p.fa_class = 'tendered'
            p.tender_team = abbr
            tendered.append((abbr, p, price))
            league.log('tender', pid=p.pid, team=abbr, price=price)
            team.sync_cap()
            # He is tendered, not signed away. He appears in the free agent
            # list like anyone else and clubs may bid; his own team simply
            # gets the right to match whatever he agrees to.
            if p.pid not in league.free_agents:
                league.free_agents.append(p.pid)

        # ---- exclusive rights: not really free agents --------------------
        for p in [x for x in groups['ERFA'] if x.pid in roster]:
            price = MS.minimum_salary(p_accrued(p), cap)
            if price > team.cap_space:          # a minimum body needs no reserve
                to_market.append((abbr, p))
                continue
            p.contract = _one_year(price, league.year)
            p.fa_class = 'exclusive_rights'
            reserved.append((abbr, p, price))
            team.sync_cap()

        # ---- everyone else walks ----------------------------------------
        for p in mine:
            if p is best:
                continue
            to_market.append((abbr, p))

    # a man reaching the market leaves his club now; his cap hit is already
    # gone because his deal expired, so there is nothing to release
    for abbr, p in to_market:
        t = league.teams.get(abbr)
        if t and p in t.roster:
            t.roster.remove(p)
        p.last_team = p.team                    # loyalty reads it in the market
        p.team, p.contract = None, None
        p.fa_class = p.fa_class if p.fa_class in ('RFA', 'ERFA') else 'UFA'
        if p.pid not in league.free_agents:
            league.free_agents.append(p.pid)
    for t in league.teams.values():
        t.sync_cap()

    if verbose:
        print(f'  {len(tagged)} tagged, {len(tendered)} tendered (biddable), '
              f'{len(reserved)} on exclusive rights, '
              f'{len(to_market)} reached the market')
    return dict(tagged=tagged, tendered=tendered, reserved=reserved,
                market=to_market)


if __name__ == '__main__':
    import collections
    import league as LG, season as SN, retirement as RT
    import regression as RG, contracts as CT
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)
    CT.run(L, rng)

    g = classify(L)
    print('expiring classes: UFA %d, RFA %d, ERFA %d, under contract %d'
          % (len(g['UFA']), len(g['RFA']), len(g['ERFA']),
             len(g['under_contract'])))
    res = run(L, rng, verbose=True)

    print('\nfranchise tags:')
    for a, p, price in sorted(res['tagged'], key=lambda x: -x[2])[:10]:
        print('  %-4s %-22s %-5s age %2.0f ovr %.0f  $%.1fM  (tag #%d)'
              % (a, p.name, p.pos, p.age, p.ovr, price, p.tag_count))
    print('\ntop men reaching the market:')
    mk = sorted(res['market'], key=lambda x: -x[1].ovr)[:8]
    for a, p in mk:
        print('  %-4s %-22s %-5s age %2.0f ovr %.0f' % (a, p.name, p.pos, p.age, p.ovr))
    print('\ntenders: %d at $%.2fM' % (len(res['tendered']),
          FA.tender_value(TENDER_KIND, CAP.get(L.year, 301.2))))
    sp = np.array([t.cap_space for t in L.teams.values()])
    print('cap space after: min %.1f mean %.1f | over: %d'
          % (sp.min(), sp.mean(), (sp < 0).sum()))


def user_tag(league, pid):
    """The user places his one tag from the Extensions page, in the offseason before the tag step.
    Same price, same rules as the AI's; 'none' tells the AI not to tag for him."""
    from cap_engine import CAP
    user = getattr(league, 'user_team', None); team = league.teams[user]; cap = CAP.get(league.year, 301.2)
    if pid in (None, 'none'):
        league.user_tag_choice = 'none'; return dict(ok=True, line='No tag this year. The AI will not place one for you.')
    p = league.player(pid)
    if p is None or p.team != user: return dict(ok=False, why='not on your roster')
    import free_agency as FA
    if FA.fa_class(p.accrued, p.contract_years_left) != 'UFA': return dict(ok=False, why='only a man whose deal is up, with four accrued seasons, can be tagged')
    if p.tag_count >= MAX_TAGS: return dict(ok=False, why='he has been tagged the most a man can be')
    if getattr(league, 'user_tag_choice', None) not in (None, 'none'): return dict(ok=False, why='you have used your tag this year')
    price = tag_price(p, cap)
    room = power(league, team, cap)
    if price > room: return dict(ok=False, why=f"the tag costs ${price:.1f}m and after the minimums for the bodies you still owe you can commit ${max(0.0, room):.1f}m; clear room first")
    p.contract = _one_year(price, league.year); p.tag_count += 1; p.tagged_year = league.year; p.fa_class = 'tagged'
    league.user_tag_choice = p.pid; team.sync_cap()
    league.log('franchise_tag', pid=p.pid, team=user, price=price, times=p.tag_count, user=True)
    return dict(ok=True, line=f"{p.name} tagged at ${price:.1f}m for {league.year}.", price=round(price, 1))


def user_tag_window(league):
    """Whether the user can still tag: the offseason, before the Extensions and Tags step has run."""
    return league.phase != 'regular' and not getattr(league, 'tags_done_year', None) == league.year
