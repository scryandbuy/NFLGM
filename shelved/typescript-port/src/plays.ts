/**
 * Play resolution: what happens on a single snap.
 *
 * Ported from plays.py. Every constant here was solved against six seasons of
 * real play-by-play (281,339 plays), FTN charting, and Next Gen tracking, and
 * re-solved a second time against the REAL 2026 rosters - synthetic test teams
 * were systematically worse than actual NFL players, so anything fitted
 * against them came out too generous. The comments record what each number is
 * anchored to, because the numbers are the asset here, not the code.
 *
 * Nothing in this file samples an outcome from a table. A snap is resolved by
 * running the individual matchups and letting the result fall out.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, edge, logistic, clip, mean, Player, Weights } from './core/math.js';
import {
  PASS_RUSH, ROUTE, THROW, CATCH, YAC, RUN_BLOCK, BALL_SECURITY, resolveZone,
} from './matchups.js';
import * as S from './schemes.js';
import { RUN_SCHEMES, FRONTS, CONCEPTS } from './schemeTables.js';
import * as CV from './coverage.js';
import * as TG from './targets.js';

/** Per-rusher base time to arrive. */
export const RUSHER_BASE = 3.16;
/** The league mean the clock must land on. */
export const BASE_TTT = 2.72;

export interface Protection {
  time: number; pressure: number; sack: boolean;
  beatenBy?: string; beaten?: string; move: string;
}

/**
 * PROTECTION. Five individual matchups per dropback. The rusher picks the move
 * his own profile favours; the blocker defends the move he actually GETS,
 * which is how a powerful tackle loses to speed and a light one loses to a
 * bull rush.
 *
 * The clock is the MINIMUM across four rushers, and the minimum of several
 * draws sits well below any one of them - which is why the per-rusher base
 * (3.16) is far above the 2.72s league mean it has to produce. An early build
 * used 2.72 per rusher and got a 2.12s average.
 */
export function resolveProtection(
  blockers: Player[], rushers: Player[], rng: RNG, qb?: Player,
): Protection {
  const wins: Array<[number, string, Player, Player | null]> = [];
  for (let i = 0; i < rushers.length; i++) {
    const r = rushers[i];
    const b = i < blockers.length ? blockers[i] : null;
    const pw = rate(r, PASS_RUSH.rusher.power);
    const fn = rate(r, PASS_RUSH.rusher.finesse);
    const move = pw >= fn ? 'power' : 'finesse';
    const atk = Math.max(pw, fn);
    if (!b) { wins.push([0.6, move, r, null]); continue; }
    const dfn = rate(b, (PASS_RUSH.blocker as any)[move]);
    const e = edge(atk, dfn);
    // Sensitivity 0.35, solved. At 1.15 the rating gap swung the clock so hard
    // an average line against an elite front sacked on 42% of dropbacks; the
    // real spread is roughly 4% to 11%.
    const t = RUSHER_BASE * (1.0 - 0.35 * e) * Math.exp(rng.normal(0.0, 0.26));
    wins.push([Math.max(0.35, t), move, r, b]);
  }

  let best = wins[0];
  for (const w of wins) if (w[0] < best[0]) best = w;
  let [tArrive, move, winner, loser] = best;

  // the QB's own escapability buys time once someone arrives
  if (qb) {
    tArrive *= 1.0 + 0.55 * (rate(qb, {
      break_sack_rating: 0.6, agility_rating: 0.25, speed_rating: 0.15,
    }) - AVG);
  }

  const pressure = clip((BASE_TTT - tArrive) / BASE_TTT, 0, 1);
  // Sack chance falls off SMOOTHLY rather than tripping a threshold. A hard
  // cliff meant any matchup whose mean clock sat under it sacked on most
  // dropbacks. Re-solved on real rosters: actual NFL linemen hold up far
  // better than test clones, which pinned sacks at 3.85% against a real 6.6%.
  let pSack = 25.0 * Math.exp(-2.40 * tArrive);
  if (qb) pSack *= 1.0 - 0.45 * (rate(qb, { break_sack_rating: 1.0 }) - AVG);
  const sack = rng.next() < clip(pSack, 0, 0.85);

  return {
    time: round2(tArrive), pressure: round3(pressure), sack, move,
    beatenBy: winner.pid, beaten: loser ? loser.pid : undefined,
  };
}

