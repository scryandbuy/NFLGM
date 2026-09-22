"""
GM decision engine.

ONE valuation function. Every decision a GM makes - who starts, who gets cut,
who to extend, what to trade for, what to bid - asks this same function a
question and acts on the answer. Nothing branches on "if rebuilding then...".
Context feeds the valuation; it never routes around it.

That is what makes a GM coherent: a man who overrates his own players does not
need three separate rules to start his declining veteran, refuse to cut him,
and overpay to re-sign him. Those are the same parameter showing up three times.

NOTHING HERE DECIDES ANYTHING. It returns what an asset is worth to this GM,
right now, for this purpose. The acting is done elsewhere.

Grounded where the research gave us numbers:
  - sunk cost is real and measured. Keefer finds a 10% rise in cap value buys
    2.7 extra games started for players of equal production, and performance
    feedback does not eliminate it over a career.
  - top picks are systematically overvalued relative to surplus (Massey/Thaler).
  - reps are the development mechanism. "How can you get that young guy to play
    like a veteran? He has to play." - Saleh, on a season already lost.
  - contract length rules by age are front-office orthodoxy: no 5-year deals
    past 26, no 4-year deals past 28, never long for an injury risk.
  - financial chemistry: you cannot pay a signing above your own best man at
    that position.
  - positional value is really REPLACEABILITY - how cheaply the market refills
    that spot, not a fixed table.
"""
import numpy as np
from dataclasses import dataclass, field

# ---------------------------------------------------------------- purposes
# The same asset is worth different things depending on what you are asking.
# A start decision ignores contract entirely; a trade cares about it enormously.
PURPOSE = {
    #                     current  future  contract  reps    risk
    'start':        dict(cur=1.00, fut=0.18, con=0.00, dev=0.30, rsk=0.35),
    'cut':          dict(cur=0.85, fut=0.35, con=0.90, dev=0.25, rsk=0.40),
    'extend':       dict(cur=0.55, fut=0.90, con=0.85, dev=0.10, rsk=0.70),
    'sign_fa':      dict(cur=0.70, fut=0.70, con=0.95, dev=0.05, rsk=0.75),
    'trade_for':    dict(cur=0.65, fut=0.80, con=0.80, dev=0.10, rsk=0.60),
    'trade_away':   dict(cur=0.70, fut=0.70, con=0.75, dev=0.15, rsk=0.45),
    'draft':        dict(cur=0.20, fut=1.00, con=0.10, dev=0.20, rsk=0.85),
    'depth':        dict(cur=0.45, fut=0.75, con=0.55, dev=0.45, rsk=0.30),
}

