"""
In-game adjustment.

Built from what coaches actually describe, plus FM26's working model. Madden
was not useful here: it detects a REPEATED PLAY within a game and counters it,
and has no memory across a season.

WHAT THE COACHES SAY:

  Halftime adjustment is largely a myth. An NFL head coach: "If you wait until
  halftime to make your adjustments, you're too late." Wade Phillips describes
  it as continuous - "One team does something, the other team adjusts to it.
  That team counters their adjustment and it goes back and forth. It goes on
  all game" - and says clubs adjust AFTER EACH SERIES. Josh McDaniels: changes
  begin almost immediately and continue each series; only the most profound
  changes wait for the half.

  THE SERIES IS THE UNIT. Not the play, not the half.

  The response is STRUCTURAL, not a single assignment. Wade Phillips had A.J.
  Green toasting his corners in aggressive man, so he went to zone concepts.
  Cincinnati went from 204 yards in the first half to 90 after.

  OFFENCE OPENS ON A SCRIPT, specifically to get its plan executed before the
  defence can counter. Walsh scripted 15-25 plays: "Scripting is planning; it's
  contingency planning. The fewer decisions to be made during the game, the
  better." Coaches come off script when a SITUATION demands it, usually third
  down, not when a play counter runs out.
  Off-script is measurably worse for some coaches: Shanahan's 2022 49ers had
  +0.32 passing EPA on script and -0.10 off it.

  THE CHEATER PLAY. When a defence cheats to stop something, the offence
  punishes the vacated space - play action or a wheel into an emptied box -
  then reverts to the base series and chips away again. Anticipating the
  adjustment rather than merely identifying it is what separates callers.

  SELF-SCOUTING is a real job: reviewing your own predictability to avoid
  exploitable habits. Kubiak was criticised league-wide for concepts that were
  "easy to read and react to".

  BOTH ERRORS ARE REAL. O'Brien threw on 75% of first downs against one of the
  worst run defences in football, averaged 2.5 yards and scored three points.
  Carroll's Raiders had four carries in a half, their fewest since 2008.
  Abandoning what works is as damaging as failing to adjust.

WHAT FM26 CONTRIBUTES:
  Adaptive pressing - the AI reads WHERE you attack and answers structurally,
  constricting against central play and shifting its block against width.
  Preventative management - proactive substitution off fatigue rather than
  waiting for the cliff.
  And a warning from its own community: FM's AI counters too fast and too
  reliably, so "every AI manager is Mourinho". An adjustment that always works
  is as wrong as no adjustment at all. Counters here can fail.

NOTE: how FAST and how MUCH a coach adjusts belongs on his ratings, which are
on the to-do list with the GM/coach pool. Everything here reads a single
`skill` parameter so those ratings drop straight in.
"""
import numpy as np
from collections import defaultdict, deque

# ============================================================ WHAT GETS WATCHED
# Trends, not repeated plays. Each is something a coordinator would actually
# notice over a handful of series.
TRENDS = ['pass_depth', 'run_direction', 'target_concentration', 'personnel',
          'tempo', 'protection', 'front_success', 'coverage_success']

MIN_SERIES = 2          # nothing fires off one drive
MIN_EVENTS = 5          # nor off a tiny sample


class GameMemory:
    """
    What one side has seen this game. Rolling, series-indexed, so a trend that
    stopped three drives ago fades instead of counting forever.
    """
    def __init__(self, window=4):
        self.window = window
        self.series = 0
        self.by_series = defaultdict(lambda: defaultdict(list))

    def new_series(self):
        self.series += 1

    def record(self, play_call, def_call, outcome):
        s = self.by_series[self.series]
        gained = outcome.get('yards', 0.0) or 0.0
        # Coerce success to a real bool. outcome.get('touchdown') returns None
        # on plays that carry no such key, and the success means below then
        # tried to sum None values.
        ok = bool(gained >= 4.0 or outcome.get('touchdown'))
        if play_call['is_pass']:
            s['pass_depth'].append((play_call.get('depth', 'short'), gained, ok))
            t = outcome.get('target')
            if t: s['targets'].append((t, gained, ok))
            s['protection'].append((outcome['type'] == 'sack',
                                    def_call.get('rushers', 4)))
            s['coverage'].append((def_call.get('shell', 'cover_3'), gained, ok))
        else:
            s['run'].append((play_call.get('scheme', 'inside_zone'), gained, ok))
            s['front'].append((def_call.get('front', '4-3 over'),
                               def_call.get('box', 6), gained, ok))
        s['personnel'].append(play_call.get('personnel', '11'))
        s['calls'].append('pass' if play_call['is_pass'] else 'run')

    def recent(self, key):
        """Everything in the rolling window."""
        lo = max(0, self.series - self.window + 1)
        out = []
        for s in range(lo, self.series + 1):
            out += self.by_series[s].get(key, [])
        return out

    def series_seen(self):
        return min(self.series, self.window)


