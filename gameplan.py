"""
The gameplan.

A team arrives with a plan and the adjustment engine modifies THE PLAN, not
individual play calls. Everything downstream reads this one object, which is
why a change persists until something changes it back - the way a real
adjustment works.

This replaces a scattered arrangement where each system carried its own
defaults and its own randomness, and where an adjustment patched one call and
then evaporated. It also fixes a real bug for free: travel (a corner following
a receiver) was being re-rolled on every snap, so a corner might follow on one
play and not the next. Travel is a game-plan decision, made once and held.

THREE THINGS ARE NOT ADJUSTABLE, and they live on the coach instead:
  - scheme identity. You cannot become a zone-blocking team at halftime, and a
    coordinator who runs Tite fronts does not install Bear fronts in the second
    quarter.
  - the playbook's concepts.
  - personnel on the roster.
The gameplan operates WITHIN those.

CHANGES COST DIFFERENT AMOUNTS. Nudging run-pass balance is free. Going from a
man team to a zone team mid-game is a structural change that should be slower,
rarer, and available only to a good coordinator. COST below encodes that.
"""
import numpy as np
from dataclasses import dataclass, field, asdict

# How hard each parameter is to change mid-game. 0 = a dial you turn freely,
# 1 = a wholesale change of identity that most coordinators never make.
COST = {
    'pass_bias':        0.05,
    'depth_mix':        0.10,
    'tempo':            0.12,
    'target_priority':  0.10,
    'protection':       0.15,
    'blitz_rate':       0.18,
    'box_bias':         0.18,
    'personnel_mix':    0.25,
    'shell_weights':    0.30,
    'travel':           0.35,
    'bracket':          0.30,
    'man_rate':         0.55,      # becoming a man team, or a zone team
    'front_pref':       0.70,      # a different defensive front family
    'run_scheme_mix':   0.75,      # zone blocking vs gap blocking
}


@dataclass
class Gameplan:
    """What a team intends to do. Every play call reads this."""
    # ---- offence ----
    pass_bias: float = 0.0            # added to the situational pass rate
    depth_mix: tuple = (0.62, 0.25, 0.13)   # short / medium / deep; re-set once plans stopped drifting shallow across a season
    personnel_mix: dict = field(default_factory=lambda: {
        '11': .595, '12': .195, '21': .070, '13': .030,
        '10': .075, '22': .025, '00': .010})
    run_scheme_mix: dict = field(default_factory=lambda: {'zone': .62, 'gap': .38})
    protection: str = 'half_slide'
    tempo: float = 0.5                # 0 = grind clock, 1 = no huddle
    target_priority: dict = field(default_factory=dict)   # pid -> weight
    play_action_rate: float = 0.5           # the caller's lean, 0.5 neutral
    motion_rate: float = 0.581           # the league-average lean (schemes.MOTION_NEUTRAL); a club with no identity plays at the average
    shell_lean: float = 0.5
    zone_aggression: float = 0.5      # underneath zones sit on the quick game (1) or sink (0)
    blitz_lean: float = 0.384            # the league-average lean (schemes.BLITZ_NEUTRAL)
    # ---- defence ----
    man_rate: float = 0.35
    shell_weights: dict = field(default_factory=lambda: {
        'cover_3': .30, 'cover_2': .18, 'cover_4': .22,
        'cover_1': .15, 'tampa_2': .08, 'cover_6': .07})
    blitz_rate: float = 0.133
    front_pref: list = field(default_factory=lambda: ['4-3 over', '4-3 under'])
    box_bias: float = 0.0
    travel: bool = False              # CB1 follows their best receiver
    travel_target: str = None
    travel_locked: bool = False          # set by the GM's game-week decision; kickoff does not re-decide
    bracket_locked: bool = False
    bracket: str = None               # pid being doubled
    # ---- bookkeeping ----
    changes: list = field(default_factory=list)

    def copy(self):
        g = Gameplan(**{k: (dict(v) if isinstance(v, dict) else
                            list(v) if isinstance(v, list) else v)
                        for k, v in asdict(self).items() if k != 'changes'})
        g.changes = list(self.changes)
        return g


def base_plan(coach=None, opponent=None, rng=None):
    """
    The plan a team walks in with. A good coordinator arrives having already
    accounted for what the opponent does; a poor one arrives with his defaults
    and has to discover everything live. That is where coach quality FIRST
    shows up, before a single adjustment is made.
    """
    rng = rng or np.random.default_rng()
    g = Gameplan()
    if coach is None:
        return g
    # scheme identity comes from the coach and is NOT adjustable later
    g.run_scheme_mix = dict(coach.get('run_scheme_mix', g.run_scheme_mix))
    g.front_pref = list(coach.get('front_pref', g.front_pref))
    g.man_rate = float(coach.get('man_rate', g.man_rate))
    g.blitz_rate = float(coach.get('blitz_rate', g.blitz_rate))
    g.tempo = float(coach.get('tempo', g.tempo))
    g.pass_bias = float(coach.get('pass_bias', 0.0))
    g.play_action_rate = float(coach.get('play_action_rate', g.play_action_rate))
    g.motion_rate = float(coach.get('motion_rate', 0.581))
    g.shell_lean = float(coach.get('shell_lean', 0.5))
    g.zone_aggression = float(coach.get('zone_aggression', 0.5))
    g.blitz_lean = float(coach.get('blitz_lean', 0.384))
    if 'personnel_mix' in coach: g.personnel_mix = dict(coach['personnel_mix'])
    if 'depth_mix' in coach: g.depth_mix = tuple(coach['depth_mix'])

    # planning quality: how much of the opponent he has already solved
    if opponent is not None:
        q = float(coach.get('plan_quality', 0.5))
        for key, val in (opponent.get('weaknesses') or {}).items():
            if key in ('pass_bias', 'box_bias', 'blitz_rate'):
                setattr(g, key, getattr(g, key) + val * q)
    return g