# ---------------------------------------------------------------- GM
@dataclass
class GM:
    """
    A GM is a set of distortions, not a set of rules. All hidden from the user;
    inferable only by watching what he does.
    """
    name: str = 'gm'
    # --- how he sees value ---
    pick_lens:      float = 0.50   # 0 = prices picks at true value, 1 = at market
    youth:          float = 0.50   # 0 = wants proven, 1 = wants upside
    contract_focus: float = 0.50   # how much a bad deal repels him
    risk:           float = 0.50   # 0 = avoids injury/variance, 1 = chases it
    # --- his blind spots ---
    own_bias:       float = 1.10   # overrates his own roster (endowment effect)
    sunk_cost:      float = 0.50   # draft capital keeps a man on the field
    loyalty:        float = 0.50   # tenure and history protect a player
    # --- how he operates ---
    patience:       float = 0.50   # tolerance for a plan that pays off later
    aggression:     float = 0.50   # willingness to move, overpay, reach
    dev_belief:     float = 0.50   # belief that reps make players better
    restructure_depth: float = 0.50 # willingness to kick the can: converts salary
                                   # into future cap hits and future dead money.
                                   # A GM who does this repeatedly makes his own
                                   # players uncuttable.
    board_trust:    float = 0.50   # 0 = pure need drafter, 1 = true to the board.
                                   # "everybody says best player available. But at
                                   # some point need enters into it, too. Earlier
                                   # for some people than for others." - Reinfeldt
    need_inflation: float = 0.50   # a BIAS, not a preference: "if you have a need
                                   # you tend to overvalue players at that need
                                   # position" - and separately you overvalue the
                                   # premium positions and try to create someone
    scheme_rigidity:float = 0.50   # how hard a scheme misfit is penalised
    scouting:       float = 0.50   # how close his read of a prospect sits to the
                                   # truth: 1 = the best room in the league, 0 = the worst
    # --- what he runs (identity_catalog axes; the coach and the GM are one man) ---
    off_blocking:   str = 'zone'    # 'zone' | 'gap' | 'mixed'
    off_personnel:  str = '11'      # base grouping: '11' | '12' | '13' | '21' | 'multiple'
    pass_lean:      float = 0.50    # run-heavy .. pass-heavy
    play_action:    float = 0.50
    motion:         float = 0.50
    tempo:          float = 0.50
    deep:           float = 0.50
    fourth_down:    float = 0.50
    def_front:      str = '4-3'     # '4-3' one-gap | '3-4' two-gap | 'multiple'
    coverage:       float = 0.25    # zone .. man
    shell:          float = 0.50    # single-high .. two-high
    blitz:          float = 0.35
    box:            float = 0.45    # light .. heavy
    tree:           str = ''        # the coaching family, for the record
    # --- state, not personality ---
    job_security:   float = 0.60   # low security collapses the time horizon
    tenure:         int   = 0      # years in the chair; 0 = brand new regime

    def shift(self, team):
        """
        A GM is not fixed. The same man values things differently at 4-13 than
        at 12-5, and a man about to be fired cannot afford a plan. His STYLE
        never changes; where he sits on it does.
        """
        g = GM(**{k: getattr(self, k) for k in self.__dataclass_fields__})
        w = team['win_pct']
        if w <= .35:
            g.pick_lens = max(0.0, g.pick_lens - .18)
            g.youth = min(1.0, g.youth + .22)
            g.aggression = max(0.0, g.aggression - .25)
            g.own_bias = max(0.92, g.own_bias - .12)
        elif w >= .65:
            g.pick_lens = min(1.0, g.pick_lens + .14)
            g.youth = max(0.0, g.youth - .20)
            g.aggression = min(1.0, g.aggression + .26)
        # a man on the hot seat stops caring about next year
        if g.job_security < 0.35:
            g.youth = max(0.0, g.youth - .30)
            g.patience = max(0.0, g.patience - .40)
            g.aggression = min(1.0, g.aggression + .30)
        return g

IDENTITY_KEYS = ('off_blocking', 'off_personnel', 'pass_lean', 'play_action', 'motion', 'tempo',
                 'deep', 'fourth_down', 'def_front', 'coverage', 'shell', 'blitz', 'box')
ROSTER_KEYS = ('youth', 'pick_lens', 'contract_focus', 'risk', 'patience', 'aggression', 'dev_belief',
               'board_trust', 'need_inflation', 'restructure_depth', 'scouting')


def scheme_of(gm):
    """
    The engine's scheme keys (targets.SCHEME_SHIFT) that this man's identity
    implies: blocking, front, coverage. A 'mixed' blocking scheme or a
    'multiple' front adds no shift at that spot; a coverage lean that is not
    clearly man or zone adds none either.
    """
    keys = []
    if gm.off_blocking in ('zone', 'gap'):
        keys.append(gm.off_blocking)
    if gm.def_front == '4-3': keys.append('one_gap')
    elif gm.def_front == '3-4': keys.append('two_gap')
    if gm.coverage >= 0.5: keys.append('man')
    elif gm.coverage <= 0.3: keys.append('zone_cov')
    return keys or None


def scheme_fit(player_ratings, pos, team):
    """
    How many overall points this club's scheme adds to or takes from him at
    his spot, scaled by how hard the man in charge holds to his scheme.
    Zero when the club has no scheme lean at his spot. This is the REASON
    two clubs disagree about a player, and it replaces the placeholder
    perception noise in trades.
    """
    import targets as TG
    scheme = getattr(team, 'scheme', None)
    if not scheme:
        return 0.0
    gm = getattr(team, 'gm', None)
    rigidity = float(getattr(gm, 'scheme_rigidity', 0.5)) if gm is not None else 0.5
    raw = TG.position_score(player_ratings, pos)
    sch = TG.position_score(player_ratings, pos, scheme)
    return float((sch - raw) * (0.6 + 0.8 * rigidity))


