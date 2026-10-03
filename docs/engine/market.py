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
import player_age as PA

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

MATCH_REQUEST_CHANCE = 0.30
MATCH_GAP_MAX = 0.18          # he only asks if the gap is closeable

RFA_MATCH_DAYS = 5
OFFER_SHEETS_A_YEAR = 3            # the real league sees a few; every tendered player with a bid had been drawing one            # the real window


class Offer:
    __slots__ = ('team', 'pid', 'apy', 'years', 'promises', 'phase', 'front_load', 'planning_gain', 'bonus')

    def __init__(self, team, pid, apy, years=3, promises=(), phase=1, front_load=None, planning_gain=None, bonus=None):
        self.team, self.pid = team, pid
        self.apy, self.years = float(apy), int(years)
        self.promises = list(promises)
        self.phase = phase
        self.front_load = front_load          # 0 back-loaded .. 1 front-loaded; None = the club's habit
        self.planning_gain = planning_gain    # roster value when this CPU bid was priced
        self.bonus = bonus

    def as_dict(self):
        return dict(apy=self.apy, years=self.years, promises=list(self.promises), front_load=self.front_load, bonus=self.bonus)

    def to_save(self):
        return dict(team=self.team, pid=self.pid, apy=self.apy, years=self.years, promises=list(self.promises), phase=self.phase, front_load=self.front_load, planning_gain=self.planning_gain, bonus=self.bonus)

    @classmethod
    def from_save(cls, d):
        return cls(d['team'], d['pid'], d['apy'], d.get('years', 3), d.get('promises', ()), d.get('phase', 1), d.get('front_load'), d.get('planning_gain'), d.get('bonus'))

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
    import contract_offer as CO
    return CO.profile_for(player)


def utility_of(league, player, offer, prof, market_apy, preferred_term=None):
    from contract_terms import preferred_years
    team = league.teams[offer.team]
    ctx = team_context(league, team, player)
    row = dict(age=player.age, ovr=player.ovr, madden_position=player.pos,
               financial_priority=(getattr(player, 'traits', None) or {}).get('financial_priority', 50))
    row['preferred_years'] = preferred_term or preferred_years(player, league.year, market_apy, CAP.get(league.year, 301.2))
    import contract_offer as CO
    freeze_offer(league, player, offer)
    evaluation = CO.assess(league, player, team, offer.as_dict(), market_apy, row['preferred_years'], profile=prof)
    # Preserve winning/role/home/tax/promises; replace BOTH old money and term
    # components with the same package valuation used by negotiations.
    neutral = dict(apy=market_apy, years=row['preferred_years'], promises=list(offer.promises))
    u = NE.utility(neutral, row, prof, ctx, market_apy) - prof['w']['total'] - prof['w']['years']
    u += prof['w']['total'] * evaluation['ratio'] + prof['w']['years']
    # the contender thumb: small, and only sometimes
    u += CONTENDER_DISCOUNT * ctx['contender'] * prof['w'].get('winning', 0.1) * 3.0
    # loyalty: his own club's offer gets a thumb on the scale; a mercenary's does not
    import personality as PT
    if getattr(player, 'last_team', None) == offer.team:
        u *= 1.0 + PT.own_club_bonus(player)
    return u


def freeze_offer(league, player, offer):
    import contract_offer as CO
    package = CO.canonical(league, player, league.teams[offer.team], offer.as_dict())
    offer.bonus, offer.front_load = package['bonus'], package['front_load']
    return offer


def best_offer(league, player, offers, market_apy=None):
    if not offers: return None
    value = VAL.value_player(league, player, rng=None) if market_apy is None else None
    market_apy = market_apy or (value or {}).get('apy', offers[0].apy)
    profile = profile_for(league, player, None)
    return max(offers, key=lambda o: utility_of(league, player, o, profile, market_apy))


def hold_user_offer(league, player, thread, offer, best):
    """Full packages, including bonus, decide whether talks stay in contention."""
    profile = profile_for(league, player, None)
    mine = Offer(thread['team'], player.pid, offer['apy'], offer['years'],
                 offer.get('promises', ()), front_load=offer.get('front_load'), bonus=offer.get('bonus'))
    a = utility_of(league, player, mine, profile, thread['ask'], thread.get('years'))
    b = utility_of(league, player, best, profile, thread['ask'], thread.get('years'))
    return a >= b - .18 * max(.1, abs(b))


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
    """Upper bound for one candidate after funding remaining roster/draft costs.

    Full proposed contracts subsequently pass through the shared financial
    plan. No second APY-based retention deduction is applied here.
    """
    import financial_plan as FP
    budget = FP.snapshot(league, team)
    row = budget['years'][0]
    # Candidate fills one projected vacancy. Soft preferences and future
    # commitments are checked against its actual shaped contract below.
    slot = row['vacancy_reserve'] / row['vacant_slots'] if row['vacant_slots'] else 0.
    return budget['funded_room'] + slot


def available_for_signing(player):
    """Ordinary FAs and live tenders only; stale offers cannot move contracts."""
    return (not getattr(player, 'retired', False)
            and (not player.team or
                 (getattr(player, 'fa_class', None) == 'tendered'
                  and getattr(player, 'tender_team', None) in (None, player.team))))


def recruit_priority(gain):
    """How much this signing helps the packages we actually put on the field."""
    return float(np.clip(float(gain) / 12.0, 0.0, 1.5))


