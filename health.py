"""
Condition, jadedness and injuries.

Architecture follows Football Manager, which models this properly and whose
mechanics are documented and tested by its community. NFL data supplies the
targets.

WHAT FM DOES, AND WHY IT IS RIGHT:

  SEPARATE STATE VARIABLES, not one "fatigue" number:
    condition   - physical freshness right now. Depletes during a game,
                  refills between them.
    jadedness   - hidden, season-long accumulated tiredness. Slow to build,
                  slow to shed.

  FM also carries SHARPNESS - match readiness, built by playing and decayed
  by not playing, which degrades performance rather than injury risk. It was
  built here and REMOVED BY DECISION. A backup who has not played since week
  2 steps in at his normal level, and a man returning from injury plays at
  full ability immediately. There is no rust in this game.

  TWO ATTRIBUTES WITH DIFFERENT JOBS:
    stamina         governs condition LOSS during a match. It does NOT affect
                    recovery - the FM community tested this explicitly.
    natural fitness governs condition RECOVERY between matches, and slows
                    jadedness. A low-fitness player cannot play every three
                    days even with good stamina.

  WHAT CONDITION IS FOR:
    Condition mostly drives INJURY RISK, not performance. FM's community found
    low-condition men mostly just get hurt rather than play badly - the
    performance half of that split was sharpness, which is removed here. So
    condition barely moves a player's ability until it gets dire, and what it
    really governs is rotation and who breaks down.

  THE INJURY-CONDITION CURVE IS VIOLENTLY NONLINEAR. Community testing found:
    100% condition ->  8 in-match injuries
     80% condition -> 20
     60% condition -> 87
  Roughly a 2.4x multiplier per 20 points of condition lost, and it is what
  makes rest a real decision rather than a nicety.

  ROLE INTENSITY drives the rate, not position labels: a defensive forward
  accrues jadedness faster than a poacher because of what the ROLE asks.

NFL TARGETS (nflverse snap counts 2024-25, injury reports 2023-25):
  snap share    C 84.0, G 81.7, QB 79.7, T 79.5, SS 70.3, FS 67.4, CB 65.1,
                LB 57.4, WR 51.5, DT 47.5, DE 46.1, TE 44.3, RB 37.6
  injuries      2.51 players ruled out per team per week (median 2, p90 4)
  duration      mean 1.50 weeks; 33.3% last 2+, 12.0% 3+, 3.1% 4+, 0.3% 6+
"""
import numpy as np

# ============================================================ ROLE INTENSITY
# What a single snap ASKS of the player. An all-out pass rush or a carry with
# contact costs far more than a pass-block set. This is FM's role-intensity
# idea, and it is what makes the defensive front rotate while the line does not.
# Solved so that equilibrium share = recovery / (recovery + intensity)
# reproduces the real league snap shares above.
SNAP_INTENSITY = {
    'C': 0.190, 'LG': 0.224, 'RG': 0.224, 'QB': 0.255, 'LT': 0.258, 'RT': 0.258,
    'SS': 0.422, 'FS': 0.484, 'CB': 0.536,
    'MIKE': 0.742, 'WILL': 0.742, 'SAM': 1.000,
    'WR': 0.942, 'DT': 1.105, 'LEDG': 1.169, 'REDG': 1.169,
    'TE': 1.257, 'HB': 1.660, 'FB': 2.333,
    'K': 0.02, 'P': 0.02, 'LS': 0.02,
}
# Solved so the emergent shares land ON the real league values rather than
# 14 points above them across the board.
SIDELINE_RECOVERY = 0.62