def apply_identity(gm, entry, name=None):
    """Write a catalog entry onto a GM: offence and defence axes, the
    roster dials, the name and the tree."""
    if name: gm.name = name
    gm.tree = entry.get('tree', '')
    for k, v in entry.get('offence', {}).items():
        setattr(gm, {'blocking': 'off_blocking', 'personnel': 'off_personnel'}.get(k, k), v)
    for k, v in entry.get('defence', {}).items():
        setattr(gm, {'front': 'def_front'}.get(k, k), v)
    for k, v in entry.get('roster', {}).items():
        if k in ROSTER_KEYS: setattr(gm, k, float(v))
    gm.scouting = float(np.clip(gm.scouting, 0.05, 0.98))
    return gm


def blend_identity(rng, offence=None, defence=None, roster=None, noise=0.08):
    """
    A man from the archetypes in identity_catalog: a weighted mix of one or
    two offensive trees, one defensive family and one front-office type,
    plus noise, which is how coaching trees actually propagate. Returns the
    dict apply_identity takes.
    """
    import identity_catalog as IC
    A = IC.ARCHETYPES
    def pick(kind, given):
        names = [k for k, v in A.items() if kind in v]
        if given: return given
        w = np.ones(len(names))
        if kind == 'offence':      # the league is a Shanahan/McVay league
            w = np.array([3.0 if n in ('shanahan_tree', 'mcvay_tree') else 1.0 for n in names])
        return str(rng.choice(names, p=w / w.sum()))
    def mix(kind, a, b=None, wa=1.0):
        out = dict(A[a][kind])
        if b:
            for k, v in A[b][kind].items():
                if isinstance(v, (int, float)): out[k] = wa * out[k] + (1 - wa) * v
        for k, v in list(out.items()):
            if isinstance(v, (int, float)): out[k] = float(np.clip(v + rng.normal(0, noise), 0, 1))
        return out
    o1 = pick('offence', offence); o2 = pick('offence', None) if rng.random() < 0.5 else None
    d1 = pick('defence', defence); r1 = pick('roster', roster)
    return dict(offence=mix('offence', o1, o2, rng.uniform(0.6, 0.85)), defence=mix('defence', d1),
                roster=mix('roster', r1), tree=f"{o1}{'+' + o2 if o2 else ''} / {d1} / {r1}")