# ============================================================ DETECTION
def detect(mem, skill=0.5):
    """
    What is actually happening to us. Returns trends with a confidence, which
    scales with the sample AND with the coach's skill - a sharper coordinator
    reads it off a smaller sample, which is the professional-versus-high-school
    difference the coaching sources describe.
    """
    found = {}
    if mem.series_seen() < MIN_SERIES:
        return found
    need = MIN_EVENTS * (1.4 - 0.8 * skill)

    # --- who is beating us, and at what depth ---
    pd = mem.recent('pass_depth')
    if len(pd) >= need:
        by = defaultdict(list)
        for d, g, ok in pd: by[d].append(ok)
        for d, res in by.items():
            if len(res) >= 3 and np.mean(res) >= 0.55:
                found[f'pass_{d}'] = dict(kind='pass_depth', value=d,
                                          rate=float(np.mean(res)),
                                          n=len(res),
                                          conf=_conf(len(res), need, skill))

    # --- one receiver eating us alive ---
    tg = mem.recent('targets')
    if len(tg) >= need:
        by = defaultdict(list)
        for t, g, ok in tg: by[t].append((g, ok))
        for t, res in by.items():
            share = len(res) / len(tg)
            succ = np.mean([o for _, o in res])
            if share >= 0.30 and succ >= 0.55 and len(res) >= 3:
                found['target'] = dict(kind='target', value=t, rate=float(succ),
                                       share=float(share), n=len(res),
                                       conf=_conf(len(res), need, skill))

    # --- the run game is gashing us ---
    rn = mem.recent('run')
    if len(rn) >= need:
        by = defaultdict(list)
        for sc, g, ok in rn: by[sc].append((g, ok))
        allg = [g for _, g, _ in rn]
        if np.mean(allg) >= 4.6:
            worst = max(by, key=lambda k: np.mean([g for g, _ in by[k]]))
            found['run'] = dict(kind='run', value=worst,
                                rate=float(np.mean(allg)), n=len(rn),
                                conf=_conf(len(rn), need, skill))

    # --- our own protection is failing ---
    pr = mem.recent('protection')
    if len(pr) >= need:
        sacked = np.mean([s for s, _ in pr])
        if sacked >= 0.14:
            found['protection'] = dict(kind='protection', value='failing',
                                       rate=float(sacked), n=len(pr),
                                       conf=_conf(len(pr), need, skill))

    # --- we are predictable (self-scout) ---
    calls = mem.recent('calls')
    if len(calls) >= need:
        p = np.mean([c == 'pass' for c in calls])
        if p >= 0.80 or p <= 0.20:
            found['predictable'] = dict(kind='predictable',
                                        value='pass' if p >= 0.8 else 'run',
                                        rate=float(max(p, 1 - p)), n=len(calls),
                                        conf=_conf(len(calls), need, skill))
    return found

def _conf(n, need, skill):
    """
    Confidence grows with sample and with the coach's eye, but SATURATES
    slowly. A linear ratio hit 1.00 after eight plays and made every coach
    identical, which defeated the whole point of skill.
    """
    raw = 1.0 - np.exp(-0.55 * n / max(need, 1))
    return float(np.clip(raw * (0.45 + 0.65 * skill), 0.0, 0.97))


# ============================================================ RESPONSE
# Structural counters, as the coaching sources describe. Each carries a COST,
# because a defence that rolls help somewhere has taken it from somewhere else.
COUNTERS = {
    'pass_deep':   dict(shell_to=['cover_2', 'cover_4'], box=-0.6,
                        cost='run_game', desc='drop the safeties, take away the top'),
    'pass_medium': dict(shell_to=['cover_3', 'tampa_2'], box=-0.3,
                        cost='run_game', desc='more zone underneath'),
    'pass_short':  dict(shell_to=['cover_1', 'cover_0'], box=+0.4,
                        cost='deep_ball', desc='press and squeeze the quick game'),
    'target':      dict(bracket=True, shell_to=['cover_2', 'cover_4'], box=-0.8,
                        cost='other_receivers',
                        desc='shadow and bracket the man beating us'),
    'run':         dict(box=+1.4, front_to=['bear', 'tite', '4-3 under'],
                        cost='play_action', desc='walk a safety down, heavier front'),
    'protection':  dict(offense=True, keep_in=1, depth_to='short',
                        cost='routes', desc='keep a back in, get the ball out'),
    'predictable': dict(offense=True, force_mix=True, cost=None,
                        desc='break our own tendency before they read it'),
}

