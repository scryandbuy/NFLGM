/**
 * The gameplan.
 *
 * A team arrives with a plan and the adjustment engine modifies THE PLAN, not
 * individual play calls. Everything downstream reads this one object, which is
 * why a change persists until something changes it back - the way a real
 * adjustment works.
 *
 * This replaces a scattered arrangement where each system carried its own
 * defaults and its own randomness, and where an adjustment patched one call
 * and then evaporated. It also fixes a real bug for free: travel (a corner
 * following a receiver) was being re-rolled on every snap, so a corner might
 * follow on one play and not the next. Travel is a game-plan decision, made
 * once and held.
 *
 * THREE THINGS ARE NOT ADJUSTABLE, and they live on the coach instead:
 *   - scheme identity. You cannot become a zone-blocking team at halftime, and
 *     a coordinator who runs Tite fronts does not install Bear fronts in the
 *     second quarter.
 *   - the playbook's concepts.
 *   - personnel on the roster.
 * The gameplan operates WITHIN those.
 *
 * CHANGES COST DIFFERENT AMOUNTS. Nudging run-pass balance is free. Going from
 * a man team to a zone team mid-game is a structural change that should be
 * slower, rarer, and available only to a good coordinator. COST encodes that.
 *
 * Ported from gameplan.py.
 */
import { RNG } from './core/rng.js';
import { clip } from './core/math.js';

/**
 * How hard each parameter is to change mid-game. 0 = a dial you turn freely,
 * 1 = a wholesale change of identity that most coordinators never make.
 */
export const COST: Record<string, number> = {
  pass_bias: 0.05,
  depth_mix: 0.10,
  tempo: 0.12,
  target_priority: 0.10,
  protection: 0.15,
  blitz_rate: 0.18,
  box_bias: 0.18,
  personnel_mix: 0.25,
  shell_weights: 0.30,
  travel: 0.35,
  bracket: 0.30,
  man_rate: 0.55,        // becoming a man team, or a zone team
  front_pref: 0.70,      // a different defensive front family
  run_scheme_mix: 0.75,  // zone blocking vs gap blocking
};

export interface PlanChange {
  param: string; value: unknown; quarter: number; note: string;
}

/** What a team intends to do. Every play call reads this. */
export class Gameplan {
  // ---- offence ----
  passBias = 0.0;                           // added to the situational pass rate
  depthMix: [number, number, number] = [0.62, 0.24, 0.14];  // short/medium/deep
  personnelMix: Record<string, number> = {
    '11': .595, '12': .195, '21': .070, '13': .030,
    '10': .075, '22': .025, '00': .010,
  };
  runSchemeMix: Record<string, number> = { zone: .62, gap: .38 };
  protection = 'half_slide';
  tempo = 0.5;                              // 0 = grind clock, 1 = no huddle
  targetPriority: Record<string, number> = {};   // pid -> weight
  playActionRate = 0.102;
  // ---- defence ----
  manRate = 0.35;
  shellWeights: Record<string, number> = {
    cover_3: .30, cover_2: .18, cover_4: .22,
    cover_1: .15, tampa_2: .08, cover_6: .07,
  };
  blitzRate = 0.133;
  frontPref: string[] = ['4-3 over', '4-3 under'];
  boxBias = 0.0;
  travel = false;                           // CB1 follows their best receiver
  travelTarget: string | null = null;
  bracket: string | null = null;            // pid being doubled
  // ---- bookkeeping ----
  changes: PlanChange[] = [];

  copy(): Gameplan {
    const g = new Gameplan();
    g.passBias = this.passBias;
    g.depthMix = [...this.depthMix] as [number, number, number];
    g.personnelMix = { ...this.personnelMix };
    g.runSchemeMix = { ...this.runSchemeMix };
    g.protection = this.protection;
    g.tempo = this.tempo;
    g.targetPriority = { ...this.targetPriority };
    g.playActionRate = this.playActionRate;
    g.manRate = this.manRate;
    g.shellWeights = { ...this.shellWeights };
    g.blitzRate = this.blitzRate;
    g.frontPref = [...this.frontPref];
    g.boxBias = this.boxBias;
    g.travel = this.travel;
    g.travelTarget = this.travelTarget;
    g.bracket = this.bracket;
    g.changes = [...this.changes];
    return g;
  }
}

export interface Coach {
  run_scheme_mix?: Record<string, number>;
  front_pref?: string[];
  man_rate?: number;
  blitz_rate?: number;
  tempo?: number;
  pass_bias?: number;
  plan_quality?: number;
  [k: string]: unknown;
}

