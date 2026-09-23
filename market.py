"""
FREE AGENCY.

Three phases, and what separates them is PRICE, not time. In phase one the
best men sign at or above market because several clubs want the same player.
Phase two is the bulk of the league. By phase three a good player who waited
is taking a one-year deal to rebuild his value. If the phases do not move the
price they are just three identical rounds, so the market level falls as the
pool thins.

HOW A BID WORKS. One bid per club per player, editable up or down until the
advance. Nothing resolves live: clubs commit, the phase advances, and every
free agent then decides at once. That is the whole reason a bid can be edited
- you are betting on what the market does, not reacting to it.

THE METER IS FIVE BARS and it does not always win. It shows how much this man
likes THIS offer relative to what else he has, so the top bar means he is
about to sign. But the number he compares is UTILITY, not money: a ring
chaser takes less from a contender, a man who wants the ball takes less for a
clear role, and an older player takes fewer dollars for more years. So the
fullest meter loses often enough to matter, which is the point.

THE INBOX. A player who wants your club but has a better offer writes and asks
you to match. You get one chance. Tendered restricted free agents land here
too, with FIVE days to match - the real window, from the league's own rules,
and longer than the three we discussed.

THE CONTENDER DISCOUNT IS SMALL AND OCCASIONAL, by decision. It is a thumb on
the scale, not a cheat code: most players still take the money.

THE POOL STAYS OPEN. It closes after the last phase and reopens at training
camp, which is where clubs patch the injuries camp produces.
"""
import numpy as np

import free_agency as FA
import negotiation_engine as NE
import valuation as VAL
from cap_engine import CAP, Contract

PHASES = 3

# What the market pays, by phase. The first wave is a bidding war and the last
# is a bargain bin; a player who waits is worth less than he was, which is why
# waiting is a real risk rather than a free option.
PHASE_LEVEL = {1: 1.00, 2: 0.88, 3: 0.72}

# Five bars. The thresholds are on utility relative to his best alternative.
METER_BARS = 5

# Small, and it has to stay small. A contender is worth about this much of a
# discount to the average man - and to a ring chaser far more, which the
# archetype weights already handle without help from here.
CONTENDER_DISCOUNT = 0.06

# A player who likes you but has more money elsewhere writes instead of
# signing. Too often and the inbox is noise; too rarely and it never fires.
# A club chases a handful of men, not the whole market. Without a limit every
# team bid on every free agent and 641 of 941 signed in the first wave, which
# is not a market, it is a queue.
MAX_TARGETS = {1: 8, 2: 7, 3: 8}

# How much of next year's obligation a club actually holds back. Not all of
# it: some of those men will be let go, and some will be cheaper than their
# current deal. Half is the working figure.
FORWARD_WEIGHT = 0.5

MATCH_REQUEST_CHANCE = 0.30
MATCH_GAP_MAX = 0.18          # he only asks if the gap is closeable

RFA_MATCH_DAYS = 5            # the real window


class Offer:
    __slots__ = ('team', 'pid', 'apy', 'years', 'promises', 'phase')

    def __init__(self, team, pid, apy, years=3, promises=(), phase=1):
        self.team, self.pid = team, pid
        self.apy, self.years = float(apy), int(years)
        self.promises = list(promises)
        self.phase = phase

    def as_dict(self):
        return dict(apy=self.apy, years=self.years, promises=self.promises)

    def total(self):
        return self.apy * self.years

    def __repr__(self):
        return f'<{self.team} ${self.apy:.1f}M x{self.years}>'


def team_context(league, team, player):
    """What this club looks like to this player."""
    grp = team.by_pos(player.pos)
    best = grp[0].ovr if grp else 0.0
    return dict(
        team=team.abbr,
        contender=team.contender,
        # a clear role means nobody in front of him
        role_clarity=float(np.clip(1.0 - max(0.0, best - player.ovr) / 12.0, 0, 1)),
        home_fit=0.0,
        contested_at_position=team.contested_at_position(player.pos) > 0.5,
        captain_slots_left=2,
        leverage=0.5, want=0.5)


def profile_for(league, player, rng):
    """His hidden weights. Drawn once and kept, so he is the same man in
    phase three as he was in phase one."""
    if player.morale is None:
        pass
    key = getattr(player, '_fa_profile', None)
    if key is not None:
        return key
    row = dict(age=player.age, ovr=player.ovr, madden_position=player.pos)
    prof = NE.make_profile(row, rng)
    try:
        player._fa_profile = prof
    except AttributeError:
        pass
    return prof


