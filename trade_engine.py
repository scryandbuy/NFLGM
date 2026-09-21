"""
Trades.

Draft pick value is DERIVED, not the Jimmy Johnson chart (which is folklore from
1990 and was never fitted to anything). It comes from dr_av: the Approximate
Value a pick actually delivered while his drafting team still controlled him,
across 20 drafts, smoothed into a monotonic curve.

Player trade value is surplus value, not rating: what he is worth minus what he
costs, adjusted for contract length, age and the dead money the selling team eats.
"""
import numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression

CAP = 301.0

# ---------------------------------------------------------------- pick value
def build_pick_curve():
    d = pd.read_csv('draft_picks.csv', low_memory=False)
    d = d[(d.season.between(2000, 2019)) & (d.pick.between(1, 262))].copy()
    d['dr_av'] = pd.to_numeric(d.dr_av, errors='coerce').fillna(0)
    g = d.groupby('pick').dr_av.mean()
    x = g.index.values.astype(float)
    iso = IsotonicRegression(increasing=False, out_of_bounds='clip').fit(x, g.values)
    sm = iso.predict(np.arange(1, 263).astype(float))
    sm = np.maximum(sm, 0.4)
    return {p: float(v) for p, v in zip(range(1, 263), sm)}, d

PICK_AV, DRAFT = build_pick_curve()
PICK_VALUE = {p: v / PICK_AV[1] for p, v in PICK_AV.items()}      # TRUE value, from outcomes

# MARKET value: what clubs actually pay, solved from 316 pure pick-for-pick trades
# 2016-2026. Far steeper than the outcome curve: pick 32 trades at 13.5% of pick 1
# but returns 55%. That gap is the edge a smart front office exploits, so we keep
# BOTH curves rather than picking one.
MARKET_VALUE = {p: float(v) for p, v in
                zip(range(1, 263), np.load('market_pick_values.npy'))}

# The two charts must share a scale or the comparison is meaningless. Anchoring
# both at "pick 1 = 1.0" made every other pick look underpriced to an analytics
# GM, which is a normalisation artifact, not an edge. Normalise so the TOTAL
# value of a whole draft is identical under both. Then the difference is purely
# about SHAPE - where the market overpays and where it underpays.
_tot_true = sum(PICK_VALUE.values())
_tot_mkt = sum(MARKET_VALUE.values())
MARKET_VALUE = {p: v * (_tot_true / _tot_mkt) for p, v in MARKET_VALUE.items()}

# where a traded FUTURE pick actually lands, from the real data. A "future 1st"
# is not pick 16; it skews late, because the clubs willing to trade one are decent.
FUTURE_SLOT = {1: 18, 2: 53, 3: 86, 4: 123, 5: 155, 6: 188, 7: 220}

# hit rates by round, straight from the data. the AI needs these to know that a
# 6th-rounder is mostly a lottery ticket.
DRAFT['bust'] = DRAFT.dr_av < 5
DRAFT['star'] = DRAFT.dr_av >= 40
ROUND_ODDS = DRAFT.groupby('round')[['bust','star']].mean().to_dict('index')

# PRICE AND BELIEF ARE DIFFERENT OBJECTS.
#
# The PRICE of a pick is what the other 31 clubs will pay for it. Full stop.
# That is MARKET_VALUE, solved from 316 real pick-for-pick trades. A GM with a
# clever opinion does not get a discount - the counterparty is not selling at
# what the pick will eventually be worth, he is selling at today's market.
#
# PICK_VALUE (what picks actually return) is not a price at all. It is a BELIEF
# about whether the market price is right. It decides whether a GM LIKES a deal,
# never what the deal costs.
#
# An earlier build blended the two into one number, which let an analytics GM
# acquire picks more cheaply than a traditional one. He cannot. He pays the same
# and simply feels differently about it.

def pick_price(pick, years_out=0):
    """What this pick COSTS in a trade. Market, always. No GM opinion."""
    p = int(np.clip(pick, 1, 262))
    return MARKET_VALUE.get(p, .01) * (0.86 ** years_out)

def pick_belief(pick, years_out=0, lens=0.5):
    """
    What this GM thinks the pick is actually WORTH.
    lens 0 = prices it at true outcome value (analytics)
    lens 1 = agrees with the market (traditional)
    """
    p = int(np.clip(pick, 1, 262))
    t, m = PICK_VALUE.get(p, .01), MARKET_VALUE.get(p, .01)
    return (lens * m + (1 - lens) * t) * (0.86 ** years_out)

