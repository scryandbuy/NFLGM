"""
The game loop.

Wraps play resolution into drives, downs, field position and a clock. This is
the gate on fatigue, injuries and stat attribution - none of them mean anything
without games.

Every constant is computed from real play-by-play (2020-2025 for most, 2025
alone for kickoffs because the rules changed).

  DRIVES        21.73 per game, 5.96 plays each, 1.84 first downs each
  OUTCOMES      punt 35.18%, TD 22.60%, FG 15.35%, turnover 10.23%,
                end of half 7.03%, downs 5.60%, missed FG 2.66%,
                opp TD 1.11%, safety 0.25%
  PLAYS         123.0 offensive per game, 172.9 including special teams
  CLOCK         pass 23.2s (complete 31.4, incomplete 10.2), run 34.7s,
                punt 9.4s, FG 4.0s, kickoff 5.8s
  FOURTH DOWN   14.12 per game; go-for-it and conversion tables below
  FIELD GOALS   overall 85.0%, 3.91 attempts per game
  PUNTS         7.65 per game, 47.2 gross (sd 9.8), 7.5% touchback,
                returned on 35%, mean return 4.23
  KICKOFFS      2025 rules: 20.7% touchback, returned on 73.9%, 26.1 avg
"""
import numpy as np
import weather as W
ENV = W.CLEAR

# ============================================================ CLOCK
SEC = {'complete': 31.4, 'incomplete': 10.2, 'run': 34.7, 'sack': 30.0,
       'scramble': 34.7, 'punt': 9.4, 'field_goal': 4.0, 'kickoff': 5.8,
       'penalty': 14.4, 'interception': 12.0, 'drop': 10.2, 'fumble': 12.0}
QUARTER = 900
HALF = 1800
GAME = 3600

def play_seconds(result, clock_stopped=False, hurry=False, timeout=False):
    s = SEC.get(result, 25.0)
    if clock_stopped: s = min(s, 8.0)
    if hurry: s *= 0.65     # a two-minute drill runs about 17 seconds a snap against 25 to 27 at the normal pace
    if timeout: s = min(s, 6.0)     # the clock stops the moment it is called
    return float(s)


# ============================================================ TIMEOUTS
# Three a half, each. Every published win-probability model uses them and this
# engine tracked none, so both sides were assumed to hold all three forever -
# which makes a two-minute drill far too easy and a defensive stop far too
# cheap.
#
# Who spends them, and why: the DEFENCE burns them when it is behind and needs
# the ball back, which is the only reason a defence ever calls one late. The
# OFFENCE spends them driving at the end of a half, to stop a clock that the
# play itself did not stop. Nobody spends one in the first quarter.
TIMEOUTS_PER_HALF = 3


class Timeouts:
    """Three a half each. Who has them left is real state, not an assumption."""

    def __init__(self):
        self.left = {'home': TIMEOUTS_PER_HALF, 'away': TIMEOUTS_PER_HALF}

    def halftime(self):
        self.left = {'home': TIMEOUTS_PER_HALF, 'away': TIMEOUTS_PER_HALF}

    def use(self, side):
        if self.left.get(side, 0) <= 0:
            return False
        self.left[side] -= 1
        return True

    def edge(self, side):
        """Timeout advantage for this side - the feature the model wants."""
        other = 'away' if side == 'home' else 'home'
        return self.left.get(side, 0) - self.left.get(other, 0)

    def __repr__(self):
        return f"<TO home {self.left['home']} away {self.left['away']}>"

# ============================================================ FOURTH DOWN
# Real go-for-it rate by distance and field zone.
GO_RATE = {
    #            FG range  midfield  own 30-50  backed up
    '1':   dict(fg_range=.825, midfield=.920, own=.534, backed=.211),
    '2':   dict(fg_range=.506, midfield=.705, own=.199, backed=.101),
    '3-4': dict(fg_range=.268, midfield=.496, own=.107, backed=.067),
    '5-7': dict(fg_range=.120, midfield=.236, own=.083, backed=.048),
    '8+':  dict(fg_range=.085, midfield=.116, own=.073, backed=.040),
}
FOURTH_CONV = {'1': .675, '2': .588, '3-4': .510, '5-7': .442, '8+': .247}

def fourth_band(ydstogo):
    if ydstogo <= 1: return '1'
    if ydstogo <= 2: return '2'
    if ydstogo <= 4: return '3-4'
    if ydstogo <= 7: return '5-7'
    return '8+'

def fourth_zone(yardline_100):
    """yardline_100 = yards to the opponent's end zone."""
    if yardline_100 <= 35: return 'fg_range'
    if yardline_100 <= 50: return 'midfield'
    if yardline_100 <= 70: return 'own'
    return 'backed'

def fourth_down_decision(yardline_100, ydstogo, score_diff, secs_left, rng,
                         aggression=0.5, timeout_edge=0, use_wp=True):
    """
    go, field_goal or punt.

    NOW DECIDED ON WIN PROBABILITY. The GO_RATE table below is what real
    clubs DO; decisions.fourth_down is what maximises the chance of winning,
    and the literature is unanimous that those are not the same thing - Yam
    and Lopez put the gap at about 0.4 wins a season, Baldwin at clubs going
    roughly half as often as they should.

    The table cannot express that gap, because it only knows down, distance
    and field zone. It has no idea what the score is, how much clock is left
    or who has timeouts, so it cannot tell a coach that trailing by ten with
    four minutes left changes everything. The model can.

    The table is kept and still reachable with use_wp=False, because it is a
    faithful record of observed behaviour and worth comparing against.
    """
    if use_wp:
        import decisions as DEC
        r = DEC.fourth_down(score_diff, max(1.0, secs_left), yardline_100,
                            ydstogo, aggression=aggression,
                            is_home=1)
        if r['call'] == 'go':
            return 'go'
        if r['call'] == 'field_goal':
            # HOW FAR CLUBS ACTUALLY KICK FROM. Field goal accuracy read 80.5%
            # against a real 85.0%, and the per-distance curve was already
            # right - 93.1% from 30-39 against 94.3%, 76.7% from 40-49 against
            # 77.9%. The kicker was fine; the ATTEMPTS were wrong. Mean attempt
            # distance ran 45.7 yards against a real 39.5, with a third of them
            # from 50-59 against a real 22%.
            #
            # Real clubs kick 60+ on 1% of attempts. Allowing anything inside
            # the 45 is a 62-yarder, and they simply do not take those unless
            # the half is ending or they are chasing the game.
            limit = 41 if secs_left > 300 or score_diff >= 0 else 44
            if secs_left < 20:
                limit = 45                 # the last play of a half
            if yardline_100 <= limit:
                return 'field_goal'
            # Out of range. Vetoing the kick does NOT make it a punt - the
            # model already weighed going against punting, and forcing the punt
            # put them at 40.7% of drives against a real 35.2%. Fall back to
            # whichever of the two it preferred.
            return 'go' if r['wp_go'] > r['wp_punt'] else 'punt'
        # TRUST THE MODEL WHEN IT SAYS PUNT. Bolting the old table's rule on
        # top - kick anything inside the 38 - overrode a decision the model
        # had already weighed, and field goals jumped to 18.3% of drives
        # against a real 15.4% while punts fell to 28.7% against 35.2%.
        return 'punt'

    band, zone = fourth_band(ydstogo), fourth_zone(yardline_100)
    p_go = GO_RATE[band][zone] * (0.70 + 0.60 * aggression)
    # trailing late, you have no choice
    if secs_left < 300 and score_diff < 0:
        p_go = max(p_go, 0.55 if score_diff < -8 else 0.35)
    if secs_left < 120 and score_diff < 0 and yardline_100 > 40:
        p_go = max(p_go, 0.90)
    if rng.random() < p_go: return 'go'
    # 45 yards out is a 62-yard attempt. Real clubs kick from about the 38 or
    # closer (a 55-yarder); beyond that they punt. Allowing 62-yarders put
    # missed field goals at 4.24% against a real 2.66%.
    if yardline_100 <= 38: return 'field_goal'
    if secs_left < 10 and yardline_100 <= 45: return 'field_goal'
    return 'punt'

# A club can finish an offseason with no kicker, no punter or no return man.
# dict.get(key, {}) hands back None when the key EXISTS holding None - which
# is exactly what build_roster writes for an empty slot - so every one of
# these used `or {}` instead. An empty dict rates as an average man, which is
# the right stand-in for a body the club will sign before Sunday.

# ============================================================ FIELD GOALS
# Real made% by distance.
# Re-solved on real kickers, whose ratings sit above the flat-70 clones the
# curve was first fitted against.
# by distance, at the modern rate: kickers made about 84-86% overall in 2023-24,
# roughly 81% from 40-49 and 70% from 50 and beyond. The earlier table was a
# 2010s one and the league kicked 81% with it against a real 85.
FG_PCT = [(29, .975), (34, .955), (39, .905), (44, .840), (49, .785),
          (54, .720), (99, .590)]

def fg_probability(distance, kicker=None, rate_fn=None, AVG=0.70):
    base = next(p for d, p in FG_PCT if distance <= d)
    if kicker is not None and rate_fn is not None:
        acc = rate_fn(kicker, {'kick_acc_rating': .75, 'awareness_rating': .25})
        pwr = rate_fn(kicker, {'kick_power_rating': 1.0})
        base *= 1.0 + 0.16 * (acc - AVG)
        if distance >= 50:                 # power only matters from distance
            base *= 1.0 + 0.55 * (pwr - AVG)
    return float(np.clip(base, 0.02, 0.995))