/**
 * MAN COVERAGE. The defender watches the RECEIVER, head often turned from the
 * ball. The contest is separation, and separation is what the throw is aimed
 * into. Returns 0-1, higher meaning more open; league average is 0.42, which
 * maps to the real 3.04 yards of tracked separation.
 */
export function resolveMan(
  receiver: Player, defender: Player, depth: Depth, timeAvailable: number, rng: RNG,
): number {
  const rel = edge(rate(receiver, ROUTE.receiver.release),
                   rate(defender, ROUTE.defenderMan.press));
  const rt = edge(rate(receiver, (ROUTE.receiver as any)[depth]),
                  rate(defender, (ROUTE.defenderMan as any)[depth]));
  // a release win compounds the longer the route runs
  const w = { short: 0.55, medium: 0.40, deep: 0.28 }[depth];
  let sep = 0.42 + 1.30 * (w * rel + (1 - w) * rt);
  sep *= 1.0 + 0.10 * (timeAvailable - BASE_TTT) / BASE_TTT;
  return clip(sep + rng.normal(0, 0.11), 0.02, 0.98);
}

export type Depth = 'short' | 'medium' | 'deep';

/**
 * These sit BEFORE drops, the concept modifier and pressure, all of which come
 * off the top. Calibrating them to the FINAL completion rate left the chain 11
 * points low and man coverage at 62.8% short against a real 74.4%.
 */
const DEPTH_MULT: Record<Depth, number> = { short: 1.74, medium: 1.24, deep: 0.88 };

export interface ThrowResult { result: 'complete' | 'incomplete' | 'interception'; contested: boolean; }

/** THE THROW. Accuracy at this depth against the separation actually available. */
export function resolveThrow(
  qb: Player, depth: Depth, separation: number, pressure: number, rng: RNG,
  opts: { onRun?: boolean; playAction?: boolean; outcomeMult?: number } = {},
): ThrowResult {
  const { onRun = false, playAction = false, outcomeMult = 1.0 } = opts;
  let acc = rate(qb, (THROW as any)[depth]);
  if (pressure > 0) {
    const up = rate(qb, THROW.under_pressure);
    acc *= 1.0 - pressure * (0.42 - 0.34 * (up - AVG));
  }
  if (onRun) acc *= 0.88 + 0.24 * (rate(qb, THROW.on_run) - AVG);
  if (playAction) acc *= 1.0 + 0.12 * (rate(qb, THROW.play_action) - AVG);

  // A deep throw is harder for EVERYONE, not just for a QB with poor deep
  // accuracy. An early build used one depth-independent multiplier, so short,
  // medium and deep completed at the same rate from the same separation.
  const p = clip(separation * DEPTH_MULT[depth] * (1.0 + 1.15 * (acc - AVG))
                 * outcomeMult, 0.02, 0.97);

  if (rng.next() < p) return { result: 'complete', contested: separation < 0.35 };
  // a bad throw into tight coverage is where picks come from - calibrated to
  // the real 2.1% league interception rate
  const pInt = (1.0 - separation) * 0.112 * (1.0 + 2.2 * (AVG - acc));
  if (rng.next() < Math.max(0, pInt)) return { result: 'interception', contested: true };
  return { result: 'incomplete', contested: separation < 0.45 };
}

/**
 * THE CATCH. Real drop rates run roughly 2% for the best hands to 8% for the
 * worst; an early build spread them only 95.0 to 96.9, so hands did not matter.
 */
export function resolveCatch(
  receiver: Player, defender: Player, contested: boolean, rng: RNG,
): boolean {
  let p: number;
  if (!contested) {
    p = 0.952 + 0.55 * (rate(receiver, CATCH.clean) - AVG);
  } else {
    p = 0.50 + 1.10 * edge(rate(receiver, CATCH.contested),
                           rate(defender, CATCH.defender));
  }
  return rng.next() < clip(p, 0.05, 0.995);
}