def pick_edge(pick, years_out=0, lens=0.5):
    """
    Belief minus price. Positive means this GM thinks the pick is underpriced
    and he should be buying it; negative means the market overpays and he
    should be selling. With the outcome chart flat at the top and the market
    steep, a low-lens GM is a persistent seller of early picks and buyer of
    middle ones - which is exactly what the trade-down research describes.
    """
    return pick_belief(pick, years_out, lens) - pick_price(pick, years_out)

def pick_value(pick, years_out=0, lens='blend', blend=0.5):
    """Deprecated. Kept so old callers do not silently break."""
    return pick_price(pick, years_out)

def future_pick(round_, years_out=1):
    """A future pick with no known slot: price it where such picks really land."""
    return FUTURE_SLOT.get(int(round_), 220), years_out

PICK_DOLLAR_ANCHOR = 0.115 / max(MARKET_VALUE.values())   # scales pick 1 to ~11.5% of cap

def pick_price_dollars(pick, years_out=0, cap=CAP):
    """The transaction price in $M, so picks and players compare on one scale."""
    return round(pick_price(pick, years_out) * PICK_DOLLAR_ANCHOR * cap, 2)

def pick_belief_dollars(pick, years_out=0, cap=CAP, lens=0.5):
    return round(pick_belief(pick, years_out, lens) * PICK_DOLLAR_ANCHOR * cap, 2)

def pick_value_dollars(pick, years_out=0, cap=CAP, lens='blend', blend=0.5):
    """Deprecated alias for the PRICE."""
    return pick_price_dollars(pick, years_out, cap)

# ---------------------------------------------------------------- player value
def trade_value(player, val, cap=CAP, contract=None):
    """
    What a player is worth in a trade = surplus (value minus cost) over the years
    you control him, discounted, minus whatever the acquiring club inherits.
    A great player on a terrible contract has negative trade value.
    """
    yrs = int(np.clip(player.get('contract_years_left', 1) or 1, 0, 6))
    if yrs == 0: yrs = 1                                   # expiring: one year of him
    age = float(player.get('age', 27) or 27)
    apy = float(player.get('apy', 0) or 0)
    worth = float(val['apy'])

    total = 0.0
    for k in range(yrs):
        # The valuation already prices his CURRENT age (comps are age-matched),
        # so applying a decline in year 0 double-counts it. Decline only applies
        # to the years ahead, and gently.
        decline = 1.0 if k == 0 else float(np.clip(1.0 - max(0.0, age + k - 28) * 0.032, 0.45, 1.0))
        total += (worth * decline - apy) * (0.90 ** k)      # future years discounted
    return round(total, 2)

def dead_money_on_trade(contract, year_index):
    """Selling club eats the remaining prorated bonus. That is the real cost of moving him."""
    if contract is None: return 0.0
    return round(contract.remaining_proration(year_index), 2)

# ---------------------------------------------------------------- GM personality
# Nobody prices assets identically, and if they did no trade would ever happen:
# a deal requires both sides to believe they gained. These are the axes GMs
# actually differ on, drawn per club and stable across seasons.
GM_ARCHETYPES = {
    # pick_lens: 0 = prices picks at true value (analytics), 1 = at market (traditional)
    'analytics':    dict(pick_lens=.12, aggression=.35, own_bias=1.02, target_bias=1.03, patience=.85),
    'traditional':  dict(pick_lens=.88, aggression=.55, own_bias=1.12, target_bias=1.10, patience=.55),
    'gunslinger':   dict(pick_lens=.72, aggression=.92, own_bias=1.05, target_bias=1.28, patience=.20),
    'hoarder':      dict(pick_lens=.45, aggression=.18, own_bias=1.22, target_bias=0.94, patience=.95),
    'win_now':      dict(pick_lens=.80, aggression=.85, own_bias=1.08, target_bias=1.20, patience=.25),
    'balanced':     dict(pick_lens=.50, aggression=.50, own_bias=1.08, target_bias=1.06, patience=.60),
}

def make_gm(rng, name=None):
    k = name or rng.choice(list(GM_ARCHETYPES))
    g = {a: float(np.clip(v * rng.normal(1.0, .12), 0.01, 2.0))
         for a, v in GM_ARCHETYPES[k].items()}
    g['pick_lens'] = float(np.clip(g['pick_lens'], 0, 1))
    g['archetype'] = k
    return g

