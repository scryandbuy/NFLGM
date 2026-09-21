/**
 * In-game adjustment.
 *
 * Built from what coaches actually describe, plus FM26's working model. Madden
 * was not useful here: it detects a REPEATED PLAY within a game and counters
 * it, and has no memory across a season.
 *
 * WHAT THE COACHES SAY:
 *
 *   Halftime adjustment is largely a myth. An NFL head coach: "If you wait
 *   until halftime to make your adjustments, you're too late." Wade Phillips
 *   describes it as continuous - one team does something, the other adjusts,
 *   that team counters the adjustment, and it goes on all game - and says
 *   clubs adjust AFTER EACH SERIES. Josh McDaniels: changes begin almost
 *   immediately and continue each series; only the most profound changes wait
 *   for the half.
 *
 *   THE SERIES IS THE UNIT. Not the play, not the half.
 *
 *   The response is STRUCTURAL, not a single assignment. Wade Phillips had
 *   A.J. Green toasting his corners in aggressive man, so he went to zone
 *   concepts. Cincinnati went from 204 yards in the first half to 90 after.
 *
 *   OFFENCE OPENS ON A SCRIPT, specifically to get its plan executed before
 *   the defence can counter. Walsh scripted 15-25 plays. Coaches come off
 *   script when a SITUATION demands it, usually third down, not when a play
 *   counter runs out. Off-script is measurably worse for some coaches:
 *   Shanahan's 2022 49ers had +0.32 passing EPA on script and -0.10 off it.
 *
 *   THE CHEATER PLAY. When a defence cheats to stop something, the offence
 *   punishes the vacated space - play action or a wheel into an emptied box -
 *   then reverts to the base series and chips away again.
 *
 *   SELF-SCOUTING is a real job: reviewing your own predictability to avoid
 *   exploitable habits.
 *
 *   BOTH ERRORS ARE REAL. Abandoning what works is as damaging as failing to
 *   adjust.
 *
 * WHAT FM26 CONTRIBUTES:
 *   Adaptive pressing - the AI reads WHERE you attack and answers structurally.
 *   Preventative management - proactive substitution off fatigue.
 *   And a warning from its own community: FM's AI counters too fast and too
 *   reliably, so "every AI manager is Mourinho". An adjustment that always
 *   works is as wrong as no adjustment at all. Counters here can fail.
 *
 * NOTE: how FAST and how MUCH a coach adjusts belongs on his ratings, which
 * are on the to-do list with the GM/coach pool. Everything here reads a single
 * `skill` parameter so those ratings drop straight in.
 *
 * Ported from adjust.py.
 */
import { RNG } from './core/rng.js';
import { clip } from './core/math.js';

/**
 * What gets watched. Trends, not repeated plays. Each is something a
 * coordinator would actually notice over a handful of series.
 */
export const TRENDS = [
  'pass_depth', 'run_direction', 'target_concentration', 'personnel',
  'tempo', 'protection', 'front_success', 'coverage_success',
] as const;

export const MIN_SERIES = 2;   // nothing fires off one drive
export const MIN_EVENTS = 5;   // nor off a tiny sample

export interface PlayCall {
  isPass: boolean; depth?: string; scheme?: string; personnel?: string;
  keepIn?: number; [k: string]: unknown;
}
export interface DefCallLike {
  rushers?: number; shell?: string; front?: string; box?: number;
  man?: boolean; bracket?: string | null; [k: string]: unknown;
}
export interface Outcome {
  type: string; yards?: number; touchdown?: boolean; target?: string;
  [k: string]: unknown;
}

/**
 * What one side has seen this game. Rolling, series-indexed, so a trend that
 * stopped three drives ago fades instead of counting forever.
 */
export class GameMemory {
  window: number;
  series = 0;
  bySeries: Map<number, Map<string, unknown[]>> = new Map();

  constructor(window = 4) { this.window = window; }

  newSeries(): void { this.series += 1; }

  private bucket(s: number, key: string): unknown[] {
    let m = this.bySeries.get(s);
    if (!m) { m = new Map(); this.bySeries.set(s, m); }
    let a = m.get(key);
    if (!a) { a = []; m.set(key, a); }
    return a;
  }