def utility_of(league, player, offer, prof, market_apy):
    team = league.teams[offer.team]
    ctx = team_context(league, team, player)
    row = dict(age=player.age, ovr=player.ovr, madden_position=player.pos)
    u = NE.utility(offer.as_dict(), row, prof, ctx, market_apy)
    # the contender thumb: small, and only sometimes
    u += CONTENDER_DISCOUNT * ctx['contender'] * prof['w'].get('winning', 0.1) * 3.0
    # loyalty: his own club's offer gets a thumb on the scale; a mercenary's does not
    import personality as PT
    if getattr(player, 'last_team', None) == offer.team:
        u *= 1.0 + PT.own_club_bonus(player)
    return u


def meter(u, best_u):
    """Five bars: how close this offer is to the best he has."""
    if best_u <= 0:
        return 1
    r = u / best_u
    for i, cut in enumerate((0.80, 0.90, 0.96, 0.995)):
        if r < cut:
            return i + 1
    return METER_BARS


# ============================================================ THE AI's BIDS
def power(league, team, cap, years=1):
    """
    Effective spending power: space minus the floor cost of the bodies the
    club still owes, and now minus what it has already promised NEXT year.

    A club with four expiring starters has spent most of next year's room in
    its head before free agency opens. Raw cap space cannot see that, so a
    rebuilding team and a team about to lose its own core looked identical.

    The forward charge scales with CONTRACT LENGTH, because that is what
    actually conflicts: a one-year deal blocks nothing and a five-year deal
    blocks everything. A one-year signing therefore stays cheap for exactly
    the club that cannot commit, which is also what happens in reality.
    """
    import min_salary as MS
    base = team.spending_power(cap, MS.minimum_salary(2, cap), ROSTER_TARGET)
    if years <= 1:
        return base
    owed = team.future_obligation()
    return base - owed * min(1.0, (years - 1) / 3.0) * FORWARD_WEIGHT


def ai_bids(league, pool, phase, rng, skip_teams=()):
    """
    Every club looks at the market and commits one bid per player it wants.
    The number comes from its own valuation of him, not from a league price -
    which is what makes two clubs value the same man differently.
    """
    cap = CAP.get(league.year, 301.2)
    comps = VAL.pool_from_league(league)
    out = {}
    for abbr, team in league.teams.items():
        if abbr in skip_teams:
            continue
        # NOT cap_space. A club with twenty holes cannot spend its whole
        # room on one man - it still owes nineteen minimum salaries.
        room = power(league, team, cap)
        if room <= 2.0:
            continue
        cand = []
        from gm_engine import scheme_fit
        for p in pool:
            grp = team.by_pos(p.pos)
            best = grp[0].ovr if grp else 0.0
            depth = len(grp)
            # HIM IN OUR SCHEME. A club shops for the men who fit what it
            # runs, and pays them as it sees them.
            fit = scheme_fit(p.ratings, p.pos, team)
            # need: thin at the spot, or he is an upgrade on what is there
            upgrade = (p.ovr + fit - best) / 12.0
            need = (1.0 if depth == 0 else np.clip(0.9 - 0.25 * depth, 0, 1))
            want = 0.55 * need + 0.45 * np.clip(upgrade, -1, 1)
            if want <= 0.12:
                continue
            v = VAL.value_player(league, p, side='team', pool=comps, rng=rng)
            if not v:
                continue
            years_want = int(np.clip(v['years'], 1, 5))
            # COMMITTING LONG TO HIM MEANS LOSING ONE OF YOUR OWN. A multi-year
            # deal is paid for out of the same room that would have re-signed a
            # pending free agent, so he has to be better than the man who walks
            # - not merely better than the backup currently behind him.
            if years_want > 2:
                keeper = team.worst_keeper()
                if keeper is not None and p.ovr <= keeper.ovr + 1.0:
                    years_want = 1        # worth having now, not worth a future
            bid = v['apy'] * PHASE_LEVEL[phase] * (1.0 + 0.045 * fit)
            # a club that wants him badly pays over its own number
            bid *= 1.0 + 0.22 * max(0.0, want - 0.5)
            bid = min(bid, power(league, team, cap, years_want) * 0.65)
            floor = 0.9
            if bid < floor:
                continue
            years = years_want
            if phase == 3:
                years = min(years, 2)     # late money is short money
            cand.append((want, p, round(bid, 2), years))
        # he pursues the men he wants most, and only as many as he can carry
        cand.sort(key=lambda x: -x[0])
        spend = 0.0
        for want, p, bid, years in cand[:MAX_TARGETS[phase] * 2]:
            if spend + bid > room * 0.80:
                continue
            spend += bid
            out.setdefault(p.pid, []).append(
                Offer(abbr, p.pid, bid, years, phase=phase))
            if spend >= room * 0.80:
                break
    return out


