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

# ============================================================ CLOCK
SEC = {'complete': 31.4, 'incomplete': 10.2, 'run': 34.7, 'sack': 30.0,
       'scramble': 34.7, 'punt': 9.4, 'field_goal': 4.0, 'kickoff': 5.8,
       'penalty': 14.4, 'interception': 12.0, 'drop': 10.2, 'fumble': 12.0}
QUARTER = 900
HALF = 1800
GAME = 3600

def play_seconds(result, clock_stopped=False, hurry=False):
    s = SEC.get(result, 25.0)
    if clock_stopped: s = min(s, 8.0)
    if hurry: s *= 0.55
    return float(s)

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
                         aggression=0.5):
    """go, field_goal or punt. Desperation overrides the table late."""
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
FG_PCT = [(29, .960), (34, .940), (39, .878), (44, .805), (49, .728),
          (54, .694), (99, .552)]

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
    made = rng.random() < fg_probability(dist, kicker, rate_fn)
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

def two_point_decision(lead_after_td, quarter):
    """Kick or go. The coach's call, not the engine's."""
    if quarter < 4: return False
    return int(round(lead_after_td)) in TWO_POINT_GO

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
PUNT = dict(gross=47.2, sd=9.8, touchback=.075, blocked=.0043,
            return_rate=.35, return_mean=11.5, return_p90=19, td_rate=.0036)