  record(playCall: PlayCall, defCall: DefCallLike, outcome: Outcome): void {
    const s = this.series;
    const gained = outcome.yards ?? 0.0;
    // Coerce success to a real bool. outcome.touchdown is undefined on plays
    // that carry no such key, and the success means below then tried to sum
    // undefined values.
    const ok = Boolean(gained >= 4.0 || outcome.touchdown);
    if (playCall.isPass) {
      this.bucket(s, 'pass_depth').push([playCall.depth ?? 'short', gained, ok]);
      const t = outcome.target;
      if (t) this.bucket(s, 'targets').push([t, gained, ok]);
      this.bucket(s, 'protection').push([outcome.type === 'sack', defCall.rushers ?? 4]);
      this.bucket(s, 'coverage').push([defCall.shell ?? 'cover_3', gained, ok]);
    } else {
      this.bucket(s, 'run').push([playCall.scheme ?? 'inside_zone', gained, ok]);
      this.bucket(s, 'front').push([defCall.front ?? '4-3 over',
                                    defCall.box ?? 6, gained, ok]);
    }
    this.bucket(s, 'personnel').push(playCall.personnel ?? '11');
    this.bucket(s, 'calls').push(playCall.isPass ? 'pass' : 'run');
  }

  /** Everything in the rolling window. */
  recent(key: string): unknown[] {
    const lo = Math.max(0, this.series - this.window + 1);
    const out: unknown[] = [];
    for (let s = lo; s <= this.series; s++) {
      const m = this.bySeries.get(s);
      if (m) { const a = m.get(key); if (a) out.push(...a); }
    }
    return out;
  }

  seriesSeen(): number { return Math.min(this.series, this.window); }
}

// ============================================================ DETECTION
export interface Trend {
  kind: string; value: string; rate: number; n: number; conf: number;
  share?: number;
}

const mean = (xs: number[]): number => {
  let s = 0; for (const x of xs) s += x; return xs.length ? s / xs.length : 0;
};

/**
 * Confidence grows with sample and with the coach's eye, but SATURATES
 * slowly. A linear ratio hit 1.00 after eight plays and made every coach
 * identical, which defeated the whole point of skill.
 */
export function conf(n: number, need: number, skill: number): number {
  const raw = 1.0 - Math.exp(-0.55 * n / Math.max(need, 1));
  return clip(raw * (0.45 + 0.65 * skill), 0.0, 0.97);
}

/**
 * What is actually happening to us. Returns trends with a confidence, which
 * scales with the sample AND with the coach's skill - a sharper coordinator
 * reads it off a smaller sample, which is the professional-versus-high-school
 * difference the coaching sources describe.
 */
export function detect(mem: GameMemory, skill = 0.5): Record<string, Trend> {
  const found: Record<string, Trend> = {};
  if (mem.seriesSeen() < MIN_SERIES) return found;
  const need = MIN_EVENTS * (1.4 - 0.8 * skill);

  // --- who is beating us, and at what depth ---
  const pd = mem.recent('pass_depth') as Array<[string, number, boolean]>;
  if (pd.length >= need) {
    const by = new Map<string, boolean[]>();
    for (const [d, , ok] of pd) {
      const a = by.get(d); if (a) a.push(ok); else by.set(d, [ok]);
    }
    for (const [d, res] of by) {
      const m = mean(res.map(x => (x ? 1 : 0)));
      if (res.length >= 3 && m >= 0.55) {
        found[`pass_${d}`] = { kind: 'pass_depth', value: d, rate: m,
                               n: res.length, conf: conf(res.length, need, skill) };
      }
    }
  }

  // --- one receiver eating us alive ---
  const tg = mem.recent('targets') as Array<[string, number, boolean]>;
  if (tg.length >= need) {
    const by = new Map<string, Array<[number, boolean]>>();
    for (const [t, g, ok] of tg) {
      const a = by.get(t); if (a) a.push([g, ok]); else by.set(t, [[g, ok]]);
    }
    for (const [t, res] of by) {
      const share = res.length / tg.length;
      const succ = mean(res.map(([, o]) => (o ? 1 : 0)));
      if (share >= 0.30 && succ >= 0.55 && res.length >= 3) {
        found['target'] = { kind: 'target', value: t, rate: succ, share,
                            n: res.length, conf: conf(res.length, need, skill) };
      }
    }
  }

  // --- the run game is gashing us ---
  const rn = mem.recent('run') as Array<[string, number, boolean]>;
  if (rn.length >= need) {
    const by = new Map<string, Array<[number, boolean]>>();
    for (const [sc, g, ok] of rn) {
      const a = by.get(sc); if (a) a.push([g, ok]); else by.set(sc, [[g, ok]]);
    }
    const allg = rn.map(([, g]) => g);
    if (mean(allg) >= 4.6) {
      // max() over a dict in Python keeps the FIRST key on a tie and iterates
      // in insertion order, so this must too.
      let worst = ''; let best = -Infinity;
      for (const [k, v] of by) {
        const m = mean(v.map(([g]) => g));
        if (m > best) { best = m; worst = k; }
      }
      found['run'] = { kind: 'run', value: worst, rate: mean(allg),
                       n: rn.length, conf: conf(rn.length, need, skill) };
    }
  }

  // --- our own protection is failing ---
  const pr = mem.recent('protection') as Array<[boolean, number]>;
  if (pr.length >= need) {
    const sacked = mean(pr.map(([s]) => (s ? 1 : 0)));
    if (sacked >= 0.14) {
      found['protection'] = { kind: 'protection', value: 'failing', rate: sacked,
                              n: pr.length, conf: conf(pr.length, need, skill) };
    }
  }

  // --- we are predictable (self-scout) ---
  const calls = mem.recent('calls') as string[];
  if (calls.length >= need) {
    const p = mean(calls.map(c => (c === 'pass' ? 1 : 0)));
    if (p >= 0.80 || p <= 0.20) {
      found['predictable'] = { kind: 'predictable',
                               value: p >= 0.8 ? 'pass' : 'run',
                               rate: Math.max(p, 1 - p), n: calls.length,
                               conf: conf(calls.length, need, skill) };
    }
  }
  return found;
}

