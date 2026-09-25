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

CAP = 301.0

# ---------------------------------------------------------------- pick value
# BOTH CURVES ARE FROZEN. This module used to derive them at import, reading a
# draft-picks CSV and a numpy file solved from 316 trades, so it could not be
# imported at all without research artefacts sitting in the directory - the
# same fault that kept standings_and_seeding, the minimum scales and
# progression_engine uncallable.
#
# outcome: mean career approximate value by slot, 2000-2019 drafts, isotonic
#   so it never rises with a later pick. What a pick is actually WORTH.
# market:  a published chart built from real pick-for-pick trades. What clubs
#   actually PAY.
#
# Keeping both is the point. Pick 32 trades at 16.9% of pick 1 and returns
# 55.3% of it. That gap is the edge a smart front office exploits, and
# collapsing to one curve would delete the whole reason to have a trade model.
import json as _json
import os as _os
_PV = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                    'pick_values.json')))
PICK_AV = {int(k): v for k, v in _PV['outcome'].items()}
PICK_VALUE = {p: v / PICK_AV[1] for p, v in PICK_AV.items()}   # TRUE value
MARKET_VALUE = {int(k): v for k, v in _PV['market'].items()}   # what clubs pay
DRAFT = None                                                   # was the raw CSV


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
# Bust and star rates by round, from the same twenty drafts. A bust returns
# under 5 career approximate value, a star 40 or more. Frozen alongside the
# curves rather than recomputed from a CSV at import.
ROUND_ODDS = {int(k): v for k, v in _PV['round_odds'].items()}

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
    # the analytics view discounts the market, but no GM gives a pick for less than 80% of what it fetches:
    # the outcome chart is flat enough that an unbounded lens sold second-round picks for backups
    return max(lens * m + (1 - lens) * t, 0.80 * m) * (0.86 ** years_out)

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

# THE DOLLAR ANCHOR sits on the MIDDLE of the first round, not on pick 1.
# The market chart is steep (pick 32 trades at 17% of pick 1) while what
# picks return is flat (55%). Anchoring pick 1 to its ~11.5%-of-cap surplus
# priced a late first at $6m and a future first at $7m, and 21 of 43 deals in
# one window sent a first-round pick for a 74-to-80 on a rookie contract.
# Pick 16 is worth about 7.5% of the cap in surplus over its rookie deal
# (Massey-Thaler, Baldwin); anchoring there puts pick 1 at ~$80m, pick 32 at
# ~$14m, a second at ~$7m, which is what those picks actually buy.
PICK_DOLLAR_ANCHOR = 0.075 / MARKET_VALUE[16]

def pick_price_dollars(pick, years_out=0, cap=CAP):
    """The transaction price in $M, so picks and players compare on one scale."""
    return round(pick_price(pick, years_out) * PICK_DOLLAR_ANCHOR * cap, 2)

def pick_belief_dollars(pick, years_out=0, cap=CAP, lens=0.5):
    return round(pick_belief(pick, years_out, lens) * PICK_DOLLAR_ANCHOR * cap, 2)

def pick_value_dollars(pick, years_out=0, cap=CAP, lens='blend', blend=0.5):
    """Deprecated alias for the PRICE."""
    return pick_price_dollars(pick, years_out, cap)