def punt(yardline_100, punter, returner, rng, rate_fn, AVG=0.70):
    if rng.random() < PUNT['blocked']:
        return dict(type='punt', blocked=True, net=0,
                    new_yardline=100 - yardline_100)
    pwr = rate_fn(punter, {'kick_power_rating': .70, 'kick_acc_rating': .30})
    gross = rng.normal(PUNT['gross'] * (1.0 + 0.30 * (pwr - AVG)), PUNT['sd'])
    land = yardline_100 - gross
    if land <= 0 or rng.random() < PUNT['touchback']:
        return dict(type='punt', blocked=False, touchback=True, net=None,
                    new_yardline=80)       # opponent's own 20
    ret = 0.0
    if rng.random() < PUNT['return_rate']:
        skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30,
                                   'juke_move_rating': .25})
        # shape/scale solved against mean 11.5 and p90 19, with a long right
        # tail so 0.36% reach the end zone
        ret = max(0.0, rng.gamma(1.9, 6.05) * (1.0 + 0.9 * (skill - AVG)))
    new = float(np.clip(100 - land + ret, 1, 99))
    return dict(type='punt', blocked=False, touchback=False,
                gross=round(float(gross), 1), ret=round(float(ret), 1),
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
            self.cond.play(pid, position, player.get('stamina_rating', 70.0))
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

    def adjust(self, quarter=1):
        """Read the trends and modify THE PLAN. Returns what changed."""
        import adjust as AD, gameplan as GP
        skill = float(self.coach.get('adjust_skill', 0.5))
        aggr = float(self.coach.get('adjust_willingness', 0.5))
        trends = AD.detect(self.mem, skill=skill)
        ctr = AD.respond(trends, skill=skill, aggressiveness=aggr,
                         rng=np.random.default_rng())
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

# ============================================================ DRIVE
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
        self.result, self.points = None, 0
        self.try_result = None
        self.log = []

def _advance(dr, gained):
    """Apply yardage, update downs and field position. Whole yards only."""
    gained = float(np.round(gained))
    dr.yardline -= gained
    dr.togo -= gained
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
CARRY_SHARE = [0.489, 0.229, 0.114, 0.069, 0.037]

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
    # a worn-down back gets fewer
    if state is not None:
        w = w * np.array([0.35 + 0.65 * (state.cond.get(b.get('pid')) / 100.0)
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
        out['db'] = cbs[:spec.get('CB', 3)] + saf[:spec.get('FS', 1) + spec.get('SS', 1)]
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
              book=None, off_state=None, def_state=None, week=1):
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
            if np.random.default_rng().random() < 0.55:
                st.adjust(quarter)

    while dr.result is None:
        if dr.clock <= 0:
            dr.result = 'End of half'; break
        if dr.plays > 25:
            dr.result = 'End of half'; break

        # ---- fourth down is a decision, not a play ----
        if dr.down == 4:
            dec = fourth_down_decision(dr.yardline, dr.togo, dr.score_diff,
                                       dr.clock, rng, aggression)
            if dec == 'field_goal':
                fg = attempt_field_goal(dr.yardline, (offense.get('k') or {}), rng, rate_fn)
                dr.clock -= play_seconds('field_goal')
                dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
                dr.points = fg['points']; dr.log.append(fg); break
            if dec == 'punt':
                p = punt(dr.yardline, (offense.get('p') or {}),
                         (defense.get('kr') or {}), rng, rate_fn)
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
        oc = call_off(dr.down, max(1, int(np.ceil(dr.togo))),
                      dr.score_diff, ytg_i, rng)
        dc = call_def(oc, dr.down, max(1, int(np.ceil(dr.togo))), rng, ytg_i)

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
                oc['depth'] = GP.depth(pl, rng)
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
            import gameplan as GP
            dp = def_state.plan
            dc['shell'] = GP.shell(dp, rng)
            dc['man'] = GP.is_man(dp, rng)
            dc['blitzers'] = GP.blitzers(dp, rng, dr.down, int(dr.togo))
            dc['rushers'] = 4 + dc['blitzers']
            dc['box'] = int(np.clip(dc.get('box', 6) +
                                    round(dp.box_bias * 4), 4, 10))
            if dp.front_pref: dc['front'] = dp.front_pref[0]
            dc['bracket'] = dp.bracket
            dc['travel'] = dp.travel

        # penalties resolve before the snap can count
        pen = E.penalty_check(rng, phase='any', is_pass=oc['is_pass'])
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
        if not oc.get('is_pass'):
            backs = offense.get('backs') or [offense.get('rb')]
            rb, _rk = pick_runner([b for b in backs if b], off_state, rng)
            if rb is not None: off_f = dict(off_f, rb=rb)

        out = resolve_fn(off_f, def_f, oc, dc, ytg_i, rng)
        if script_mod != 1.0 and out.get('yards'):
            out['yards'] = round(float(out['yards']) * script_mod, 1)
        dr.plays += 1
        dr.log.append(out)
        if book is not None: book.record(out, off_f, def_f, rng)
        for st in (off_state, def_state):
            if st is not None: st.observe(oc, dc, out)

        # injuries attach to contact events
        if off_state is not None and out['type'] in ('run', 'complete', 'sack',
                                                     'scramble'):
            contact = 0.9 if out['type'] in ('run', 'sack') else 0.7
            # the man who actually took the snap, not the depth-chart starter
            carrier = (off_f['qb'] if out['type'] in ('sack', 'scramble')
                       else off_f['rb'] if out['type'] == 'run'
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
            fum = E.fumble_check(carrier, ev, rng, rate_fn)
            if fum and fum['lost']:
                dr.clock -= play_seconds('fumble'); dr.result = 'Turnover'; break

        dr.clock -= play_seconds(t, hurry=(dr.clock < 120 and dr.score_diff < 0))
        scored = _advance(dr, out.get('yards', 0.0))
        if scored: break
        if dr.down > 4:
            dr.result = 'Turnover on downs'; break

    if dr.result is None: dr.result = 'End of half'

    # ---- the try, once the touchdown is on the board ----
    if dr.result == 'Touchdown':
        if two_point_decision(dr.score_diff + 6, dr.quarter):
            t = attempt_two_point(offense, defense, rng, resolve_fn, call_off,
                                  call_def, rate_fn, off_state, def_state)
        else:
            t = attempt_extra_point(offense.get('k') or {}, rng, rate_fn)
        dr.points += t['points']
        dr.try_result = t
        dr.log.append(t)
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
                       o_st, d_st, week)
        dr_snaps = dr.plays
        if o_st is not None: o_st.sideline_recovery(dr.plays)
        drives.append((pos, dr))
        clock = max(0.0, dr.clock)
        quarter = min(4, int((GAME - clock) // QUARTER) + 1)

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            score['away' if pos == 'home' else 'home'] += 2

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
                injuries=inj, overtime=ot)

# ============================================================ STAT ATTRIBUTION
# Every play already names its contributors, so accumulation is nearly free.
class StatBook:
    """Accumulates individual lines across plays, games and a season."""
    def __init__(self):
        self.p = {}

    def _get(self, pid):
        if pid not in self.p:
            self.p[pid] = dict(
                pass_att=0, pass_cmp=0, pass_yds=0.0, pass_td=0, ints=0, sacked=0,
                rush_att=0, rush_yds=0.0, rush_td=0,
                tgt=0, rec=0, rec_yds=0.0, rec_td=0, drops=0,
                tackles=0, sacks=0.0, int_def=0, pressures=0, ff=0,
                fum=0, fum_lost=0,
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
            d = self._get(out.get('by', deff['dl'][0].get('pid', 'DL1')))
            d['sacks'] += 1.0; d['tackles'] += 1
        elif t == 'scramble':
            s = self._get(qb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown'): s['rush_td'] += 1
        elif t == 'run':
            rb = off['rb'].get('pid', 'RB1')
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