# ============================================================ CONDITION
class Condition:
    """
    In-game physical freshness, 0-100. Stamina governs the LOSS rate only.
    Recovery between games is governed separately by natural fitness, exactly
    as FM does it - the two are different attributes and do not trade off.
    """
    def __init__(self, policy=0.5):
        self.cond = {}
        self.snaps = {}
        self.policy = policy          # coach rotation policy, a settings slider

    def get(self, pid): return self.cond.get(pid, 100.0)

    def play(self, pid, position, stamina=70.0, effort=1.0):
        cost = SNAP_INTENSITY.get(position, 0.80) * effort
        cost *= 1.0 - 0.45 * ((stamina - 50.0) / 50.0)
        self.cond[pid] = max(0.0, self.get(pid) - cost * 4.2)
        self.snaps[pid] = self.snaps.get(pid, 0) + 1

    def rest(self, pid, position=None):
        """
        A snap on the sideline. Recovery is a FIXED rate - a man recovers at
        his own pace regardless of how taxing the snap he skipped would have
        been, and it is not stamina-driven (FM tested that explicitly).

        This matters enormously: scaling recovery by the position's intensity
        made intensity cancel out of the equilibrium entirely, so every
        position settled at the same 55% snap share. With a fixed rate the
        equilibrium is recovery / (recovery + intensity x stamina), which is
        what reproduces the real spread from 84% at centre to 37.6% at back.
        """
        self.cond[pid] = min(100.0, self.get(pid) + SIDELINE_RECOVERY * 4.2)

    def needs_rest(self, pid, position, rng, stamina=70.0, quality_gap=0.0):
        """
        Rotation is an OUTPUT of condition, never forced by a scheme table.
        The coach's policy shifts the trigger and a star stays on longer than
        a marginal starter at the same condition.
        """
        c = self.get(pid)
        # A high trigger means even a low-intensity man eventually needs a
        # breather; a low one means only the spent come off. At 78 the
        # equilibrium was capped for cheap positions and centres played 97.5%.
        trigger = 92.0 - 20.0 * (1.0 - self.policy) \
                  - 12.0 * float(np.clip(quality_gap, -1, 1))
        if c >= trigger: return False
        p = ((trigger - c) / max(1.0, trigger)) ** 0.85
        return rng.random() < float(np.clip(p * 2.2, 0.0, 0.95))

    def reset_game(self): self.cond = {}; self.snaps = {}

def recover_between_games(condition, natural_fitness=70.0, days_rest=7,
                          jadedness=0.0):
    """
    Natural fitness governs the RATE; stamina does not enter. Jadedness slows
    it, which is how a season grinds a player down.
    """
    rate = 0.55 + 0.75 * (natural_fitness / 100.0)
    rate *= 1.0 - 0.35 * float(np.clip(jadedness, 0.0, 1.0))
    gain = (100.0 - condition) * float(np.clip(rate * (days_rest / 7.0), 0.0, 1.0))
    return float(np.clip(condition + gain, 0.0, 100.0))

# ============================================================ SHARPNESS
CONDITION_DECAY = {
    'speed_rating': .55, 'accel_rating': .70, 'agility_rating': .60,
    'change_of_direction_rating': .60, 'jump_rating': .55,
    'power_moves_rating': .50, 'finesse_moves_rating': .50,
    'pursuit_rating': .55, 'strength_rating': .30,
}

def apply_state(player, condition=100.0):
    """The player as he actually is right now."""
    p = dict(player)
    if condition < 85.0:
        c = (85.0 - condition) / 85.0
        for k, w in CONDITION_DECAY.items():
            if k in p: p[k] = max(20.0, p[k] * (1.0 - 0.26 * w * c))
    return p

# ============================================================ JADEDNESS
def update_jadedness(jaded, snaps_played, natural_fitness=70.0,
                     expected_snaps=45.0, bye=False):
    """
    Hidden, slow to build and slow to shed. High natural fitness slows it.
    This is what makes a heavy workload cost something in December rather
    than in September.
    """
    if bye: return float(np.clip(jaded - 0.12, 0.0, 1.0))
    load = snaps_played / max(1.0, expected_snaps)
    gain = 0.020 * load * (1.0 - 0.55 * (natural_fitness - 50.0) / 50.0)
    return float(np.clip(jaded + gain - 0.006, 0.0, 1.0))