def attempt_field_goal(yardline_100, kicker, rng, rate_fn):
    dist = yardline_100 + 17               # 10 end zone + 7 snap
    p_make = fg_probability(dist, kicker, rate_fn) * (ENV.kick_mult if dist >= 35 else 1.0 - 0.3 * (1.0 - ENV.kick_mult))
    # the special teams coordinator: a good one keeps the kicker near his number, a poor one adds variance either way
    kn = float(kicker.get('st_noise', 1.0)) if isinstance(kicker, dict) else 1.0
    if kn != 1.0:
        p_make = float(np.clip(0.5 + (p_make - 0.5) / kn, 0.02, 0.99))
    made = rng.random() < p_make
    return dict(type='field_goal', distance=dist, made=made,
                points=3 if made else 0)

# ============================================================ THE TRY
# A touchdown is six. What follows is a separate decision and a separate
# play, so the extra point can be missed and the two-point try can fail.
#
# The kick is a 33-yard field goal - ball on the 15, seven yards back to the
# hold, ten yards of end zone - so it runs through the same distance curve and
# the same kicker ratings as every other kick rather than a flat league rate.
#
# The two-point try is ONE REAL SNAP from the two, resolved by the same play
# engine as any other goal-line play. The conversion rate is therefore an
# output of the rosters and the red zone physics, not a constant. It is not
# calibrated to the real 47.9% and should not be until the red zone
# touchdown rate is fixed, since both come from the same per-play numbers.

# Leads (from the scoring team's view, counting the six just scored) where the
# accepted chart says go for two. Late game only: before the fourth quarter
# the chart has no opinion and teams kick.
TWO_POINT_GO = (-18, -16, -10, -5, -2, 1, 4, 5)

def two_point_decision(lead_after_td, quarter, secs_left=None,
                       conv_prob=None, aggression=0.5):
    """
    Kick or go, on win probability rather than a chart.

    The chart below gated on the fourth quarter and produced tries on 2.5% of
    touchdowns against a real 6.4%, because a chart cannot price the thing
    that actually decides it: the two options are worth 0.957 points and 0.950
    points, so it is an active choice every time and what tips it is score AND
    clock together.

    TWO_POINT_GO is kept as the fallback when no clock is available.
    """
    if secs_left is None:
        if quarter < 4: return False
        return int(round(lead_after_td)) in TWO_POINT_GO
    import decisions as DEC
    r = DEC.two_point(lead_after_td, max(1.0, secs_left),
                      conv_prob=conv_prob if conv_prob else DEC.TWO_RATE,
                      aggression=aggression)
    return r['call'] == 'two'

def attempt_extra_point(kicker, rng, rate_fn):
    made = rng.random() < fg_probability(33, kicker, rate_fn)
    return dict(type='extra_point', distance=33, made=bool(made),
                points=1 if made else 0)

def attempt_two_point(offense, defense, rng, resolve_fn, call_off, call_def,
                      rate_fn, off_state=None, def_state=None):
    """
    One snap from the two. Deliberately NOT fed to state.observe: the
    adjustment engine reads a rolling four-series window of normal downs, and
    a goal-line try is not one of those.
    """
    oc = call_off(1, 2, 0, 2, rng)
    dc = call_def(oc, 1, 2, rng, 2)
    off_f, _ = field_units(offense, off_state, rng, True, oc.get('personnel'))
    def_f, _ = field_units(defense, def_state, rng, False, dc.get('personnel'))
    if not oc.get('is_pass'):
        backs = offense.get('backs') or [offense.get('rb')]
        rb, _rk = pick_runner([b for b in backs if b], off_state, rng)
        if rb is not None: off_f = dict(off_f, rb=rb)
    out = resolve_fn(off_f, def_f, oc, dc, 2, rng)
    good = out.get('type') in ('run', 'complete', 'scramble') and \
           float(out.get('yards', 0.0)) >= 2.0
    return dict(type='two_point', play=out.get('type'), made=bool(good),
                points=2 if good else 0)

# ============================================================ PUNTS
# Real: returned on 35% of punts, mean 11.5 yards WHEN returned (the 4.23
# figure counted all punts including fair catches), p90 19, max 97, and 0.36%
# go for a touchdown.
PUNT = dict(gross=47.2, sd=8.5, blocked=.0043,
            # real: 45% returned, mean return 10.4; the rest fair caught,
            # downed, out of bounds or a touchback
            return_rate=.45, return_mean=10.4, return_p90=19, td_rate=.0036,
            # A FULL swing from a league-average leg. The 47.2 league gross
            # includes every kick shortened from midfield, so the leg is
            # longer than the mean. Real punters rate well above 0.70 on power,
            # which the multiplier below turns into their extra distance.
            full=49.0,
            # where he tries to drop it when a full swing would carry through
            # the end zone, and how far an average leg misses that spot
            aim=12.0, aim_sd=7.0,
            # a ball that comes down inside the 10 and is not caught bounces
            # toward the goal; gunners down it unless it gets there first
            roll_mean=6.0, roll_sd=4.0)

def punt(yardline_100, punter, returner, rng, rate_fn, AVG=0.70):
    """
    The punter READS THE FIELD, and so does the returner.

    This used to kick a full gross from wherever the punter stood and touched
    back only if the ball crossed the goal, so a punt from midfield landed at
    the 3 every time: 9.8% of drives started inside the own 10 (real is a few
    percent) and safeties ran three times the real rate off the sacks and
    losses that followed. From midfield a real punter shortens the kick and
    drops it around the 10; the distance is a decision made from field
    position and his own leg, not a constant. At the other end the returner
    decides what to do with a ball coming down near his goal line: fair catch
    it, return it, or let it bounce and hope for the touchback. Every real
    touchback is one of those decisions going the kicking team's way.
    """
    if rng.random() < PUNT['blocked']:
        return dict(type='punt', blocked=True, net=0, origin=yardline_100,
                    new_yardline=100 - yardline_100)
    pwr = rate_fn(punter, {'kick_power_rating': .70, 'kick_acc_rating': .30})
    acc = rate_fn(punter, {'kick_acc_rating': 1.0})
    full = rng.normal(PUNT['full'] * (1.0 + 0.30 * (pwr - AVG)) * ENV.punt_mult, PUNT['sd'])
    pooch = False
    if yardline_100 - full < PUNT['aim']:
        # a full swing goes into or through the end zone: drop it short.
        # Accuracy decides how close to the spot he actually lands it.
        pooch = True
        miss = rng.normal(0.0, PUNT['aim_sd'] * (1.0 - 0.6 * (acc - AVG)))
        gross = max(15.0, yardline_100 - PUNT['aim'] + miss)
    else:
        gross = full
    land = yardline_100 - gross
    touchback = land <= 0
    ret = 0.0
    how = 'touchback'
    if not touchback:
        if land < 10:
            # THE RETURNER'S CALL. Deep in his own end he rarely runs it
            # back; the closer to the goal the more he lets it go, because a
            # bounce into the end zone is worth twenty yards to him.
            let_go = rng.random() < (0.85 if land < 5 else 0.35)
            if let_go:
                roll = max(0.0, rng.normal(PUNT['roll_mean'], PUNT['roll_sd']))
                if land - roll <= 0:
                    touchback = True
                else:
                    land -= roll; how = 'downed'
            else:
                how = 'fair_catch'
        elif rng.random() < PUNT['return_rate']:
            how = 'return'
            skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30,
                                       'juke_move_rating': .25})
            # shape/scale solved against mean 10.4 and p90 19, with a long
            # right tail so 0.36% reach the end zone
            ret = max(0.0, rng.gamma(1.9, 5.5) * (1.0 + 0.9 * (skill - AVG)))
        else:
            how = 'fair_catch'
    if touchback:
        return dict(type='punt', blocked=False, touchback=True, how='touchback',
                    gross=round(float(gross), 1), pooch=pooch,
                    origin=yardline_100, net=round(float(yardline_100 - 20), 1),
                    new_yardline=80)       # opponent's own 20
    # A return brings the ball OUT, toward the kicking team's goal, so it
    # SHORTENS the receiving team's field. This was + ret: every punt return
    # in the engine's history pushed the returner backwards by the length of
    # his own return, and the punt net came out longer than the gross.
    new = float(np.clip(100 - land - ret, 1, 99))
    return dict(type='punt', blocked=False, touchback=False, pooch=pooch, how=how,
                gross=round(float(gross), 1), ret=round(float(ret), 1),
                land=round(float(land), 1), origin=yardline_100,
                net=round(float(yardline_100 - (100 - new)), 1),
                new_yardline=round(new, 0))

# ============================================================ KICKOFFS
# 2026 DYNAMIC KICKOFF. The rule has changed every year since 2024, so older
# seasons describe a game that no longer exists: touchbacks ran 73.0% in 2023,
# 64.2% in 2024, 20.7% in 2025 and 15.5% through the start of 2026.
#
# Under the current rule the kicker kicks from his own 35, coverage waits at the
# opponent's 40, and a kick reaching the end zone in the air is a touchback out
# to the RECEIVING TEAM'S OWN 35 - not the 30, which is what the first build
# used. The live 2026 data confirms it: the mean drive start after a touchback
# is the own 35.0.
#
# 2026-specific tweaks also in effect: an onside kick may be declared at any
# point in the game, only five receiving players must have a foot on the
# restraining line (was six), and a touchback on a kickoff from the 50 after
# penalty enforcement is spotted at the 20 rather than the 35.
KICKOFF = dict(touchback=.155, return_rate=.799, return_mean=26.9,
               touchback_to=65,            # receiving team's own 35
               touchback_from_50=80,       # own 20, the 2026 anti-loophole rule
               onside_recovery=.0645)      # under the dynamic kickoff

