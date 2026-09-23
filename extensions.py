"""
EXTENSIONS.

A club extends a man it wants to keep before he reaches the market. The
remaining years of his deal stay as signed; the new years are added on top
and the new signing bonus prorates over up to five years from now. Cap
hits, dead money and the trade engine read the result like any contract.

WHO CAN. Two or fewer years left, and a rookie deal only after his third
season (first-rounders carry the fifth-year option separately).

THE PRICE. The agent asks the market's agent-side number; the club offers
its team-side number. The player takes a small certainty discount for money
now, which shrinks to nothing for a star in his final year, who has no
reason to give one. A deal is done when the club's number clears the ask
less the discount.

THE AI. Each offseason before the market opens, and once more before week
one, each club reviews its expiring men: starters and near-starters on the
right side of the age curve, who fit the scheme, and whom it can afford
against next year's books. Two to four a club a year is the real pace.

THE USER. extend(league, pid, apy, years) returns accepted, countered or
refused with the agent's reasoning; the inbox gets a note when one of his
men enters his final year.
"""
import numpy as np
from cap_engine import Contract, CAP, MAX_PRORATION_YEARS
import contract_structure as CS
import valuation as VAL

MAX_PER_CLUB = 4
AGE_LIMIT = {'QB': 36, 'K': 38, 'P': 38}
CERTAINTY_DISCOUNT = 0.07


def eligible(p, league):
    c = p.contract
    if c is None or c.years > 2:
        return False
    if p.draft_year and (league.year - p.draft_year) < 3 and p.draft_round is not None:
        return False
    return True


def terms(league, p, rng):
    """(ask_apy, offer_apy, years_wanted, discount)."""
    a = VAL.value_player(league, p, side='agent', rng=rng)
    t = VAL.value_player(league, p, side='team', rng=rng)
    if not a or not t:
        return None
    import personality as PT
    star = p.ovr >= 88 and p.contract.years <= 1
    disc = 0.0 if star else CERTAINTY_DISCOUNT * (1.0 if p.contract.years <= 1 else 1.4)
    disc = disc * PT.certainty_discount_mult(p) + PT.extension_discount(p)    # money and loyalty
    disc = float(np.clip(disc, -0.05, 0.25))
    ask = a['apy'] * PT.ask_mult(p)
    years = int(np.clip(a['years'], 1, 5))
    if p.age >= 30: years = min(years, 3)
    return dict(ask=ask, offer=t['apy'], years=years, discount=disc)


def build(p, add_years, apy, cap, gm, league):
    """The extended contract: old years kept, new years appended, new bonus prorated from now."""
    old = p.contract
    left = old.years
    st = CS.structure(apy, add_years, p.pos, cap, gm)
    # the old bonus still owed keeps its proration; the new bonus spreads over
    # everything left, up to five years
    old_prorated_left = old.annual_proration * min(left, old.proration_years) if old.sb else 0.0
    new_years = left + add_years
    base = list(old.base) + list(st['base'])
    rb = list(old.rb) + [0.0] * add_years
    c = Contract(years=new_years, base=base, signing_bonus=old_prorated_left + st['signing_bonus'],
                 roster_bonus=rb, signed=league.year)
    return c