# ============================================================ RESOLUTION
def resolve_phase(league, pool, offers, phase, rng, user_team=None):
    """
    Every free agent decides at once. He signs, he waits, or he writes to the
    club he wants and asks them to match.
    """
    cap = CAP.get(league.year, 301.2)
    comps = VAL.pool_from_league(league)
    signed, waiting, messages = [], [], []

    for p in list(pool):
        mine = offers.get(p.pid) or []
        if not mine:
            waiting.append(p)
            continue
        prof = profile_for(league, p, rng)
        v = VAL.value_player(league, p, pool=comps, rng=rng)
        market = v['apy'] if v else 3.0
        scored = sorted(((utility_of(league, p, o, prof, market), o)
                         for o in mine), key=lambda x: -x[0])
        best_u, best = scored[0]

        # THE METER DOES NOT ALWAYS WIN. He is choosing on utility, and two
        # offers close in utility are a coin weighted by how close they are -
        # so the fullest bar loses often enough to matter.
        if len(scored) > 1:
            us = np.array([s for s, _o in scored[:5]])
            w = np.exp((us - us.max()) / max(0.06, 0.10 * abs(us.max())))
            pick = int(rng.choice(len(us), p=w / w.sum()))
            best_u, best = scored[pick]

        # would he rather wait? early on, a thin market is worth sitting out
        # What he will not sign below. High early, because a good man in
        # March believes somebody will pay him; low late, because by then
        # nobody will.
        reserve = market * (0.96 if phase == 1 else (0.82 if phase == 2 else 0.55))
        if best.apy < reserve and phase < PHASES:
            waiting.append(p)
            continue

        # he wants somebody else's club but the money is here
        if user_team is not None and rng.random() < MATCH_REQUEST_CHANCE:
            theirs = [(u, o) for u, o in scored if o.team == user_team]
            if theirs and theirs[0][1] is not best:
                gap = (best.apy - theirs[0][1].apy) / max(best.apy, 0.1)
                if 0 < gap <= MATCH_GAP_MAX:
                    messages.append(dict(
                        kind='match_request', pid=p.pid, name=p.name,
                        team=user_team, rival=best.team,
                        their_offer=theirs[0][1].apy, rival_offer=best.apy,
                        expires_phase=phase))
                    waiting.append(p)
                    continue

        # A TENDERED MAN CANNOT JUST BE SIGNED. His own club holds a right to
        # match, so agreeing terms elsewhere produces an OFFER SHEET and the
        # incumbent gets five days. That is the entire difference between
        # tendering a restricted player and letting him walk: not whether he
        # is available, but who gets the last word.
        holder = getattr(p, 'tender_team', None)
        if holder and holder != best.team:
            messages.append(dict(
                kind='offer_sheet', pid=p.pid, name=p.name, team=holder,
                suitor=best.team, offer=round(best.apy, 2),
                years=best.years, days=RFA_MATCH_DAYS, phase=phase))
            waiting.append(p)
            continue

        # Cap room is checked AGAIN here. A club bids on several men at once
        # and cannot sign them all; without this, teams finished 48m over.
        if power(league, league.teams[best.team], cap) < best.apy * 1.05:
            alt = next((o for _u, o in scored
                        if power(league, league.teams[o.team], cap)
                        >= o.apy * 1.05), None)
            if alt is None:
                waiting.append(p)
                continue
            best = alt
        sign(league, p, best, cap)
        league.teams[best.team].sync_cap()
        signed.append((best.team, p, best))

    return signed, waiting, messages


def sign(league, player, offer, cap):
    """Put him under contract. Structure comes from the same builder the rest
    of the game uses, so a free agent deal looks like any other."""
    import contract_structure as CS
    team = league.teams[offer.team]
    st = CS.structure(offer.apy, offer.years, player.pos, cap, team.gm)
    c = Contract(years=offer.years, base=st['base'],
                 signing_bonus=st['signing_bonus'], signed=league.year)
    # the incumbent at his spot who is now behind a man the club just paid
    try:
        import morale as MO
        team = league.teams[offer.team]
        for q in team.depth.get(player.pos, [])[:2]:
            if q is not player and q.ovr <= player.ovr + 1.0:
                MO.shock(league, q.pid, 'team_signed_over_him')
    except Exception:
        pass
    league.sign(player.pid, offer.team, c)
    player.fa_class = 'signed'
    for k in offer.promises:
        league.log('promise', pid=player.pid, team=offer.team, kind=k)