def kickoff(returner, rng, rate_fn, AVG=0.70, from_50=False):
    if rng.random() < KICKOFF['touchback']:
        spot = KICKOFF['touchback_from_50'] if from_50 else KICKOFF['touchback_to']
        return dict(type='kickoff', touchback=True, new_yardline=spot)
    skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30,
                               'juke_move_rating': .25})
    ret = rng.gamma(2.4, KICKOFF['return_mean'] / 2.4) * (1.0 + 0.8 * (skill - AVG))
    # the landing zone runs from the goal line to the 20, so a returned kick
    # starts from roughly the 5 and the return is measured from there
    start = 5.0 + ret
    return dict(type='kickoff', touchback=False, ret=round(float(ret), 1),
                new_yardline=float(np.clip(100 - start, 1, 99)))

# ============================================================ TEAM STATE
class TeamState:
    """
    Live health for one team. Condition and injuries were built but nothing
    called them, so nobody tired, nobody rotated and nobody got hurt during an
    actual game. This is what connects them.
    """
    def __init__(self, roster, policy=0.5, plan=None, coach=None, scheme=None):
        import health as H, gameplan as GP, adjust as AD, targets as TG
        self.roster = roster
        self.plan = plan if plan is not None else GP.base_plan(coach)
        # the plan he walks in with, kept so every game starts from it
        self.base_plan = self.plan.copy()
        self.coach = coach or {}
        self.scheme = scheme
        self.mem = AD.GameMemory()
        # Walsh's opener, run before the defence can counter. Off-script
        # performance is measurably worse for some callers: Shanahan's 2022
        # 49ers had +0.32 passing EPA on script and -0.10 off it.
        self.script = AD.Script(length=int((coach or {}).get('script_length', 15)),
                                off_script_skill=float((coach or {}).get(
                                    'off_script_skill', 0.5)))
        self.last_adjustment = None      # what the OTHER side just did to us
        self.chart = None
        self.cond = H.Condition(policy)
        self.jaded = {}          # pid -> 0-1, carries across a season
        self.injuries = []       # this game's injuries
        self.cov_memory = {}     # what his coverage calls have produced
        self.out = set()         # unavailable right now
        self.snaps = {}

    def available(self, group, position):
        """Men at this position who are not hurt, deepest-first order kept."""
        return [p for p in group if p.get('pid') not in self.out] or list(group)

    def pick(self, group, position, rng, stamina_key='stamina_rating'):
        """
        Who takes this snap. Walks the depth chart until someone is fresh
        enough to go - which is what actually produces rotation.
        """
        import health as H
        men = self.available(group, position)
        for rank, p in enumerate(men):
            pid = p.get('pid', f'{position}{rank}')
            gap = 0.6 if rank == 0 and len(men) > 1 else 0.0
            if not self.cond.needs_rest(pid, position, rng,
                                        p.get(stamina_key, 70.0), gap):
                return p, rank
        return men[-1], len(men) - 1

    def snap(self, player, position, on_field=True):
        import health as H
        pid = player.get('pid', position)
        if on_field:
            self.cond.play(pid, position, player.get('stamina_rating', 70.0), effort=getattr(self, 'road_stamina', 1.0))
            self.snaps[pid] = self.snaps.get(pid, 0) + 1
        else:
            self.cond.rest(pid, position)

    def state(self, player, position):
        """The player as he actually is, condition applied."""
        import health as H
        pid = player.get('pid', position)
        return H.apply_state(player, self.cond.get(pid))

    def hurt(self, player, position, contact, rng, rate_fn, week=1):
        import health as H
        pid = player.get('pid', position)
        # A man already ruled out cannot be hurt again. Without this the same
        # back was injured three times in one game.
        if pid in self.out:
            return None
        inj = H.roll_injury(player, position, contact, rng, rate_fn,
                            condition=self.cond.get(pid),
                            jaded=self.jaded.get(pid, 0.0))
        if inj:
            inj['week'] = week
            self.injuries.append(inj)
            self.out.add(pid)
        return inj

    def rebuild_chart(self):
        """Order every position group by POSITION-SPECIFIC rating."""
        import targets as TG
        groups = {}
        for key, pos in (('wr', 'WR'), ('ol', 'LT'), ('dl', 'DT'),
                         ('lb', 'MIKE'), ('db', 'CB')):
            if key in self.roster:
                groups[key] = TG.order_depth(self.roster[key], pos,
                                             self.scheme, self.out)
        self.chart = groups
        return groups

    def sideline_recovery(self, snaps=30):
        """
        This unit is OFF THE FIELD while the other side plays. Real players
        recover on the bench between series; without this, condition collapsed
        to a mean of 53 by the end of a game - with some men at zero - which
        drove the injury multiplier to 16.7x and produced 4-5 men ruled out per
        team per game against a real 2.51.
        """
        for pid in list(self.cond.cond):
            self.cond.rest(pid)
            for _ in range(max(0, int(snaps * 0.55)) // 6):
                self.cond.rest(pid)

    def new_series(self):
        self.mem.new_series()

    def observe(self, off_call, def_call, outcome):
        self.mem.record(off_call, def_call, outcome)

    def remember_coverage(self, call, yards, sack=False, turnover=False):
        """
        What has been WORKING. A coordinator leans on a call that is getting
        stops and drops one that is not, and he does it inside the game rather
        than waiting for the film.

        Kept as a running score per call, decayed so an early stop does not
        justify the same call all afternoon.
        """
        if not call:
            return
        good = -0.55 if turnover or sack else (0.28 if yards >= 7 else
                                               (-0.30 if yards <= 2 else 0.0))
        for k in list(self.cov_memory):
            self.cov_memory[k] *= 0.93
        # a NEGATIVE outcome for the offence is a positive for this call, so
        # the sign flips: the memory is the defence's, not the offence's
        self.cov_memory[call] = float(np.clip(
            self.cov_memory.get(call, 0.0) - good, -1.2, 1.2))

    def adjust(self, quarter=1, rng=None):
        """Read the trends and modify THE PLAN. Returns what changed."""
        if rng is None:
            import numpy as _np
            rng = _np.random.default_rng()
        import adjust as AD, gameplan as GP
        skill = float(self.coach.get('adjust_skill', 0.5))
        aggr = float(self.coach.get('adjust_willingness', 0.5))
        trends = AD.detect(self.mem, skill=skill)
        ctr = AD.respond(trends, skill=skill, aggressiveness=aggr,
                         rng=rng)
        if not ctr:
            return []
        self.plan, applied = GP.adjust_plan(self.plan, ctr, skill, 0.55, quarter)
        if applied:
            self.last_adjustment = ctr
        return applied

    def end_game(self, rng, expected_snaps=45.0, bye=False):
        """Recovery and jadedness roll forward between games."""
        import health as H
        self.last_snaps = dict(self.snaps)     # keep the game log readable
        for pid, n in self.snaps.items():
            self.jaded[pid] = H.update_jadedness(self.jaded.get(pid, 0.0), n,
                                                 70.0, expected_snaps, bye)
        self.cond.reset_game()
        self.snaps = {}
        self.injuries = []
        self.cov_memory = {}
        # A GAME PLAN IS FOR A GAME. Adjustments made in one game (a max
        # protect with an 80/16/4 depth mix after a pressure read, a man
        # lean, a shell shift) were carried into the next and the next, so a
        # club that got pressured in September was throwing screens in
        # December: the shallow drift across a season. Each game now starts
        # from the plan the coach walks in with; what carries between games
        # is what he learned, not what he did about it.
        import gameplan as GP, adjust as AD
        if getattr(self, 'base_plan', None) is not None:
            travel, target, bracket = self.plan.travel, self.plan.travel_target, self.plan.bracket
            self.plan = self.base_plan.copy()
            self.plan.travel, self.plan.travel_target, self.plan.bracket = travel, target, bracket
        self.mem = AD.GameMemory()
        self.last_adjustment = None
        self.seq = {'run_hot': 0.0}
        # THE OUT LIST WAS NEVER CLEARED. hurt() refuses to roll for a man
        # already on it, so once a player was hurt he stopped being able to be
        # hurt again FOR THE REST OF THE SEASON - and so did everyone else, one
        # by one, until almost nobody on the roster could get injured at all.
        # Week one produced about six injuries a team and the season averaged
        # 0.96 against a real 2.51; the rate was never the problem.
        #
        # Who is ACTUALLY unavailable is the League's business - it holds
        # out_until on the player and the season rebuilds the units from men
        # who are fit. This list only exists to stop the same man being hurt
        # twice inside one game, so it belongs to the game and dies with it.
        self.out = set()

# ============================================================ DRIVE
def _resolve_live_penalty(dr, pen, out, oc):
    """
    A foul during or after the play. Returns 'replaced' if the penalty is
    taken instead of the play, 'added' if it is tacked on after it, None if
    declined.

    THE OFFENCE CHOOSES. A defensive foul during the play is an option: take
    the yards and the automatic first down, or keep a play that did better.
    A touchdown stands. A dead-ball foul after the whistle is not a choice -
    it is added to whatever the play produced.
    """
    import events as E
    yards = float(pen['yards'])
    gained = float(out.get('yards') or 0.0)
    play_first = gained >= dr.togo or bool(out.get('touchdown'))
    turnover = out.get('type') == 'interception'
    if pen['on_offense']:
        if E.PEN_INFO[pen['penalty']]['phase'] == 'post':
            # after the whistle: the result stands and they walk back
            dr.log_pen_after = yards
            return 'added'
        # during the play (grounding, a face mask by a blocker): the play is
        # wiped and the offence is set back from the previous spot
        dr.yardline = min(99.0, dr.yardline + yards)
        dr.togo += yards
        if pen['penalty'] == 'Intentional Grounding':
            dr.down += 1                          # loss of down
        return 'replaced'
    # defensive foul
    if out.get('touchdown'):
        return None                               # six beats fifteen
    if E.PEN_INFO[pen['penalty']]['phase'] == 'post':
        # dead ball: added to the play result from where it ended
        dr.log_pen_after = -yards
        dr.log_pen_first = bool(pen['auto_first'])
        return 'added'
    # live-ball defensive foul: the better of the two, and a turnover is
    # always wiped by an accepted flag. Interference and illegal contact are
    # the exception: they are called BECAUSE the ball did not arrive, so the
    # flag is the play. Drawing them independently of the outcome and then
    # letting the offence decline them on completions produced 0.34 a game
    # against a real 1.05.
    pen_first = pen['auto_first'] or yards >= dr.togo
    take = turnover or (pen_first and not play_first) or \
        (pen_first == play_first and yards > gained) or \
        pen['penalty'] in ('Defensive Pass Interference', 'Illegal Contact')
    if not take:
        return None
    gained_p = min(yards, dr.yardline - 1)
    dr.yardline -= gained_p
    if pen_first:
        dr.down, dr.togo = 1, min(10.0, dr.yardline); dr.first_downs += 1
    else:
        dr.togo -= gained_p
    return 'replaced'

class Drive:
    """One possession: downs, field position and the plays that move them."""
    def __init__(self, offense, defense, start_yardline, clock, quarter,
                 score_diff, rng):
        self.off, self.deff = offense, defense
        self.yardline = float(start_yardline)     # yards to opponent end zone
        self.down, self.togo = 1, 10
        self.clock, self.quarter = clock, quarter
        self.score_diff = score_diff
        self.rng = rng
        self.plays, self.first_downs = 0, 0
        self.start = float(start_yardline)        # where it began, for analysis
        self.best = float(start_yardline)         # closest it ever got
        self.result, self.points = None, 0
        self.try_result = None
        self.log = []

def _advance(dr, gained):
    """Apply yardage, update downs and field position. Whole yards only."""
    gained = float(np.round(gained))
    # a dead-ball foul tacked on after the play (see _resolve_live_penalty)
    after = getattr(dr, 'log_pen_after', 0.0)
    if after:
        gained += after
        dr.log_pen_after = 0.0
        if getattr(dr, 'log_pen_first', False):
            dr.log_pen_first = False
            dr.yardline -= gained
            dr.best = min(dr.best, max(0.0, dr.yardline))
            if dr.yardline <= 0:
                dr.result, dr.points = 'Touchdown', 6
                return True
            dr.down, dr.togo = 1, min(10, dr.yardline)
            dr.first_downs += 1
            return False
    dr.yardline -= gained
    dr.togo -= gained
    dr.best = min(dr.best, max(0.0, dr.yardline))
    if dr.yardline <= 0:
        # Six. The try is resolved at the end of run_drive, where the kicker
        # and the play engine are both in scope.
        dr.result, dr.points = 'Touchdown', 6
        return True
    if dr.yardline >= 100:
        dr.result, dr.points = 'Safety', -2
        return True
    if dr.togo <= 0:
        dr.down, dr.togo = 1, min(10, dr.yardline)
        dr.first_downs += 1
    else:
        dr.down += 1
    return False

# Eleven men a side. QB + RB + 5 OL + 3 WR/TE on offence; 4 DL + 2 LB + 5 DB
# in nickel, which is the league's base defence. The first build fielded five
# receivers, five linemen and four linebackers every snap - sixteen defenders -
# which made every backup a starter and flattened the snap distribution.
# Real carry share by rank within a team-season: 48.9 / 22.9 / 11.4 / 6.9 / 3.7
# (the third-ranked ball carrier on a typical team is the QUARTERBACK, at 52
# carries, which scrambles already supply).
CARRY_SHARE = [0.56, 0.24, 0.13, 0.07]

def pick_runner(backs, state, rng, gameplan=None):
    """
    Who carries it. Nothing decided this before, so one back took every carry
    and finished with 462 attempts and 3,788 yards against a real 334 and 1,763.
    Condition and injury are honoured, so a tiring starter cedes carries.
    """
    if not backs: return None, 0
    avail = [b for b in backs
             if state is None or b.get('pid') not in state.out] or backs
    n = min(len(avail), len(CARRY_SHARE))
    w = np.array(CARRY_SHARE[:n], float)
    # a worn-down back gets fewer. The lead back is on the field every snap
    # (the 'rb' slot never rotates) so his condition always sits under the
    # bench's; at 0.35 + 0.65 x condition that handed the backups most of
    # the carries and the league's leading rusher was a third-stringer with
    # 298 carries and 188 snaps. Real lead backs take 55-60% of carries.
    if state is not None:
        w = w * np.array([0.80 + 0.20 * (state.cond.get(b.get('pid')) / 100.0)
                          for b in avail[:n]])
    w = w / w.sum()
    i = int(rng.choice(n, p=w))
    return avail[i], i


OFF_SLOTS = [('ol', ['LT', 'LG', 'C', 'RG', 'RT']), ('wr', ['WR', 'WR', 'WR'])]
DEF_SLOTS = [('dl', ['LEDG', 'DT', 'DT', 'REDG']),
             ('lb', ['MIKE', 'WILL']),
             ('db', ['CB', 'CB', 'CB', 'FS', 'SS'])]

POS_KEY = {'WR': 'wr', 'TE': 'wr', 'HB': 'wr', 'CB': 'db', 'FS': 'db',
           'SS': 'db', 'LB': 'lb', 'DL': 'dl'}

def package_units(roster, state, rng, is_offense, package):
    """
    Which men the PACKAGE puts on the field. This is the piece fatigue alone
    cannot produce: five DBs play every snap in nickel, so without packages the
    top five are permanently starters and the sixth never appears.
    """
    import targets as TG
    spec = (TG.OFF_PACKAGES if is_offense else TG.DEF_PACKAGES).get(package)
    if not spec:
        return None
    out = {}
    if is_offense:
        pool = list(roster.get('wr', []))
        wrs = [p for p in pool if p.get('pos') == 'WR']
        tes = [p for p in pool if p.get('pos') == 'TE'] + \
              [p for p in roster.get('extra_blockers', []) if p.get('pos') == 'TE']
        hbs = [p for p in pool if p.get('pos') in ('HB', 'RB', 'FB')] or \
              [roster.get('rb')]
        chosen = wrs[:spec.get('WR', 3)] + tes[:spec.get('TE', 1)] + \
                 hbs[:max(0, spec.get('HB', 1) - 1)]
        out['wr'] = [c for c in chosen if c] or pool[:3]
    else:
        db = list(roster.get('db', []))
        cbs = [d for d in db if d.get('pos') == 'CB']
        saf = [d for d in db if d.get('pos') in ('FS', 'SS')]
        n_cb = spec.get('CB', 3)
        # BIG NICKEL. The fifth defensive back is a third safety about a
        # third of the time in the real league, which is most of why the
        # third corner plays 57% of snaps and not 80%. The dime stays corners.
        if n_cb == 3 and len(saf) >= 3 and rng.random() < 0.34:
            n_cb = 2
            out['db'] = cbs[:2] + saf[:3]
        else:
            out['db'] = cbs[:n_cb] + saf[:spec.get('FS', 1) + spec.get('SS', 1)]
        out['lb'] = list(roster.get('lb', []))[:spec.get('LB', 2)]
        out['dl'] = list(roster.get('dl', []))[:spec.get('DL', 4)]
    return out


def field_units(roster, state, rng, is_offense, package=None):
    """
    Put eleven men on the field for this snap, honouring condition and
    injuries. Anyone not selected recovers. This is where rotation actually
    happens - the depth chart is walked until someone is fresh enough.
    """
    if state is None:
        return roster, {}
    # the package decides WHO is eligible this snap; condition then decides
    # which of them actually goes
    pk = package_units(roster, state, rng, is_offense, package) if package else None
    if pk:
        roster = dict(roster); roster.update(pk)
    out, positions = dict(roster), {}
    slots = OFF_SLOTS if is_offense else DEF_SLOTS
    if is_offense:
        for key in ('qb', 'rb'):
            if roster.get(key) is not None:
                pos = 'QB' if key == 'qb' else 'HB'
                p = roster[key]
                # THE BACK ROTATES LIKE EVERYONE ELSE. The rb slot was fixed
                # to the lead back every snap, so his condition hit zero by
                # the second quarter and the carry draw, which reads
                # condition, handed most carries to fresh backups who were
                # never on the field. Walk the backfield by condition the way
                # every other slot is walked; real lead backs play ~65% of
                # snaps and take 55-60% of carries.
                if key == 'rb':
                    backs = [b for b in (roster.get('backs') or [p]) if b and b.get('pid') not in state.out] or [p]
                    pick = None
                    for rank, b in enumerate(backs):
                        gap = 1.0 if rank == 0 and len(backs) > 1 else (0.3 if rank == 1 else 0.0)   # a coach commits to his lead back; the third man is an emergency
                        if not state.cond.needs_rest(b.get('pid'), 'HB', rng, b.get('stamina_rating', 70.0), gap):
                            pick = b; break
                    p = pick or backs[0]
                    for b in backs:
                        if b is not p: state.snap(b, 'HB', False)
                # an injured starter yields to the backup - real leagues carry
                # ~2.4 QBs taking meaningful snaps, which is most of why the
                # real QB15-to-QB25 distribution falls off a cliff
                if key == 'qb' and p.get('pid') in state.out:
                    bench = roster.get('qbs') or []
                    alt = next((q for q in bench
                                if q.get('pid') not in state.out), None)
                    if alt is not None: p = alt
                state.snap(p, pos, True)
                out[key] = state.state(p, pos)
                positions[p.get('pid')] = pos
    for key, poslist in slots:
        group = roster.get(key, [])
        if not group: continue
        # Walk the depth chart IN ORDER, skipping men who need rest and men
        # already on the field for another slot. Rotating the list per slot -
        # what the first build did - gave every player a turn as the starter
        # and produced a completely flat snap distribution.
        avail = state.available(group, poslist[0])
        used, chosen = set(), []
        for pos in poslist[:min(len(poslist), len(avail))]:
            pick = None
            for rank, p in enumerate(avail):
                pid = p.get('pid')
                if pid in used: continue
                gap = 0.6 if rank < len(poslist) else 0.0
                if not state.cond.needs_rest(pid, pos, rng,
                                             p.get('stamina_rating', 70.0), gap):
                    pick = p; break
            if pick is None:
                pick = next((p for p in avail if p.get('pid') not in used),
                            avail[-1])
            used.add(pick.get('pid'))
            state.snap(pick, pos, True)
            chosen.append(state.state(pick, pos))
            positions[pick.get('pid')] = pos
        for p in group:
            if p.get('pid') not in used:
                state.snap(p, poslist[0], False)
        out[key] = chosen
    return out, positions

def run_drive(offense, defense, start_yardline, clock, quarter, score_diff,
              rng, resolve_fn, call_off, call_def, rate_fn, aggression=0.5,
              book=None, off_state=None, def_state=None, week=1,
              timeouts=None, pos='home', half_end=None):
    """
    Play a full possession. resolve_fn is plays.resolve_play; call_off/call_def
    are the scheme-layer callers.
    """
    dr = Drive(offense, defense, start_yardline, clock, quarter, score_diff, rng)
    import events as E
    # Adjustment happens AFTER EACH SERIES, which is what the coaches describe:
    # "If you wait until halftime to make your adjustments, you're too late."
    for st in (off_state, def_state):
        if st is not None:
            st.new_series()
            # Adjustment is considered every series but does not fire every
            # series. Calling it unconditionally on ~11 drives produced 5.56
            # plan changes per team per game against the ~3 the standalone
            # calibration targeted.
            # Use the GAME's generator. A fresh unseeded one here made the
            # whole engine non-reproducible: the same seed produced a
            # different season every time, so no calibration run could be
            # compared to another and a real regression was indistinguishable
            # from noise. The register swung four rows between identical runs.
            if rng.random() < 0.55:
                st.adjust(quarter, rng)

    import advanced_stats as AS
    pending = None                        # the last scrimmage play, waiting for its after-state
    while dr.result is None:
        if pending is not None:
            _o, _off, _def, _st = pending
            _v = AS.epa(_o, _st[0], _st[1], _st[2], dr.down, dr.togo, dr.yardline)
            _o['epa'] = round(_v, 3); AS.book_play(book, _o, _off, _def, _v); pending = None
        if dr.clock <= 0:
            dr.result = 'End of half'; break
        # THE HALF IS A WALL TOO. Without this the game ran as one continuous
        # 3600 seconds and only ONE drive a game was ever killed by a clock -
        # the last one. Real games kill two, one per half, and end-of-half
        # drives are 7.1% of all drives against the 4.0% this produced.
        if half_end is not None and dr.clock <= half_end:
            dr.clock = half_end
            dr.result = 'End of half'; break
        if dr.plays > 25:
            dr.result = 'End of half'; break

        # ---- THE CLOCK KICK. Down three or tied with the clock about to
        # expire and the ball in range, the field goal unit comes on
        # whatever the down: a team down three with eight seconds left at
        # the 30 does not run another play. The drive loop only ever kicked
        # on fourth down, so the tying kick was rarely attempted and
        # overtime ran at 3% against a real 6.2%. ----
        # the seconds left in THIS half: the first-half two-minute drill and the
        # kick before the break were missing, and the second quarter scored 8.4
        # points a game against a real 13; games without those points finish
        # farther apart than they should (12% decided by 1-3 against a real 23)
        secs_in_half = dr.clock - half_end if half_end is not None else dr.clock
        no_tos = timeouts is not None and timeouts.left.get(pos, 0) == 0
        clock_kick_time = secs_in_half <= 8 or (secs_in_half <= 22 and no_tos)
        if ((quarter >= 4 and -3 <= dr.score_diff <= 0) or (half_end is not None and quarter <= 2)) \
                and dr.yardline <= 37 and dr.down < 4 and clock_kick_time:
            fg = attempt_field_goal(dr.yardline, (offense.get('k') or {}), rng, rate_fn)
            if book is not None: book.special('fg', (offense.get('k') or {}).get('pid'), **fg)
            dr.clock -= min(dr.clock, play_seconds('field_goal'))
            dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
            dr.points = fg['points']; dr.log.append(fg); break
        # ---- fourth down is a decision, not a play ----
        if dr.down == 4:
            # the head coach's appetite, off his identity when he has one
            aggr4 = float(off_state.coach.get('fourth_down', aggression)) if off_state is not None and off_state.coach else aggression
            dec = fourth_down_decision(dr.yardline, dr.togo, dr.score_diff,
                                       dr.clock, rng, aggr4)
            if dec == 'field_goal':
                fg = attempt_field_goal(dr.yardline, (offense.get('k') or {}), rng, rate_fn)
                if book is not None: book.special('fg', (offense.get('k') or {}).get('pid'), **fg)
                dr.clock -= play_seconds('field_goal')
                dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
                dr.points = fg['points']; dr.log.append(fg); break
            if dec == 'punt':
                p = punt(dr.yardline, (offense.get('p') or {}),
                         (defense.get('kr') or {}), rng, rate_fn)
                if book is not None:
                    book.special('punt', (offense.get('p') or {}).get('pid'), **p)
                    if p.get('how') == 'return' or (p.get('ret') and not p.get('touchback')):
                        book.special('pr', (defense.get('kr') or {}).get('pid'), ret=p.get('ret', 0.0))
                dr.clock -= play_seconds('punt')
                dr.result = 'Punt'; dr.log.append(p)
                dr.next_yardline = p['new_yardline']; break

        # ---- a real play ----
        # Pass the REAL down. The first build sent down=1 on fourth down, so a
        # team going for it on 4th-and-8 called a first-down run and failed,
        # putting turnovers on downs at 21.6% against a real 5.6%.
        # yards_to_endzone must never round DOWN to zero. The first build passed
        # int(yardline), so a ball at the 0.4 gave the resolver a zero-yard field,
        # every gain capped at 0.0, and the offence physically could not score -
        # touchdowns came out at 2.1% against a real 22.6%.
        ytg_i = max(1, int(np.ceil(dr.yardline)))
        # THE PLAY CALLER'S IDENTITY: pass lean, play-action rate, motion
        # and deep-ball appetite from the plan go into the call
        olean = None
        if off_state is not None and off_state.plan is not None:
            pl0 = off_state.plan
            # SEQUENCING. A coordinator sets plays up: play action comes off a
            # run game that is working (a decayed count of runs of four or
            # more), and the ball finds the receiver who is winning his
            # matchups (target_priority, read by select_target). Both decay
            # within the game so an early stretch does not run the afternoon.
            seq = getattr(off_state, 'seq', None) or {'run_hot': 0.0}
            pa_boost = float(np.clip(1.0 + 0.55 * min(seq['run_hot'], 3.0) / 3.0, 0.85, 1.55))
            olean = dict(pass_bias=pl0.pass_bias, play_action=min(0.95, pl0.play_action_rate * pa_boost),
                         motion=getattr(pl0, 'motion_rate', 0.365), protection=getattr(pl0, 'protection', None),
                         screen_boost=getattr(pl0, 'screen_boost', 0.0))
        secs_for_call = dr.clock
        if half_end is not None and quarter <= 2 and secs_in_half <= 240 and dr.score_diff <= 0:
            secs_for_call = secs_in_half          # the drive before the break is a two-minute drill for the side not ahead
        oc = call_off(dr.down, max(1, int(np.ceil(dr.togo))),
                      dr.score_diff, ytg_i, rng, secs_left=secs_for_call,
                      offense=offense, rate_fn=rate_fn, lean=olean)
        # Backed up against the own goal the offence plays differently. That
        # used to be an OVERRIDE here that rewrote a called pass as a run or
        # forced its depth short. The coach now reads the field position
        # himself: schemes.pass_rate and identity.situational_depth carry the
        # real backed-up rates and nothing is decided for him after the call.
        if dr.yardline >= 91 and oc.get('is_pass'):
            oc = dict(oc, backed_up=True)
        # THE COVERAGE CALL NEVER FIRED IN A GAME. call_defense only consults
        # coverage_call when it is handed both the defence AND rate_fn, and this
        # passed the defence alone - so every real game fell back to the shell
        # draw, man only under cover 0 and cover 1, and the eleven-call system
        # ran nowhere but its own demo. Every register row measured since it
        # was built was measured against a defence that did not use it.
        # THE COORDINATOR'S IDENTITY GOES INTO THE CALL, not over it: the
        # plan's coverage lean, shell lean, blitz lean and front family are
        # read by the coverage call itself, so one truth per snap
        dlean = None
        if def_state is not None and def_state.plan is not None:
            dp0 = def_state.plan
            dlean = dict(coverage=dp0.man_rate, shell=getattr(dp0, 'shell_lean', 0.5),
                         blitz=getattr(dp0, 'blitz_lean', 0.35), front_pref=dp0.front_pref)
        dc = call_def(oc, dr.down, max(1, int(np.ceil(dr.togo))), rng, ytg_i,
                      defense=defense, rate_fn=rate_fn, score_diff=dr.score_diff,
                      secs_left=dr.clock, lean=dlean,
                      recent=(def_state.cov_memory if def_state else None))

        # THE AUDIBLE. He reads the look they are SHOWING and modifies the
        # call - he does not go back to the sheet and pick again, which would
        # let a good quarterback beat every defence every time. And the look
        # can be a lie: a disguised coverage sells him a picture that is not
        # there and he checks into something worse. That is what disguise is
        # for, and the engine already carried a shown shell and an actual one
        # with nothing reading the difference.
        try:
            import playcall as PC
            oc, checked = PC.audible(oc, dc, offense, rate_fn, rng)
            if checked:
                dr.log.append(dict(type='audible', kind=checked,
                                   off_a_lie=bool(dc.get('shown_shell')
                                                  != dc.get('shell'))))
        except Exception:
            pass

        # The opener. A situation - usually third down - forces him off it.
        script_mod = 1.0
        if off_state is not None:
            off_state.script.next_call(dr.down, int(dr.togo), rng)
            script_mod = off_state.script.performance_modifier()

        # Overlay the gameplans. Everything downstream reads THE PLAN, so an
        # adjustment made three series ago is still in force now.
        if off_state is not None and off_state.plan is not None:
            import gameplan as GP
            pl = off_state.plan
            oc['personnel'] = GP.personnel(pl, rng)
            oc['plan'] = pl
            oc['travel_willingness'] = float(
                off_state.coach.get('travel_willingness', 0.5))
            if oc.get('is_pass'):
                oc['depth'] = GP.depth(pl, rng, yards_to_endzone=ytg_i,
                                       down=dr.down, ydstogo=int(dr.togo))
            else:
                fam = GP.run_family(pl, rng)
                oc['scheme'] = ('inside_zone' if fam == 'zone' else 'power')

            # THE CHEATER PLAY. An adjustment vacates something, and that
            # something is the answer: "once a cheater play is used to reset
            # the defense, the play-caller can revert back". Anticipating the
            # adjustment rather than merely identifying it is what separates
            # callers, so this is gated on the caller's skill.
            import adjust as AD
            their = def_state.last_adjustment if def_state is not None else None
            ch = AD.cheater_available(their)
            if ch and rng.random() < 0.20 + 0.55 * float(
                    off_state.coach.get('adjust_skill', 0.5)):
                if ch['call'] == 'run':
                    oc['is_pass'] = False
                    oc['scheme'] = 'inside_zone'
                elif ch['call'] == 'deep':
                    oc['is_pass'] = True; oc['depth'] = 'deep'
                    oc['concept'] = 'four_verts'
                elif ch['call'] == 'play_action':
                    oc['is_pass'] = True; oc['play_action'] = True
                    oc['depth'] = 'medium'
                elif ch['call'] == 'other_target':
                    oc['avoid_bracket'] = True
                oc['cheater'] = ch['call']
                dr.cheaters = getattr(dr, 'cheaters', []) + [ch['call']]
                if def_state is not None:
                    def_state.last_adjustment = None      # the reset
        if def_state is not None and def_state.plan is not None:
            dp = def_state.plan
            # the in-game adjustments that are not part of the call itself
            dc['box'] = int(np.clip(dc.get('box', 6) +
                                    round(dp.box_bias * 4), 4, 10))
            dc['bracket'] = dp.bracket
            dc['travel'] = dp.travel
            dc['zone_aggression'] = dp.zone_aggression

        # Penalties. A pre-snap foul or a nullifying one (holding, OPI) wipes
        # the snap. EVERYTHING ELSE WAS BEING THROWN AWAY: the draw below
        # returned pass interference, defensive holding, roughing the passer,
        # unnecessary roughness, face masks and illegal contact, and the loop
        # dropped them on the floor because they do not nullify. So the engine
        # applied every foul that sets an offence back and none of the ones
        # that extend a drive - 0.17 automatic first downs a game against a
        # real ~3.4 - and drives died four yards and a third of a first down
        # short of real. The non-nullifying fouls are held here and resolved
        # after the play, where the offence decides whether to take them.
        pen = E.penalty_check(rng, phase='any', is_pass=oc['is_pass'],
                              noise=getattr(off_state, 'road_noise', 1.0) if off_state is not None else 1.0)
        live_pen = pen if (pen and not pen['nullifies']) else None
        if pen and pen['nullifies']:
            dr.clock -= play_seconds('penalty')
            if pen['on_offense']:
                dr.yardline = min(99, dr.yardline + pen['yards'])
                dr.togo += pen['yards']
            else:
                gained = min(pen['yards'], dr.yardline - 1)
                if pen['auto_first']:
                    dr.yardline -= gained; dr.down, dr.togo = 1, min(10, dr.yardline)
                    dr.first_downs += 1
                else:
                    dr.yardline -= gained; dr.togo -= gained
                    if dr.togo <= 0:
                        dr.down, dr.togo = 1, min(10, dr.yardline); dr.first_downs += 1
            dr.log.append(dict(type='penalty', **pen))
            continue

        # field the units for THIS snap - condition, injuries and rotation
        off_f, off_pos = field_units(offense, off_state, rng, True,
                                     oc.get('personnel'))
        def_f, def_pos = field_units(defense, def_state, rng, False,
                                     dc.get('personnel'))

        # the back who actually carries it
        # the back who carries it is the back on the field: the rotation in
        # field_units decides who that is
        out = resolve_fn(off_f, def_f, oc, dc, ytg_i, rng)
        # the situation rides with the play, for the ticker and the probes
        if isinstance(out, dict):
            out['down'] = dr.down; out['ydstogo'] = dr.togo; out['yardline'] = dr.yardline; out['clock'] = dr.clock
            out['passer'] = off_f['qb'].get('pid') if out.get('is_pass') or out.get('type') in ('complete', 'incomplete', 'interception', 'drop', 'sack', 'scramble') else None
            _snap_state = (dr.down, dr.togo, dr.yardline)
        if script_mod != 1.0 and out.get('yards'):
            out['yards'] = round(float(out['yards']) * script_mod, 1)
        dr.plays += 1
        if off_state is not None:
            seq = getattr(off_state, 'seq', None)
            if seq is None: seq = off_state.seq = {'run_hot': 0.0}
            if out.get('type') == 'run' and not out.get('sneak'):
                seq['run_hot'] = seq['run_hot'] * 0.85 + (1.0 if float(out.get('yards') or 0) >= 4.0 else -0.4)
                seq['run_hot'] = max(0.0, seq['run_hot'])
            elif out.get('type') in ('complete', 'incomplete', 'interception', 'drop'):
                seq['run_hot'] *= 0.92
            # the hot hand: a receiver who beat his man (a completion of 12+
            # or good separation) climbs the read order for the rest of the
            # game; a drop or a smothered target slips
            tgt = out.get('target')
            if tgt and off_state.plan is not None:
                tp = off_state.plan.target_priority
                if tp is None: tp = off_state.plan.target_priority = {}
                won = out.get('type') == 'complete' and (float(out.get('yards') or 0) >= 12 or float(out.get('separation') or 0) > 1.5)
                lost = out.get('type') in ('drop', 'interception')
                tp[tgt] = float(np.clip(tp.get(tgt, 0.0) * 0.9 + (0.35 if won else -0.25 if lost else 0.0), -0.6, 1.0))
        # WHAT HAS BEEN WORKING. The coordinator's own record of his calls,
        # decayed so an early stop does not justify the same call all
        # afternoon. Nothing fed this before, so `recent` was always empty.
        if def_state is not None and dc.get('coverage'):
            def_state.remember_coverage(
                dc['coverage'], float(out.get('yards') or 0.0),
                sack=(out.get('type') == 'sack'),
                turnover=(out.get('type') in ('interception', 'fumble')))
        # THE CALL, ON THE RECORD. Play action, motion and the blitz were
        # decided on every snap and then discarded, so the register carried
        # their real values as constants and reported ok whatever the engine
        # did. Now the log says what was called and the register measures it.
        out['is_pass'] = bool(oc.get('is_pass'))
        out['play_action'] = bool(oc.get('play_action'))
        out['motion'] = bool(oc.get('motion'))
        out['blitzers'] = int(dc.get('blitzers', 0))
        out['shell'] = dc.get('shell'); out['box'] = dc.get('box'); out['personnel'] = oc.get('personnel')
        out['blitz'] = bool(dc.get('blitz')) or int(dc.get('rushers', 4)) >= 5
        dr.log.append(out)
        if book is not None: book.record(out, off_f, def_f, rng)
        pending = (out, off_f, def_f, _snap_state)
        for st in (off_state, def_state):
            if st is not None: st.observe(oc, dc, out)

        # injuries attach to contact events
        if off_state is not None and out['type'] in ('run', 'complete', 'sack',
                                                     'scramble'):
            contact = 0.9 if out['type'] in ('run', 'sack') else 0.7
            # the man who actually took the snap, not the depth-chart starter
            carrier = (off_f['qb'] if out['type'] in ('sack', 'scramble')
                       else (off_f['qb'] if out.get('sneak') else off_f['rb']) if out['type'] == 'run'
                       else off_f['wr'][0])
            cpos = ('QB' if out['type'] in ('sack', 'scramble')
                    else 'HB' if out['type'] == 'run' else 'WR')
            off_state.hurt(carrier, cpos, contact, rng, rate_fn, week)
        if def_state is not None and out['type'] in ('run', 'complete'):
            pool = def_f['db'] + def_f['lb'] + def_f['dl']
            d = pool[rng.integers(0, len(pool))]
            def_state.hurt(d, def_pos.get(d.get('pid'), 'CB'), 0.8, rng,
                           rate_fn, week)

        t = out['type']
        if live_pen is not None:
            taken = _resolve_live_penalty(dr, live_pen, out, oc)
            if taken == 'replaced':
                # accepted in place of the play: the down is replayed, the
                # snap is wiped from the drive the same way a holding call is
                dr.plays -= 1; dr.log.pop()
                dr.log.append(dict(type='penalty', **live_pen))
                dr.clock -= play_seconds('penalty')
                continue
            if taken == 'added':
                dr.log.append(dict(type='penalty', **live_pen))

        # a collapsed pocket is not automatically a sack - a mobile QB runs
        if t == 'sack':
            if rng.random() < E.scramble_chance(offense['qb'], 1.0, 1.4, rate_fn):
                out = E.resolve_scramble(offense['qb'], [], ytg_i, rng, rate_fn)
                t = 'scramble'; dr.log[-1] = out

        if t == 'interception':
            dr.clock -= play_seconds('interception'); dr.result = 'Turnover'; break

        # fumbles attach to the event that produced them
        ev = {'complete': 'complete_pass', 'run': 'run', 'sack': 'sack',
              'scramble': 'scramble'}.get(t)
        if ev:
            carrier = offense['qb'] if ev in ('sack', 'scramble') else \
                      (offense['rb'] if ev == 'run' else offense['wr'][0])
            fum = E.fumble_check(carrier, ev, rng, rate_fn, env_mult=ENV.fumble_mult)
            if fum and fum['lost']:
                dr.clock -= play_seconds('fumble'); dr.result = 'Turnover'; break

        # ---- timeouts ----
        # The trailing side spends them to get the ball back; the driving side
        # to keep the clock alive. Neither wastes one early.
        used = False
        if timeouts is not None and dr.clock < 300:
            other = 'away' if pos == 'home' else 'home'
            if dr.score_diff > 0 and dr.clock < 180 and timeouts.left.get(other, 0) > 0:
                used = timeouts.use(other)
            elif dr.score_diff <= 0 and dr.clock < 120 and timeouts.left.get(pos, 0) > 0:
                used = timeouts.use(pos)
        hurry = secs_in_half < 120 and dr.score_diff <= 0
        dr.clock -= play_seconds(t, hurry=hurry, timeout=used)
        scored = _advance(dr, out.get('yards', 0.0))
        if scored: break
        if dr.down > 4:
            dr.result = 'Turnover on downs'; break

    if dr.result is None: dr.result = 'End of half'

    # ---- the try, once the touchdown is on the board ----
    if dr.result == 'Touchdown':
        if two_point_decision(dr.score_diff + 6, dr.quarter, dr.clock):
            t = attempt_two_point(offense, defense, rng, resolve_fn, call_off,
                                  call_def, rate_fn, off_state, def_state)
        else:
            t = attempt_extra_point(offense.get('k') or {}, rng, rate_fn)
            if book is not None: book.special('xp', (offense.get('k') or {}).get('pid'), **t)
        dr.points += t['points']
        dr.try_result = t
        dr.log.append(t)
    if pending is not None:
        _o, _off, _def, _st = pending
        _v = AS.epa(_o, _st[0], _st[1], _st[2], dr.down, dr.togo, dr.yardline, result=dr.result)
        _o['epa'] = round(_v, 3); AS.book_play(book, _o, _off, _def, _v)
    # the kick or the punt that ended it has an EPA of its own, so the ledger
    # balances: what the offence had on fourth down against what it left
    if dr.result in ('Punt', 'Field goal', 'Missed field goal') and dr.log and isinstance(dr.log[-1], dict):
        last = dr.log[-1]
        AS.book_special(book, dr, last, offense)
    return dr

OT_LENGTH = 600          # one 10-minute period in the regular season
OT_PLAYOFF_LENGTH = 900  # 15-minute periods, repeated until someone wins

def play_overtime(home, away, score, rng, resolve_fn, call_off, call_def,
                  rate_fn, home_state=None, away_state=None, week=1,
                  playoffs=False, first='away'):
    """
    2026 NFL overtime (Rule 16).

      - one 10-minute period in the regular season; 15-minute periods in the
        postseason, repeated until someone wins
      - BOTH teams get an opening opportunity to possess, even if the first
        team scores a touchdown. This changed in 2025; before that an opening
        TD ended it.
      - after both opportunities, a lead wins; still tied and time remaining
        means sudden death
      - the regular-season period does NOT extend to let the second team
        finish, so the clock can expire before it even possesses
      - a safety by the KICKING team on the receiving team's initial
        possession ends the game immediately
      - the regular season can end in a tie. Real rate: 0.29% of games.
        Overtime itself is reached in 6.2% of games.
    """
    # Real: 6.2% of games reach overtime and only 0.29% of all games end
    # tied - so roughly 1 in 20 overtimes. Teams play overtime with real
    # urgency, which a neutral game script does not reproduce on its own.
    clock = OT_PLAYOFF_LENGTH if playoffs else OT_LENGTH
    pos = first
    had = {'home': False, 'away': False}
    drives = []
    start = kickoff(((home if pos == 'away' else away).get('kr') or {}),
                    rng, rate_fn)['new_yardline']

    while clock > 0:
        off = home if pos == 'home' else away
        deff = away if pos == 'home' else home
        o_st = home_state if pos == 'home' else away_state
        d_st = away_state if pos == 'home' else home_state
        sd = score[pos] - score['away' if pos == 'home' else 'home']

        # overtime is played aggressively: nobody is protecting a lead
        # Overtime is played with maximum aggression - nobody protects a
        # lead, everyone goes for it on fourth down. Ties are real but rare:
        # 0.29% of all games, roughly 1 in 20 overtimes.
        dr = run_drive(off, deff, start, clock, 5, sd, rng, resolve_fn,
                       call_off, call_def, rate_fn, 0.98, None, o_st, d_st, week)
        drives.append((pos, dr))
        clock = max(0.0, dr.clock)
        had[pos] = True
        other = 'away' if pos == 'home' else 'home'

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            # a safety by the kicking team on the receiving team's FIRST
            # possession ends it immediately - the one exception to both
            # teams getting the ball
            score[other] += 2
            if not had[other]:
                return score, drives, 'safety_walkoff'

        # both have possessed: a lead wins, otherwise sudden death
        if had['home'] and had['away']:
            if score['home'] != score['away']:
                return score, drives, 'decided'

        if dr.result in ('Touchdown', 'Field goal'):
            start = kickoff((deff.get('kr') or {}), rng, rate_fn)['new_yardline']
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        else:
            start = 75
        pos = other

    if playoffs:                       # the postseason never ties
        return play_overtime(home, away, score, rng, resolve_fn, call_off,
                             call_def, rate_fn, home_state, away_state, week,
                             True, first)
    return score, drives, ('tie' if score['home'] == score['away'] else 'decided')


def play_game(home, away, rng, resolve_fn, call_off, call_def, rate_fn,
              home_aggr=0.5, away_aggr=0.5, book=None,
              home_state=None, away_state=None, week=1, playoffs=False):
    """A full 60-minute game. Returns the score and every drive."""
    score = {'home': 0, 'away': 0}
    drives, clock, quarter = [], GAME, 1
    pos = 'away'                                   # away receives first
    start = kickoff((home.get('kr') or {}), rng, rate_fn)['new_yardline']

    tos = Timeouts()
    half_done = False
    # THE BUILDING AND THE SKY. Conditions are drawn for this home city in
    # this week and set on the two modules that read them; they can turn at
    # the half. The road team pays the crowd and the altitude.
    global ENV
    import plays as _P
    home_abbr = (home_state.abbr if home_state is not None and getattr(home_state, 'abbr', None) else home.get('abbr', ''))
    ENV = W.draw(home_abbr, week, rng, neutral=playoffs and week >= 22)
    _P.ENV = ENV
    if away_state is not None:
        away_state.road_noise = ENV.road_false_start; away_state.road_stamina = ENV.road_stamina
    if home_state is not None:
        home_state.road_noise = 1.0; home_state.road_stamina = 1.0
    # SHADOWING IS A GAME-WEEK DECISION. A coordinator decides on Tuesday
    # whether his best corner follows their best receiver, and then he does
    # it all game. Decided per snap it ran at 4% of pass plays; the real rate
    # for clubs that shadow is 15-25% of all snaps, near 50% of games for a
    # premier corner against a premier receiver.
    import coverage as CV
    for st, ros, opp in ((home_state, home, away), (away_state, away, home)):
        if st is None or st.plan is None: continue
        cbs = sorted([d for d in ros.get('db', []) if d.get('pos') == 'CB'],
                     key=lambda d: -rate_fn(d, {'man_cover_rating': .55, 'speed_rating': .25, 'press_rating': .20}))
        wrs = [w for w in opp.get('wr', []) if w.get('pos') == 'WR']
        if len(cbs) >= 2 and wrs:
            wr1 = max(wrs, key=lambda w: rate_fn(w, {'route_run_short_rating': .20, 'route_run_med_rating': .25,
                                                     'route_run_deep_rating': .25, 'speed_rating': .30}))
            if not getattr(st.plan, 'travel_locked', False):     # the GM's own call, when he made one, stands
                st.plan.travel = CV.should_travel(cbs[0], cbs[1], wr1, rate_fn, True, rng,
                                                  coach_willingness=float(st.coach.get('travel_willingness', 0.5)),
                                                  scale=1.6)          # a game-week call has a lower bar than a snap
                st.plan.travel_target = wr1.get('pid') if st.plan.travel else None
            elif st.plan.travel and not getattr(st.plan, 'travel_target', None):
                st.plan.travel_target = wr1.get('pid')
            # BRACKETING IS A GAME-WEEK DECISION TOO. A coordinator doubles
            # their star when the second receiver is not one and the plan can
            # afford the safety: real clubs bracket the top man on about a
            # third of his snaps, more against the true elite.
            if not getattr(st.plan, 'bracket_locked', False): st.plan.bracket = None
            if len(wrs) >= 2 and not getattr(st.plan, 'bracket_locked', False):
                srt = sorted(wrs, key=lambda w: -rate_fn(w, {'route_run_short_rating': .20, 'route_run_med_rating': .25,
                                                              'route_run_deep_rating': .25, 'speed_rating': .30}))
                gap = rate_fn(srt[0], {'route_run_med_rating': .5, 'speed_rating': .5}) - rate_fn(srt[1], {'route_run_med_rating': .5, 'speed_rating': .5})
                star = rate_fn(srt[0], {'route_run_med_rating': .5, 'speed_rating': .5}) >= 0.86
                p_br = (0.55 if star else 0.25) * float(np.clip(gap / 0.08, 0.3, 1.5)) * float(st.coach.get('bracket_willingness', 0.5)) / 0.5
                if rng.random() < min(0.8, p_br):
                    st.plan.bracket = srt[0].get('pid')
    while clock > 0:
        off = home if pos == 'home' else away
        deff = away if pos == 'home' else home
        sd = score[pos] - score['away' if pos == 'home' else 'home']
        aggr = home_aggr if pos == 'home' else away_aggr

        o_st = home_state if pos == 'home' else away_state
        d_st = away_state if pos == 'home' else home_state
        # the unit that just came off recovers while the other side plays
        if d_st is not None: d_st.sideline_recovery(dr_snaps if 'dr_snaps' in dir() else 30)
        dr = run_drive(off, deff, start, clock, quarter, sd, rng,
                       resolve_fn, call_off, call_def, rate_fn, aggr, book,
                       o_st, d_st, week, timeouts=tos, pos=pos,
                       half_end=(GAME / 2 if not half_done else None))
        dr_snaps = dr.plays
        if o_st is not None: o_st.sideline_recovery(dr.plays)
        drives.append((pos, dr))
        clock = max(0.0, dr.clock)
        quarter = min(4, int((GAME - clock) // QUARTER) + 1)

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            score['away' if pos == 'home' else 'home'] += 2

        # ---- HALFTIME ----
        # The side that KICKED OFF to open the game receives the second half,
        # which is why a club can go into the break with the ball and come out
        # of it with the ball again. The engine had no concept of a half, so
        # that swing did not exist at all.
        if not half_done and clock <= GAME / 2:
            tos.halftime()
            half_done = True
            ENV.turn(rng, home_abbr); _P.ENV = ENV
            pos = 'home'                            # away received the opener
            start = kickoff((away.get('kr') or {}), rng, rate_fn)['new_yardline']
            continue

        # where the next possession starts
        if dr.result in ('Touchdown', 'Field goal'):
            start = kickoff((deff.get('kr') or {}), rng, rate_fn)['new_yardline']
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        elif dr.result == 'Missed field goal':
            start = float(np.clip(100 - dr.yardline - 8, 1, 99))
        else:
            start = 75
        pos = 'away' if pos == 'home' else 'home'

    # overtime
    ot = None
    if score['home'] == score['away']:
        first = 'away' if rng.random() < 0.5 else 'home'
        score, ot_drives, ot = play_overtime(
            home, away, score, rng, resolve_fn, call_off, call_def, rate_fn,
            home_state, away_state, week, playoffs, first)
        drives += ot_drives

    inj = []
    for st in (home_state, away_state):
        if st is not None:
            inj += st.injuries
            st.end_game(rng)
    return dict(home=score['home'], away=score['away'], drives=drives,
                injuries=inj, overtime=ot, env=ENV.to_dict())

# ============================================================ STAT ATTRIBUTION
# Every play already names its contributors, so accumulation is nearly free.
class StatBook:
    """Accumulates individual lines across plays, games and a season."""
    def __init__(self):
        self.p = {}

    def special(self, kind, pid, **kw):
        """A kick, a punt or a return: the kicking game's box score."""
        if not pid: return
        d = self._get(pid)
        if kind == 'fg':
            d['fg_att'] += 1
            if kw.get('made'):
                d['fg_made'] += 1; d['fg_long'] = max(d['fg_long'], int(kw.get('distance', 0)))
        elif kind == 'xp':
            d['xp_att'] += 1; d['xp_made'] += 1 if kw.get('made') else 0
        elif kind == 'punt':
            d['punts'] += 1; d['punt_yds'] += float(kw.get('gross', 0.0)); d['punt_net_yds'] += float(kw.get('net', 0.0))
            if kw.get('touchback'): d['punt_tb'] += 1
            elif kw.get('new_yardline', 50) >= 80: d['punt_in20'] += 1
        elif kind == 'kr':
            d['kr'] += 1; d['kr_yds'] += float(kw.get('ret', 0.0))
        elif kind == 'pr':
            d['pr'] += 1; d['pr_yds'] += float(kw.get('ret', 0.0))

    def _get(self, pid):
        if pid not in self.p:
            self.p[pid] = dict(
                pass_att=0, pass_cmp=0, pass_yds=0.0, pass_td=0, ints=0, sacked=0,
                rush_att=0, rush_yds=0.0, rush_td=0,
                tgt=0, rec=0, rec_yds=0.0, rec_td=0, drops=0,
                tackles=0, sacks=0.0, int_def=0, pressures=0, ff=0,
                pass_def=0,
                fum=0, fum_lost=0,
                # ---- specialists ----
                fg_att=0, fg_made=0, fg_long=0, xp_att=0, xp_made=0,
                punts=0, punt_yds=0.0, punt_net_yds=0.0, punt_in20=0, punt_tb=0,
                kr=0, kr_yds=0.0, pr=0, pr_yds=0.0,
                # ---- offensive line ----
                # There are no traditional stats for a lineman, which is why
                # his page on any real site is blank. The industry settled on
                # win rates: ESPN counts a pass block win as sustaining the
                # block 2.5 seconds or longer, and a run block win as beating
                # the man across from you. Football GM, which hit exactly this
                # problem, landed on the same three - PBWR, RBWR and sacks
                # allowed. Pancakes are deliberately NOT here: no credible
                # source tracks them and there is no standard definition, and
                # run block win rate is the real version of that idea.
                pb_snaps=0, pb_wins=0, sacks_allowed=0, pressures_allowed=0,
                # ---- advanced ----
                pass_epa=0.0, pass_plays=0, rush_epa=0.0, rush_plays=0, rec_epa=0.0, def_epa=0.0, def_plays=0,
                xcomp=0.0, cpoe_att=0, pr_reps=0, pr_wins=0, sep_total=0.0, sep_n=0, st_epa=0.0,
                rb_snaps=0, rb_wins=0)
        return self.p[pid]

    def record(self, out, off, deff, rng):
        t = out.get('type')
        qb = off['qb'].get('pid', 'QB')

        # ---- the line. Every rep, on every snap, both phases ----
        for pid, won in out.get('pb_reps') or ():
            l = self._get(pid)
            l['pb_snaps'] += 1
            l['pb_wins'] += 1 if won else 0
            if not won and out.get('pressured'):
                l['pressures_allowed'] += 1
        for pid, won in out.get('rb_reps') or ():
            l = self._get(pid)
            l['rb_snaps'] += 1
            l['rb_wins'] += 1 if won else 0
        # A sack is charged to the man who was actually beaten, which the
        # protection resolver already names.
        if out.get('pass_def'):
            self._get(out['pass_def'])['pass_def'] += 1
        if t == 'sack' and out.get('beaten'):
            self._get(out['beaten'])['sacks_allowed'] += 1
        if t in ('complete', 'incomplete', 'drop', 'interception'):
            s = self._get(qb); s['pass_att'] += 1
            wr = out.get('target', off['wr'][0].get('pid', 'WR1'))
            w = self._get(wr); w['tgt'] += 1
            if t == 'complete':
                s['pass_cmp'] += 1; s['pass_yds'] += out['yards']
                w['rec'] += 1; w['rec_yds'] += out['yards']
                if out.get('touchdown'): s['pass_td'] += 1; w['rec_td'] += 1
            elif t == 'drop':
                w['drops'] += 1
            elif t == 'interception':
                s['ints'] += 1
                d = self._get(out.get('by', deff['db'][0].get('pid', 'DB1')))
                d['int_def'] += 1
        elif t == 'sack':
            s = self._get(qb); s['sacked'] += 1
            d = self._get(out.get('by', (deff.get('dl') or [{}])[0].get('pid', 'DL1')))
            d['sacks'] += 1.0; d['tackles'] += 1
        elif t == 'scramble':
            s = self._get(qb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown'): s['rush_td'] += 1
        elif t == 'run':
            rb = out.get('carrier_pid') or off['rb'].get('pid', 'RB1')
            s = self._get(rb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown'): s['rush_td'] += 1
        # a tackle is credited on any play that ends in the field of play
        if t in ('run', 'complete', 'scramble') and not out.get('touchdown'):
            pool = deff['db'] + deff['lb'] + deff['dl']
            tk = pool[rng.integers(0, len(pool))]
            self._get(tk.get('pid', 'D?'))['tackles'] += 1

    def table(self):
        import pandas as pd
        return pd.DataFrame(self.p).T
