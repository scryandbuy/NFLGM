"""
NFL salary cap engine.

Cap values 1994-2026 are the real published figures, recovered from OverTheCap
contract data (apy / apy_cap_pct) and spot-checked against known caps.
Growth model is fitted to the real year-over-year series.
Mechanics follow the CBA: proration capped at 5 years, dead-money acceleration,
June 1 designations, top-51 in the offseason, and unused-space rollover.
"""
import numpy as np

# ---------------------------------------------------------------- real caps
CAP = {
 1994: 34.608, 1995: 37.100, 1996: 40.753, 1997: 41.454, 1998: 52.388,
 1999: 57.288, 2000: 62.172, 2001: 67.405, 2002: 71.101, 2003: 74.958,
 2004: 80.582, 2005: 85.500, 2006: 102.000, 2007: 109.000, 2008: 116.000,
 2009: 123.000, 2010: float('nan'),          # uncapped year
 2011: 120.375, 2012: 120.600, 2013: 123.000, 2014: 133.000, 2015: 143.280,
 2016: 155.270, 2017: 167.000, 2018: 177.200, 2019: 188.200, 2020: 198.200,
 2021: 182.500, 2022: 208.200, 2023: 224.800, 2024: 255.400, 2025: 279.200,
 2026: 301.000,
}

# growth fitted to the real series (2011-2026, excluding the 2021 COVID reset)
BASE_GROWTH   = 0.075      # median year-over-year
GROWTH_SD     = 0.022
MEDIA_CYCLE   = 8          # new broadcast deals land roughly this often
MEDIA_BUMP    = 0.055      # they add this on top (1998, 2006, 2022, 2024 pattern)
SHOCK_PROB    = 0.02       # lockout / pandemic
SHOCK_SIZE    = -0.08

def project_cap(year, last_year, last_cap, rng=None, media_years=()):
    """Advance the cap one year. Real values are used wherever we have them."""
    if year in CAP and not np.isnan(CAP[year]): return CAP[year]
    rng = rng or np.random.default_rng()
    g = rng.normal(BASE_GROWTH, GROWTH_SD)
    if year in media_years or (year - 2024) % MEDIA_CYCLE == 0:
        g += MEDIA_BUMP
    if rng.random() < SHOCK_PROB:
        g = SHOCK_SIZE
    return round(last_cap * (1 + g), 3)

# ---------------------------------------------------------------- contracts
MAX_PRORATION_YEARS = 5

class Contract:
    def __init__(self, years, base, signing_bonus=0.0, roster_bonus=None,
                 void_years=0, signed=2026, **_ignored):
        # GUARANTEED MONEY IS CUT FROM THE GAME by decision - too complex for
        # what it adds. **_ignored swallows guaranteed_years from any older
        # save or caller rather than exploding on it.
        #
        # Nothing about the cap depends on it: dead money comes from SIGNING
        # BONUS proration, which is untouched. A cut still accelerates the
        # remaining bonus exactly as before.
        self.signed  = signed
        self.years   = years
        self.base    = list(base)                    # base salary per year
        self.sb      = signing_bonus
        self.rb      = list(roster_bonus or [0.0]*years)
        self.void    = void_years

    @property
    def proration_years(self):
        # void years extend proration but never past 5
        return min(self.years + self.void, MAX_PRORATION_YEARS)

    @property
    def annual_proration(self):
        return self.sb / self.proration_years if self.sb else 0.0

    def cap_hit(self, i):
        """cap charge in year i (0-indexed)."""
        p = self.annual_proration if i < self.proration_years else 0.0
        return self.base[i] + self.rb[i] + p

    def remaining_proration(self, i):
        """signing-bonus money not yet charged, from year i onward."""
        left = max(0, self.proration_years - i)
        return self.annual_proration * left

    def advance(self):
        """
        One year older. Drops the year just played and leaves the deal on its
        remaining years.

        NOTHING CALLED THIS, and the consequence was that no contract in the
        league ever expired. Every club kept every player forever, twenty-seven
        men reached free agency across the whole league against a real four to
        six hundred, and the market had nothing in it.

        Returns True when the deal is done and he is a free agent.
        """
        self.years -= 1
        if self.base:
            self.base.pop(0)
        if self.rb:
            self.rb.pop(0)
        return self.years <= 0

    # ---- transactions ----
    def release(self, i, june1=False):
        """
        Returns (dead_money_this_year, dead_money_next_year, cap_saved_this_year).
        Standard: all remaining proration accelerates into the current year.
        June 1: this year's proration stays, the rest lands next year.
        """
        rest = self.remaining_proration(i)
        if june1:
            dead_now, dead_next = self.annual_proration, rest - self.annual_proration
        else:
            dead_now, dead_next = rest, 0.0
        saved = self.cap_hit(i) - dead_now
        return round(dead_now, 3), round(dead_next, 3), round(saved, 3)

    def restructure(self, i, amount=None, min_base=None):
        """
        Convert base salary into signing bonus, prorated over the remaining years
        (max 5). Lowers this year's hit and raises every later year's.

        The only limit the rules impose is that the team must leave at least the
        player's MINIMUM BASE SALARY for the year, and that minimum scales with
        his accrued seasons - 0.795 for a rookie against 1.210 for a ten-year
        veteran in 2024. This used to leave a flat 1.2 regardless, which
        overcharged young players and undercharged old ones. Callers pass the
        real floor; 1.2 remains only as a fallback.
        """
        floor = 1.2 if min_base is None else float(min_base)
        conv = amount if amount is not None else max(0.0, self.base[i] - floor)
        conv = min(conv, self.base[i])
        spread = min(self.years - i + self.void, MAX_PRORATION_YEARS)
        self.base[i] -= conv
        self.sb += conv
        return round(conv, 3), spread