# ============================================================ THE INBOX
def inbox_add(league, msg):
    """Free-agency messages go through the same inbox as everything else,
    keeping their own fields on the top level for resolve_offer_sheets."""
    import inbox as IB
    league.__dict__.setdefault('inbox', [])
    m = IB.post(league, msg.get('kind', 'note'), msg.get('subject') or msg.get('kind', 'note'),
                msg.get('body', ''), sender=msg.get('team'), payload=msg)
    m.update({k: v for k, v in msg.items() if k not in ('id', 'status')})
    return m


def resolve_offer_sheets(league, rng, verbose=False):
    """
    The incumbent matches or lets him go. No draft compensation either way, by
    decision - the tender buys the right to match and nothing else.
    """
    kept, lost = [], []
    for msg in [m for m in league.inbox if m.get('kind') == 'offer_sheet'
                and not m.get('resolved')]:
        p = league.player(msg['pid'])
        if p is None or p.retired:
            msg['resolved'] = True
            continue
        holder = league.teams.get(msg['team'])
        suitor = league.teams.get(msg['suitor'])
        cap = CAP.get(league.year, 301.2)
        price, years = msg['offer'], msg.get('years', 2)
        # he matches if the man is worth the new number to him and he can
        # carry it
        v = VAL.value_player(league, p, side='team', rng=rng)
        worth = v['apy'] if v else price
        # HE MATCHES UNLESS THE PRICE IS GENUINELY BAD. A tendered man is one
        # the club already decided it wanted and already has on its cap at the
        # tender, so the real question is only the difference. At a 0.92 bar
        # incumbents lost 33 of 45, where the sources are blunt that the vast
        # majority of offer sheets are matched.
        gap = max(0.0, price - (p.apy if p.contract else 0.0))
        can = (holder is not None
               and power(league, holder, cap) + (p.apy if p.contract else 0.0)
               >= price * 1.02)
        if can and worth >= price * 0.72:
            o = Offer(msg['team'], p.pid, price, years, phase=3)
            _unlist(league, p)
            sign(league, p, o, cap)
            holder.sync_cap()
            kept.append((msg['team'], p, price))
        elif suitor and power(league, suitor, cap) >= price * 1.05:
            o = Offer(msg['suitor'], p.pid, price, years, phase=3)
            _unlist(league, p)
            sign(league, p, o, cap)
            suitor.sync_cap()
            lost.append((msg['suitor'], p, price))
        msg['resolved'] = True
        p.tender_team = None
    if verbose:
        print(f'  offer sheets: {len(kept)} matched, {len(lost)} lost')
    return kept, lost


def _unlist(league, player):
    """Clear a tendered man's placeholder deal before he signs a real one."""
    t = league.teams.get(player.team)
    if t and player in t.roster:
        t.roster.remove(player)
    player.team, player.contract = None, None
    if player.pid not in league.free_agents:
        league.free_agents.append(player.pid)


def rfa_offer_sheets(league, rng):
    """
    A club that wants another team's restricted man signs him to an offer
    sheet; the incumbent has FIVE DAYS to match. Tenders carry no draft
    compensation by decision, so the only question is whether you match.
    """
    out = []
    for p in league.players.values():
        if p.fa_class != 'tendered' or p.retired:
            continue
        # somebody has to want him more than his own club is paying
        v = VAL.value_player(league, p, side='team', rng=rng)
        if not v or not p.contract:
            continue
        if v['apy'] <= p.apy * 1.25:
            continue
        suitors = [a for a, t in league.teams.items()
                   if a != p.team and t.cap_space > v['apy'] * 1.3]
        if not suitors:
            continue
        buyer = suitors[int(rng.integers(0, len(suitors)))]
        out.append(dict(kind='offer_sheet', pid=p.pid, name=p.name,
                        team=p.team, suitor=buyer,
                        offer=round(v['apy'], 2), days=RFA_MATCH_DAYS))
    return out