// ============================================================ RESPONSE
/**
 * Structural counters, as the coaching sources describe. Each carries a COST,
 * because a defence that rolls help somewhere has taken it from somewhere else.
 */
export interface CounterDef {
  shell_to?: string[]; front_to?: string[]; box?: number; bracket?: boolean;
  offense?: boolean; keep_in?: number; depth_to?: string; force_mix?: boolean;
  cost: string | null; desc: string;
}

export const COUNTERS: Record<string, CounterDef> = {
  pass_deep: { shell_to: ['cover_2', 'cover_4'], box: -0.6, cost: 'run_game',
               desc: 'drop the safeties, take away the top' },
  pass_medium: { shell_to: ['cover_3', 'tampa_2'], box: -0.3, cost: 'run_game',
                 desc: 'more zone underneath' },
  pass_short: { shell_to: ['cover_1', 'cover_0'], box: +0.4, cost: 'deep_ball',
                desc: 'press and squeeze the quick game' },
  target: { bracket: true, shell_to: ['cover_2', 'cover_4'], box: -0.8,
            cost: 'other_receivers', desc: 'shadow and bracket the man beating us' },
  run: { box: +1.4, front_to: ['bear', 'tite', '4-3 under'], cost: 'play_action',
         desc: 'walk a safety down, heavier front' },
  protection: { offense: true, keep_in: 1, depth_to: 'short', cost: 'routes',
                desc: 'keep a back in, get the ball out' },
  predictable: { offense: true, force_mix: true, cost: null,
                 desc: 'break our own tendency before they read it' },
};

export interface Adjustment extends CounterDef {
  works: boolean; trigger: string; target: string | null; confidence: number;
  [k: string]: unknown;
}

/**
 * Pick an adjustment. A coach with a low willingness stays the course, which
 * the coaching material explicitly defends: "Change for change sake is a
 * really bad idea in the middle of a football game."
 */
export function respond(
  trends: Record<string, Trend>, skill = 0.5, aggressiveness = 0.5, rng?: RNG,
): Adjustment | null {
  const r = rng ?? new RNG(1);
  const keys = Object.keys(trends);
  if (!keys.length) return null;
  // A receiver destroying you is a more urgent problem than a generic depth
  // trend, and a run game gashing you more urgent still. Without a priority
  // weight the plain max() always picked the same trend on ties.
  const PRIORITY: Record<string, number> = {
    target: 1.45, run: 1.35, protection: 1.30, predictable: 0.85,
  };
  // Python's max() keeps the FIRST item on a tie, and dict order is insertion
  // order, so a strict > comparison over the same order is required.
  let key = ''; let t: Trend | null = null; let best = -Infinity;
  for (const k of keys) {
    const v = trends[k];
    const score = v.conf * v.rate * (PRIORITY[k] ?? 1.0);
    if (score > best) { best = score; key = k; t = v; }
  }
  if (!t) return null;
  const ckey = key in COUNTERS ? key : t.kind;
  if (!(ckey in COUNTERS)) return null;

  // will he even act? confidence x willingness
  if (r.next() > t.conf * (0.30 + 0.80 * aggressiveness)) return null;

  const c = { ...COUNTERS[ckey] } as Adjustment;
  // FM's community complains their AI counters too reliably - "every AI
  // manager is Mourinho" - so a counter that always works is as wrong as no
  // counter at all. A counter that works three times in four removes the
  // contest; these numbers put an average coordinator near a coin flip and an
  // elite one at about 70%.
  c.works = r.next() < (0.18 + 0.58 * skill);
  c.trigger = key;
  c.target = t.value ?? null;
  c.confidence = t.conf;
  return c;
}

