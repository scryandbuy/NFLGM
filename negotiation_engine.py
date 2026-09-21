"""
Contract negotiation.

Both sides run the SAME valuation engine on DIFFERENT comp sets:
  agent  -> flatters (recent deals, peak production, rating-tier peers)
  team   -> discounts (wider window, career baseline, production-tier peers)
The gap between the two answers is the bargaining range. Nothing is a fixed
number; every figure resolves to real players on real contracts.

A player does not compare offers in dollars, he compares them in utility.
Weights are hidden and differ per player, so the same offer is accepted by one
man and rejected by another. Promises are non-cash currency: they buy a
discount now and create an obligation the sim can audit later.
"""
import numpy as np, pandas as pd

CAP = 301.0

# ---------------------------------------------------------------- preferences
# Hidden per-player weights. They sum to 1 and are drawn from archetypes so the
# league contains recognisably different personalities.
ARCHETYPES = {
    'max_money':      dict(total=.65, years=.06, winning=.10, role=.10, home=.05, tax=.04),
    'security':       dict(total=.32, years=.32, winning=.11, role=.16, home=.07, tax=.02),
    'ring_chaser':    dict(total=.26, years=.07, winning=.45, role=.16, home=.04, tax=.02),
    'wants_the_ball': dict(total=.31, years=.07, winning=.12, role=.45, home=.04, tax=.01),
    'homebody':       dict(total=.34, years=.10, winning=.12, role=.12, home=.30, tax=.02),
    'balanced':       dict(total=.42, years=.13, winning=.18, role=.19, home=.05, tax=.03),
}
# Guaranteed money is cut from the game, so the gtd weight each archetype
# carried is redistributed across what is left rather than simply dropped -
# the weights still sum to one, and a man who wanted security now expresses
# it through YEARS, which is the honest substitute.
ARCH_P = [0.20, 0.18, 0.14, 0.12, 0.10, 0.26]

# tax deliberately tiny: it breaks ties, it never decides a deal
NO_TAX_STATES = {'FL','TX','TN','WA','NV','NH'}
TEAM_STATE = {
 'MIA':'FL','TB':'FL','JAX':'FL','DAL':'TX','HOU':'TX','TEN':'TN','SEA':'WA','LV':'NV',
 'BUF':'NY','NYG':'NJ','NYJ':'NJ','NE':'MA','PIT':'PA','PHI':'PA','BAL':'MD','WAS':'MD',
 'CLE':'OH','CIN':'OH','IND':'IN','CHI':'IL','GB':'WI','MIN':'MN','DET':'MI','KC':'MO',
 'DEN':'CO','ARI':'AZ','LA':'CA','LAC':'CA','SF':'CA','NO':'LA','ATL':'GA','CAR':'NC',
}

def make_profile(player_row, rng):
    """Assign hidden weights. Age and career stage tilt the draw, as they do in life."""
    age = float(player_row.get('age', 27) or 27)
    p = list(ARCH_P)
    if age >= 30: p[1] += .10; p[2] += .06; p[0] -= .10; p[3] -= .06   # older: security, rings
    if age <= 24: p[0] += .08; p[1] -= .06                              # younger: chase the number
    p = np.clip(p, .01, None); p = np.array(p)/sum(p)
    name = rng.choice(list(ARCHETYPES), p=p)
    w = dict(ARCHETYPES[name])
    for k in w: w[k] = max(0.0, w[k] * rng.normal(1.0, 0.18))           # individual variation
    s = sum(w.values())
    return {'archetype': name, 'w': {k: v/s for k, v in w.items()},
            'trust': 1.0, 'broken': 0}

# ---------------------------------------------------------------- promises
# Only things the sim can objectively audit later.
PROMISES = {
    'starting_role':  dict(label='named the starter',        base=0.055),
    'captaincy':      dict(label='team captaincy',           base=0.030),
    'no_trade':       dict(label='no-trade commitment',      base=0.035),
    'extension_by':   dict(label='extension by a set year',  base=0.040),
    'no_franchise':   dict(label='will not franchise-tag him', base=0.030),
}