# ---------------------------------------------------------------- player value
STAR_PREMIUM = 0.50     # share of a proven player's market salary his certainty is worth, per year, at the elite tier
# specialists do not fetch premium picks whatever their overall: kickers and
# punters go for late-round picks in the real market, full stop
POSITION_TRADE_MULT = {'K': 0.30, 'P': 0.30, 'LS': 0.20, 'FB': 0.60}


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

    # A PROVEN PLAYER IS WORTH MORE THAN HIS CAP SURPLUS. Surplus alone said a
    # 90 paid at market was worth nothing in a trade, so any first-round pick
    # ($6m to $9m of surplus) outbid nearly every player in the league and a
    # 36-year-old tackle fetched two of them. Real clubs pay firsts for stars
    # on full contracts (Hill, Adams, Ramsey) because a proven 90 cannot be
    # bought reliably in free agency at any price: certainty and scarcity
    # are worth a share of his salary on top. Nothing for a replacement-
    # level man, rising through the 80s to a full share for the elite.
    ovr = float(player.get('ovr', 75) or 75)
    tier = float(np.clip((ovr - 80.0) / 10.0, 0.0, 1.7))
    # certainty is what the premium buys, and a 36-year-old offers little of
    # it: Lane Johnson at 93 was worth 19 on this alone. Fades from 30.
    tier *= float(np.clip(1.0 - max(0.0, age - 30.0) * 0.12, 0.25, 1.0))
    # and a quarterback's certainty is worth more than a guard's: the same
    # positional table the draft board uses
    try:
        from draft import PREMIUM as _POSP
        tier *= float(_POSP.get(player.get('madden_position'), 1.0))
    except Exception:
        pass
    # THE SHORTFALL ON A MAX CONTRACT IS NOT A LIABILITY AT THE TOP. The
    # comps put Chase's market under the $38m he is paid, and surplus alone
    # priced a 97 at 27 like a second-round pick. Below 90 a bad deal still
    # costs you; from 90 up the shortfall is capped at a slice of his salary,
    # because to the club that wants him the contract is the price of having
    # him, not a debt.
    elite = float(np.clip((ovr - 88.0) / 4.0, 0.0, 1.0))
    floor = -worth * (0.35 * (1.0 - elite) + 0.08 * elite)
    total = 0.0
    for k in range(yrs):
        # The valuation already prices his CURRENT age (comps are age-matched),
        # so applying a decline in year 0 double-counts it. Decline only applies
        # to the years ahead, and gently.
        decline = 1.0 if k == 0 else float(np.clip(1.0 - max(0.0, age + k - 28) * 0.032, 0.45, 1.0))
        surplus = worth * decline - apy
        if elite > 0:
            surplus = max(surplus, floor)
        total += surplus * (0.90 ** k)                      # future years discounted
        total += STAR_PREMIUM * worth * decline * tier * (0.90 ** k)
    # SCARCITY. A backup's paper surplus (market minus salary over his years) is not what the league pays
    # for him: a 71 or a 75 is on the street for the minimum, so his surplus is worth a fraction until he is a
    # starter. Real compensation for depth is a sixth or a seventh (Kaleb Johnson for a 2028 sixth, Irvin Charles
    # for a conditional seventh, Mac Jones for a sixth); a starter fetches a fourth or fifth; a star a second or first.
    scarcity = float(np.clip((ovr - 72.0) / 12.0, 0.0, 1.0)) ** 1.5
    total *= scarcity
    total *= POSITION_TRADE_MULT.get(player.get('madden_position'), 1.0)
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
        v *= max(0.75, WINDOW_PICK_BIAS[wdw] * (1.25 - 0.45*g['aggression']))
        return v
    # the owner values him on the full contract he is paying; a buyer on the
    # base and roster bonus he would inherit, the bonus having been paid
    v = asset['trade_value'] if owns else asset.get('trade_value_buyer', asset['trade_value'])
    if asset['age'] >= 30: v *= WINDOW_AGE_BIAS[wdw]
    if asset['need']: v *= 1.18
    v *= g['own_bias'] if owns else g['target_bias']
    if owns and asset.get('star'):
        v *= float(asset.get('ask', 1.3))            # a starter is not for sale at his value
    if owns:
        # THE SELLER'S DEAD MONEY. Moving him accelerates what is left of his
        # bonus onto this year's cap. That is a real cost of the deal and it
        # goes into what the seller wants back: at par when he has the room,
        # above par as it eats into his space. So the other side pays more
        # to make it worth his while - or, past the point where it kills the
        # cap (see evaluate), he will not do it at any price.
        dead = float(asset.get('dead', 0.0) or 0.0)
        if dead > 0:
            squeeze = float(np.clip(dead / max(cap_space, 1.0), 0.0, 2.0))
            v += dead * (1.0 + 0.75 * squeeze)
    else:
        hit = float(asset.get('inherit', asset['apy']) or 0.0)
        if hit > cap_space: v -= (hit - cap_space) * 1.4
    return v


def cap_blocks(offer, space_a, space_b, gm_a=None, gm_b=None):
    """
    The two ways a trade dies before the assets are weighed. The seller's
    dead money would put him over the cap, or past the share of his room his
    contract_focus will stomach. Or the buyer cannot fit the inherited hits.
    Returns the reason, or None.
    """
    def tol(gm):
        if isinstance(gm, dict): f = float(gm.get('contract_focus', 0.5))
        else: f = float(getattr(gm, 'contract_focus', 0.5)) if gm is not None else 0.5
        return 0.9 - 0.5 * f                    # a cap hawk tolerates 40% of his room, a spender 90%
    # the cap block is about THIS year's books, so post-June 1 only this
    # year's proration counts against the room
    dead_a = sum(float(x.get('dead_now', x.get('dead', 0)) or 0) for x in offer['a_sends'] if x['kind'] == 'player')
    dead_b = sum(float(x.get('dead_now', x.get('dead', 0)) or 0) for x in offer['a_gets'] if x['kind'] == 'player')
    in_a = sum(float(x.get('inherit', 0) or 0) for x in offer['a_gets'] if x['kind'] == 'player')
    in_b = sum(float(x.get('inherit', 0) or 0) for x in offer['a_sends'] if x['kind'] == 'player')
    out_a = sum(float(x.get('inherit', 0) or 0) for x in offer['a_sends'] if x['kind'] == 'player')
    out_b = sum(float(x.get('inherit', 0) or 0) for x in offer['a_gets'] if x['kind'] == 'player')
    # after the deal: space + hits shed - hits taken on - dead eaten
    after_a = space_a + out_a - in_a - dead_a
    after_b = space_b + out_b - in_b - dead_b
    if dead_a > 0 and (after_a < 0 or dead_a > space_a * tol(gm_a)):
        return 'a_dead_money'
    if dead_b > 0 and (after_b < 0 or dead_b > space_b * tol(gm_b)):
        return 'b_dead_money'
    if after_a < 0: return 'a_cannot_fit'
    if after_b < 0: return 'b_cannot_fit'
    return None

def evaluate(offer, team_a, team_b, space_a, space_b, gm_a=None, gm_b=None):
    """
    A trade happens when BOTH clubs think they gained. Each prices through its own
    window, its own GM, and its own season, so a deal can be genuinely positive for
    both. That disagreement is the mechanism, not a rounding error.
    """
    block = cap_blocks(offer, space_a, space_b, gm_a, gm_b)
    if block:
        return dict(a_gain=-999.0, b_gain=-999.0, accepted=False, blocked=block)
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
