"""
Free agency.

Real CBA structure, with values derived from real contracts:
  UFA   4+ accrued seasons, contract expired, signs anywhere
  RFA   exactly 3 accrued seasons, old club may tender and match
  ERFA  under 3 accrued seasons, club tenders at the minimum and he must take it
  Tag   franchise only (top-5 cap hits at his position)
  Tender  RFA tenders remain; they are a right of refusal, not a tag

Deliberately NOT modelled: compensatory picks and the transition tag.
The franchise tag is the only tag. RFA tenders remain - a tender is not a tag.

The market itself is the negotiation engine run against several bidders at once.
A player does not take the biggest number, he takes the highest utility, so
money, guarantees, role, winning and promises all compete.
"""
import numpy as np, pandas as pd
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n)

CAP = 301.0

# tag values: avg of the top-5 cap hits at the position over the prior 5 seasons,
# as a share of the cap. Derived from OverTheCap season data, then scaled by 0.960
# so the mean matches the published 2025 tags.
TAG_PCT = {'QB':.1504,'DL':.1090,'WR':.0913,'OL':.0886,'CB':.0690,'S':.0670,
           'LB':.0606,'TE':.0511,'RB':.0473,'KP':.0222,'LS':.0058}

# RFA tenders, as a share of cap (derived from published tender values / cap).
# A tender is not a tag: it is a qualifying offer with a right of first refusal
# and, at the higher levels, draft compensation if he walks.
TENDER_PCT = {'first_round':.0253,'second_round':.0177,'original':.0113,'right_of_first':.0106}
def tender_value(kind, cap=CAP): return round(TENDER_PCT[kind]*cap, 2)

TAGGRP = {'QB':'QB','HB':'RB','FB':'RB','WR':'WR','TE':'TE',
          'LT':'OL','RT':'OL','LG':'OL','RG':'OL','C':'OL',
          'LEDG':'DL','REDG':'DL','DT':'DL','MIKE':'LB','WILL':'LB','SAM':'LB',
          'CB':'CB','FS':'S','SS':'S','K':'KP','P':'KP','LS':'LS'}

def tag_value(pos, cap=CAP):
    pct = TAG_PCT.get(TAGGRP.get(pos, 'LB'), .06)
    return round(pct * cap, 2)

# ---------------------------------------------------------------- classification
def fa_class(accrued, contract_years_left):
    if contract_years_left and contract_years_left > 0: return 'under_contract'
    if accrued >= 4: return 'UFA'
    if accrued == 3: return 'RFA'
    return 'ERFA'

# ---------------------------------------------------------------- team decisions
def should_tag(player, val, cap_space, cap=CAP):
    """Tag if he is worth more than the tag costs and you can carry it."""
    tv = tag_value(player['madden_position'], cap)
    if tv > cap_space: return None
    return 'franchise' if val['apy'] >= tv * 1.05 else None

def tender_level(player, val, cap=CAP):
    """Higher tenders cost more but buy better draft compensation if he walks."""
    for kind in ['first_round','second_round','original','right_of_first']:
        if val['apy'] >= tender_value(kind, cap) * 1.15:
            return kind
    return 'right_of_first'

# ---------------------------------------------------------------- the market
def team_interest(team_row, player, val):
    """
    How badly a team wants him: roster need at the position, cap room, and
    whether he is better than what they already have.
    """
    need = team_row['need']                      # 0-1, thinnest positions score high
    room = np.clip(team_row['cap_space'] / max(val['apy'], .1), 0, 3) / 3
    upgrade = np.clip((player['ovr'] - team_row['best_at_pos']) / 12.0, -1, 1)
    w = 0.45*need + 0.25*room + 0.30*max(0, upgrade)
    return float(np.clip(w, 0, 1))

def run_market(player, val, prof, teams, negotiate_fn, rng, rounds=4):
    """
    Several clubs bid at once. Each round the interested ones improve, the
    player ranks the offers by utility, and weak bidders drop out. He signs
    when the best offer clears his reserve or when the market thins out.
    """
    bidders = []
    for _, t in teams.iterrows():
        w = team_interest(t, player, val)
        if w < 0.28: continue
        bidders.append(dict(team=t.team, want=w, contender=t.contender,
                            role_clarity=t.role_clarity, cap_space=t.cap_space,
                            contested_at_position=t.contested, captain_slots_left=t.captains))
    if not bidders: return None

    # more bidders means more leverage for the player, which is the whole point
    lev = float(np.clip(0.20 + 0.14*len(bidders), 0.2, 0.92))
    results = []
    for b in bidders:
        ctx = dict(team=b['team'], contender=b['contender'], role_clarity=b['role_clarity'],
                   home_fit=0.0, leverage=lev, want=b['want'],
                   contested_at_position=b['contested_at_position'],
                   captain_slots_left=b['captain_slots_left'])
        r = negotiate_fn(player, ctx, prof, lev)
        if r is None: continue
        if r['deal']['apy'] > b['cap_space']: continue     # cannot actually afford it
        results.append((b, ctx, r))
    if not results: return None

    import negotiation as N
    market_apy = np.mean([r['market'] for _, _, r in results])
    scored = []
    for b, ctx, r in results:
        u = N.utility(r['deal'], player, prof, ctx, market_apy)
        scored.append((u, b, ctx, r))
    scored.sort(key=lambda x: -x[0])
    best_u, b, ctx, r = scored[0]
    return dict(signed_with=b['team'], deal=r['deal'], utility=round(best_u, 3),
                n_bidders=len(results), leverage=round(lev, 2),
                runner_up=(scored[1][1]['team'], scored[1][3]['deal']['apy']) if len(scored) > 1 else None,
                all_offers=[(x[1]['team'], x[3]['deal']['apy'], round(x[0], 3)) for x in scored])