def situational_shift(gm, team):
    """
    A GM is not a fixed personality. The same man values picks differently in a
    4-13 season than in a 12-5 one. This is what makes a star available in a lost
    year that would never have been on the market in a good one.
    """
    g = dict(gm)
    w = team['win_pct']
    if w <= .35:                      # season is gone: stock up, sell veterans
        g['pick_lens'] = max(0.0, g['pick_lens'] - .18)   # values picks nearer TRUE value
        g['aggression'] = max(0.0, g['aggression'] - .30)
        g['own_bias']   = max(0.90, g['own_bias'] - .16)  # less attached to his own men
    elif w >= .65:                    # window is open: chase it
        g['pick_lens'] = min(1.0, g['pick_lens'] + .14)   # discounts picks toward market
        g['aggression'] = min(1.0, g['aggression'] + .28)
        g['target_bias'] = g['target_bias'] * 1.12        # overpays for the man he wants
    return g

# ---------------------------------------------------------------- AI willingness
def window(team):
    """contending / retooling / rebuilding, from record and roster age."""
    w = team['win_pct']; age = team['avg_age']
    if w >= .60 and age <= 28.5: return 'contending'
    if w >= .60:                 return 'win_now'
    if w <= .40 and age >= 28.0: return 'rebuilding'
    if w <= .40:                 return 'retooling'
    return 'middling'

# how each type of club prices a future pick versus a player who helps today
WINDOW_PICK_BIAS = {'contending': .70, 'win_now': .55, 'middling': 1.00,
                    'retooling': 1.25, 'rebuilding': 1.45}
# a club chasing a title pays UP for a 31-year-old; a rebuild discounts him hard
WINDOW_AGE_BIAS  = {'contending': 1.18, 'win_now': 1.35, 'middling': 1.00,
                    'retooling': 0.78, 'rebuilding': 0.58}   # applied to players 30+

def team_price(asset, team, cap_space, gm=None, owns=False):
    """
    What THIS club, run by THIS man, in THIS season, thinks the asset is worth.
    owns=True means it is currently his player, which he overrates.
    """
    wdw = window(team)
    g = situational_shift(gm, team) if gm else dict(pick_lens=.5, aggression=.5,
                                                    own_bias=1.08, target_bias=1.06, patience=.6)
    if asset['kind'] == 'pick':
        # He PAYS the market price; what he thinks it is worth is separate and
        # only decides whether he wants the deal.
        v = pick_belief_dollars(asset['pick'], asset.get('years_out', 0),
                                lens=g['pick_lens'])
        v *= WINDOW_PICK_BIAS[wdw] * (1.25 - 0.45*g['aggression'])
        return v
    v = asset['trade_value']
    if asset['age'] >= 30: v *= WINDOW_AGE_BIAS[wdw]
    if asset['need']: v *= 1.18
    v *= g['own_bias'] if owns else g['target_bias']
    if asset['apy'] > cap_space: v -= (asset['apy'] - cap_space) * 1.4
    return v

def evaluate(offer, team_a, team_b, space_a, space_b, gm_a=None, gm_b=None):
    """
    A trade happens when BOTH clubs think they gained. Each prices through its own
    window, its own GM, and its own season, so a deal can be genuinely positive for
    both. That disagreement is the mechanism, not a rounding error.
    """
    a_out = sum(team_price(x, team_a, space_a, gm_a, owns=True)  for x in offer['a_sends'])
    a_in  = sum(team_price(x, team_a, space_a, gm_a, owns=False) for x in offer['a_gets'])
    b_out = sum(team_price(x, team_b, space_b, gm_b, owns=True)  for x in offer['a_gets'])
    b_in  = sum(team_price(x, team_b, space_b, gm_b, owns=False) for x in offer['a_sends'])
    return dict(a_gain=round(a_in - a_out, 2), b_gain=round(b_in - b_out, 2),
                accepted=(a_in - a_out) > 0.5 and (b_in - b_out) > 0.5)

