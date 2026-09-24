"""
Player morale.

Design decisions already made:
  - Visible: current morale and the per-attribute modifier it causes.
    Hidden: WHY he is there and what would fix it (his preference weights).
  - Asymmetric. Good morale does close to nothing; bad morale bites.
  - Small on-field effect. -1 at Unhappy, capped at -3 at rock bottom.
  - Only mental / effort attributes move. Speed and strength never do.
  - Broken promises affect that player only, escalating with severity and count.

Morale runs 0-100. 50 is neutral. It moves on three clocks so it feels alive
without being twitchy.
"""
import numpy as np, pandas as pd
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n)

NEUTRAL = 50.0

# ---------------------------------------------------------------- inputs
# fast   : game to game, decays quickly, small
# slow   : accumulates over a season
# shock  : single events, large, decay slowly
FAST = {
    'win':                +1.2,
    'loss':               -1.0,
    'blowout_loss':       -2.0,
    'good_game':          +1.5,
    'bad_game':           -1.0,
}
# per week, on a clock that keeps 96.5% a week: the equilibrium of a
# constant weekly push is about 29x the push, so -1.3 a week for a losing
# season would settle a whole roster at -37. First wired, half the league
# sat Unsettled after nine weeks; these are re-set so a losing season costs
# a man about a band and being buried costs a starter-grade man two.
SLOW = {
    'losing_season':      -0.40,   # per week while under .500
    'underused':          -0.80,   # per week below his expected usage
    'well_used':          +0.35,
    'buried_on_depth':    -0.70,
}
SHOCK = {
    'benched':            -12.0,
    'made_available':     -10.0,
    'team_signed_over_him': -9.0,
    'passed_for_captain': -5.0,
    'extension_signed':   +14.0,
    'named_captain':      +10.0,
    'playoff_berth':      +8.0,
    'won_title':          +20.0,
}
DECAY = {'fast': 0.55, 'slow': 0.965, 'shock': 0.975}   # per week retention
BASE_RECOVERY = 0.02                                     # weekly pull of the baseline toward neutral

# ---------------------------------------------------------------- entitlement
# What a player thinks he is owed. A 62-overall fourth-stringer who never plays
# is not upset; he is lucky to have a job. A 92-overall who is buried is
# furious. Every status-related event is scaled by this, not just usage.
STATUS_EVENTS = {'underused', 'buried_on_depth', 'benched',
                 'passed_for_captain', 'team_signed_over_him', 'well_used'}

def entitlement(ovr, pos_rank=None, pay_rank=None, promised_start=False):
    """
    0 = expects nothing, 1 = expects to be a featured starter.
    Driven by how good he is, where he sits on his own depth chart, what he is
    paid relative to his room, and whether he was promised anything.
    """
    # rating is the main driver: below ~70 a man does not expect to start
    e = float(np.clip((ovr - 66) / 24.0, 0.0, 1.0))
    if pos_rank is not None:                      # 1 = best in his room
        e = max(e, np.clip(1.15 - 0.30*pos_rank, 0.0, 1.0))
    if pay_rank is not None:                      # paid like a starter, expects to be one
        e = max(e, np.clip(1.10 - 0.28*pay_rank, 0.0, 1.0))
    if promised_start:
        e = 1.0
    return float(np.clip(e, 0.0, 1.0))

# a broken promise is a shock whose size depends on what was broken and how often
PROMISE_SEVERITY = {
    'starting_role': 16.0, 'captaincy': 11.0, 'no_trade': 20.0,
    'extension_by': 15.0,  'no_franchise': 12.0,
}