export interface AfterResult { yards: number; brokenTackles: number; touchdown: boolean; ybc?: number; }

/**
 * YARDS AFTER. Shared by yards after catch and by a run that clears the line.
 * Nothing caps the yardage: he runs until someone catches him, and the FIELD
 * is the limit.
 *
 * Each successive defender is HARDER to beat, because the further he runs the
 * better the angles behind him get. Without that ramp a good back beats the
 * two or three men in front of him and is gone, which produced a 30-yard
 * average and a 50% explosive rate against a real 4.52 and 2.46%.
 */
export function resolveYardsAfter(
  carrier: Player, tacklers: Player[], yardsToEndzone: number, rng: RNG,
  opts: { contactAt?: number; inSpace?: boolean } = {},
): AfterResult {
  const { contactAt = 0, inSpace = false } = opts;
  let gained = contactAt;
  const elus = rate(carrier, YAC.carrier.elusive);
  const powr = rate(carrier, YAC.carrier.power);
  const brk = rate(carrier, YAC.carrier.breakaway);
  const vis = rate(carrier, YAC.carrier.vision);
  let broken = 0;
  let beatAll = true;

  for (let i = 0; i < tacklers.length; i++) {
    if (gained >= yardsToEndzone) { beatAll = false; break; }
    const t = tacklers[i];
    const wrap = rate(t, YAC.tackler.wrap);
    const atk = Math.max(elus, powr) + 0.30 * (vis - AVG);
    // A receiver catching the ball in space is not a back hitting a pile: he
    // has room to make the first man miss. Using the run chain's difficulty
    // for both left YAC at 2.96 against a real 5.19.
    const base = inSpace ? 0.145 : 0.13;
    const ramp = inSpace ? 0.105 : 0.10;
    const pBreak = logistic(edge(atk, wrap) - base - ramp * i, 7.0);
    if (rng.next() > pBreak) {
      gained += Math.max(0, rng.normal(0.9, 0.8));       // brought down
      beatAll = false;
      break;
    }
    broken++;
    const chase = logistic(edge(brk, rate(t, YAC.tackler.angle)), 5.5);
    gained += Math.max(0.3, rng.gamma(1.7, (inSpace ? 1.6 : 1.4)
                                           + (inSpace ? 4.6 : 4.4) * chase));
  }

  if (beatAll) {
    // Every pursuer beaten. Rare by construction, and even then the secondary
    // still has to be outrun. Mean and tail must be tuned SEPARATELY: raising
    // the break rate lifts both together and cannot hit a 4.52 mean with a
    // 2.46% explosive rate at the same time.
    const ang = tacklers.length
      ? mean(tacklers.map(t => rate(t, YAC.tackler.angle))) : AVG;
    const chaseAll = logistic(edge(brk, ang), 5.0);
    if (rng.next() < 0.35 + 0.45 * chaseAll) {
      gained = yardsToEndzone;                            // house call
    } else {
      gained += Math.max(1.0, rng.gamma(2.2, 5.0 + 9.0 * chaseAll));
    }
  }

  gained = Math.min(gained, yardsToEndzone);
  return { yards: round1(gained), brokenTackles: broken, touchdown: gained >= yardsToEndzone };
}

/**
 * RUN PLAY. Blocking produces yards before contact, then the carrier runs the
 * same gauntlet as a receiver after the catch.
 */