def acquisition_read(league, team, player, offer, gain, reference_apy=None, baseline=None):
    """Compare a marginal job upgrade with its complete cash commitment.

    A discounted veteran can be useful behind a star. Premium reserve spending
    must justify the salary and the guaranteed money displaced in existing jobs.
    This is a preference only; financial_plan and legal accounting still bind.
    """
    import roster_needs as RN
    import min_salary as MS
    preview=offer_contract(league,player,offer)
    cash=sum(preview.base)+sum(preview.rb)+preview.sb
    before=RN.assess(team) if baseline is None else baseline
    after=RN.assess(team,[p for p in before['players'] if p.pid!=player.pid]+[player])
    def shares(report):
        result={}
        for r in report['package_assignments']:
            if r['player'] is not None:
                pid=r['player'].pid;result[pid]=result.get(pid,0.)+r['weight']
        for pos in ('K','P','LS'):
            men=[p for p in report['players'] if p.pos==pos and not p.retired]
            if men: result[max(men,key=lambda p:p.ovr).pid]=1.
        return result
    old,new=shares(before),shares(after)
    displaced=sum(p.contract.remaining_proration(0) for p in before['players']
        if p.contract and old.get(p.pid,0.)>=.15 and new.get(p.pid,0.)<old[p.pid]*.5)
    annual=(cash+displaced)/max(1,preview.years)
    cap=CAP.get(league.year,301.2)
    cheap=annual<=1.25*MS.minimum_salary(player.accrued or 0,cap)
    if reference_apy is None:
        quote=VAL.value_player(league,player,side='team',rng=None)
        reference_apy=quote['apy'] if quote else offer.apy
    ceiling=reference_apy*(.45+.55*min(1.,max(0.,gain)/8.))
    approved=gain>1. and (cheap or gain>=8. or annual<=ceiling*1.1)
    return dict(approved=approved,reason='useful_upgrade' if approved else 'cost_exceeds_marginal_role',
        gain=round(gain,4),cash_commitment=round(cash,3),displaced_guarantees=round(displaced,3),
        annual_economic_cost=round(annual,3),role_price_ceiling=round(ceiling,3))


def _prefer_affordable_alternatives(candidates, gains):
    """Try a nearly equivalent, materially cheaper same-position option first.

    A preference, not a veto: if its actual contract cannot fit, the original
    target still gets a turn. Current players and pending bids are assessed
    again at that point so two bids cannot both claim the same vacant job.
    """
    ordered=[]
    remaining=list(candidates)
    while remaining:
        target=remaining[0]
        alternatives=[c for c in remaining if c[1].pos==target[1].pos
            and gains[c[1].pid]>=.9*gains[target[1].pid]
            and c[2]<=.8*target[2] and c[2]*c[3]<=.7*target[2]*target[3]]
        choice=min(alternatives,key=lambda c:(c[2]*c[3],-gains[c[1].pid])) if alternatives else target
        ordered.append(choice);remaining.remove(choice)
    return ordered


def ai_bids(league, pool, phase, rng, skip_teams=()):
    import contract_structure as CS
    import roster_needs as RN
    """
    Every club looks at the market and commits one bid per player it wants.
    The number comes from its own valuation of him, not from a league price -
    which is what makes two clubs value the same man differently.
    """
    cap = CAP.get(league.year, 301.2)
    comps = VAL.pool_from_league(league)
    # Team-side valuation is fixed to the five-year comparison window. No
    # contracts change while bids are assembled, so every club sees the same
    # market quote for a player; scheme and roster need still shape each bid.
    quotes = {}
    out = {}
    for abbr, team in league.teams.items():
        if abbr in skip_teams:
            continue
        report = RN.assess(team)
        gains = RN.candidate_gains(team, pool, baseline=report)
        cand = []
        from gm_engine import scheme_fit
        for p in pool:
            # HIM IN OUR SCHEME. A club shops for the men who fit what it
            # runs, and pays them as it sees them.
            fit = scheme_fit(p.ratings, p.pos, team)
            # Marginal package gain includes WR3/TE2 and defensive role fit.
            # A rare package cannot claim the value of a full-time vacancy.
            want = recruit_priority(gains.get(p.pid, 0.0))
            if want <= 0.12:
                continue
            if p.pid not in quotes:
                quotes[p.pid] = VAL.value_player(league, p, side='team', pool=comps, rng=rng)
            v = quotes[p.pid]
            if not v:
                continue
            from contract_terms import MAX_OFFER_YEARS
            years_want = int(np.clip(v['years'], 1, MAX_OFFER_YEARS))
            bid = v['apy'] * PHASE_LEVEL[phase] * (1.0 + 0.045 * fit)
            # Limited rotation/depth help gets a bounded discount; full-time
            # improvement earns the normal quote, before the urgency premium.
            bid *= .45+.55*min(1.,gains.get(p.pid,0.)/8.)
            # a club that wants him badly pays over its own number
            bid *= 1.0 + 0.22 * max(0.0, want - 0.5)
            floor = 0.9
            if bid < floor:
                continue
            years = years_want
            if phase == 3:
                years = min(years, 2)     # late money is short money
            cand.append((want, p, round(bid, 2), years))
        # he pursues the men he wants most, and only as many as he can carry
        cand.sort(key=lambda x: -x[0])
        cand=_prefer_affordable_alternatives(cand,gains)
        pending = []
        targets = 0
        for want, p, bid, years in cand[:MAX_TARGETS[phase] * 2]:
            if targets >= MAX_TARGETS[phase]:
                break
            # the club shapes the deal to its own books: tight now and open
            # later means back-load it, and the reverse means pay it now
            planned=RN.assess(team,list(report['players'])+[q for q,_ in pending]) if pending else report
            gain=RN.move_gain(team,p,baseline=planned) if pending else gains[p.pid]
            if gain<=1.: continue
            bid=round(bid*min(1.,(.45+.55*min(1.,gain/8.))/
                             (.45+.55*min(1.,gains[p.pid]/8.))),2)
            offer = Offer(abbr, p.pid, bid, years, phase=phase,
                          front_load=CS.choose_shape(team, years), planning_gain=gain)
            if not acquisition_read(league,team,p,offer,gain,quotes[p.pid]['apy'],planned)['approved']:
                continue
            preview = offer_contract(league, p, offer)
            import financial_plan as FP
            decision = FP.evaluate(league, team, additions=[(p, preview)],
                                   pending=pending, gain=gain, action='fa_bid')
            if not decision['approved']:
                continue
            pending.append((p, preview))
            targets += 1
            out.setdefault(p.pid, []).append(offer)
    return out