# ---------------------------------------------------------------- state
class Morale:
    def __init__(self, player_id, baseline=NEUTRAL):
        self.pid = player_id
        self.base = baseline          # slow-moving core
        self.fast = 0.0
        self.slow = 0.0
        self.shock = 0.0
        self.trust = 1.0              # multiplies the value of your promises
        self.broken = []              # history of promises broken to HIM
        self.events = []

    @property
    def value(self):
        return float(np.clip(self.base + self.fast + self.slow + self.shock, 0, 100))

    def tick(self):
        self.fast  *= DECAY['fast']
        self.slow  *= DECAY['slow']
        self.shock *= DECAY['shock']
        # the shock bleeds into the baseline: lasting damage, not just a dip
        self.base = float(np.clip(self.base + 0.055*self.shock + 0.035*self.slow, 10, 90))
        # and the baseline recovers: a man who has had a bad stretch comes
        # back over a season if nothing new goes wrong. Without this the
        # league drifted a point or two a year and never came back
        self.base += BASE_RECOVERY * (NEUTRAL - self.base)

    def offseason(self):
        """A new season is a new season. The grudges that survive it are the
        big ones (a broken promise, a benching); the weight of a 6-11 year
        does not."""
        self.fast = 0.0; self.slow = 0.0; self.shock *= 0.5
        self.base = float(np.clip(self.base + 0.33 * (NEUTRAL - self.base), 10, 90))

    def apply(self, kind, note='', entitle=None):
        """
        entitle: 0-1, how much this player believes he is owed a role.
        Status events are multiplied by it, so a backup shrugs at things that
        would enrage a starter. Non-status events (wins, losses, contracts)
        are felt by everyone equally.
        """
        scale = 1.0
        if kind in STATUS_EVENTS and entitle is not None:
            scale = 0.08 + 0.92 * float(entitle)
        if kind in FAST:  self.fast  += FAST[kind] * scale
        elif kind in SLOW: self.slow += SLOW[kind] * scale
        elif kind in SHOCK: self.shock += SHOCK[kind] * scale
        else: raise KeyError(kind)
        self.events.append((kind, note))

    def break_promise(self, kind):
        """Severity scales with what was broken and how many times you've done it to him."""
        n = len(self.broken)
        hit = PROMISE_SEVERITY[kind] * (1.0 + 0.6*n)
        self.shock -= hit
        self.base = float(np.clip(self.base - 0.35*hit, 10, 90))
        self.trust = float(max(0.0, self.trust - (0.35 + 0.2*n)))
        self.broken.append(kind)
        self.events.append(('broken_promise', kind))
        return round(hit, 1)

# ---------------------------------------------------------------- contract dissatisfaction
def contract_pressure(surplus_m, market_apy, on_rookie_deal=False, yrs_left=2):
    """
    Underpaid relative to his own valuation drags the baseline. Computed, not
    invented: it is the surplus the valuation engine already produces.

    Two corrections the first build got wrong:
      - A player on a slotted rookie contract cannot renegotiate, and real
        rookies are not disgruntled about a deal the CBA set for them. The drag
        is heavily damped, and instead builds as he nears the end of it.
      - Being underpaid stings more the longer you are stuck with it.
    """
    if market_apy <= 0: return 0.0
    r = surplus_m / market_apy
    if r <= 0.10: return 0.0
    drag = min(16.0, 22.0 * (r - 0.10))
    if on_rookie_deal:
        drag *= 0.18 + 0.22 * max(0, 3 - yrs_left)      # bites as the deal runs out
    else:
        drag *= 1.0 + 0.10 * max(0, yrs_left - 1)
    return float(-min(18.0, drag))

# ---------------------------------------------------------------- readout
BANDS = [(78, 'Delighted'), (62, 'Happy'), (42, 'Content'),
         (28, 'Unsettled'), (15, 'Unhappy'), (0, 'Disgruntled')]

def band(v):
    for lo, name in BANDS:
        if v >= lo: return name
    return 'Disgruntled'

# only mental / effort traits move. physical never does.
AFFECTED = {
    'awareness_rating': 1.00, 'play_rec_rating': 1.00, 'cit_rating': 0.75,
    'throw_under_pressure_rating': 0.85, 'pursuit_rating': 0.80,
    'block_shed_rating': 0.70, 'tough_rating': 0.60, 'release_rating': 0.55,
    'catch_rating': 0.50, 'break_sack_rating': 0.50,
}
NEVER = ['speed_rating','accel_rating','strength_rating','agility_rating','jump_rating']