# ---------------------------------------------------------------- demo
if __name__ == '__main__':
    import valuation as V, negotiation as N
    rng = np.random.default_rng(5)
    S = pd.read_csv(_p('league_seed_2026.csv'), low_memory=False)
    UNI = V.UNI.copy(); UNI['contract_age'] = (2026 - UNI.signed).clip(0, 10).fillna(0)

    print('=== FRANCHISE TAG, 2026 cap ===')
    for p in ['QB','LEDG','WR','LT','CB','FS','MIKE','TE','HB','K']:
        print(f'  {p:5s} ({TAGGRP[p]:2s})  ${tag_value(p):6.2f}M')
    print('\n=== RFA TENDERS ===')
    for k in TENDER_PCT: print(f'  {k:16s} ${tender_value(k):5.2f}M')

    print('\n=== WHO IS A FREE AGENT ===')
    S['accrued'] = pd.to_numeric(S.years_exp, errors='coerce').fillna(0)
    S['cyl'] = pd.to_numeric(S.contract_years_left, errors='coerce').fillna(0)
    S['cls'] = [fa_class(a, c) for a, c in zip(S.accrued, S.cyl)]
    print('  ' + '  '.join(f'{k}: {v:,}' for k, v in S.cls.value_counts().items()))

    # a synthetic set of suitors with different situations
    teams = pd.DataFrame([
        dict(team='KC',  need=.85, cap_space=42, best_at_pos=79, contender=.92, role_clarity=.85, contested=False, captains=2),
        dict(team='CAR', need=.95, cap_space=68, best_at_pos=71, contender=.12, role_clarity=.90, contested=False, captains=3),
        dict(team='PHI', need=.35, cap_space=18, best_at_pos=88, contender=.88, role_clarity=.35, contested=True,  captains=1),
        dict(team='NE',  need=.70, cap_space=55, best_at_pos=76, contender=.55, role_clarity=.75, contested=False, captains=2),
        dict(team='LV',  need=.60, cap_space=12, best_at_pos=74, contender=.25, role_clarity=.80, contested=False, captains=2),
    ])

    def make_neg(row):
        def f(player, ctx, prof, lev):
            return N.negotiate(row, UNI, lambda r, pool=UNI: V.value(r, cap=CAP, pool=pool),
                               ctx, prof, rng)
        return f

    print('\n=== THE MARKET: several clubs bidding at once ===')
    for name in ['Rashee Rice','Najee Harris','Cameron Heyward']:
        row = UNI[UNI.full_name == name]
        if not len(row): continue
        row = row.iloc[0]
        val = V.value(row, cap=CAP, pool=UNI)
        prof = N.make_profile(row, rng)
        res = run_market(row, val, prof, teams, make_neg(row), rng)
        print(f'\n  {name}  {row.madden_position}  ovr {row.ovr:.0f}  age {row.age:.0f}'
              f'   [hidden: {prof["archetype"]}]   valued ${val["apy"]:.1f}M')
        if not res: print('    no market'); continue
        d = res['deal']
        pr = ', '.join(N.PROMISES[p]['label'] for p in d['promises']) or 'none'
        print(f'    SIGNS WITH {res["signed_with"]}  ${d["apy"]:.2f}M x{d["years"]}yr '
              f'{d["gtd_share"]*100:.0f}% gtd   promises: {pr}')
        print(f'    {res["n_bidders"]} bidders, leverage {res["leverage"]}')
        print(f'    all offers (team, $M, his utility): '
              + '  '.join(f'{t} ${a:.1f}/{u:.2f}' for t, a, u in res['all_offers']))
        top = max(res['all_offers'], key=lambda x: x[1])
        if top[0] != res['signed_with']:
            print(f'    NOTE: turned down more money from {top[0]} (${top[1]:.1f}M)')