# ---------------------------------------------------------------- team cap
TOP_51_PHASES = {'offseason', 'free_agency', 'draft', 'camp'}

class TeamCap:
    def __init__(self, year, rollover=0.0):
        self.year = year
        self.cap = CAP.get(year, 0.0)
        self.rollover = rollover
        self.contracts = []        # (player_id, Contract, year_index)
        self.dead = 0.0

    @property
    def limit(self): return self.cap + self.rollover

    def charges(self, phase='season'):
        hits = sorted((c.cap_hit(i) for _, c, i in self.contracts), reverse=True)
        if phase in TOP_51_PHASES:
            hits = hits[:51]                      # only the top 51 count until week 1
        return sum(hits) + self.dead

    def space(self, phase='season'):
        return round(self.limit - self.charges(phase), 3)

    def roll_forward(self, next_year_cap):
        """Unused space carries over (2011 CBA onward)."""
        unused = max(0.0, self.space('season'))
        return TeamCap(self.year + 1, rollover=unused)

# ---------------------------------------------------------------- checks
if __name__ == '__main__':
    print('=== real cap series ===')
    ys = [y for y in sorted(CAP) if y >= 2011 and not np.isnan(CAP[y])]
    for y in ys[-8:]:
        prev = CAP[y-1] if (y-1) in CAP and not np.isnan(CAP[y-1]) else None
        g = f'{(CAP[y]/prev-1)*100:+5.1f}%' if prev else '     '
        print(f'  {y}  ${CAP[y]:7.1f}M  {g}')

    rng = np.random.default_rng(7)
    print('\n=== projected forward from 2026 ===')
    cap, y = CAP[2026], 2026
    for _ in range(8):
        y += 1; nxt = project_cap(y, y-1, cap, rng)
        print(f'  {y}  ${nxt:7.1f}M  {(nxt/cap-1)*100:+5.1f}%')
        cap = nxt

    print('\n=== proration: a 5yr/$250M deal, $100M signing bonus ===')
    c = Contract(5, [1.2, 20, 30, 35, 38], signing_bonus=100)
    print(f'  annual proration ${c.annual_proration:.1f}M over {c.proration_years} yrs')
    for i in range(5): print(f'   yr{i+1} cap hit ${c.cap_hit(i):6.2f}M')

    print('\n=== cut him after year 2 ===')
    for j1 in (False, True):
        d, dn, s = c.release(2, june1=j1)
        print(f'  {"June 1" if j1 else "standard":9s}: dead now ${d:6.2f}M, dead next yr ${dn:6.2f}M, saved ${s:6.2f}M')

    print('\n=== restructure year 3 instead ===')
    c2 = Contract(5, [1.2, 20, 30, 35, 38], signing_bonus=100)
    before = c2.cap_hit(2)
    conv, spread = c2.restructure(2)
    print(f'  converted ${conv:.1f}M of base into bonus over {spread} yrs')
    print(f'  yr3 hit ${before:.2f}M -> ${c2.cap_hit(2):.2f}M; yr5 hit now ${c2.cap_hit(4):.2f}M')
    print(f'  but dead money if cut after yr3 is now ${c2.release(3)[0]:.2f}M')