def modifier(v):
    """
    Asymmetric and small. Flat from 42 up. -1 around Unhappy, hard floor at -3.
    Half the penalty shows as a lower mean, half as wider game-to-game variance.
    """
    if v >= 42: return 0.0, 0.0
    deficit = (42 - v) / 42.0                     # 0 at 42, 1 at 0
    mean_pen = -min(3.0, 3.0 * deficit**1.35)
    variance = min(3.0, 3.2 * deficit**1.2)       # swing, not a flat drop
    return round(mean_pen, 2), round(variance, 2)

def attribute_modifiers(v):
    m, _ = modifier(v)
    if m == 0: return {}
    return {a: int(round(m*wgt)) for a, wgt in AFFECTED.items() if round(m*wgt) <= -1}

# ---------------------------------------------------------------- locker room
def locker_room_pass(players, morales, weight_captain=2.5, weight_vet=1.4):
    """
    Not everyone affects everyone. Influence flows inside a position group,
    weighted by seniority and captaincy, so an unhappy captain is corrosive
    and an unhappy fourth-stringer is not.
    """
    df = players.copy()
    df['m'] = df.pid.map(lambda p: morales[p].value if p in morales else NEUTRAL)
    for grp, d in df.groupby('grp'):
        if len(d) < 2: continue
        w = np.where(d.is_captain, weight_captain, np.where(d.years_exp >= 6, weight_vet, 1.0))
        w = w * np.clip(d.ovr / d.ovr.max(), .4, 1.0)      # better players carry more weight
        avg = float(np.average(d.m, weights=w))
        for pid, own in zip(d.pid, d.m):
            if pid not in morales: continue
            pull = (avg - own) * 0.045
            if avg < 35: pull += (avg - 35) * 0.020        # a toxic room drags harder
            morales[pid].slow += pull

# ---------------------------------------------------------------- escalation
def status(m, ovr, is_captain):
    """Escalating consequences. A marginal player cannot hold a room hostage."""
    v = m.value
    influential = is_captain or ovr >= 85
    if v >= 42: return 'settled'
    if v >= 28: return 'quietly unhappy'          # shows up only in his next negotiation
    if v >= 15: return 'publicly discontent' if influential else 'quietly unhappy'
    if len(m.broken) >= 2 or v < 8:
        return 'trade request'
    return 'locker room distraction' if influential else 'publicly discontent'

def negotiation_effect(m):
    """What his state does to his next contract talk."""
    v = m.value
    premium = 0.0 if v >= 42 else min(0.30, (42 - v) / 42 * 0.30)
    return dict(demand_premium=round(premium, 3),
                trust=round(m.trust, 2),
                will_discount=v >= 55 and m.trust > 0.6)