// ============================================================ APPLY
/** Fold a defensive adjustment into this play's call. */
export function applyDefensive<T extends DefCallLike>(
  defCall: T, adj: Adjustment | null, rng: RNG,
): T {
  if (!adj || adj.offense || !adj.works) return defCall;
  const d = { ...defCall } as DefCallLike;
  if (adj.shell_to && adj.shell_to.length && rng.next() < 0.70) {
    d.shell = adj.shell_to[rng.integers(0, adj.shell_to.length)];
    d.man = d.shell === 'cover_0' || d.shell === 'cover_1';
  }
  if (adj.front_to && adj.front_to.length && rng.next() < 0.55) {
    d.front = adj.front_to[rng.integers(0, adj.front_to.length)];
  }
  if (adj.box) {
    d.box = clip((d.box ?? 6) + pyRound(adj.box), 4, 10);
  }
  if (adj.bracket) d.bracket = adj.target;
  return d as T;
}

/** Fold an offensive adjustment into this play's call. */
export function applyOffensive<T extends PlayCall>(
  offCall: T, adj: Adjustment | null, _rng: RNG,
): T {
  if (!adj || !adj.offense || !adj.works) return offCall;
  const o = { ...offCall } as PlayCall;
  if (adj.depth_to) o.depth = adj.depth_to;
  if (adj.keep_in) o.keepIn = adj.keep_in;
  if (adj.force_mix) o.isPass = !o.isPass;     // break the tendency
  return o as T;
}

/**
 * Python's round() is banker's rounding: 0.5 goes to the nearest EVEN integer,
 * where JavaScript's Math.round always goes up. The box deltas above include
 * values that land on a half, so this has to match or a walked-down safety
 * appears in one port and not the other.
 */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// ============================================================ THE CHEATER PLAY
export interface Cheater { call: string; reason: string; }

/**
 * The counter-punch. When the defence cheats to stop the pitch by pinching the
 * corners, a play action pass or a slot receiver wheel can empty the box. Once
 * a cheater play resets the defence, the play-caller reverts back.
 * An adjustment vacates something, and that something is the answer.
 */
export function cheaterAvailable(theirAdj: Adjustment | null): Cheater | null {
  if (!theirAdj || theirAdj.offense) return null;
  if (theirAdj.cost === 'run_game') {
    return { call: 'run', reason: 'they dropped the safeties' };
  }
  if (theirAdj.cost === 'deep_ball') {
    return { call: 'deep', reason: 'they pressed and came downhill' };
  }
  if (theirAdj.cost === 'other_receivers') {
    return { call: 'other_target', reason: 'they bracketed our best man' };
  }
  if (theirAdj.cost === 'play_action') {
    return { call: 'play_action', reason: 'they walked a safety into the box' };
  }
  return null;
}

// ============================================================ THE SCRIPT
/**
 * Walsh's opener: a pre-planned sequence run before the defence can counter.
 * Coaches come off it when a SITUATION demands, usually third down - not when
 * a counter runs out. Off-script performance is measurably worse for some
 * callers (Shanahan 2022: +0.32 EPA on script, -0.10 off it), so this carries
 * an explicit on/off-script state.
 */
export class Script {
  plays: unknown[];
  length: number;
  used = 0;
  offScriptSkill: number;
  active = true;

  constructor(plays: unknown[] | null = null, length = 15, offScriptSkill = 0.5) {
    this.plays = plays ?? [];
    this.length = length;
    this.offScriptSkill = offScriptSkill;
  }

  nextCall(down: number, ydstogo: number, _rng?: RNG): unknown {
    if (!this.active || this.used >= this.length) {
      this.active = false;
      return null;
    }
    // a situation forces him off it
    if (down >= 3 || ydstogo <= 2 || ydstogo >= 15) return null;
    this.used += 1;
    return this.used <= this.plays.length ? this.plays[this.used - 1] : null;
  }

  /** On script is worth something; off script depends on the caller. */
  performanceModifier(): number {
    if (this.active && this.used < this.length) return 1.06;
    return 0.94 + 0.12 * this.offScriptSkill;
  }
}
