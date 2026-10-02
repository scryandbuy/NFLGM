"""Contract cash evaluation shared by negotiations and the free-agent market.

Compare incremental offers over one nine-year horizon. Future earnings are
player beliefs, not simulated outcomes or access to hidden development data.
Salary guarantees remain absent. Coefficients are hypotheses for testing,
not claims about observed player preferences or an approved balance change.
"""
from dataclasses import dataclass
import math

HORIZON = 9  # maximum two remaining years plus seven new years
SCENARIOS = ((.25, 'down'), (.5, 'steady'), (.25, 'up'))
PEAK_END = {'HB': 27, 'FB': 28, 'WR': 29, 'CB': 29, 'QB': 34,
            'TE': 31, 'LT': 32, 'LG': 32, 'C': 32, 'RG': 32, 'RT': 32,
            'K': 36, 'P': 36, 'LS': 36}


def clip(value, low, high):
    return max(low, min(high, value))


@dataclass(frozen=True)
class PlayerBeliefs:
    age: float
    pos: str
    market_apy: float
    security: float = .5
    money: float = .5
    # Optional visible recent-performance trend; the current adapter uses zero.
    # Never read potential, development tier, or future simulation outcomes.
    recent_growth: float = 0.
    cap_growth: float = .04

    def __post_init__(self):
        for name in ('age', 'market_apy', 'security', 'money', 'recent_growth', 'cap_growth'):
            if not math.isfinite(getattr(self, name)):
                raise ValueError('Nonfinite belief')
        if self.market_apy <= 0 or not 18 <= self.age <= 60:
            raise ValueError('Invalid age or market value')
        if not 0 <= self.security <= 1 or not 0 <= self.money <= 1:
            raise ValueError('Personality must be between zero and one')
        if not -.08 <= self.recent_growth <= .08 or not 0 <= self.cap_growth <= .10:
            raise ValueError('Forecast outside modeling bounds')


@dataclass(frozen=True)
class OfferCash:
    # New cash only. An extension excludes existing salaries and old bonus.
    base: tuple
    bonus: float
    starts_in: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'base', tuple(float(v) for v in self.base))
        if not 1 <= len(self.base) <= 7 or self.starts_in not in (0, 1, 2):
            raise ValueError('Unsupported real years or extension offset')
        if self.starts_in + len(self.base) > HORIZON:
            raise ValueError('Contract exceeds comparison horizon')
        if any(not math.isfinite(v) or v < 0 for v in (*self.base, self.bonus)):
            raise ValueError('Invalid new compensation')
        if self.total <= 0:
            raise ValueError('Empty offer')

    @property
    def years(self):
        return len(self.base)

    @property
    def total(self):
        return sum(self.base) + self.bonus

    @property
    def apy(self):
        return self.total / self.years


def from_extension(old, proposed):
    """Read the ACTUAL preview builder result; never reconstruct its cash.

    Bonus schedule is accounting allocation, not annual player cash. Its
    difference is the new up-front payment. Void years are excluded.
    """
    left = old.years if old is not None else 0
    previous = sum(old.bonus_schedule) if old is not None else 0.
    bonus = sum(proposed.bonus_schedule) - previous
    base = tuple(proposed.base[i] + proposed.rb[i] for i in range(left, proposed.years))
    return OfferCash(base, max(0., bonus), left)


def from_free_agent(proposed):
    if getattr(proposed, 'start_offset', 0):
        raise ValueError('Delayed FA salary needs an explicit adapter')
    return OfferCash(tuple(proposed.base[i] + proposed.rb[i] for i in range(proposed.years)),
                     sum(proposed.bonus_schedule))


def beliefs_from_profile(player, market_apy, profile, *, recent_growth=0., cap_growth=.04):
    """Reuse the saved FA profile; no RNG and no separate personality draw."""
    weights = profile['w']
    return PlayerBeliefs(float(player.age), player.pos, market_apy,
                         clip(float(weights['years']) / .32, 0., 1.),
                         clip(float(weights['total']) / .65, 0., 1.),
                         recent_growth, cap_growth)