# ---------------------------------------------------------------- demo
if __name__ == '__main__':
    S = pd.read_csv(_p('league_seed_2026.csv'), low_memory=False)
    V = pd.read_csv(_p('player_valuations_2026.csv'), low_memory=False)
    S['ovr'] = pd.to_numeric(S.overall, errors='coerce')

    print('=== MORALE -> ATTRIBUTE MODIFIER (the visible column) ===')
    print(f'{"morale":>7s}  {"band":<16s} {"mean":>6s} {"swing":>6s}   affected attributes')
    for v in [85, 70, 55, 45, 38, 30, 22, 12, 4]:
        m, sw = modifier(v)
        mods = attribute_modifiers(v)
        txt = ', '.join(f'{a.replace("_rating","")} {d}' for a, d in list(mods.items())[:5]) or 'none'
        print(f'{v:7.0f}  {band(v):<16s} {m:6.2f} {sw:6.2f}   {txt}')
    print(f'\n  never affected: {", ".join(n.replace("_rating","") for n in NEVER)}')

    print('\n=== ENTITLEMENT: what a player thinks he is owed ===')
    print(f'  {"player":<38s} {"entitle":>7s}')
    for lbl, ov, rank, promised in [
        ('92 ovr WR1, best in his room', 92, 1, False),
        ('84 ovr WR2', 84, 2, False),
        ('74 ovr WR4', 74, 4, False),
        ('66 ovr WR5, fourth-stringer', 66, 5, False),
        ('66 ovr WR5, PROMISED a start', 66, 5, True)]:
        print(f'  {lbl:<38s} {entitlement(ov, pos_rank=rank, promised_start=promised):7.2f}')

    print('\n=== SAME SEASON, THREE DIFFERENT PLAYERS ===')
    script = [('loss','wk1'),('loss','wk2'),('bad_game','wk2'),('blowout_loss','wk3'),
              ('underused','wk3'),('underused','wk4'),('benched','wk5'),
              ('underused','wk6'),('losing_season','wk6'),('losing_season','wk7'),
              ('underused','wk8'),('losing_season','wk8'),('underused','wk9')]
    for lbl, ov, rank, promised in [
        ('star WR, 92 ovr, WR1', 92, 1, False),
        ('rotational WR, 78 ovr, WR3', 78, 3, False),
        ('backup WR, 66 ovr, WR5', 66, 5, False),
        ('backup WR, 66 ovr, PROMISED a start', 66, 5, True)]:
        m = Morale('x', baseline=58)
        e = entitlement(ov, pos_rank=rank, promised_start=promised)
        for ev, note in script:
            m.apply(ev, note, entitle=e); m.tick()
        mm, _ = modifier(m.value)
        print(f'  {lbl:<38s} entitle {e:.2f} -> morale {m.value:5.1f} '
              f'({band(m.value):<11s}) mod {mm:5.2f}  {status(m, ov, False)}')

    print('\n=== BREAKING PROMISES TO THE SAME MAN ===')
    m2 = Morale('P0002', baseline=64)
    for k in ['captaincy', 'starting_role', 'no_trade']:
        hit = m2.break_promise(k)
        ne = negotiation_effect(m2)
        print(f'  broke {k:<15s} -{hit:5.1f}  morale {m2.value:5.1f} ({band(m2.value)})'
              f'  trust {ne["trust"]:.2f}  next deal +{ne["demand_premium"]*100:.0f}%'
              f'  -> {status(m2, 90, True)}')

    print('\n=== UNDERPAID DRAG, computed from the valuation engine ===')
    for name in ['Puka Nacua','Caleb Williams','Kobie Turner','Brian Branch']:
        r = V[V.full_name == name]
        if not len(r): continue
        r = r.iloc[0]
        rook = bool(pd.notna(r.get('pick')) and (r.get('contract_age', 9) or 9) < 4 and r.yrs == 4)
        drag = contract_pressure(r.surplus, r.val_apy, on_rookie_deal=rook,
                                 yrs_left=int(r.get('contract_years_left', 2) or 2))
        base = NEUTRAL + drag
        print(f'  {name:16s} earns ${r.apy:5.2f}M, valued ${r.val_apy:5.2f}M'
              f'  {"[rookie deal]" if rook else "[veteran deal]":15s}'
              f' -> baseline {base:5.1f} ({band(base)}), mod {modifier(base)[0]:.2f}')

    print('\n=== LOCKER ROOM: one unhappy captain vs one unhappy backup ===')
    grp = S[(S.team == 'KC') & (S.madden_position == 'WR')].head(6).copy()
    grp['pid'] = [f'K{i}' for i in range(len(grp))]
    grp['grp'] = 'WR'
    grp['years_exp'] = pd.to_numeric(grp.years_exp, errors='coerce').fillna(2)
    for who, label in [(0, 'the best receiver, a captain'), (len(grp)-1, 'the sixth receiver')]:
        mor = {p: Morale(p, 60) for p in grp.pid}
        grp['is_captain'] = [i == 0 for i in range(len(grp))]
        mor[grp.pid.iloc[who]].base = 8
        before = {p: mor[p].value for p in grp.pid}
        for _ in range(6): locker_room_pass(grp, mor)
        after = {p: mor[p].value for p in grp.pid}
        others = [p for p in grp.pid if p != grp.pid.iloc[who]]
        drop = np.mean([before[p] - after[p] for p in others])
        print(f'  {label:30s} -> rest of the room drops {drop:.1f} morale over 6 weeks')