/**
 * The plan a team walks in with. A good coordinator arrives having already
 * accounted for what the opponent does; a poor one arrives with his defaults
 * and has to discover everything live. That is where coach quality FIRST shows
 * up, before a single adjustment is made.
 */
export function basePlan(
  coach?: Coach | null,
  opponent?: { weaknesses?: Record<string, number> } | null,
): Gameplan {
  const g = new Gameplan();
  if (!coach) return g;
  // scheme identity comes from the coach and is NOT adjustable later
  if (coach.run_scheme_mix) g.runSchemeMix = { ...coach.run_scheme_mix };
  if (coach.front_pref) g.frontPref = [...coach.front_pref];
  if (coach.man_rate !== undefined) g.manRate = Number(coach.man_rate);
  if (coach.blitz_rate !== undefined) g.blitzRate = Number(coach.blitz_rate);
  if (coach.tempo !== undefined) g.tempo = Number(coach.tempo);
  g.passBias = Number(coach.pass_bias ?? 0.0);

  // planning quality: how much of the opponent he has already solved
  if (opponent) {
    const q = Number(coach.plan_quality ?? 0.5);
    const w = opponent.weaknesses ?? {};
    for (const [key, val] of Object.entries(w)) {
      if (key === 'pass_bias') g.passBias += val * q;
      else if (key === 'box_bias') g.boxBias += val * q;
      else if (key === 'blitz_rate') g.blitzRate += val * q;
    }
  }
  return g;
}

/**
 * Is this coordinator capable of making this change mid-game? A cheap dial
 * yes; a change of identity only if he is good and the situation demands it.
 */
export function canChange(param: string, skill: number, urgency = 0.5): boolean {
  const c = COST[param] ?? 0.3;
  return (skill * (0.55 + 0.75 * urgency)) >= c;
}

/**
 * Modify the PLAN. Returns [newPlan, applied]. A change that is too expensive
 * for this coordinator simply does not happen.
 */
export function applyChange(
  plan: Gameplan, param: string, value: unknown, skill: number,
  urgency = 0.5, note = '', quarter = 1,
): [Gameplan, boolean] {
  if (!canChange(param, skill, urgency)) return [plan, false];
  const g = plan.copy();
  if (param === 'shell_weights' && value && typeof value === 'object') {
    const w: Record<string, number> = { ...g.shellWeights };
    for (const [k, v] of Object.entries(value as Record<string, number>)) {
      w[k] = Math.max(0.0, (w[k] ?? 0.0) + v);
    }
    let tot = 0; for (const v of Object.values(w)) tot += v;
    if (!tot) tot = 1.0;
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(w)) out[k] = v / tot;
    g.shellWeights = out;
  } else if (param === 'depth_mix' && Array.isArray(value)) {
    const v = (value as number[]).map(x => Math.max(0.02, x));
    let s = 0; for (const x of v) s += x;
    g.depthMix = v.map(x => x / s) as unknown as [number, number, number];
  } else if (param === 'pass_bias') {
    g.passBias = clip(g.passBias + Number(value), -0.45, 0.45);
  } else if (param === 'box_bias') {
    g.boxBias = clip(g.boxBias + Number(value), -0.45, 0.45);
  } else if (param === 'man_rate') {
    g.manRate = clip(g.manRate + Number(value), 0.0, 1.0);
  } else if (param === 'blitz_rate') {
    g.blitzRate = clip(g.blitzRate + Number(value), 0.0, 1.0);
  } else if (param === 'tempo') {
    g.tempo = clip(g.tempo + Number(value), 0.0, 1.0);
  } else if (param === 'play_action_rate') {
    g.playActionRate = clip(g.playActionRate + Number(value), 0.0, 1.0);
  } else if (param === 'protection') {
    g.protection = String(value);
  } else if (param === 'front_pref') {
    g.frontPref = [...(value as string[])];
  } else if (param === 'travel') {
    g.travel = Boolean(value);
  } else if (param === 'bracket') {
    g.bracket = value as string | null;
  } else if (param === 'personnel_mix') {
    g.personnelMix = { ...(value as Record<string, number>) };
  } else if (param === 'run_scheme_mix') {
    g.runSchemeMix = { ...(value as Record<string, number>) };
  } else if (param === 'target_priority') {
    g.targetPriority = { ...(value as Record<string, number>) };
  }
  g.changes.push({ param, value, quarter, note });
  return [g, true];
}