def can_change(param, skill, urgency=0.5):
    """
    Is this coordinator capable of making this change mid-game? A cheap dial
    yes; a change of identity only if he is good and the situation demands it.
    """
    c = COST.get(param, 0.3)
    return (skill * (0.55 + 0.75 * urgency)) >= c


def apply_change(plan, param, value, skill, urgency=0.5, note='', quarter=1):
    """
    Modify the PLAN. Returns (new_plan, applied). A change that is too
    expensive for this coordinator simply does not happen.
    """
    if not can_change(param, skill, urgency):
        return plan, False
    g = plan.copy()
    if param == 'shell_weights' and isinstance(value, dict):
        w = dict(g.shell_weights)
        for k, v in value.items(): w[k] = max(0.0, w.get(k, 0.0) + v)
        tot = sum(w.values()) or 1.0
        g.shell_weights = {k: v / tot for k, v in w.items()}
    elif param == 'depth_mix' and isinstance(value, (tuple, list)):
        v = np.array(value, float); v = np.clip(v, 0.02, None); v /= v.sum()
        g.depth_mix = tuple(v)
    elif param in ('pass_bias', 'box_bias'):
        setattr(g, param, float(np.clip(getattr(g, param) + value, -0.45, 0.45)))
    elif param in ('man_rate', 'blitz_rate', 'tempo', 'play_action_rate'):
        setattr(g, param, float(np.clip(getattr(g, param) + value, 0.0, 1.0)))
    else:
        setattr(g, param, value)
    g.changes.append(dict(param=param, value=value, quarter=quarter, note=note))
    return g, True


# ============================================================ READING THE PLAN
def shell(plan, rng):
    ks = list(plan.shell_weights)
    p = np.array([plan.shell_weights[k] for k in ks], float)
    p = p / p.sum()
    return str(rng.choice(ks, p=p))

def is_man(plan, rng):
    return rng.random() < plan.man_rate

def depth(plan, rng, yards_to_endzone=50, down=1, ydstogo=10):
    import identity as ID
    mix = ID.situational_depth(np.array(plan.depth_mix) / sum(plan.depth_mix),
                               yards_to_endzone, down, ydstogo)
    return str(rng.choice(['short', 'medium', 'deep'], p=mix))

def personnel(plan, rng):
    ks = list(plan.personnel_mix)
    p = np.array([plan.personnel_mix[k] for k in ks], float); p /= p.sum()
    return str(rng.choice(ks, p=p))

def run_family(plan, rng):
    return 'zone' if rng.random() < plan.run_scheme_mix.get('zone', .62) else 'gap'

def blitzers(plan, rng, down=1, ydstogo=10):
    r = plan.blitz_rate * (1.35 if (down == 3 and ydstogo >= 6) else 1.0)
    x = rng.random()
    if x < r * 0.73: return 1
    if x < r * 0.96: return 2
    if x < r:        return 3
    return 0


# ============================================================ ADJUSTMENT BRIDGE
# Maps the adjustment engine's structural counters onto gameplan changes, so an
# adjustment persists instead of patching one call and evaporating.
COUNTER_TO_PLAN = {
    'pass_deep':   [('shell_weights', {'cover_2': .18, 'cover_4': .16,
                                       'cover_1': -.08, 'cover_3': -.10}),
                    ('box_bias', -0.10)],
    'pass_medium': [('shell_weights', {'cover_3': .14, 'tampa_2': .12,
                                       'cover_1': -.10})],
    'pass_short':  [('shell_weights', {'cover_1': .16, 'cover_0': .06,
                                       'cover_4': -.12}),
                    ('man_rate', 0.12), ('box_bias', 0.08)],
    'target':      [('bracket', 'TARGET'), ('travel', True),
                    ('shell_weights', {'cover_2': .12, 'cover_4': .10})],
    'run':         [('box_bias', 0.22), ('front_pref', ['bear', 'tite'])],
    'protection':  [('protection', 'seven'), ('depth_mix', (0.80, 0.16, 0.04))],
    'predictable': [('pass_bias', 0.0)],      # handled by forcing a mix
}

def adjust_plan(plan, counter, skill, urgency=0.5, quarter=1):
    """
    Fold an adjustment into the plan. Each parameter is gated by its own cost,
    so a coordinator may successfully walk a safety down (cheap) and fail to
    become a man team (expensive) off the same read.
    """
    if not counter or not counter.get('works'):
        return plan, []
    trig = counter.get('trigger')
    steps = COUNTER_TO_PLAN.get(trig) or COUNTER_TO_PLAN.get(counter.get('kind'), [])
    applied = []
    g = plan
    # A change already in effect is not made again. Without this the same
    # counter re-fired every series and an elite coordinator racked up 16 plan
    # changes in a game; a real one makes a handful.
    recent = {c['param'] for c in plan.changes[-6:]}
    for param, val in steps:
        if param in recent:
            continue
        if param == 'travel' and plan.travel:
            continue
        if param == 'bracket' and plan.bracket == counter.get('target'):
            continue
        if param == 'bracket' and val == 'TARGET':
            val = counter.get('target')
            if not val: continue
        if param == 'travel':
            # you cannot shadow anyone out of zone - nobody is assigned a man
            if g.man_rate < 0.25: continue
            plan_target = counter.get('target')
            g2, ok = apply_change(g, 'travel', True, skill, urgency,
                                  trig, quarter)
            if ok:
                g2.travel_target = plan_target
                g = g2; applied.append('travel')
            continue
        g, ok = apply_change(g, param, val, skill, urgency, trig, quarter)
        if ok: applied.append(param)
    return g, applied