# ============================================================ INJURIES
INJURY_SHARE = {
    'CB': .1427, 'MIKE': .0465, 'WILL': .0465, 'SAM': .0465, 'WR': .1324,
    'FS': .0463, 'SS': .0463, 'LT': .0454, 'RT': .0454, 'DT': .0744,
    'TE': .0691, 'HB': .0650, 'LEDG': .0315, 'REDG': .0315, 'LG': .0295,
    'RG': .0295, 'QB': .0302, 'C': .0217, 'K': .0094, 'FB': .0067,
    'P': .0026, 'LS': .0009,
}
INJURY_TYPES = [
    ('Knee', .1826, 1.9), ('Ankle', .1451, 1.5), ('Hamstring', .1319, 1.6),
    ('Concussion', .0997, 1.3), ('Shoulder', .0498, 1.6), ('Calf', .0402, 1.5),
    ('Foot', .0393, 1.8), ('Groin', .0314, 1.5), ('Neck', .0296, 1.4),
    ('Hip', .0284, 1.5), ('Quadricep', .0255, 1.4), ('Back', .0211, 1.4),
    ('Pectoral', .0155, 2.6), ('Toe', .0138, 1.5), ('Elbow', .0114, 1.5),
    ('Hand', .0106, 1.4), ('Illness', .0182, 1.1), ('Other', .1059, 1.5),
]
_it = [t[0] for t in INJURY_TYPES]
_ip = np.array([t[1] for t in INJURY_TYPES]); _ip = _ip / _ip.sum()
_isev = {t[0]: t[2] for t in INJURY_TYPES}
INJURIES_PER_TEAM_WEEK = 2.51
# The 2.51 figure counts players RULED OUT for a game. Many in-game injuries
# never reach that - a man is shaken up, misses a series and returns. The
# per-contact roll is scaled so the men who actually miss a WEEK land on 2.51.
# Re-solved twice. First once the roll was wired into a live game, where it
# fires on BOTH sides of every contact play. Then again once ROTATION went
# live: rotating men means fewer contact events for the starters and the rate
# fell to 1.17 per team per game against a real 2.51.
_RULED_OUT_SHARE = 0.165

def condition_injury_multiplier(condition):
    """
    FM community testing at a fixed workload: 100% condition produced 8
    in-match injuries, 80% produced 20, 60% produced 87. That is roughly a
    2.4x multiplier per 20 points lost, and the nonlinearity is the point.
    """
    return float(np.exp(0.0603 * (100.0 - condition)))

# The base rate has to be set AFTER the condition multiplier, not before it.
# At a realistic in-game condition around 88 that multiplier is already ~2.0,
# so calibrating the base against 100% condition produced 8.5 players out per
# team per week against a real 2.51.
_COND_REFERENCE = 88.0

def injury_chance(player, position, contact, rate_fn, condition=100.0,
                  jaded=0.0, AVG=0.70, snaps_per_game=65.0):
    base = (INJURIES_PER_TEAM_WEEK / (snaps_per_game * 2.0)) * \
           (INJURY_SHARE.get(position, .04) / .045) * _RULED_OUT_SHARE / \
           condition_injury_multiplier(_COND_REFERENCE)
    # Durability is measured against the REAL league mean, not the 0.70
    # midpoint. Actual NFL players average 89 on injury rating, so centring on
    # 70 made every real player read as 38% less injury-prone than average and
    # pinned the league at 1.2 men out per team per game against a real 2.51.
    DUR_LEAGUE = 0.87
    dur = rate_fn(player, {'injury_rating': .60, 'tough_rating': .40})
    p = base * (1.0 + 2.0 * (DUR_LEAGUE - dur)) * (0.5 + 1.0 * contact)
    p *= condition_injury_multiplier(condition)
    p *= 1.0 + 0.45 * jaded
    return float(np.clip(p, 0.0, 0.10))

def roll_injury(player, position, contact, rng, rate_fn, condition=100.0,
                jaded=0.0, AVG=0.70, snaps_per_game=65.0):
    if rng.random() >= injury_chance(player, position, contact, rate_fn,
                                     condition, jaded, AVG, snaps_per_game):
        return None
    kind = _it[int(rng.choice(len(_it), p=_ip))]
    sev = _isev[kind]
    r = rng.random()
    if   r < .667: weeks = 1
    elif r < .880: weeks = 2
    elif r < .969: weeks = 3
    elif r < .997: weeks = int(rng.integers(4, 6))
    else:          weeks = int(rng.integers(6, 17))
    weeks = max(1, int(round(weeks * (0.92 + 0.16 * (sev - 1.5)))))
    return dict(player=player.get('pid'), position=position, kind=kind,
                weeks_out=weeks, season_ending=weeks >= 8,
                ir_eligible=weeks >= 4)

def out_this_week(injuries, week):
    return {i['player'] for i in injuries
            if i['week'] <= week < i['week'] + i['weeks_out']}
