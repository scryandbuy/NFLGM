"""
Contract construction.

The negotiation engine settles WHAT a deal is worth - money, years, guarantee
share. This decides HOW it is laid out, which is a different question and the
one that creates the uncuttable trap two years later.

Everything here is derived from 46,208 real contracts signed 2015-2026, plus
the year-by-year cap accounting on deals worth $40M+.

What the data says:

  TIER            median APY   yrs   gtd share (p25-p75)
  minimum              0.59M    1     0%
  depth (1-2.5%)       3.00M    2     49%  (26-82)
  starter (2.5-5%)     7.00M    3     51%  (37-75)
  core (5-9%)         13.50M    3     46%  (34-63)
  elite (9%+)         24.01M    4     46%  (38-57)

Guarantee share does NOT rise with money - it sits near half at every tier and
the SPREAD narrows as deals get bigger. Length is the thing that scales.

  POSITION (deals >= 4% of cap)   yrs   gtd    median APY
  QB                               3    .54     22.50M
  WR                               3    .46     15.00M
  IDL                              3    .49     14.00M
  EDGE                             3    .51     14.00M
  OL                               4    .44     12.63M
  CB                               3    .49     12.25M
  LB                               4    .45     10.75M

Linemen and linebackers sign LONGER and are guaranteed LESS. Quarterbacks get
the highest guarantee share of any position.

  CASH FLOW on a big deal, by contract year:
    yr1 hit is a median 0.80x the deal average (p25 0.54, p75 1.08)
    base salary runs 1.38 / 3.00 / 4.50 / 2.74 / 2.25 / 2.00
    prorated bonus stays flat near 3.9 until the tail

So the classic shape is a suppressed first year, a peak in years two and three,
and a decline after - not a smooth ramp.
"""
import numpy as np

MAX_PRORATION_YEARS = 5
MIN_BASE = 1.2

# ---------------------------------------------------------------- derived tables
TIER_BOUNDS = [(0.010, 'min'), (0.025, 'depth'), (0.050, 'starter'),
               (0.090, 'core'), (1.00, 'elite')]
TIER_SHAPE = {   # median years, median guarantee share, IQR of guarantee share
    'min':     dict(years=1, gtd=0.00, gtd_lo=0.00, gtd_hi=0.00),
    'depth':   dict(years=2, gtd=0.49, gtd_lo=0.26, gtd_hi=0.82),
    'starter': dict(years=3, gtd=0.51, gtd_lo=0.37, gtd_hi=0.75),
    'core':    dict(years=3, gtd=0.46, gtd_lo=0.34, gtd_hi=0.63),
    'elite':   dict(years=4, gtd=0.46, gtd_lo=0.38, gtd_hi=0.57),
}
POS_SHAPE = {    # on deals >= 4% of cap
    'QB':   dict(years=3, gtd=0.543), 'WR': dict(years=3, gtd=0.458),
    'IDL':  dict(years=3, gtd=0.488), 'EDGE': dict(years=3, gtd=0.513),
    'OL':   dict(years=4, gtd=0.444), 'CB':  dict(years=3, gtd=0.485),
    'S':    dict(years=3, gtd=0.475), 'RB':  dict(years=3, gtd=0.505),
    'TE':   dict(years=3, gtd=0.458), 'LB':  dict(years=4, gtd=0.447),
}
POSMAP = {'QB':'QB','HB':'RB','FB':'RB','WR':'WR','TE':'TE','LT':'OL','RT':'OL',
          'LG':'OL','RG':'OL','C':'OL','LEDG':'EDGE','REDG':'EDGE','DT':'IDL',
          'MIKE':'LB','WILL':'LB','SAM':'LB','CB':'CB','FS':'S','SS':'S',
          'K':'ST','P':'ST','LS':'ST'}

# The observed cash-flow shape: suppressed year 1, peak in years 2-3, tail off.
BASE_CURVE = [0.32, 0.70, 1.05, 0.64, 0.52, 0.47]

def tier_of(apy, cap):
    pct = apy / max(cap, 1)
    for hi, name in TIER_BOUNDS:
        if pct < hi: return name
    return 'elite'

# ---------------------------------------------------------------- construction
def structure(apy, years, pos, cap, gm, void_years=0, front_load=None):
    """
    Lay out a deal. Returns per-year base, bonus proration and cap hit.

    A GM with high restructure_depth pushes money into signing bonus up front,
    which lowers year 1 and loads the dead money. A patient one keeps base
    salary high, which costs more now and leaves him free to walk away later.
    """
    g = gm
    total = apy * years
    t = tier_of(apy, cap)
    shape = TIER_SHAPE[t]
    pshape = POS_SHAPE.get(POSMAP.get(pos, 'LB'), dict(years=3, gtd=0.47))

    # Guaranteed money is cut from the game, so the tier and position
    # guarantee shares below are unused and kept only as a record of what the
    # real contracts looked like. How much goes into signing bonus is now a
    # question of the GM alone.
    bonus_share = float(np.clip(0.22 + 0.45 * g.restructure_depth, 0.05, 0.78))
    signing = total * bonus_share
    spread = min(years + void_years, MAX_PRORATION_YEARS)
    proration = signing / spread

    # base salary follows the observed shape, scaled so the money adds up
    fl = front_load if front_load is not None else (1.0 - g.restructure_depth)
    curve = np.array(BASE_CURVE[:years], float)
    if years > len(BASE_CURVE):
        curve = np.concatenate([curve, np.full(years - len(BASE_CURVE), BASE_CURVE[-1])])
    curve = curve * (1.0 + (fl - 0.5) * 0.5 * np.linspace(1, -1, years))
    base_total = total - signing
    base = np.maximum(MIN_BASE, curve / curve.sum() * base_total)

    hits, dead = [], []
    for i in range(years):
        p = proration if i < spread else 0.0
        hits.append(round(float(base[i] + p), 3))
        remaining = proration * max(0, spread - i)
        dead.append(round(float(remaining), 3))

    return dict(apy=round(apy, 3), years=years, total=round(total, 3),
                signing_bonus=round(signing, 3), proration=round(proration, 3),
                proration_years=spread,
                base=[round(float(b), 3) for b in base],
                cap_hits=hits, dead_if_cut=dead, tier=t,
                bonus_share=round(bonus_share, 3))

def suggested_years(pos, apy, cap, age, gm):
    """
    Length from the position and tier medians, capped by the age rules that are
    front-office orthodoxy: no five-year deals past 26, no four past 28.
    """
    t = tier_of(apy, cap)
    yrs = TIER_SHAPE[t]['years']
    # The position table was derived ONLY from deals worth >= 4% of the cap.
    # Applying it to a minimum-salary man gave him a three-year deal; in the
    # real data every minimum deal is one year.
    if apy / max(cap, 1) >= 0.04:
        yrs = max(yrs, POS_SHAPE.get(POSMAP.get(pos, 'LB'), {}).get('years', 3))
    yrs = int(round(yrs * (0.85 + 0.30 * gm.patience)))
    if age >= 28: yrs = min(yrs, 3)
    elif age >= 26: yrs = min(yrs, 4)
    return int(np.clip(yrs, 1, 6))

def trap_risk(deal):
    """
    Does this structure make him uncuttable later? A deal where dead money
    exceeds the cap hit in any year is one the club cannot escape, and the club
    built it itself.
    """
    years = [i for i, (h, d) in enumerate(zip(deal['cap_hits'], deal['dead_if_cut']))
             if d >= h]
    return dict(uncuttable_years=years, worst=max(deal['dead_if_cut']))
