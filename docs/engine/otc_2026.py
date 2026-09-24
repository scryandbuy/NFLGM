"""
Real 2026 team cap positions.

WHY THIS FILE EXISTS: the league seed carries APY, total value, guarantees and
years, but no per-year cap hit and no signing bonus. Neither does nflverse's
contracts release - its `contract_history` column is a list of a player's PRIOR
deals, not a year-by-year breakdown. Over the Cap publishes the per-year
figures on its team pages but not as a dataset.

So the per-player cap hit has to be reconstructed. Reconstructing it from APY
alone put the average team 38m over the cap, because APY is not a cap hit: a
signing bonus prorates over up to five years and base salary is backloaded, so
a year-one hit sits well under the APY.

What IS knowable is the team total, and that is what this file holds. Each
team's contracts are then solved so its year-one spending lands on the real
number. The distribution across players is still a model; the aggregate is not.

TWO THINGS THIS FIXED THAT NOTHING ELSE WOULD HAVE:

1. DEAD MONEY. The build carried none, and it is enormous - Miami at 182.6m is
   roughly 60% of its entire cap, paid to men who are not on the roster. No
   amount of tuning contract structure reaches a Dolphins roster spending
   116.9m on active players without knowing why.

2. EVERY TEAM IS COMPLIANT. The tightest is the Rams at 3.27m. There is no
   real team starting the year over the cap, so a seed that produces 17 of
   them is wrong, not realistic.

Source: overthecap.com/salary-cap-space, 2026 base cap $301.2m. Cap space is
Team Cap minus Active Spending minus Dead Money, where Team Cap is the base
cap plus carryover, which is why several teams have more than 301.2 to spend.
"""

BASE_CAP_2026 = 301.200

# team: (cap_space, active_spending, dead_money, roster_count)
OTC_2026 = {
    'SF':  (44.107357, 255.491775,  40.963967, 84),
    'DET': (38.920104, 251.522038,  31.974429, 77),
    'ATL': (34.154888, 223.776477,  46.915283, 76),
    'TEN': (31.647648, 275.948467,  35.342268, 76),
    'LAC': (30.337981, 266.404756,   8.390693, 74),
    'WAS': (27.583561, 274.370017,  26.214788, 73),
    'IND': (21.908829, 261.473864,  19.681329, 75),
    'DAL': (21.694751, 264.246384,  45.411952, 77),
    'TB':  (16.277652, 284.223372,  16.194483, 74),
    'DEN': (16.059492, 281.033683,   6.424353, 77),
    'CLE': (15.136147, 204.111195, 119.200005, 76),
    'ARI': (14.539827, 231.355372,  81.614125, 77),
    'NYJ': (14.294089, 193.581900, 115.162439, 73),
    'SEA': (14.158492, 297.375369,   2.879912, 77),
    'PIT': (13.155737, 289.130401,  18.805421, 76),
    'NYG': (12.877569, 245.329374,  41.988391, 75),
    'PHI': (12.781197, 228.039766,  75.275672, 76),
    'GB':  (12.108344, 254.138224,  48.012896, 76),
    'CIN': (11.111041, 294.564752,  11.688726, 71),
    'NE':  ( 8.656231, 300.396803,  43.236061, 77),
    'MIA': ( 8.625355, 116.909861, 182.578662, 75),
    'LV':  ( 8.372246, 248.084722,  57.975117, 79),
    'CHI': ( 7.727192, 278.145447,  23.503895, 81),
    'NO':  ( 7.209249, 193.599375, 116.196842, 83),
    'MIN': ( 7.122095, 258.005837,  49.256797, 76),
    'HOU': ( 6.681442, 231.710816,  71.669810, 84),
    'JAX': ( 6.389295, 243.075911,  60.683262, 76),
    'CAR': ( 5.966061, 281.336816,  24.680837, 75),
    'BAL': ( 5.799084, 289.469601,  18.795290, 74),
    'BUF': ( 5.770063, 248.128646,  47.172892, 74),
    'KC':  ( 3.835759, 282.330844,  15.403480, 75),
    'LA':  ( 3.272112, 298.101293,  12.234425, 76),
}

# Future base caps, also from OTC. cap_engine projects beyond these.
FUTURE_CAP = {2027: 327.000, 2028: 352.000}

# The seed uses LA for the Rams; OTC's table is keyed the same way here.
ALIASES = {'LAR': 'LA', 'STL': 'LA', 'OAK': 'LV', 'SD': 'LAC', 'WSH': 'WAS'}


def team_cap(abbr):
    """(cap_space, active_spending, dead_money, roster_count) or None."""
    return OTC_2026.get(ALIASES.get(abbr, abbr))


def team_limit(abbr):
    """
    What this team may actually spend: base cap plus its carryover. Derived
    rather than stated, because OTC publishes space, spending and dead money
    but not the carryover itself - and the three pin it down exactly.
    """
    row = team_cap(abbr)
    if not row:
        return BASE_CAP_2026
    space, active, dead, _ = row
    return round(space + active + dead, 3)