# ============================================================ RESOLUTION
def reconsider_bid(league, player, offer, user_team=None):
    """Reprice an unsigned CPU offer after another acquisition changes its job.

    The snapshot travels with the offer through save/load. No new valuation
    noise is drawn, no signed contract is altered, and complementary starters
    at one position retain the value of their distinct package assignments.
    """
    if offer.team == user_team:
        return offer
    import roster_needs as RN
    team = league.teams[offer.team]
    gain = RN.move_gain(team, player)
    if gain <= 1.0:
        return None
    original = offer.planning_gain
    scale = min(1.0, gain / original) if original is not None and original > 0 else 1.0
    price = round(offer.apy * scale, 2)
    if price < .9:
        return None
    revised = Offer(offer.team, offer.pid, price, offer.years, offer.promises,
                    offer.phase, offer.front_load, gain,
                    None if offer.bonus is None else offer.bonus * price / offer.apy)
    if not acquisition_read(league,team,player,revised,gain)['approved']:
        return None
    import financial_plan as FP
    if not FP.evaluate(league, team, additions=[(player, offer_contract(league, player, revised))],
                       gain=gain, action='fa_reconsider')['approved']:
        return None
    return revised


def refresh_bids(league, player, offers, user_team=None):
    rows = [reconsider_bid(league, player, o, user_team) for o in offers.get(player.pid, ())]
    offers[player.pid] = [o for o in rows if o is not None]
    return offers[player.pid]


def refresh_negotiation_rivals(league, bids, user_team):
    """Held user talks must not quote a CPU bid invalidated by this round."""
    import negotiations as NG
    for thread in NG._threads(league):
        # A delivered counter/match request is already a distinct negotiation
        # stage. Only refresh offers whose answer is about to be generated.
        if thread.get('kind') != 'fa_offseason' or thread.get('state') != 'waiting':
            continue
        player = league.player(thread['pid'])
        if player is None or not available_for_signing(player):
            continue
        others = [o for o in refresh_bids(league, player, bids, user_team)
                  if o.team != thread['team']]
        if others:
            best = best_offer(league, player, others)
            NG.set_rival(league, player.pid, best.team, best.apy, best.years, best.bonus, best.front_load, best.promises)
        else:
            thread['rival'] = None