def promise_value(kind, player_row, prof, team_ctx):
    """
    What a promise is worth to THIS player, as a fraction of contract value.
    Scaled by his own weights and situation, never a flat number.
    """
    w, age = prof['w'], float(player_row.get('age', 27) or 27)
    base = PROMISES[kind]['base']
    if kind == 'starting_role':
        base *= (0.6 + 2.0*w['role'])
        if team_ctx.get('contested_at_position'): base *= 1.35
    elif kind == 'captaincy':
        base *= (0.5 + 1.3*w['role']) * (1.5 if age >= 30 else 0.8)
    elif kind == 'no_trade':
        base *= (0.5 + 2.2*w['home']) * (1.3 if age >= 29 else 1.0)
    elif kind == 'extension_by':
        base *= (0.6 + 1.8*w['years']) * (1.4 if age <= 26 else 0.8)
    elif kind == 'no_franchise':
        base *= (0.5 + 2.0*w['years'])
    return base * prof['trust']      # a player who has been lied to discounts your word

def promise_cost(kind, team_ctx):
    """
    What it costs the team in flexibility. These are deliberately expensive:
    a promise mortgages a future decision, and the first build had the AI
    handing out four of them rather than paying a dollar more.
    """
    if kind == 'starting_role':
        return 3.2 if team_ctx.get('contested_at_position') else 1.1
    if kind == 'captaincy':   return 2.0 if team_ctx.get('captain_slots_left', 1) <= 1 else 0.9
    if kind == 'no_trade':    return 2.6
    if kind == 'extension_by':return 2.4
    if kind == 'no_franchise':return 1.8
    return 2.0

MAX_PROMISES = 2       # a team that needs three is overpaying in the wrong currency

# ---------------------------------------------------------------- utility
def utility(offer, player_row, prof, team_ctx, market_apy):
    """One number the player uses to compare offers. Everything converts here."""
    w = prof['w']
    apy, yrs = offer['apy'], offer['years']
    age = float(player_row.get('age', 27) or 27)

    u  = w['total'] * (apy / max(market_apy, 0.1))
    # older players want years, younger ones want to get back to market
    want_long = 1.0 if age >= 29 else (0.35 if age >= 26 else 0.0)
    u += w['years'] * (1 - abs(yrs - (2 + 3*want_long)) / 4)
    u += w['winning'] * team_ctx.get('contender', 0.5)
    u += w['role']    * team_ctx.get('role_clarity', 0.5)
    u += w['home']    * team_ctx.get('home_fit', 0.0)
    u += w['tax']     * (1.0 if TEAM_STATE.get(team_ctx.get('team')) in NO_TAX_STATES else 0.0)

    for k in offer.get('promises', []):
        u += promise_value(k, player_row, prof, team_ctx)
    return float(u)

# ---------------------------------------------------------------- two-sided comps
def sided_value(row, pool, side, valuation_fn):
    """
    Same engine, different comp set.
      agent: recent deals only, comps skewed to his rating tier and best season
      team:  wider window, comps skewed to his production tier and career baseline
    """
    p = pool.copy()
    if side == 'agent':
        p = p[p.contract_age <= 2] if (p.contract_age <= 2).sum() >= 25 else p
        shifted = row.copy()
        shifted['prod_f'] = min(1.0, float(row.get('peak_prod', row.get('prod_f', .5))) + .05)
    else:
        shifted = row.copy()
        shifted['prod_f'] = max(0.0, float(row.get('career_prod', row.get('prod_f', .5))) - .05)
        shifted['age'] = float(row['age']) + 1.0      # team prices the decline it expects
    v = valuation_fn(shifted, pool=p)
    return v