// ============================================================ READING THE PLAN
export function shell(plan: Gameplan, rng: RNG): string {
  const ks = Object.keys(plan.shellWeights);
  return rng.choice(ks, ks.map(k => plan.shellWeights[k]));
}

export function isMan(plan: Gameplan, rng: RNG): boolean {
  return rng.next() < plan.manRate;
}

export function depth(plan: Gameplan, rng: RNG): 'short' | 'medium' | 'deep' {
  return rng.choice(['short', 'medium', 'deep'] as const, plan.depthMix);
}

export function personnel(plan: Gameplan, rng: RNG): string {
  const ks = Object.keys(plan.personnelMix);
  return rng.choice(ks, ks.map(k => plan.personnelMix[k]));
}

export function runFamily(plan: Gameplan, rng: RNG): 'zone' | 'gap' {
  return rng.next() < (plan.runSchemeMix['zone'] ?? 0.62) ? 'zone' : 'gap';
}

export function blitzers(plan: Gameplan, rng: RNG, down = 1, ydstogo = 10): number {
  const r = plan.blitzRate * ((down === 3 && ydstogo >= 6) ? 1.35 : 1.0);
  const x = rng.next();
  if (x < r * 0.73) return 1;
  if (x < r * 0.96) return 2;
  if (x < r) return 3;
  return 0;
}

// ============================================================ ADJUSTMENT BRIDGE
/**
 * Maps the adjustment engine's structural counters onto gameplan changes, so
 * an adjustment persists instead of patching one call and evaporating.
 */
export const COUNTER_TO_PLAN: Record<string, Array<[string, unknown]>> = {
  pass_deep: [
    ['shell_weights', { cover_2: .18, cover_4: .16, cover_1: -.08, cover_3: -.10 }],
    ['box_bias', -0.10],
  ],
  pass_medium: [
    ['shell_weights', { cover_3: .14, tampa_2: .12, cover_1: -.10 }],
  ],
  pass_short: [
    ['shell_weights', { cover_1: .16, cover_0: .06, cover_4: -.12 }],
    ['man_rate', 0.12], ['box_bias', 0.08],
  ],
  target: [
    ['bracket', 'TARGET'], ['travel', true],
    ['shell_weights', { cover_2: .12, cover_4: .10 }],
  ],
  run: [['box_bias', 0.22], ['front_pref', ['bear', 'tite']]],
  protection: [['protection', 'seven'], ['depth_mix', [0.80, 0.16, 0.04]]],
  predictable: [['pass_bias', 0.0]],   // handled by forcing a mix
};

export interface Counter {
  works?: boolean; trigger?: string; kind?: string; target?: string | null;
  [k: string]: unknown;
}

/**
 * Fold an adjustment into the plan. Each parameter is gated by its own cost,
 * so a coordinator may successfully walk a safety down (cheap) and fail to
 * become a man team (expensive) off the same read.
 */
export function adjustPlan(
  plan: Gameplan, counter: Counter | null, skill: number,
  urgency = 0.5, quarter = 1,
): [Gameplan, string[]] {
  if (!counter || !counter.works) return [plan, []];
  const trig = counter.trigger;
  const steps = (trig ? COUNTER_TO_PLAN[trig] : undefined)
    ?? (counter.kind ? COUNTER_TO_PLAN[counter.kind] : undefined) ?? [];
  const applied: string[] = [];
  let g = plan;
  // A change already in effect is not made again. Without this the same
  // counter re-fired every series and an elite coordinator racked up 16 plan
  // changes in a game; a real one makes a handful.
  const recent = new Set(plan.changes.slice(-6).map(c => c.param));
  for (const [param, valIn] of steps) {
    let val = valIn;
    if (recent.has(param)) continue;
    if (param === 'travel' && plan.travel) continue;
    if (param === 'bracket' && plan.bracket === counter.target) continue;
    if (param === 'bracket' && val === 'TARGET') {
      val = counter.target ?? null;
      if (!val) continue;
    }
    if (param === 'travel') {
      // you cannot shadow anyone out of zone - nobody is assigned a man
      if (g.manRate < 0.25) continue;
      const planTarget = counter.target ?? null;
      const [g2, ok] = applyChange(g, 'travel', true, skill, urgency,
                                   trig ?? '', quarter);
      if (ok) { g2.travelTarget = planTarget; g = g2; applied.push('travel'); }
      continue;
    }
    const [g3, ok] = applyChange(g, param, val, skill, urgency, trig ?? '', quarter);
    g = g3;
    if (ok) applied.push(param);
  }
  return [g, applied];
}