export function resolveRun(
  carrier: Player, blockers: Player[], defenders: Player[],
  yardsToEndzone: number, rng: RNG,
): AfterResult {
  const n = Math.min(blockers.length, defenders.length);
  const wins: number[] = [];
  for (let i = 0; i < n; i++) {
    const pw = rate(blockers[i], RUN_BLOCK.blocker.power);
    const fn = rate(blockers[i], RUN_BLOCK.blocker.finesse);
    const shed = rate(defenders[i], RUN_BLOCK.defender.shed);
    wins.push(edge(Math.max(pw, fn), shed));
  }
  const push = wins.length ? mean(wins) : 0;
  const fill = defenders.length
    ? mean(defenders.map(d => rate(d, RUN_BLOCK.defender.fill))) : AVG;

  // yards before contact: average line vs average front ~ 2.1 yards
  let ybc = 2.32 + 9.0 * push - 3.2 * (fill - AVG) + rng.normal(0, 1.42);
  ybc = Math.max(-4.0, ybc);
  if (ybc < 0) {                                          // stuffed behind the line
    return { yards: round1(ybc), brokenTackles: 0, touchdown: false, ybc: round1(ybc) };
  }

  // He faces everyone still on his feet, not just the unblocked leftovers.
  // Passing two or three chasers made breaking into the open trivial.
  const chasers = [...defenders.slice(n), ...defenders.slice(0, n)];
  const out = resolveYardsAfter(carrier, chasers, yardsToEndzone, rng, { contactAt: ybc });
  out.ybc = round1(ybc);
  return out;
}

export function fumbleChance(carrier: Player, hitPower: number, rng: RNG): boolean {
  const sec = rate(carrier, BALL_SECURITY);
  const p = 0.011 * (1.0 + 2.4 * (AVG - sec)) * (1.0 + 1.3 * (hitPower - AVG));
  return rng.next() < Math.max(0, p);
}

/**
 * You cannot throw a 22-yard route from the 8. The field decides. But from the
 * 15-20 a shot to the back of the end zone IS available, and barring it made
 * scoring from there nearly impossible: 1.9% per play against a real 6.96%.
 */
export function availableDepths(ytg: number): Depth[] {
  if (ytg <= 6) return ['short'];
  if (ytg <= 12) return ['short', 'medium'];
  return ['short', 'medium', 'deep'];
}

const round1 = (x: number) => Math.round(x * 10) / 10;
const round2 = (x: number) => Math.round(x * 100) / 100;
const round3 = (x: number) => Math.round(x * 1000) / 1000;

// ============================================================ THE PLAY
/**
 * Red-zone compression is an OUTCOME, not an input. An earlier build
 * multiplied yardage by 0.52 inside the 5 to pull touchdowns down from 28.5%
 * of drives to the real 22.6% - a fudge factor, and exactly the thing the
 * whole resolve-don't-sample approach exists to avoid. It also suppressed the
 * scoring play itself, which is why QB touchdowns came out at 12 against a
 * real 43.
 *
 * What REALLY happens near the goal line, from the data:
 *   - air yards collapse because the field runs out: mean 8.09 between the 21
 *     and 50, 4.47 from the 6-10, 2.18 inside the 5. Inside the 10 the maximum
 *     air yards ever recorded is 10 and ZERO throws travel more than 20.
 *   - the box gets heavier: 6.55 defenders inside the 5 against 4.40 at 21-50
 *   - rushers increase: 4.68 inside the 5 against 4.30
 *   - completion falls out of all that: 42% inside the 5 against 61% at 21-50
 * So the compression is produced, not imposed.
 */
export interface PlayOutcome {
  type: string;
  yards: number;
  touchdown: boolean;
  scheme?: string;
  concept?: string;
  protection?: string;
  depth?: string;
  target?: string;
  read?: string;
  by?: string | null;
  separation?: number;
  air?: number;
  yac?: number;
  ybc?: number;
  brokenTackles?: number;
}

export interface OffField {
  qb: Player; rb: Player; ol: Player[]; wr: Player[];
  extra_blockers?: Player[]; [k: string]: unknown;
}
export interface DefField {
  dl: Player[]; lb: Player[]; db: Player[]; [k: string]: unknown;
}

const r1 = (x: number) => +x.toFixed(1);
const r3 = (x: number) => +x.toFixed(3);

/**
 * off/deff: position -> player (or list for OL/DL/WR).
 * Returns the play outcome with every contributor named.
 */
export function resolvePlay(
  off: OffField, deff: DefField, offCall: any, defCall: any,
  yardsToEndzone: number, rng: RNG,
): PlayOutcome {
  return offCall.isPass
    ? passPlay(off, deff, offCall, defCall, yardsToEndzone, rng)
    : runPlay(off, deff, offCall, defCall, yardsToEndzone, rng);
}

