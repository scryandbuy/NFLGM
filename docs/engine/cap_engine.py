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
 2026: 301.200,
}

# growth fitted to the real series (2011-2026, excluding the 2021 COVID reset)
BASE_GROWTH   = 0.075      # median year-over-year
GROWTH_SD     = 0.022
MIN_GROWTH    = 0.030      # the cap never goes down, and never stalls: the worst year is still +3%
MEDIA_CYCLE   = 8          # new broadcast deals land roughly this often
MEDIA_BUMP    = 0.055      # they add this on top (1998, 2006, 2022, 2024 pattern)

def project_cap(year, last_year, last_cap, rng=None, media_years=()):
    """Advance the cap one year. Real values are used wherever we have them. The cap only ever rises."""
    if year in CAP and not np.isnan(CAP[year]): return CAP[year]
    rng = rng or np.random.default_rng()
    g = max(MIN_GROWTH, float(rng.normal(BASE_GROWTH, GROWTH_SD)))
    if year in media_years or (year - 2024) % MEDIA_CYCLE == 0:
        g += MEDIA_BUMP
    return round(last_cap * (1 + g), 3)

# ---------------------------------------------------------------- contracts
MAX_PRORATION_YEARS = 5

class Contract:
    """Remaining salary plus fixed bonus allocations; no salary guarantees."""
    def __init__(self, years, base, signing_bonus=0.0, roster_bonus=None,
                 void_years=0, signed=2026, bonus_schedule=None,
                 earned_base=0.0, earned_roster=0.0, pay_start=0, start_offset=0, **_ignored):
        self.signed, self.years, self.void = signed, years, void_years
        self.base = list(base)
        self.rb = list(roster_bonus or [0.0]*years)
        # Legacy saves contain only the remaining balance. Preserve that balance
        # and today's allocation; unavailable historical tranches are not invented.
        n = max(1, min(years + void_years, MAX_PRORATION_YEARS))
        self.bonus_schedule = (list(bonus_schedule) if bonus_schedule is not None
                               else [float(signing_bonus)/n]*n)
        self.earned_base, self.earned_roster = earned_base, earned_roster
        self.pay_start = pay_start
        self.start_offset = start_offset

    @property
    def sb(self): return sum(self.bonus_schedule)

    @sb.setter
    def sb(self, value):
        # Seed scaling and transfer clearing preserve the existing allocation shape.
        old = self.sb
        if old: self.bonus_schedule = [x*float(value)/old for x in self.bonus_schedule]
        else:
            n=max(1,min(self.years+self.void,MAX_PRORATION_YEARS))
            self.bonus_schedule=[float(value)/n]*n

    @property
    def proration_years(self): return len(self.bonus_schedule)

    @property
    def annual_proration(self): return self.bonus_at(0)

    def bonus_at(self, i):
        return self.bonus_schedule[i] if 0 <= i < len(self.bonus_schedule) else 0.0

    def cap_hit(self, i):
        if i >= self.years: return 0.0
        return self.base[i] + self.rb[i] + self.bonus_at(i)

    def remaining_proration(self, i): return sum(self.bonus_schedule[max(0,i):])

    def add_bonus(self, amount, start=0):
        n=max(1,min(self.years-start+self.void,MAX_PRORATION_YEARS))
        self.bonus_schedule += [0.0]*max(0,start+n-len(self.bonus_schedule))
        for i in range(start,start+n): self.bonus_schedule[i] += amount/n
        return n

    def advance(self):
        if self.bonus_schedule: self.bonus_schedule.pop(0)
        self.years -= 1
        self.start_offset = max(0,self.start_offset-1)
        if self.base: self.base.pop(0)
        if self.rb: self.rb.pop(0)
        self.earned_base=self.earned_roster=0.0
        self.pay_start=0
        return self.years <= 0

    def release(self, i, june1=False):
        rest=self.remaining_proration(i)
        now=self.bonus_at(i) if june1 else rest
        nxt=max(0.0,rest-now)
        earned=(self.earned_base+self.earned_roster) if i==0 else 0.0
        return round(now,3),round(nxt,3),round(self.cap_hit(i)-now-earned,3)

    def restructure(self, i, amount=None, min_base=None):
        floor=1.2 if min_base is None else float(min_base)
        if i==0: floor=max(floor,self.earned_base)
        maximum=max(0.0,self.base[i]-floor)
        conv=maximum if amount is None else max(0.0,min(float(amount),maximum))
        self.base[i]-=conv
        spread=self.add_bonus(conv,i)
        return round(conv,3),spread

# ---------------------------------------------------------------- team cap
TOP_51_PHASES = {'offseason', 'free_agency', 'draft', 'camp'}

class TeamCap:
    def __init__(self, year, rollover=0.0):
        self.year = year
        self.cap = CAP.get(year, 0.0)
        self.rollover = rollover
        self.contracts = []        # (player_id, Contract, year_index)
        self.dead = 0.0
        self.earned = 0.0         # paid salary on departed contracts
        self.ps_earned = 0.0
        self.paid_week = 0
        self.dead_next = 0.0       # June 1 splits and retirements land here, for next year
        self.practice_squad = 0.0  # the squad's weekly pay for the season, while he is on it

    @property
    def limit(self): return self.cap + self.rollover

    def charges(self, phase='season'):
        rows = sorted(self.contracts, key=lambda row: row[1].cap_hit(row[2]), reverse=True)
        hits = sum(c.cap_hit(i) if phase not in TOP_51_PHASES or n < 51
                   else c.bonus_at(i) + c.rb[i] for n, (_, c, i) in enumerate(rows))
        return hits + self.dead + self.earned + self.practice_squad

    def space(self, phase='season'):
        return round(self.limit - self.charges(phase), 3)

    def roll_forward(self, next_year_cap):
        """Unused space carries over (2011 CBA onward), and so does the dead
        money already assigned to next year. This used to start the new
        ledger at zero dead, which erased every June 1 split and every
        retirement's acceleration."""
        unused = max(0.0, self.space('season'))
        nxt = TeamCap(self.year + 1, rollover=unused)
        nxt.dead = self.dead_next
        nxt.cap = next_year_cap
        return nxt

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