def make_gm(rng, archetype=None):
    A = {
      'analytics':   dict(pick_lens=.12, youth=.72, contract_focus=.85, risk=.40,
                          own_bias=1.02, sunk_cost=.18, loyalty=.25, patience=.85,
                          restructure_depth=.20, aggression=.35, dev_belief=.65, board_trust=.85,
                          need_inflation=.20, scheme_rigidity=.35, scouting=.70),
      'traditional': dict(pick_lens=.88, youth=.35, contract_focus=.40, risk=.45,
                          own_bias=1.16, sunk_cost=.75, loyalty=.75, patience=.50,
                          restructure_depth=.62, aggression=.50, dev_belief=.45, board_trust=.40,
                          need_inflation=.72, scheme_rigidity=.70, scouting=.55),
      'gunslinger':  dict(pick_lens=.72, youth=.40, contract_focus=.25, risk=.85,
                          own_bias=1.06, sunk_cost=.50, loyalty=.35, patience=.20,
                          restructure_depth=.88, aggression=.92, dev_belief=.40, board_trust=.30,
                          need_inflation=.85, scheme_rigidity=.30, scouting=.40),
      'hoarder':     dict(pick_lens=.40, youth=.80, contract_focus=.75, risk=.30,
                          own_bias=1.25, sunk_cost=.60, loyalty=.70, patience=.92,
                          restructure_depth=.25, aggression=.18, dev_belief=.70, board_trust=.78,
                          need_inflation=.30, scheme_rigidity=.45, scouting=.65),
      'win_now':     dict(pick_lens=.82, youth=.20, contract_focus=.30, risk=.70,
                          own_bias=1.10, sunk_cost=.55, loyalty=.45, patience=.22,
                          restructure_depth=.92, aggression=.85, dev_belief=.30, board_trust=.25,
                          need_inflation=.88, scheme_rigidity=.55, scouting=.45),
      'developer':   dict(pick_lens=.45, youth=.85, contract_focus=.60, risk=.50,
                          own_bias=1.14, sunk_cost=.45, loyalty=.65, patience=.88,
                          restructure_depth=.35, aggression=.40, dev_belief=.92, board_trust=.70,
                          need_inflation=.35, scheme_rigidity=.80, scouting=.70),
      'balanced':    dict(pick_lens=.50, youth=.50, contract_focus=.55, risk=.50,
                          own_bias=1.10, sunk_cost=.45, loyalty=.50, patience=.55,
                          restructure_depth=.50, aggression=.50, dev_belief=.55, board_trust=.55,
                          need_inflation=.50, scheme_rigidity=.50, scouting=.55),
    }
    k = archetype or rng.choice(list(A))
    p = {a: float(np.clip(v * rng.normal(1.0, .13), 0.0, 2.0)) for a, v in A[k].items()}
    # the endowment effect only ever INFLATES what is already yours. Sampling
    # was letting own_bias fall below 1.0, which had GMs undervaluing their own
    # players - the opposite of the documented behaviour.
    p['own_bias'] = max(1.0, p['own_bias'])
    p['scouting'] = float(np.clip(p['scouting'], 0.05, 0.98))
    g = GM(name=k, **p)
    g.job_security = float(np.clip(rng.normal(.60, .18), .05, .98))
    g.tenure = int(rng.integers(0, 8))
    # what he runs: drawn from the trees unless a catalog entry replaces it
    ident = blend_identity(rng)
    for kk, v in ident['offence'].items():
        setattr(g, {'blocking': 'off_blocking', 'personnel': 'off_personnel'}.get(kk, kk), v)
    for kk, v in ident['defence'].items():
        setattr(g, {'front': 'def_front'}.get(kk, kk), v)
    g.tree = ident['tree']
    return g

# ---------------------------------------------------------------- replaceability
# Positional value is not a fixed table. It is how cheaply the market refills
# that spot: a team needing a C, TE, S or RB has options for little capital;
# a team needing a QB does not. Derived from the contract market, not asserted.
REPLACEABILITY = {   # 1.0 = trivially replaced, 0.0 = irreplaceable
    'QB': 0.10, 'LT': 0.45, 'REDG': 0.42, 'LEDG': 0.42, 'WR': 0.55, 'CB': 0.50,
    'DT': 0.58, 'RT': 0.60, 'LG': 0.72, 'RG': 0.72, 'C': 0.75, 'FS': 0.78,
    'SS': 0.78, 'MIKE': 0.80, 'WILL': 0.80, 'SAM': 0.85, 'TE': 0.72, 'HB': 0.88,
    'FB': 0.95, 'K': 0.90, 'P': 0.92, 'LS': 0.97,
}

# ---------------------------------------------------------------- the engine
# Positions where teams "overvalue the position and try to create someone".
# This is the FIRST of the two reach mechanisms and it stacks with the second.
PREMIUM = {'QB': 1.00, 'LT': 0.45, 'LEDG': 0.42, 'REDG': 0.42, 'CB': 0.35,
           'WR': 0.30, 'DT': 0.22, 'RT': 0.20, 'TE': 0.12, 'C': 0.08,
           'LG': 0.05, 'RG': 0.05, 'MIKE': 0.10, 'WILL': 0.08, 'SAM': 0.04,
           'FS': 0.10, 'SS': 0.10, 'HB': 0.06, 'FB': 0.0, 'K': 0.0, 'P': 0.0, 'LS': 0.0}