export function runPlay(
  off: OffField, deff: DefField, offCall: any, defCall: any,
  ytg: number, rng: RNG,
): PlayOutcome {
  const scheme = offCall.scheme ?? 'inside_zone';
  const fam = (RUN_SCHEMES as any)[scheme].family;
  // Zone rewards agility and finesse blocking; gap rewards power and leverage.
  // Taking the max of both erased the whole distinction between them.
  const key: 'finesse' | 'power' = fam === 'zone' ? 'finesse' : 'power';
  const blockers = off.ol.slice(0, 5);
  const front = deff.dl.slice(0, (FRONTS as any)[defCall.front].dl);
  const defenders = [...front, ...deff.lb, ...deff.db];

  const wins: number[] = [];
  for (let i = 0; i < Math.min(blockers.length, front.length); i++) {
    wins.push(edge(rate(blockers[i], (RUN_BLOCK.blocker as any)[key]),
                   rate(front[i], RUN_BLOCK.defender.shed)));
  }
  const push = wins.length ? mean(wins) : 0.0;
  const fill = mean(defenders.slice(0, 7).map(d => rate(d, RUN_BLOCK.defender.fill)));

  let ybc = 2.32 + 9.0 * push - 3.2 * (fill - AVG) + rng.normal(0, 1.42);
  ybc *= S.boxRunMultiplier(defCall.box);
  ybc *= S.runSchemeMultiplier(scheme, defCall.front, ytg, defCall.box);
  ybc *= Math.pow((FRONTS as any)[defCall.front].run_fit, -1);
  if (offCall.motion) ybc *= 1.04;
  ybc = Math.max(-4.0, ybc);

  if (ybc < 0) {
    return { type: 'run', yards: r1(ybc), scheme, brokenTackles: 0,
             touchdown: false, ybc: r1(ybc) };
  }

  const chasers = [...defenders.slice(front.length), ...defenders.slice(0, front.length)];
  const out = resolveYardsAfter(off.rb, chasers, ytg, rng, { contactAt: ybc });
  return { type: 'run', scheme, ybc: r1(ybc), yards: out.yards,
           brokenTackles: out.brokenTackles, touchdown: out.touchdown };
}