def respond(trends, skill=0.5, aggressiveness=0.5, rng=None):
    """
    Pick an adjustment. A coach with a low willingness stays the course, which
    the coaching material explicitly defends: "Change for change sake is a
    really bad idea in the middle of a football game."
    """
    rng = rng or np.random.default_rng()
    if not trends: return None
    # A receiver destroying you is a more urgent problem than a generic depth
    # trend, and a run game gashing you more urgent still. Without a priority
    # weight the plain max() always picked the same trend on ties.
    PRIORITY = {'target': 1.45, 'run': 1.35, 'protection': 1.30,
                'predictable': 0.85}
    key, t = max(trends.items(),
                 key=lambda kv: kv[1]['conf'] * kv[1]['rate'] *
                                PRIORITY.get(kv[0], 1.0))
    ckey = key if key in COUNTERS else t['kind']
    if ckey not in COUNTERS: return None

    # will he even act? confidence x willingness
    if rng.random() > t['conf'] * (0.30 + 0.80 * aggressiveness):
        return None

    c = dict(COUNTERS[ckey])
    # And it can simply fail. FM's own community complains their AI counters
    # too reliably - "every AI manager is Mourinho" - so a counter that always
    # works is as wrong as no counter at all.
    # FM's community complains their AI counters too reliably. A counter that
    # works three times in four removes the contest; these numbers put an
    # average coordinator near a coin flip and an elite one at about 70%.
    c['works'] = rng.random() < (0.18 + 0.58 * skill)
    c['trigger'] = key
    c['target'] = t.get('value')
    c['confidence'] = t['conf']
    return c


# ============================================================ APPLY
def apply_defensive(def_call, adj, rng):
    """Fold a defensive adjustment into this play's call."""
    if not adj or adj.get('offense') or not adj.get('works'):
        return def_call
    d = dict(def_call)
    if adj.get('shell_to') and rng.random() < 0.70:
        d['shell'] = adj['shell_to'][int(rng.integers(0, len(adj['shell_to'])))]
        d['man'] = d['shell'] in ('cover_0', 'cover_1')
    if adj.get('front_to') and rng.random() < 0.55:
        d['front'] = adj['front_to'][int(rng.integers(0, len(adj['front_to'])))]
    if adj.get('box'):
        d['box'] = int(np.clip(d.get('box', 6) + round(adj['box']), 4, 10))
    if adj.get('bracket'):
        d['bracket'] = adj.get('target')
    return d

def apply_offensive(off_call, adj, rng):
    """Fold an offensive adjustment into this play's call."""
    if not adj or not adj.get('offense') or not adj.get('works'):
        return off_call
    o = dict(off_call)
    if adj.get('depth_to'): o['depth'] = adj['depth_to']
    if adj.get('keep_in'):  o['keep_in'] = adj['keep_in']
    if adj.get('force_mix'):
        o['is_pass'] = not o['is_pass']          # break the tendency
    return o


# ============================================================ THE CHEATER PLAY
def cheater_available(their_adj):
    """
    The counter-punch. "When the defense cheats to stop the pitch by pinching
    the corners, a play action pass or slot receiver wheel route can be used to
    empty the box. Once a cheater play is used to reset the defense, the
    play-caller can revert back."
    An adjustment vacates something, and that something is the answer.
    """
    if not their_adj or their_adj.get('offense'): return None
    if their_adj.get('cost') == 'run_game':
        return dict(call='run', reason='they dropped the safeties')
    if their_adj.get('cost') == 'deep_ball':
        return dict(call='deep', reason='they pressed and came downhill')
    if their_adj.get('cost') == 'other_receivers':
        return dict(call='other_target', reason='they bracketed our best man')
    if their_adj.get('cost') == 'play_action':
        return dict(call='play_action', reason='they walked a safety into the box')
    return None


# ============================================================ THE SCRIPT
class Script:
    """
    Walsh's opener: a pre-planned sequence run before the defence can counter.
    Coaches come off it when a SITUATION demands, usually third down - not when
    a counter runs out. Off-script performance is measurably worse for some
    callers (Shanahan 2022: +0.32 EPA on script, -0.10 off it), so this carries
    an explicit on/off-script state.
    """
    def __init__(self, plays=None, length=15, off_script_skill=0.5):
        self.plays = plays or []
        self.length = length
        self.used = 0
        self.off_script_skill = off_script_skill
        self.active = True

    def next_call(self, down, ydstogo, rng):
        if not self.active or self.used >= self.length:
            self.active = False
            return None
        # a situation forces him off it
        if down >= 3 or ydstogo <= 2 or ydstogo >= 15:
            return None
        self.used += 1
        return self.plays[self.used - 1] if self.used <= len(self.plays) else None

    def performance_modifier(self):
        """On script is worth something; off script depends on the caller."""
        if self.active and self.used < self.length:
            return 1.06
        return 0.94 + 0.12 * self.off_script_skill