def resolve_phase(league, pool, offers, phase, rng, user_team=None):
    """
    Every free agent decides at once. He signs, he waits, or he writes to the
    club he wants and asks them to match.
    """
    cap = CAP.get(league.year, 301.2)
    import roster_needs as RN
    comps = VAL.pool_from_league(league)
    signed, waiting, messages = [], [], []

    for p in list(pool):
        if not available_for_signing(p):
            continue
        if pending_offer_sheet(league, p.pid):
            waiting.append(p); continue
        # Bids were placed together at the start of the round. A club may
        # already have signed an alternative at this spot by the time this
        # player decides, so reconsider the actual roster before accepting.
        mine = refresh_bids(league, p, offers, user_team)
        if not mine:
            waiting.append(p)
            continue
        prof = profile_for(league, p, rng)
        v = VAL.value_player(league, p, pool=comps, rng=rng)
        market = v['apy'] if v else 3.0
        scored = sorted(((utility_of(league, p, o, prof, market, v['years'] if v else None), o)
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
        import contract_offer as CO
        reserve_ok = CO.assess(league, p, league.teams[best.team], best.as_dict(), reserve,
                               v['years'] if v else best.years, profile=prof)['acceptable']
        if not reserve_ok and phase < PHASES:
            waiting.append(p)
            continue

        # he wants somebody else's club but the money is here
        if user_team is not None and rng.random() < MATCH_REQUEST_CHANCE:
            theirs = [(u, o) for u, o in scored if o.team == user_team]
            if theirs and theirs[0][1] is not best:
                gap = (best_u - theirs[0][0]) / max(abs(best_u), 0.1)
                if 0 < gap <= MATCH_GAP_MAX:
                    messages.append(dict(
                        kind='match_request', pid=p.pid, name=p.name,
                        team=user_team, rival=best.team,
                        their_offer=theirs[0][1].apy, rival_offer=best.apy,
                        expires_phase=phase, rival_package=best.to_save(),
                        subject=f"{p.name} asks you to match", body=f"{best.team} have offered {p.name} ${best.apy:.1f}m a year against your ${theirs[0][1].apy:.1f}m. He would rather be with you; match it before the round closes and he signs.", link=f'player:{p.pid}'))
                    waiting.append(p)
                    continue

        # A TENDERED MAN CANNOT JUST BE SIGNED. His own club holds a right to
        # match, so agreeing terms elsewhere produces an OFFER SHEET and the
        # incumbent gets five days. That is the entire difference between
        # tendering a restricted player and letting him walk: not whether he
        # is available, but who gets the last word.
        holder = getattr(p, 'tender_team', None)
        if holder and holder != best.team:
            # OFFER SHEETS ARE RARE: a handful a year across the league. The suitor must be paying well above the
            # tender for a clear upgrade at a real need; otherwise the tendered player stays with the holder
            yr = str(league.year); sheets = league.__dict__.setdefault('offer_sheets_year', {})
            tender = float(p.contract.base[0]) if (p.contract is not None and getattr(p.contract, 'base', None)) else market * 0.6
            suitor = league.teams.get(best.team); ps = (suitor.depth.get(p.pos) or []) if suitor is not None else []
            starter_gap = p.ovr - (ps[0].ovr if ps else 60.0)
            if sheets.get(yr, 0) >= OFFER_SHEETS_A_YEAR or best.apy < tender * 1.5 or starter_gap < 3.0:
                waiting.append(p); continue
            sheets[yr] = sheets.get(yr, 0) + 1
            messages.append(dict(
                kind='offer_sheet', pid=p.pid, name=p.name, team=holder,
                suitor=best.team, offer=round(best.apy, 2),
                years=best.years, bonus=best.bonus, front_load=best.front_load, promises=list(best.promises), days=RFA_MATCH_DAYS, phase=phase,
                subject=f"Offer sheet: {p.name}", body=f"{best.team} have signed {p.name} ({p.pos}, {round(p.ovr)}) to an offer sheet at ${best.apy:.1f}m a year for {best.years} years. Match the offer and he stays; decline and he leaves with no draft compensation.", link=f'player:{p.pid}'))
            waiting.append(p)
            continue

        # refresh_bids already repriced the complete schedule against current
        # books. sign performs the authoritative cap check before mutation.
        try: sign(league, p, best, cap, market_apy=market)
        except ValueError:
            waiting.append(p)
            continue
        league.teams[best.team].sync_cap()
        signed.append((best.team, p, best))

    return signed, waiting, messages


def signing_terms(league, player, team, apy, years, cap, front_load=None, bonus=None):
    """Shared FA preview and signing calculation; only base salary is time-prorated."""
    import contract_structure as CS
    years = int(years)
    if not 1 <= years <= 7 or not np.isfinite(float(apy)) or float(apy) <= 0:
        raise ValueError('Offer must have a positive salary and one to seven years')
    if bonus is not None and (not np.isfinite(float(bonus)) or not 0 <= float(bonus) <= float(apy) * years):
        raise ValueError('Signing bonus must be between zero and the total contract value')
    st = CS.structure(float(apy), years, player.pos, cap, team.gm, front_load=front_load)
    base = list(st['base']); sb = float(st['signing_bonus'])
    if bonus is not None:
        sb = max(0.0, float(bonus)); total_base = max(0.0, float(apy) * years - sb)
        sh = float(st.get('front_load', 0.5))
        weights = [1.0 + (sh - 0.5) * 2 * (1 - 2 * i / max(1, years - 1)) for i in range(years)] if years > 1 else [1.0]
        base = [total_base * w / sum(weights) for w in weights]
    wk = int(league.week or 0)
    paid = getattr(getattr(team, 'cap', None), 'paid_week', max(0, min(18, wk - 1)))
    fraction = (18 - paid) / 18.0 if league.phase in ('regular', 'playoffs', 'playoffs_closed') else 1.0
    if base: base[0] = round(base[0] * fraction, 3)
    preview = Contract(years=years, base=base, signing_bonus=sb)
    from cap_accounting import pre_roll
    start_year = league.year + int(pre_roll(league))
    return dict(base=base, signing_bonus=sb, fraction=fraction, start_year=start_year,
                cash_this_season=round(base[0] + sb, 3),
                cap_hits=[round(preview.cap_hit(i), 3) for i in range(years)], total=round(sum(base) + sb, 3))


def offer_contract(league, player, offer):
    """Preview exactly the contract sign() will install, including pre-roll."""
    team = league.teams[offer.team]
    freeze_offer(league, player, offer)
    cap = CAP.get(league.year, 301.2)
    st = signing_terms(league, player, team, offer.apy, offer.years, cap,
                       offer.front_load, offer.bonus)
    c = Contract(offer.years, st['base'], signing_bonus=st['signing_bonus'],
                 signed=league.year, pay_start=team.cap.paid_week, market_cap=cap)
    from cap_accounting import pre_roll
    if pre_roll(league):
        c.base.insert(0,0.); c.rb.insert(0,0.); c.bonus_schedule.insert(0,0.)
        c.years += 1; c.start_offset=1; c.signed=league.year+1
    return c


def sign(league, player, offer, cap, bonus=None, market_apy=None):
    team = league.teams[offer.team]
    import practice_squad as PSQ
    squad_source = player.team if (player.team in league.teams and player.team != offer.team
                                    and player in PSQ.squad(league.teams[player.team])) else None
    if not available_for_signing(player) and squad_source is None:
        raise ValueError('This player is no longer available as a free agent')
    if bonus is not None: offer.bonus = bonus
    freeze_offer(league, player, offer)
    st = signing_terms(league, player, team, offer.apy, offer.years, cap, offer.front_load, offer.bonus)
    base = st['base']
    paid = team.cap.paid_week
    c = Contract(years=offer.years, base=base,
                 signing_bonus=st['signing_bonus'], signed=league.year, pay_start=paid,
                 market_cap=cap)
    from cap_accounting import require_room, pre_roll
    if pre_roll(league):
        # The displayed cap year is next year until Step 4; no new salary is
        # charged to the completed season or consumed by its contract advance.
        c.base.insert(0,0.0); c.rb.insert(0,0.0); c.bonus_schedule.insert(0,0.0)
        c.years+=1; c.start_offset=1; c.signed=league.year+1
    require_room(league, team, player.pid, c)
    if market_apy is None:
        quote = VAL.value_player(league, player, side='agent', rng=None)
        market_apy = (quote or {}).get('apy', offer.apy)
    if player.team and player.fa_class == 'tendered': _unlist(league, player)
    # the incumbent at his spot who is now behind a man the club just paid
    try:
        import morale as MO
        team = league.teams[offer.team]
        for q in team.depth.get(player.pos, [])[:2]:
            if q is not player and q.ovr <= player.ovr + 1.0:
                MO.shock(league, q.pid, 'team_signed_over_him')
    except Exception:
        pass
    league.sign(player.pid, offer.team, c, log=not bool(squad_source))
    import contract_offer as CO
    CO.remember(league, player, c, offer.apy, market_apy)
    if squad_source:
        # Negotiated practice-squad signings carry the same roster lock as
        # PSQ.poach. The advisor opens this existing negotiation route.
        player.xp_spent['_poach_lock'] = (league.week or 0) + PSQ.POACH_LOCK_GAMES
        league.log('ps_poach', pid=player.pid, team=offer.team, source=squad_source,
                   locked_until=player.xp_spent['_poach_lock'])
    player.fa_class = 'signed'
    for k in offer.promises:
        league.log('promise', pid=player.pid, team=offer.team, promise=k)
        import negotiations as NG
        NG.record_promise(league, player.pid, offer.team, k)


# ============================================================ THE INBOX
def pending_offer_sheet(league, pid):
    return next((m for m in getattr(league, 'inbox', [])
                 if m.get('kind') == 'offer_sheet' and m.get('pid') == pid
                 and not m.get('resolved') and m.get('status', 'unread') in ('unread', 'open')), None)


def inbox_add(league, msg, rng=None):
    """Only the incumbent user's sheets enter the human decision inbox.

    CPU incumbents decide immediately; their decisions never depend on a
    human reading/deleting a message. Historical CPU sheets are drained by
    resolve_offer_sheets after a load.
    """
    import inbox as IB
    if msg.get('kind') == 'offer_sheet':
        old = pending_offer_sheet(league, msg['pid'])
        if old is not None: return old
        if msg.get('team') != getattr(league, 'user_team', None):
            if rng is None:
                from stable import stable_seed
                rng = np.random.default_rng(stable_seed(str(league.year) + msg['pid'] + 'sheet'))
            result = dict(msg, status='unread')
            _settle_offer_sheet(league, result, rng)
            return result
    m = IB.post(league, msg.get('kind', 'note'), msg.get('subject') or msg.get('kind', 'note'),
                msg.get('body', ''), sender=msg.get('team'), payload=dict(msg))
    m.update({k: v for k, v in msg.items() if k not in ('id', 'status')})
    return m


def _settle_offer_sheet(league, msg, rng, action=None):
    """Settle one sheet atomically through sign's cap check; no compensation."""
    p = league.player(msg['pid'])
    holder = league.teams.get(msg['team'])
    def finish(outcome, destination=None):
        msg.update(resolved=True, status='done', outcome=outcome)
        if isinstance(msg.get('payload'), dict): msg['payload']['outcome'] = outcome
        if p is not None and p.team == msg['team'] and getattr(p, 'fa_class', None) == 'tendered':
            p.fa_class = 'under_contract'
        if p is not None: p.tender_team = None
        return dict(ok=True, outcome=outcome, team=destination)
    if (p is None or p.retired or holder is None or p.team != msg['team']
            or getattr(p, 'fa_class', None) != 'tendered'):
        # A stale request must not alter a player's newer deal/tender.
        msg.update(resolved=True, status='done', outcome='void')
        return dict(ok=True, outcome='void')
    cap = CAP.get(league.year, 301.2)
    price, years = msg['offer'], msg.get('years', 2)
    if action is None:
        value = VAL.value_player(league, p, side='team', rng=rng)
        worth = value['apy'] if value else price
        # The exact replacement contract is budgeted below, including removal
        # of the existing tender. APY is not an incremental cap charge.
        action = 'match' if worth >= price * .72 else 'decline'
    destination = msg['team'] if action == 'match' else msg['suitor']
    if destination not in league.teams:
        return finish('void')
    try:
        # Older sheets lack explicit bonus/shape. Resolve against the original
        # suitor once, so a matching incumbent cannot change the contract.
        original = freeze_offer(league, p, Offer(msg['suitor'], p.pid, price, years,
            bonus=msg.get('bonus'), front_load=msg.get('front_load'), promises=msg.get('promises', ())))
        msg.update(bonus=original.bonus, front_load=original.front_load)
        proposal = Offer(destination, p.pid, price, years, phase=3,
                         bonus=msg.get('bonus'), front_load=msg.get('front_load'), promises=msg.get('promises', ()))
        if destination != getattr(league,'user_team',None):
            import financial_plan as FP
            import roster_needs as RN
            team = league.teams[destination]
            gain = (RN.assess(team)['score']-RN.assess(team,[q for q in team.active() if q.pid!=p.pid])['score']
                    if p.team==destination else RN.move_gain(team,p))
            if not FP.evaluate(league,team,additions=[(p,offer_contract(league,p,proposal))],
                               gain=gain,action='offer_sheet')['approved']:
                raise ValueError('CPU financial plan cannot fund this offer sheet')
        sign(league,p,proposal,cap)
    except ValueError as exc:
        if action == 'match' and msg['team'] == getattr(league, 'user_team', None):
            return dict(ok=False, why=str(exc))  # retain the user's decision
        if action == 'match':
            return _settle_offer_sheet(league, msg, rng, action='decline')
        return finish('void')  # suitor cannot honor it: original tender stands
    league.teams[destination].sync_cap()
    return finish('matched' if action == 'match' else 'departed', destination)


def answer_offer_sheet(league, msg_id, action, rng=None):
    """Session/UI API: match or decline an open sheet for the user's player."""
    if action not in ('match', 'decline'): return dict(ok=False, why='choose match or decline')
    msg = next((m for m in getattr(league, 'inbox', []) if m.get('id') == msg_id), None)
    if (not msg or msg.get('kind') != 'offer_sheet' or msg.get('resolved')
            or msg.get('status') not in ('unread', 'open')
            or msg.get('team') != getattr(league, 'user_team', None)):
        return dict(ok=False, why='no open offer sheet for your team')
    return _settle_offer_sheet(league, msg, rng, action=action)


def resolve_offer_sheets(league, rng, verbose=False):
    """Resolve legacy CPU sheets; user incumbents retain their match decision."""
    kept, lost = [], []
    for msg in getattr(league, 'inbox', []):
        if msg.get('kind') != 'offer_sheet': continue
        if msg.get('resolved'):
            msg['status'] = 'done'; continue
        if msg.get('status', 'unread') not in ('unread', 'open'): continue
        if msg.get('team') == getattr(league, 'user_team', None): continue
        result = _settle_offer_sheet(league, msg, rng)
        p = league.player(msg['pid'])
        if result.get('outcome') == 'matched': kept.append((msg['team'], p, msg['offer']))
        elif result.get('outcome') == 'departed': lost.append((msg['suitor'], p, msg['offer']))
    if verbose: print(f'  offer sheets: {len(kept)} matched, {len(lost)} lost')
    return kept, lost


def _unlist(league, player):
    """Clear a tendered man's placeholder deal before he signs a real one."""
    t = league.teams.get(player.team)
    if t and player in t.roster:
        t.roster.remove(player)
        t.sync_cap()
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
        if p.fa_class != 'tendered' or p.retired or pending_offer_sheet(league, p.pid):
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


def fill_out_rosters(league, pool, rng, verbose=False, user_team=None):
    """
    After the draft, clubs still short of a roster sign cheap depth.

    Wait until the rookie class and undrafted signings are on rosters. A club
    can be short after expiries, but filling every slot at market close just
    creates veterans who are immediately displaced by draft picks.
    """
    import min_salary as MS
    import roster_needs as RN
    from cutdown import POS_CAP
    from replacement_contracts import minimum_acceptance
    cap = CAP.get(league.year, 301.2)
    signed = 0
    comps = VAL.pool_from_league(league)
    protected = {user_team, getattr(league, 'user_team', None)} - {None}
    for abbr, team in league.teams.items():
        if abbr in protected:
            continue  # The user fills their own roster, including cheap depth.
        need = ROSTER_TARGET - len(team.active())
        if need <= 0:
            continue
        # best available who will play for the minimum, his own position; never a player who should be paid
        # scarcity first
        avail = [q for q in pool if q.ovr < REPLACEMENT_GRADE or q.pos in ('K', 'P', 'LS')]
        roster_needs = RN.assess(team)['needs']
        avail.sort(key=lambda p: -(p.ovr + 20.0 * roster_needs.get(p.pos, 0.0)))
        for p in list(avail):
            if need <= 0:
                break
            if not minimum_acceptance(league, team, p, pool=comps)['accepts']:
                continue
            floor = MS.minimum_salary(p.accrued, cap)
            # filling a slot RELEASES reserve, so the test is plain space
            if team.cap_space < floor * 1.05:
                continue  # A cheaper rookie behind this veteran may still fit.
            grp = team.by_pos(p.pos)
            if len(grp) >= POS_CAP.get(p.pos, 4):
                continue                  # already deep here
            o = Offer(abbr, p.pid, round(floor, 3), 1, phase=3)
            # Post-draft depth remains disposable; no bonus to turn a later
            # waiver upgrade into unnecessary dead money.
            try: sign(league, p, o, cap, bonus=0)
            except ValueError: continue
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
    import negotiations as NG
    for phase in range(1, PHASES + 1):
        PA.offseason(league, 5 + phase)
        league.fa_step = phase
        bids = ai_bids(league, pool, phase, rng, skip_teams=(user_team,) if user_team else ())
        # the user's live offers do not sign inside the market: the player mulls
        # and answers through his thread (yes, no, counter, or match). The
        # best rival bid is told to the thread, and a player whose best offer is
        # the user's holds out of this step's signings so he can answer
        held = []
        for t in NG._threads(league):
            if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered') and t['offers']:
                p = league.player(t['pid'])
                if p is None or p not in pool: continue
                o = t['offers'][-1]
                others = bids.get(p.pid, [])
                if others:
                    best = best_offer(league, p, others, t['ask']); NG.set_rival(league, p.pid, best.team, best.apy, best.years, best.bonus, best.front_load, best.promises)
                    if hold_user_offer(league, p, t, o, best):
                        held.append(p)
                else:
                    held.append(p)
        pool_now = [p for p in pool if p not in held]
        signed, waiting, msgs = resolve_phase(league, pool_now, bids, phase, rng,
                                              user_team)
        refresh_negotiation_rivals(league, bids, user_team)
        waiting = waiting + held
        # threads whose man signed elsewhere close; the rest get their answer
        for t in NG._threads(league):
            if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'):
                p = league.player(t['pid'])
                if p is not None and p.team and p.team != t['team']:
                    t['state'] = 'declined'; NG._post(league, t, f"{p.name} signs with {p.team}", "He took another offer.")
        NG.resolve(league, fa_step=phase)
        waiting = [p for p in waiting if p.team is None]    # a player who signed through his thread is off the market
        for m in msgs:
            inbox_add(league, m, rng)
        all_signed += signed
        pool = waiting
        if verbose:
            print(f'  phase {phase}: {len(signed)} signed, {len(pool)} left, '
                  f'{len(msgs)} messages')

    # The market closes before the draft. Depth is filled after teams see
    # their rookie classes and undrafted signings.
    PA.offseason(league, 9)
    league.fa_step = PHASES + 1
    NG.resolve(league, fa_step=PHASES + 1)
    for t in NG._threads(league):
        if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'):
            t['state'] = 'declined'; NG._post(league, t, f"{league.player(t['pid']).name} moves on", "The market has closed without a deal.")
    resolve_offer_sheets(league, rng, verbose)

    # Nobody leaves the market over the cap. Decisions compound even when each
    # one was affordable on its own.
    import contracts as CT
    CT.enforce(league, rng, verbose)

    # the pool does not empty - it stays open and reopens at camp
    league.free_agents = [pid for pid in dict.fromkeys([p.pid for p in pool] + league.free_agents)
                          if (p := league.player(pid)) and p.team is None and not p.retired]
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
    print('\nbest players still unsigned:')
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


# ============================================================ THE MARKET AS STAGES
# The offseason calendar carries four free-agency stages: Round 1, Round 2, Round 3, Market Closes. Entering a round
# lodges the AI clubs' bids (league.fa_bids) so the user's talks can see who else is in on a player; advancing
# resolves the round, with the user's offers in the mix (his answers come back through his talks); the close prices
# whoever is left and fills rosters with genuine depth only. run() below is the old one-shot version and stays for
# the register and the offline tools.

def _pool(league):
    # unsigned players, and the tendered restricted free agents (still the holder's, but biddable)
    pool = [league.player(pid) for pid in list(league.free_agents)]
    return [p for p in pool if p and not p.retired and (p.team is None or getattr(p, 'fa_class', None) == 'tendered')]


def open_round(league, rng, phase, user_team=None):
    """A round opens: every club lodges its bids on the players it wants. The user's open talks learn their rival."""
    import negotiations as NG
    league.set_phase('free_agency'); league.fa_step = phase
    league.__dict__.setdefault('inbox', [])
    pool = _pool(league)
    bids = ai_bids(league, pool, phase, rng, skip_teams=(user_team,) if user_team else ())
    league.fa_bids = {pid: [freeze_offer(league, league.player(pid), o).to_save() for o in offers] for pid, offers in bids.items()}
    league.fa_bids_phase = phase
    # what the user can see: the best rival on each player he is talking to
    for t in NG._threads(league):
        if t['kind'] == 'fa_offseason' and t['state'] in ('open', 'waiting', 'countered', 'match_requested'):
            others = bids.get(t['pid'], [])
            if others:
                best = best_offer(league, league.player(t['pid']), others, t['ask']); NG.set_rival(league, t['pid'], best.team, best.apy, best.years, best.bonus, best.front_load, best.promises)
    return bids


def resolve_round(league, rng, phase, user_team=None):
    """The round closes at the advance: every player with offers signs, waits, or asks for a match; the user's talks
    get their answers (yes, no, more, match). Returns (signed, waiting, messages)."""
    import negotiations as NG
    league.fa_step = phase
    pool = _pool(league)
    bids = {pid: [Offer.from_save(d) for d in offers] for pid, offers in (getattr(league, 'fa_bids', None) or {}).items()}
    if getattr(league, 'fa_bids_phase', None) != phase:
        bids = ai_bids(league, pool, phase, rng, skip_teams=(user_team,) if user_team else ())
    # the user's offers ride alongside the AI's: a player he is bidding on within reach of the best rival waits for
    # his talk to answer instead of being decided by the AI resolution alone
    held = []
    for t in NG._threads(league):
        if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested') and t['offers']:
            p = league.player(t['pid'])
            if p is None or p not in pool: continue
            o = t['offers'][-1]; others = bids.get(p.pid, [])
            if others:
                best = best_offer(league, p, others, t['ask']); NG.set_rival(league, p.pid, best.team, best.apy, best.years, best.bonus, best.front_load, best.promises)
                if hold_user_offer(league, p, t, o, best): held.append(p)
            else:
                held.append(p)
    pool_now = [p for p in pool if p not in held]
    # THE AI CONVERTS TENDERS: a club with a good tendered player and the room signs him long term during the market,
    # as real clubs do, rather than letting him play the year on the tender
    converted = convert_tenders(league, rng, phase, user_team=user_team)
    pool_now = [p for p in pool_now if p not in converted]
    signed, waiting, msgs = resolve_phase(league, pool_now, bids, phase, rng, user_team)
    refresh_negotiation_rivals(league, bids, user_team)
    league.fa_bids = {pid: [o.to_save() for o in rows] for pid, rows in bids.items()}
    waiting = waiting + held
    for t in NG._threads(league):
        if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'):
            p = league.player(t['pid'])
            if p is not None and p.team and p.team != t['team']:
                t['state'] = 'declined'; NG._post(league, t, f"{p.name} signs with {p.team}", "He took another offer.")
    NG.resolve(league, fa_step=phase)
    waiting = [p for p in waiting if p.team is None]
    for mm in msgs: inbox_add(league, mm, rng)
    league.free_agents = [p.pid for p in waiting]
    league.fa_bids = {}; league.fa_bids_phase = None
    league.__dict__.setdefault('fa_signed', []).extend([(t_, p.pid, o.apy, o.years, phase) for t_, p, o in signed])
    return signed, waiting, msgs


def close_market(league, rng, user_team=None, verbose=False):
    """The market closes: the user's unanswered talks lapse, the players still worth real money sign one-year deals at
    a discount with clubs that have room (or wait for camp), offer sheets resolve, every club is brought under the
    cap. Minimum-salary depth waits until after the draft."""
    import negotiations as NG
    PA.offseason(league, 9)
    league.fa_step = PHASES + 1
    NG.resolve(league, fa_step=PHASES + 1)
    for t in NG._threads(league):
        if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'):
            pp = league.player(t['pid'])
            t['state'] = 'declined'; NG._post(league, t, f"{pp.name if pp else 'He'} moves on", "The market has closed without a deal.")
    pool = _pool(league)
    for p in [q for q in pool if getattr(q, 'fa_class', None) == 'tendered' and q.team and not pending_offer_sheet(league, q.pid)]:
        p.fa_class = 'under_contract'; p.tender_team = None           # the tender stands: he plays the year on it
        if p.pid in league.free_agents: league.free_agents.remove(p.pid)
    pool = [p for p in pool if p.team is None]
    signed = sign_the_leftovers(league, pool, rng, user_team=user_team)
    pool = [p for p in pool if p.team is None]
    resolve_offer_sheets(league, rng, verbose)
    import contracts as CT
    CT.enforce(league, rng, verbose)
    league.free_agents = [pid for pid in dict.fromkeys([p.pid for p in pool] + league.free_agents)
                          if (p := league.player(pid)) and p.team is None and not p.retired]
    league.fa_bids = {}; league.fa_bids_phase = None
    return signed


REPLACEMENT_GRADE = 78.0            # above this a player is not a body; he is priced

def sign_the_leftovers(league, pool, rng, user_team=None):
    """April's veterans: anyone above replacement grade still on the market signs a one-year deal at about 70% of his
    market with the club that has the room and the need, best players first. A player nobody can afford waits for
    camp rather than signing for the minimum. The user's club never signs anyone here; the page is his."""
    cap = CAP.get(league.year, 301.2)
    comps = VAL.pool_from_league(league)
    import roster_needs as RN
    import financial_plan as FP
    # A club's allocation only changes when it signs someone. Reuse that
    # snapshot across the remaining market instead of rebuilding every
    # package twice for every player/team pairing.
    reports = {abbr: RN.assess(team) for abbr, team in league.teams.items()}
    out = []
    for p in sorted([q for q in pool if q.ovr >= REPLACEMENT_GRADE and q.pos not in ('K', 'P', 'LS')], key=lambda q: -q.ovr):
        v = VAL.value_player(league, p, pool=comps, rng=rng)
        market = v['apy'] if v else 3.0
        price = round(max(market * 0.70, 1.5), 2)
        best = None; best_score = -1e9
        for abbr, team in league.teams.items():
            if abbr in (user_team,getattr(league,'user_team',None)): continue
            if len(team.active()) >= 90: continue
            report=reports[abbr]
            gain = RN.move_gain(team, p, baseline=report)
            if gain <= 1.: continue
            proposal = Offer(abbr, p.pid, price, 1, phase=PHASES+1)
            if not acquisition_read(league,team,p,proposal,gain,market,report)['approved']:
                continue
            if not FP.evaluate(league, team, additions=[(p,offer_contract(league,p,proposal))],
                               gain=gain, action='fa_leftover')['approved']:
                continue
            score = gain + 10.0 * report['needs'].get(p.pos, 0.0) + rng.normal(0, 1.5)
            if score > best_score: best, best_score = team, score
        if best is None: continue
        o = Offer(best.abbr, p.pid, price, 1, phase=PHASES + 1)
        try: sign(league, p, o, cap)
        except ValueError: continue
        best.sync_cap(); out.append((best.abbr, p, o))
        reports[best.abbr] = RN.assess(best)
        league.__dict__.setdefault('fa_signed', []).append((best.abbr, p.pid, o.apy, 1, PHASES + 1))
    return out


def convert_tenders(league, rng, phase, user_team=None):
    """AI clubs sign their better tendered restricted free agents to long-term deals during the market: about a third
    of them a round for a player graded 76 and up, at his market, when the club has the room. The user's own tendered
    players are his to extend from the Extensions page."""
    import extensions as EXT
    cap = CAP.get(league.year, 301.2)
    done = []
    for abbr, team in league.teams.items():
        if abbr == user_team: continue
        for p in [q for q in team.active() if getattr(q, 'fa_class', None) == 'tendered' and q.ovr >= 76]:
            if rng.random() > 0.35: continue
            try:
                tm = EXT.terms(league, p, rng)
                if tm is None: continue
                apy = max(float(tm['offer']), float(tm['ask']) * (1.0 - tm['discount']))
                years = int(tm['years'])
                r = EXT.negotiate_ai(league, p, apy, years, rng)
                if r.get('result') != 'accepted': continue
                p.fa_class = 'under_contract'; p.tender_team = None
                if p.pid in league.free_agents: league.free_agents.remove(p.pid)
                team.sync_cap(); done.append(p)
            except Exception:
                continue
    return done