def _future_market(beliefs, year, scenario):
    # Same forecast applies to all offers. Dollars are normalized to today's
    # market APY, so 40 years of cap inflation do not change the preference.
    peak = PEAK_END.get(beliefs.pos, 30)
    aging = max(0., beliefs.age + year - peak) - max(0., beliefs.age - peak)
    growth = beliefs.recent_growth * min(year, 3)
    central = (1 + beliefs.cap_growth) ** year * math.exp(growth - .075 * aging)
    uncertainty = min(.65, .13 * year)
    shift = {'down': 1 - uncertainty, 'steady': 1., 'up': 1 + uncertainty}[scenario]
    return central * shift


def evaluate(offer, beliefs):
    """Risk-adjusted earnings in current-market annual-pay units.

    Every path includes subsequent FA earnings after expiry or release. One
    down path represents earning uncertainty, not a known injury prediction.
    This v1 deliberately exposes retention/forecast sensitivity for audit.
    """
    totals = []
    peak = PEAK_END.get(beliefs.pos, 30)
    # Time value is common to both deals; added risk aversion is separate.
    discount = .045
    for probability, scenario in SCENARIOS:
        total = offer.bonus / beliefs.market_apy
        retained = 1.
        for year in range(offer.starts_in, HORIZON):
            market = _future_market(beliefs, year, scenario)
            t = year - offer.starts_in
            if t < offer.years:
                hazard = (.035 + .012 * max(0., beliefs.age + year - peak)
                          + {'down': .12, 'steady': .02, 'up': 0.}[scenario])
                # Salary is never represented as guaranteed. Extension years
                # also carry the risk of being cut before those years begin.
                salary = offer.base[t] / beliefs.market_apy
                # Unguaranteed salary far above the player's projected market
                # is precisely the part the club can avoid by releasing him.
                # Already-paid signing bonus is sunk cash, not salary protection.
                excess = max(0., salary / max(.01, market) - 1.10)
                before = retained
                retained *= math.exp(-hazard * (offer.starts_in + 1 if t == 0 else 1)
                                     - 2.5 * excess * excess)
                newly_released = before - retained
                cash = retained * salary + (1 - retained) * market - newly_released * market * .15
            else:
                cash = market
            total += cash / (1 + discount) ** year
        totals.append((probability, total))
    expected = sum(p * cash for p, cash in totals)
    downside = sum(p * max(0., expected - cash) for p, cash in totals)
    risk_weight = .15 + 1.6 * beliefs.security * (1 - .45 * beliefs.money)
    score = expected - risk_weight * downside
    return dict(score=score, expected=expected, downside=downside,
                scenarios=[cash for _, cash in totals],
                secured_now=offer.bonus, nominal_total=offer.total,
                years=offer.years, apy=offer.apy)


def compare(offer, reference, beliefs):
    """Reference is the agent's current acceptable package, not a naked APY.

    A bounded security concession prevents forecast beliefs alone pricing a
    veteran far below his current market. Team/role/promises and cap legality
    remain in the calling negotiation and market systems.
    """
    if offer.starts_in != reference.starts_in:
        raise ValueError('Offers must share an extension start date')
    actual, alternative = evaluate(offer, beliefs), evaluate(reference, beliefs)
    allowance = .03 + .09 * beliefs.security * (1 - .5 * beliefs.money)
    raw_gap = actual['score'] - alternative['score']
    annuity = sum(1 / 1.045 ** (offer.starts_in + i) for i in range(offer.years))
    raw_equivalent = reference.apy + raw_gap * beliefs.market_apy / annuity
    # One bounded valuation, rather than a second veto after the model says
    # yes. A stronger package buys a modest concession; false late money can
    # lose substantially more value. The same number drives every decision.
    equivalent = min(raw_equivalent, offer.apy / (1 - allowance))
    gap = equivalent - reference.apy
    return dict(preferred=gap >= -1e-9, acceptable=gap >= -1e-9,
                value_gap=gap / reference.apy, raw_value_gap=raw_gap, max_discount=allowance,
                equivalent_apy=equivalent, ratio=max(0., equivalent / reference.apy),
                offer=actual, reference=alternative)