# ---------------------------------------------------------------- demo
if __name__ == '__main__':
    print('=== DRAFT PICK VALUE, derived from 20 drafts of real outcomes ===')
    print(f'  {"pick":>5s} {"AV on rookie deal":>18s} {"share of #1":>12s} {"$M":>8s}')
    for p in [1, 5, 10, 16, 32, 48, 64, 96, 128, 160, 200, 256]:
        print(f'  {p:5d} {PICK_AV[p]:18.1f} {PICK_VALUE[p]*100:11.1f}% {pick_value_dollars(p):7.2f}')

    print('\n=== HIT RATES BY ROUND (why late picks are lottery tickets) ===')
    for r in sorted(ROUND_ODDS):
        o = ROUND_ODDS[r]
        print(f'  round {int(r)}: bust {o["bust"]*100:4.1f}%   star {o["star"]*100:4.1f}%')

    print('\n=== FUTURE PICKS ARE WORTH LESS ===')
    for yo in [0, 1, 2]:
        print(f'  a 1st next+{yo}: ${pick_value_dollars(16, yo):.2f}M   '
              f'a 3rd next+{yo}: ${pick_value_dollars(80, yo):.2f}M')

    import valuation as V
    UNI = V.UNI.copy()
    print('\n=== PLAYER TRADE VALUE (surplus, not rating) ===')
    print(f'  {"player":<20s} {"pos":5s} {"ovr":>4s} {"age":>4s} {"apy":>7s} {"valued":>7s} {"yrs":>4s} {"trade value":>12s}')
    for name in ['Caleb Williams','Puka Nacua','Myles Garrett','Deshaun Watson',
                 'Cameron Heyward','Brandon Aiyuk','Najee Harris']:
        r = UNI[UNI.full_name == name]
        if not len(r): continue
        r = r.iloc[0]
        val = V.value(r, cap=CAP, pool=UNI)
        tv = trade_value(r, val)
        print(f'  {name:<20s} {r.madden_position:5s} {r.ovr:4.0f} {r.age:4.0f} '
              f'{r.apy:7.2f} {val["apy"]:7.2f} {int(r.contract_years_left or 1):4d} {tv:12.2f}')

    print('\n=== THE SAME TRADE, SEEN BY DIFFERENT CLUBS ===')
    contender  = dict(win_pct=.72, avg_age=27.8)
    rebuilding = dict(win_pct=.25, avg_age=29.4)
    vet = dict(kind='player', trade_value=14.0, age=31, apy=14.0, need=True)
    p2  = dict(kind='pick', pick=48, years_out=0)
    print(f'  a 31-year-old vet worth $14.0M surplus who fills a hole, for pick 48:')
    for nm, t in [('contender', contender), ('rebuilding club', rebuilding)]:
        print(f'    {nm:16s} window={window(t):11s} values the vet at '
              f'${team_price(vet, t, 30):5.2f}M, the pick at ${team_price(p2, t, 30):5.2f}M')
    res = evaluate(dict(a_sends=[vet], a_gets=[p2]), rebuilding, contender, 30, 12)
    print(f'    rebuilding club sends the vet, gets the pick -> '
          f'seller gain ${res["a_gain"]:.2f}M, buyer gain ${res["b_gain"]:.2f}M  '
          f'-> {"ACCEPTED" if res["accepted"] else "no deal"}')
    res2 = evaluate(dict(a_sends=[vet], a_gets=[p2]), contender, rebuilding, 12, 30)
    print(f'    contender sends the vet to a rebuild instead -> '
          f'{"ACCEPTED" if res2["accepted"] else "no deal"}  (nobody gains; correct)')


# ---------------------------------------------------------------- pick trades
def trade_up_appetite(gm, team, target_pick, from_pick, ctx=None):
    """
    Moving up is a RIGHT-TAIL BET, not simply a mistake. Blind raters judged the
    trade-down side the winner in 19 of 29 same-year 2021 pick trades (83% once
    neutrals are excluded), and top-5 picks identify the best eventual career
    only 10.3% of the time. But across 2011-2023 clubs collectively paid about
    the right price, because when a trade-up hits it hits big enough to cover
    the misses.
    So: a GM who believes the market is wrong sells; one chasing a specific man
    buys, and must pay a PREMIUM over chart value to make the other side move.
    """
    ctx = ctx or {}
    g = gm.shift(team)
    # gm.shift returns a GM object, not a dict - read attributes, not keys
    lens, aggr, sec = g.pick_lens, g.aggression, g.job_security
    cost = pick_price_dollars(target_pick) - pick_price_dollars(from_pick)
    edge = (pick_belief_dollars(target_pick, lens=lens)
            - pick_belief_dollars(from_pick, lens=lens))
    # the premium the team moving DOWN requires for giving up its own target
    premium = cost * (0.08 + 0.12 * (1 - target_pick / 262))
    appetite = (edge - cost - premium)
    appetite += ctx.get('target_conviction', 0.0) * 12.0 * aggr
    if sec < 0.35: appetite += 6.0                    # cannot wait for next year
    return round(float(appetite), 2)

def trade_down_appetite(gm, team, from_pick, to_pick, extra_picks=()):
    """The mirror. A low-lens GM should be a persistent net seller at the top."""
    g = gm.shift(team)
    lens, aggr = g.pick_lens, g.aggression
    gained = pick_price_dollars(to_pick) + sum(pick_price_dollars(p) for p in extra_picks)
    given = pick_price_dollars(from_pick)
    belief_gained = (pick_belief_dollars(to_pick, lens=lens)
                     + sum(pick_belief_dollars(p, lens=lens) for p in extra_picks))
    belief_given = pick_belief_dollars(from_pick, lens=lens)
    return round(float((belief_gained - belief_given) + (gained - given) * 0.25
                       - aggr * 4.0), 2)