def future_need(team, pos, horizon=3):
    """
    Anticipatory need: the position is fine this year but about to turn over.
    Green Bay taking A.J. Dillon with a starting back in place is the archetype.
    team['expiring'][pos] = list of (overall, years_of_control_left, age)
    """
    rows = team.get('expiring', {}).get(pos, [])
    if not rows: return 0.0
    loss = 0.0
    for ovr, yrs_left, age in rows:
        gone_soon = yrs_left <= horizon - 1
        ageing_out = age + horizon >= 31
        if gone_soon or ageing_out:
            loss += max(0.0, (ovr - 68) / 24.0) * (1.0 if gone_soon else 0.6)
    scarcity = 1.0 - REPLACEABILITY.get(pos, 0.6)
    return float(np.clip(loss * (0.5 + 0.9 * scarcity), 0.0, 1.0))

def board_weight(round_):
    """
    Best-player-available is a luxury of the top and the bottom of the draft.
    At the very top there are genuine outlier prospects; at the back you are
    swinging for home runs anyway. In the middle you cannot confidently say
    prospect 20 beats prospect 21, so you take the need you DO know.
    Returns how much to trust the board vs. need at this round.
    """
    return {1: 0.85, 2: 0.55, 3: 0.45, 4: 0.45, 5: 0.55, 6: 0.70, 7: 0.80}.get(int(round_), 0.55)

def team_need(team, pos):
    """
    Not headcount. A gap relative to what this roster should have at that spot,
    weighted by how hard the position is to refill.
    team['depth'][pos] = sorted list of overalls at that position.
    """
    d = sorted(team.get('depth', {}).get(pos, []), reverse=True)
    starters = {'QB':1,'LT':1,'RT':1,'LG':1,'RG':1,'C':1,'TE':1,'HB':1,'FB':0,
                'WR':3,'LEDG':1,'REDG':1,'DT':2,'MIKE':1,'WILL':1,'SAM':0,
                'CB':3,'FS':1,'SS':1,'K':1,'P':1,'LS':1}.get(pos, 1)
    have = d[:max(1, starters)]
    level = np.mean(have) if have else 50.0
    # The bar is not the same at every position. A 74-overall quarterback is a
    # crisis; a 74-overall guard is a starter you are fine with. A flat 72
    # threshold said neither was a need, which is why round weighting had
    # nothing to act on.
    bar = 72 + 16 * (1.0 - REPLACEABILITY.get(pos, 0.6))
    gap = float(np.clip((bar - level) / 22.0, 0.0, 1.0))
    if len(d) < starters: gap = min(1.0, gap + 0.35)
    scarcity = 1.0 - REPLACEABILITY.get(pos, 0.6)
    return float(np.clip(gap * (0.55 + 0.9 * scarcity), 0.0, 1.0))