export function passPlay(
  off: OffField, deff: DefField, offCall: any, defCall: any,
  ytg: number, rng: RNG,
): PlayOutcome {
  let depth: Depth = offCall.depth ?? 'short';
  const ok = availableDepths(ytg);
  if (!ok.includes(depth)) depth = ok[ok.length - 1];
  const concept = offCall.concept ?? 'curl_flat';
  // The offence does NOT know the rush count before the snap. Choosing max
  // protect because six are coming let the defence's blitz cancel itself, so
  // the sack rate barely moved from four to six rushers.
  const protName = S.chooseProtection(offCall.personnel, 4, depth, rng);
  const prot = S.protectionMath(protName, defCall.rushers);

  const blockers = [...off.ol.slice(0, 5),
                    ...(off.extra_blockers ?? []).slice(0, Math.max(0, prot.blockers - 5))];
  const rushers = [...deff.dl, ...deff.lb].slice(0, defCall.rushers);

  const p = resolveProtection(blockers, rushers, rng, off.qb);
  let time = p.time;
  // A protection scheme is worth real time against a blitz, and a simulated
  // pressure makes the line set for a front that never comes.
  if (defCall.rushers >= 5) {
    // Real: 4-man 6.61% sack / 61.9% comp, blitz 8.35% / 56.1%. The blitz
    // penalty has to be SMALL - 8.5% per extra rusher put a six-man rush at an
    // 18% sack rate against a real ~10%.
    time *= prot.vsBlitz * (1.0 - 0.030 * (defCall.rushers - 4));
  }
  if (defCall.protectionError) time *= 1.0 - defCall.protectionError;
  let pressure = clip((2.72 - time) / 2.72, 0.0, 1.0);
  // 25.0/2.40 was solved for a bare four-man rush in isolation. Once blitzes,
  // deep drops and protection schemes are in the mix the BLEND has to land on
  // 6.6%, so the constant comes down.
  let sack = rng.next() < clip(16.0 * Math.exp(-2.40 * time), 0, .85);

  // Free rushers force the ball out. That is what a hot route IS, and it is
  // the real answer to a blitz - not simply eating the sack.
  const hot = prot.hot;
  if (hot) {
    depth = 'short';
    pressure = Math.min(1.0, pressure + 0.20);
    sack = sack && rng.next() < 0.35;
  }
  if (sack && !hot) {
    return { type: 'sack', yards: r1(-rng.gamma(2.0, 3.4)), touchdown: false,
             by: p.beatenBy, concept, protection: protName };
  }

  // the concept, against the coverage it actually faces
  let cmult = S.conceptMultiplier(concept, defCall.shell);
  if (offCall.playAction && !offCall.shotgun) {
    cmult *= 1.18;                    // real: 6.91 ypp vs 3.63 without
  } else if (offCall.playAction) {
    cmult *= 1.10;
  }
  const dis = S.disguisePenalty(off.qb, Boolean(defCall.fooled));

  // The pattern is the concept's receivers, but the BACK is always an outlet
  // and a tight end is usually in it. Slicing purely by the concept's route
  // count cut the TE and the RB out of the pattern entirely, so they never saw
  // a target - against a real 22.5% for tight ends and 18.1% for backs.
  const nRoutes = Math.max(1, (CONCEPTS as any)[concept].n - prot.routesLost);
  const pool = [...off.wr];
  const receivers = pool.slice(0, nRoutes);
  for (const extra of pool.slice(nRoutes)) {
    const ep = extra.pos ?? '';
    if ((ep === 'TE' || ep === 'HB' || ep === 'RB' || ep === 'FB') && receivers.length < 5) {
      receivers.push(extra);
    }
  }
  if (!receivers.length) receivers.push(...pool.slice(0, 1));

  // Coverage assignment and target selection. Before this the target was a
  // uniform draw from the receivers and the defender a uniform draw from the
  // secondary, so a TE could be covered by a corner and a WR1 by a safety.
  const aligned = CV.receiverAlignment(receivers);
  const { pairs } = CV.assignCoverage(aligned, deff, defCall, rng,
                                      offCall.travelWillingness ?? 0.5,
                                      defCall.travel);

  // every man in the pattern gets his own separation from his own matchup
  for (const pr of pairs) {
    pr.separation = resolveMan(pr.receiver, pr.defender, depth, time, rng);
    // a bracketed man is squeezed, not erased - an elite receiver doubled
    // still beats an average one singled
    if (defCall.bracket === pr.receiver.pid) pr.separation *= 0.72;
  }

  const sel = TG.selectTarget(pairs, off.qb, rng, offCall.plan);
  let tgt = sel.receiver, cov = sel.defender;
  let readKind = sel.kind as string, sepRaw = sel.separation;
  if (tgt === null || cov === null) {
    tgt = receivers[0]; cov = deff.db[0]; readKind = 'first'; sepRaw = 0.42;
  }

  const rmod = (TG.READ_MODIFIER as any)[readKind] ?? (TG.READ_MODIFIER as any)['first'];

  let complete: boolean, picked: boolean, contested: boolean;
  const cb = cov;
  if (defCall.man) {
    // Apply the concept and read modifiers to the COMPLETION PROBABILITY, not
    // to separation. Separation runs through a steep depth multiplier, so
    // folding a 0.94 concept factor into it cost far more than the same factor
    // applied at the end - which is what the zone path does. The mismatch left
    // man coverage 12 points below zone at short depth (61.6% against 75.7%)
    // and dragged league completion to 58.5%.
    const sep = clip(sepRaw, .02, .98);
    const thr = resolveThrow(off.qb, depth, sep, pressure, rng, {
      playAction: Boolean(offCall.playAction),
      outcomeMult: cmult * (1.0 - dis) * rmod.comp,
    });
    complete = thr.result === 'complete';
    picked = thr.result === 'interception';
    contested = thr.contested;
  } else {
    // Only the NEAREST defender contests - handing the resolver the whole
    // secondary made every window contested by the best of six and dropped
    // league completion to 51.6% against a real 65.0%.
    const dbs = [{ ...cb, dist_to_window: 0 }];
    const z = resolveZone(tgt, dbs, off.qb, defCall.shell, depth, pressure, rng);
    // Apply the concept to the WINDOW, not as a second independent gate.
    // Gating twice dropped four-man-rush completion to 51.8% against a real
    // 61.9%. Coverage bodies matter: a blitz leaves fewer men to cover, which
    // is exactly why blitzing costs completion percentage and gains sacks.
    const coverRelief = 1.0 + 0.085 * Math.max(0, defCall.rushers - 4);
    const adj = clip(z.p_complete * cmult * coverRelief * (1.0 - dis) * rmod.comp,
                     0.02, 0.97);
    complete = rng.next() < adj;
    // 2.1% is the rate per ATTEMPT, not per incompletion. Applying it to
    // incompletions only produced ~1.1% league-wide.
    picked = !complete && rng.next() < 0.080;
    contested = z.contested;
  }

  if (picked) {
    return { type: 'interception', yards: 0.0, touchdown: false, concept,
             protection: protName, target: tgt.pid, by: cb.pid, read: readKind };
  }
  if (!complete) {
    return { type: 'incomplete', yards: 0.0, touchdown: false, concept,
             protection: protName, target: tgt.pid, read: readKind };
  }
  // A contested ball that already survived the throw should not face the full
  // contested-catch gate again; drops were running at 8.7% against a real ~5%.
  if (!resolveCatch(tgt, cb, contested && rng.next() < 0.45, rng)) {
    return { type: 'drop', yards: 0.0, touchdown: false, concept,
             protection: protName, target: tgt.pid, read: readKind };
  }

  // Real air yards ON COMPLETIONS: 5.72 overall, with the bands running -2.76
  // behind the line, 4.03 short, 11.93 medium, 25.29 deep. The short band
  // includes throws behind the line, which pulled the real mean down.
  const baseAir = ({ short: 2.6, medium: 9.8, deep: 22.0 } as any)[depth];
  let air = 0.55 * baseAir + 0.45 * Math.max(0.0, rmod.air);
  air = Math.max(0.0, air + rng.normal(0, 3.0));
  // A throw to the back of the end zone travels the full remaining distance -
  // it is not clipped short. Clipping it left the YAC chain no room and made
  // scoring from the 15-20 nearly impossible: 1.9% per play against a real 7.0%.
  if (air >= ytg * 0.68 && ytg <= 25) air = ytg;
  else air = Math.min(air, ytg);

  if (air >= ytg) {
    return { type: 'complete', yards: r1(ytg), air: r1(air), yac: 0.0,
             touchdown: true, concept, protection: protName, depth,
             target: tgt.pid, read: readKind, separation: r3(sepRaw) };
  }
  // Real YAC by throw depth: behind the line 8.63, short 3.97, medium 3.48,
  // deep 5.31 - a U-shape, because a screen has blockers in front and a deep
  // ball is caught past everyone, while an intermediate throw is caught in
  // traffic. Flat pursuit produced 3.06 overall against a real 5.19.
  const tpool = [...deff.db, ...deff.lb];
  let nNear = ({ short: 3, medium: 4, deep: 2 } as any)[depth];
  if (air <= 0) nNear = 2;                     // screen: blockers ahead
  const tacklers: Player[] = [];
  for (let i = 0; i < nNear; i++) tacklers.push(tpool[rng.integers(0, tpool.length)]);
  const yac = resolveYardsAfter(tgt, tacklers, ytg - air, rng, { inSpace: true });
  const total = Math.min(air + yac.yards, ytg);
  return { type: 'complete', yards: r1(total), air: r1(air), yac: yac.yards,
           touchdown: total >= ytg, concept, protection: protName, depth,
           target: tgt.pid, read: readKind, separation: r3(sepRaw) };
}