# ---------------------------------------------------------------- the negotiation
def negotiate(row, pool, valuation_fn, team_ctx, prof, rng, max_rounds=10,
              allow_promises=('starting_role','captaincy','no_trade','extension_by','no_franchise')):
    ask  = sided_value(row, pool, 'agent', valuation_fn)
    off  = sided_value(row, pool, 'team',  valuation_fn)
    if ask is None or off is None: return None
    market = (ask['apy'] + off['apy']) / 2

    lev = team_ctx.get('leverage', 0.5)        # 0 = team holds all of it, 1 = player does
    player_pos = dict(apy=ask['apy_high'], years=ask['years'],
                      promises=[])
    team_pos   = dict(apy=off['apy_low'],  years=off['years'],
                      promises=[])

    # what he'd need from a neutral deal at market to say yes
    neutral = dict(apy=market, years=off['years'], promises=[])
    reserve = utility(neutral, row, prof, team_ctx, market) * (0.92 + 0.16*lev)

    log = []
    for rnd in range(1, max_rounds+1):
        u = utility(team_pos, row, prof, team_ctx, market)
        log.append(dict(round=rnd, team_apy=round(team_pos['apy'],2),
                        ask_apy=round(player_pos['apy'],2),
                        yrs=team_pos['years'],
                        promises=list(team_pos['promises']),
                        utility=round(u,3), reserve=round(reserve,3)))
        if u >= reserve:
            return dict(agreed=True, deal=team_pos, rounds=rnd, log=log,
                        ask=ask, opening=off, market=round(market,2))

        gap = reserve - u
        # cheapest way to close the gap: money, structure, or a promise
        options = []
        aggression = 0.26 + 0.30*lev + 0.22*team_ctx.get('want', 0.5)
        step = max(0.4, (player_pos['apy'] - team_pos['apy']) * aggression)
        cand = dict(team_pos); cand['apy'] = min(player_pos['apy'], team_pos['apy'] + step)
        options.append(('money', cand, (step / max(market,1)) * 0.55))
    
        cand = dict(team_pos); cand['years'] = int(np.clip(team_pos['years'] + rng.choice([-1,1]), 1, 6))
        options.append(('years', cand, 0.05))
        # promises are a closer, not an opener: only once real money is on the table
        money_moved = team_pos['apy'] > off['apy_low'] * 1.12
        if money_moved and len(team_pos['promises']) < MAX_PROMISES:
            for k in allow_promises:
                if k in team_pos['promises']: continue
                cand = dict(team_pos); cand['promises'] = team_pos['promises'] + [k]
                options.append((f'promise:{k}', cand, promise_cost(k, team_ctx) * 0.09))

        best = None
        for name, cand, cost in options:
            du = utility(cand, row, prof, team_ctx, market) - u
            if du <= 0: continue
            eff = du / max(cost, 1e-6)
            if best is None or eff > best[0]: best = (eff, name, cand, du)
        if best is None: break
        _, name, cand, du = best
        team_pos = cand
        log[-1]['team_move'] = name
        # the agent comes down too, faster when the player has less leverage
        player_pos['apy'] = max(team_pos['apy'],
                                player_pos['apy'] - (player_pos['apy'] - team_pos['apy']) * (0.34 - 0.18*lev))

    return dict(agreed=False, deal=team_pos, rounds=max_rounds, log=log,
                ask=ask, opening=off, market=round(market,2))

# ---------------------------------------------------------------- demo
if __name__ == '__main__':
    import valuation as V
    rng = np.random.default_rng(11)
    UNI = V.UNI.copy()
    UNI['contract_age'] = (2026 - UNI.signed).clip(0, 10).fillna(0)

    def valfn(row, pool=UNI):
        return V.value(row, cap=CAP, pool=pool)

    CONTEXTS = {
      'contender, clear role':   dict(team='KC',  contender=.90, role_clarity=.90, home_fit=.0, leverage=.55, want=.70, contested_at_position=False, captain_slots_left=2),
      'rebuild, overpaying':     dict(team='CAR', contender=.15, role_clarity=.85, home_fit=.0, leverage=.75, want=.95, contested_at_position=False, captain_slots_left=3),
      'contender, crowded room': dict(team='PHI', contender=.85, role_clarity=.30, home_fit=.0, leverage=.30, want=.35, contested_at_position=True,  captain_slots_left=1),
    }

    for name in ['Rashee Rice','Cameron Heyward','Najee Harris']:
        row = UNI[UNI.full_name == name]
        if not len(row): continue
        row = row.iloc[0]
        prof = make_profile(row, rng)
        print(f'\n{"="*74}\n{name}  {row.madden_position}  ovr {row.ovr:.0f}  age {row.age:.0f}'
              f'   [hidden: {prof["archetype"]}]')
        for cname, ctx in CONTEXTS.items():
            r = negotiate(row, UNI, valfn, ctx, prof, rng)
            if not r: continue
            d = r['deal']
            status = 'AGREED' if r['agreed'] else 'NO DEAL'
            pr = ', '.join(PROMISES[p]['label'] for p in d['promises']) or 'none'
            print(f'  {cname:26s} {status:8s} ${d["apy"]:6.2f}M x{d["years"]}yr '
                  f'in {r["rounds"]} rounds')
            print(f'      agent opened ${r["ask"]["apy_high"]:.1f}M, team opened ${r["opening"]["apy_low"]:.1f}M, '
                  f'market ${r["market"]:.1f}M | promises: {pr}')