def value(asset, gm, team, purpose, ctx=None):
    """
    What is this worth to THIS gm, on THIS team, for THIS purpose, right now.
    Returns a number on a $M-ish scale plus the terms that produced it, so any
    decision can be traced back to the weighting that drove it.
    """
    ctx = ctx or {}
    w = PURPOSE[purpose]
    g = gm.shift(team)
    a = asset

    # --- the four raw inputs -------------------------------------------------
    cur = float(a.get('now', 0.0))            # what he is worth today, $M
    fut = float(a.get('later', cur))          # projected across control years
    cost = float(a.get('cost', 0.0))          # cap cost per year
    dead = float(a.get('dead', 0.0))          # dead money if he goes
    age = float(a.get('age', 27))
    pos = a.get('pos', 'WR')

    # --- youth / proven axis -------------------------------------------------
    youth_tilt = 1.0 + (g.youth - 0.5) * 0.60 * np.clip((27 - age) / 6.0, -1.2, 1.2)

    # --- reps: playing time is a development tool, not just a talent ranking --
    # strongest on a team going nowhere, on a young man, at a position where
    # snaps are cheap to hand out. Quarterback is the exception: one man plays.
    rep_room = REPLACEABILITY.get(pos, 0.6) if pos != 'QB' else 0.15
    lost_season = 1.0 - float(np.clip(team['win_pct'] / 0.55, 0, 1))
    reps = (g.dev_belief * np.clip((26 - age) / 5.0, 0, 1)
            * (0.35 + 0.65 * lost_season) * (0.4 + 0.6 * rep_room))

    # --- sunk cost: measured, and it does NOT decay with evidence ------------
    pedigree = float(a.get('pedigree', 0.0))          # 0 = UDFA, 1 = 1st overall
    paid = float(np.clip(cost / 12.0, 0, 1.5))
    sunk = g.sunk_cost * (0.55 * pedigree + 0.45 * paid)

    # --- endowment: he overrates what is already his -------------------------
    mine = a.get('ours', False)
    own = (g.own_bias + 0.10 * g.loyalty * float(np.clip(a.get('tenure', 0) / 5, 0, 1))) if mine else 1.0
    # a brand-new regime does NOT inherit the last man's valuations
    if mine and g.tenure == 0: own = 1.0 + (own - 1.0) * 0.25

    # --- availability is not ability -----------------------------------------
    avail = float(a.get('availability', 1.0))         # share of games played
    risk_pen = (1.0 - avail) * (1.4 - g.risk)

    # --- put it together -----------------------------------------------------
    base = (w['cur'] * cur + w['fut'] * fut * youth_tilt) * own
    base *= (1.0 + w['dev'] * reps + 0.30 * sunk)
    base *= (1.0 - w['rsk'] * risk_pen * 0.45)
    # --- need, present and anticipated -------------------------------------
    need_now = team_need(team, pos)
    need_soon = future_need(team, pos)
    need = float(np.clip(max(need_now, 0.75 * need_soon), 0.0, 1.0))

    if purpose == 'draft':
        # Two distinct reach mechanisms, and they stack:
        #   1. you overvalue the premium positions and try to create someone
        #   2. if you have a need you overvalue players AT that need position
        rnd = float(ctx.get('round', 1))
        trust = g.board_trust * board_weight(rnd) + (1 - g.board_trust) * 0.25
        premium = PREMIUM.get(pos, 0.1) * g.need_inflation * 0.55
        inflate = need * g.need_inflation * 0.85 * (1.0 - trust)
        base *= (1.0 + premium + inflate)
        # scheme fit is a filter, not a nudge: good tape in the wrong system slides
        fit = float(ctx.get('scheme_fit', 1.0))
        base *= (1.0 - (1.0 - fit) * g.scheme_rigidity * 0.55)
        # a man who will be fired if the pick busts takes the defensible one
        if g.job_security < 0.40:
            base *= (1.0 + need * 0.25)
    else:
        base *= (1.0 + 0.55 * need)

    money = w['con'] * (cost * (0.6 + 0.9 * g.contract_focus))
    if purpose == 'cut':
        # cutting him frees his salary but accelerates the bonus. That is the
        # whole decision, and a fully guaranteed deal makes it impossible.
        savings = max(0.0, cost - dead)
        base = base - savings * (0.6 + 0.9 * g.contract_focus)
        money = 0.0

    total = base - money
    return dict(total=round(float(total), 2), base=round(float(base), 2),
                reps=round(float(reps), 3), sunk=round(float(sunk), 3),
                own=round(float(own), 3), need=round(float(need), 3),
                need_now=round(float(need_now), 3), need_soon=round(float(need_soon), 3),
                risk_pen=round(float(risk_pen), 3), youth_tilt=round(float(youth_tilt), 3))

# ---------------------------------------------------------------- hard limits
# Constraints, not preferences. A GM may be bad at every judgment call in the
# game, but he cannot break a rule.
def max_contract_years(age, injury_risk=False):
    """Front-office orthodoxy: no 5yr past 26, no 4yr past 28, never long if hurt."""
    if injury_risk: return min(2, 3)
    if age >= 28: return 3
    if age >= 26: return 4
    return 5

def financial_chemistry_ceiling(team, pos):
    """You cannot pay a signing more than your own best man at that position."""
    cur = team.get('top_apy', {}).get(pos)
    return cur if cur else float('inf')