def fill_out_rosters(league, pool, rng, verbose=False):
    """
    Clubs still short of a roster sign cheap depth.

    This is most of free agency by headcount and none of it by money. After
    expiries a team can be down to twenty men under contract, and it has to
    field eleven on each side - so it signs minimum-salary bodies until it is
    whole. Without this the AI chased eight stars apiece and left the league
    with clubs carrying thirty players.
    """
    import min_salary as MS
    cap = CAP.get(league.year, 301.2)
    signed = 0
    for abbr, team in league.teams.items():
        need = ROSTER_TARGET - len(team.active())
        if need <= 0:
            continue
        # best available who will play for the minimum, his own position
        # scarcity first
        avail = sorted(pool, key=lambda p: -p.ovr)
        for p in list(avail):
            if need <= 0:
                break
            floor = MS.minimum_salary(p.accrued, cap)
            # filling a slot RELEASES reserve, so the test is plain space
            if team.cap_space < floor * 1.05:
                break
            grp = team.by_pos(p.pos)
            if len(grp) >= 4:
                continue                  # already deep here
            o = Offer(abbr, p.pid, round(floor, 3), 1, phase=3)
            sign(league, p, o, cap)
            team.sync_cap()
            pool.remove(p)
            need -= 1
            signed += 1
    if verbose:
        print(f'  depth signings: {signed}')
    return signed


# What a club fills to before camp. Real rosters are 90 in the spring and cut
# to 53; this is the working number until cut-down exists.
ROSTER_TARGET = 53


# ============================================================ THE MARKET
def run(league, rng, user_team=None, verbose=False):
    """
    Three phases. Between each one the price level falls and the pool thins.
    Anyone left when it closes stays available until training camp.
    """
    league.set_phase('free_agency')
    league.__dict__.setdefault('inbox', [])
    pool = [league.player(pid) for pid in list(league.free_agents)]
    pool = [p for p in pool if p and not p.retired]

    all_signed = []
    for phase in range(1, PHASES + 1):
        bids = ai_bids(league, pool, phase, rng, skip_teams=(user_team,) if user_team else ())
        signed, waiting, msgs = resolve_phase(league, pool, bids, phase, rng,
                                              user_team)
        for m in msgs:
            inbox_add(league, m)
        all_signed += signed
        pool = waiting
        if verbose:
            print(f'  phase {phase}: {len(signed)} signed, {len(pool)} left, '
                  f'{len(msgs)} messages')

    fill_out_rosters(league, pool, rng, verbose)

    resolve_offer_sheets(league, rng, verbose)

    # Nobody leaves the market over the cap. Decisions compound even when each
    # one was affordable on its own.
    import contracts as CT
    CT.enforce(league, rng, verbose)

    # the pool does not empty - it stays open and reopens at camp
    league.free_agents = [p.pid for p in pool]
    if verbose:
        sp = np.array([t.cap_space for t in league.teams.values()])
        print(f'  {len(all_signed)} signed in all, {len(pool)} unsigned, '
              f'cap min {sp.min():.1f} / mean {sp.mean():.1f}')
    return all_signed, pool


if __name__ == '__main__':
    import league as LG, season as SN, retirement as RT
    import regression as RG, contracts as CT, tags as TG
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    SN.run_season(L, rng)
    RT.run(L, rng)
    RG.run(L, rng)
    L.roll_year(rng)
    L.advance_contracts()
    CT.run(L, rng)
    TG.run(L, rng)
    print(f'market opens with {len(L.free_agents)} free agents\n')
    signed, left = run(L, rng, user_team='KC', verbose=True)

    print('\nbiggest signings:')
    for t, p, o in sorted(signed, key=lambda x: -x[2].apy)[:10]:
        print('  %-4s %-22s %-5s ovr %.0f age %2.0f  $%.1fM x%d (phase %d)'
              % (t, p.name, p.pos, p.ovr, p.age, o.apy, o.years, o.phase))
    print('\nbest men still unsigned:')
    for p in sorted(left, key=lambda x: -x.ovr)[:6]:
        print('  %-22s %-5s ovr %.0f age %2.0f' % (p.name, p.pos, p.ovr, p.age))
    print(f'\ninbox: {len(L.inbox)} messages')
    for m in L.inbox[:5]:
        if m['kind'] == 'match_request':
            print('  %s wants %s but %s offered $%.1fM against your $%.1fM'
                  % (m['name'], m['team'], m['rival'], m['rival_offer'],
                     m['their_offer']))
        else:
            print('  OFFER SHEET: %s signed with %s at $%.1fM - %s has %d days'
                  % (m['name'], m['suitor'], m['offer'], m['team'], m['days']))