def extend(league, pid, apy, years, rng=None, by_ai=False):
    """The offer to the man. Returns dict(result, ...)."""
    rng = rng or np.random.default_rng()
    p = league.player(pid)
    if p is None or p.team is None:
        return dict(result='refused', why='not under contract to a club')
    if not eligible(p, league):
        return dict(result='refused', why='not eligible: more than two years left, or a rookie deal before his third season')
    tm = terms(league, p, rng)
    if tm is None:
        return dict(result='refused', why='no market read on him')
    floor = tm['ask'] * (1.0 - tm['discount'])
    if getattr(p, 'morale', None) is not None:
        import morale_system as MS
        ne = MS.negotiation_effect(p.morale)
        floor *= 1.0 + ne['demand_premium']
        if not ne['will_discount']: floor = max(floor, tm['ask'] * (1.0 + ne['demand_premium']) * (1.0 - 0.02))
    team = league.teams[p.team]
    if apy + 1e-9 < floor * 0.97:
        counter = round(floor, 2)
        return dict(result='countered', ask=counter, years=tm['years'], why=f"his agent wants ${counter}m a year over {tm['years']} years")
    if years < 1:
        return dict(result='refused', why='at least one new year')
    cap = CAP.get(league.year, 301.2)
    c = build(p, years, apy, cap, team.gm, league)
    p.contract = c
    team.sync_cap()
    import morale as MO
    MO.shock(league, pid, 'extension_signed')
    if MO.wants_out(p) and p.xp_spent['_request'].get('reason') == 'contract':
        MO.resolve_request(league, pid, 'extension')
    league.log('extension', pid=pid, team=p.team, apy=round(apy, 2), years=years, ai=by_ai)
    return dict(result='accepted', apy=round(apy, 2), years=years, contract=c)


def next_year_room(team, cap_next):
    """What the club has committed next year against next year's cap."""
    committed = sum(p.contract.cap_hit(1) for p in team.active() if p.contract and p.contract.years > 1)
    return cap_next - committed - team.cap.dead_next


def ai_round(league, rng, verbose=False):
    """Every club keeps who it can, before the market."""
    from gm_engine import scheme_fit
    cap = CAP.get(league.year, 301.2); cap_next = CAP.get(league.year + 1, cap * 1.07)
    done = []
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None) or team.gm is None:
            continue
        gm = team.gm
        cands = []
        for pos, ps in team.depth.items():
            for rank, p in enumerate(ps[:2]):
                if not eligible(p, league): continue
                if p.age > AGE_LIMIT.get(p.pos, 31) - (0 if rank == 0 else 2): continue
                if scheme_fit(p.ratings, p.pos, team) < -2.0: continue
                cands.append((rank, -p.ovr, p))
        # starters first, then by value on the common scale, so a kicker's 90
        # does not jump the queue over a tackle's 86
        import draft as DFT
        scale = DFT.position_scale(league)
        cands.sort(key=lambda x: (x[0], -DFT.common_scale(x[2].ovr, x[2].pos, scale)))
        room = next_year_room(team, cap_next)
        n = 0
        for rank, _o, p in cands:
            if n >= MAX_PER_CLUB: break
            tm = terms(league, p, rng)
            if tm is None: continue
            floor = tm['ask'] * (1.0 - tm['discount'])
            # what the club will pay: its own number, stretched toward the ask
            # by how much it wants him (a starter more than a backup) and by
            # its youth lean (a youth club lets the 29-year-old walk)
            want = 1.0 - 0.06 * rank - 0.10 * max(0.0, gm.youth - 0.5) * (p.age >= 28)
            offer = tm['offer'] * (1.0 + 0.12 * want)
            if offer < floor: continue
            if offer * tm['years'] > room + offer * 0.35:       # cannot carry him next year
                continue
            res = extend(league, p.pid, round(min(offer, tm['ask']), 2), tm['years'], rng, by_ai=True)
            if res['result'] == 'accepted':
                room -= offer; n += 1; done.append((abbr, p.name, p.pos, round(p.ovr), res['apy'], res['years']))
    if verbose:
        print(f'  {len(done)} extensions')
    return done


def notify_user(league):
    """The inbox: your men entering their final year."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if not user: return 0
    n = 0
    for p in league.teams[user].active():
        if p.contract and p.contract.years == 1 and eligible(p, league) and p.ovr >= 76:
            IB.post(league, 'contract_year', f'{p.name} enters his final year', 
                    f"{p.name} ({p.pos}, {p.ovr:.0f}, age {p.age:.0f}) is in the last year of his deal at ${p.apy:.1f}m. "
                    f"He can be extended now; his agent will price him at the market.", sender=user,
                    payload=dict(pid=p.pid, link=f'player:{p.pid}'), expires_week=None)
            n += 1
    return n