def can_cut(cost, dead):
    """A fully guaranteed contract is uncuttable: no savings, all dead."""
    return (cost - dead) > 0.0


# ---------------------------------------------------------------- cap tools
# Four ways out of a bad contract, not three. Each is a different trade between
# money now, money later, and keeping the man.
MAX_PRORATION_YEARS = 5

def simple_restructure_room(base, yrs_left, min_salary=1.2):
    """
    Convert base salary into signing bonus, spread over the years ALREADY on the
    deal. A team can do this unilaterally - the player's consent is not needed -
    but the years remaining cap how much room it buys.

    Available to EVERY general manager by decision. It is a mechanic the rules
    allow any club to use, not a personality trait, so nothing here reads a GM
    rating. What separates one front office from another is how often need
    drives them to it, and the dead money they are left holding afterwards.
    """
    if yrs_left <= 1: return 0.0, 0.0
    conv = max(0.0, base - min_salary)
    spread = min(yrs_left, MAX_PRORATION_YEARS)
    return round(conv * (1 - 1/spread), 3), round(conv, 3)

def max_restructure_room(base, yrs_left, void_years=0, min_salary=1.2):
    """
    Same conversion but void years are bolted on to spread it further. This is a
    renegotiation, so it REQUIRES the player's agreement, and it loads the dead
    money even harder.
    """
    conv = max(0.0, base - min_salary)
    spread = min(yrs_left + void_years, MAX_PRORATION_YEARS)
    if spread <= 1: return 0.0, 0.0
    return round(conv * (1 - 1/spread), 3), round(conv, 3)

def is_uncuttable(cap_hit, dead_if_cut):
    """
    Restructures create their own trap: enough accumulated proration and cutting
    him costs MORE than keeping him. The team did that to itself.
    """
    return dead_if_cut >= cap_hit

def deferred_cut_value(dead_now, dead_next_year, cap_now, cap_next):
    """
    The Lockett pattern: you do not resolve a bad contract, you WAIT until the
    dead money shrinks enough to swallow. Positive means waiting a year is
    cheaper in cap-share terms.
    """
    return round(dead_now/max(cap_now,1) - dead_next_year/max(cap_next,1), 4)

def cap_options(player, team, gm, cap_now, cap_next):
    """
    Score the four exits. Returns them ranked; this ENGINE DOES NOT ACT.
    player: base, yrs_left, cap_hit, dead_if_cut, dead_next, value_to_team
    """
    g = gm.shift(team)
    base = player['base']; yrs = player['yrs_left']
    room_simple, _ = simple_restructure_room(base, yrs)
    room_max, _ = max_restructure_room(base, yrs, void_years=2)
    keeps_him = player['value_to_team']

    out = {}
    # 1. restructure (free, no consent, but loads future dead money)
    future_cost = room_simple * (1.0 - g.patience) * 0.8
    out['restructure'] = keeps_him + room_simple * (0.5 + g.restructure_depth) - future_cost
    # 2. max restructure - needs consent, buys more, costs more later
    out['max_restructure'] = (keeps_him + room_max * (0.4 + g.restructure_depth)
                              - room_max * (1.0 - g.patience) * 1.25)
    # 3. extend - lowers the annual number but commits further
    out['extend'] = keeps_him * (0.9 + 0.4 * g.patience) - player['cap_hit'] * 0.35
    # 4. cut - frees salary, accelerates the bonus
    savings = max(0.0, player['cap_hit'] - player['dead_if_cut'])
    out['cut'] = savings * (0.6 + 0.9 * g.contract_focus) - keeps_him
    if is_uncuttable(player['cap_hit'], player['dead_if_cut']):
        out['cut'] = float('-inf')
    # 5. wait a year and cut then, if the dead money shrinks enough
    defer = deferred_cut_value(player['dead_if_cut'], player.get('dead_next', 0.0),
                               cap_now, cap_next)
    out['defer_cut'] = keeps_him * 0.6 + defer * cap_now * 0.5 * (0.4 + g.patience)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
