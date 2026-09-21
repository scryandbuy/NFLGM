/**
 * The scheme layer: what play gets CALLED, before any matchup resolves.
 *
 * Ported from schemes.py. Every rate comes from nflverse play-by-play or FTN
 * charting. The calibration that matters: play action 10.2% of all plays,
 * motion 36.5%, four rushers on 71% of dropbacks, blitz 13.3%, and a run game
 * whose efficiency collapses as the box fills - 6.6 yards a carry against four
 * men, 2.41 against nine.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';
import {
  PERSONNEL_OFF, PERSONNEL_DEF, FRONTS, FRONT_VS_SCHEME, BOX_YPC,
  PROTECTIONS, RUN_SCHEMES, CONCEPTS, SHELL_KEY, PASS_RATE, SCRIPT,
  NEUTRAL_SCRIPT,
} from './schemeTables.js';

const P_OFF = PERSONNEL_OFF as any;
const P_DEF = PERSONNEL_DEF as any;
const FR = FRONTS as any;

export interface OffCall {
  personnel: string; shotgun: boolean; isPass: boolean;
  playAction?: boolean; screen?: boolean; rpo?: boolean;
  concept?: string; depth?: 'short' | 'medium' | 'deep'; scheme?: string;
  motion: boolean; noHuddle: boolean;
  plan?: any; travelWillingness?: number; cheater?: string; keepIn?: number;
}

export interface DefCall {
  personnel: string; front: string; rushers: number; blitzers: number;
  shell: string; shownShell: string; fooled: boolean; box: number;
  simPressure: boolean; protectionError: number; man: boolean;
  bracket?: string | null; travel?: boolean;
}

/** What the defence puts on the field to answer the offence's grouping. */
export function defensivePersonnel(
  offPers: string, down: number, ydstogo: number, rng: RNG, gmAggr = 0.5,
): string {
  const wr = (P_OFF[offPers] ?? P_OFF['11']).wr;
  let base: string;
  if (wr >= 4) base = (down === 3 && ydstogo >= 7) ? 'dime' : 'nickel';
  else if (wr === 3) base = 'nickel';
  else if (wr === 2) base = rng.next() < 0.55 ? 'base' : 'nickel';
  else base = rng.next() < 0.50 ? 'heavy' : 'base';
  if (down === 3 && ydstogo >= 8 && (base === 'base' || base === 'nickel')) {
    base = base === 'base' ? 'nickel' : 'dime';
  }
  if ((down === 3 || down === 4) && ydstogo <= 2 && base === 'nickel') {
    base = rng.next() < 0.6 ? 'base' : 'nickel';
  }
  return base;
}

/**
 * Real box counts: 6.55 inside the 5, 5.49 from the 6-10, 4.40 at 21-50. The
 * defence walks up because there is nothing to defend behind them. Goal-line
 * defence is heavier still than 6.55 suggests, because that blends pass and
 * run downs; on the 1 and 2 everyone is in the box.
 */
export function goalLineBoxBonus(yardsToEndzone: number): number {
  if (yardsToEndzone <= 2) return 4.30;
  if (yardsToEndzone <= 5) return 3.05;
  if (yardsToEndzone <= 10) return 1.95;
  return 0.0;
}

/**
 * Bodies in the box. Not every linebacker is IN it, and the ends are often
 * widened out of it - counting the whole front seven produced 7-man boxes on
 * 34% of snaps against a real 18%, and a 6.15 average at midfield against 4.40.
 */
export function boxCount(
  defPers: string, front: string, offPers: string, blitzers: number,
  rng: RNG, yardsToEndzone = 50,
): number {
  const off = P_OFF[offPers] ?? P_OFF['11'];
  let b = FR[front].dl * 0.74 + P_DEF[defPers].lb * 0.62;
  b += P_DEF[defPers].box_bonus * 0.34;
  b += 0.45 * off.te + 0.34 * off.rb;
  b += blitzers * 0.80;
  b += goalLineBoxBonus(yardsToEndzone);
  return clip(Math.round(b + rng.normal(0, 0.34)), 4, 10);
}

/**
 * How much this box count helps or hurts a run, relative to a 6-man box. The
 * raw ratio applies to YARDS BEFORE CONTACT only and the break-tackle chain
 * then compresses it, so it is exponentiated to survive that - without which
 * the sim spread only 5.51 to 3.72 against a real 5.92 to 2.41.
 */
export function boxRunMultiplier(box: number): number {
  const k = String(clip(Math.round(box), 4, 10)) as keyof typeof BOX_YPC;
  return Math.pow(((BOX_YPC as any)[k] ?? 4.5) / (BOX_YPC as any)['6'], 2.1);
}

/** Longer-developing concepts need more bodies; quick game needs fewer. */
export function chooseProtection(
  offPers: string, expectedRush: number, depth: string, rng: RNG,
): string {
  const avail = (P_OFF[offPers] ?? P_OFF['11']).protect;
  if (depth === 'short' && rng.next() < 0.55) return 'five';
  if (depth === 'deep' && avail >= 7 && rng.next() < 0.30) return 'seven';
  if (expectedRush >= 6 && avail >= 7) return 'seven';
  return rng.next() < 0.62 ? 'half_slide' : 'six_bob';
}

/**
 * Who is unblocked, and is there an answer. When the offence cannot block
 * everyone there is a built-in hot route and the QB must beat the free rusher
 * with a quick throw. That is the real answer to a blitz.
 */
export function protectionMath(protection: string, rushers: number, hotAvailable = true) {
  const p = (PROTECTIONS as any)[protection];
  const free = Math.max(0, rushers - p.blockers);
  return {
    blockers: p.blockers, freeRushers: free, routesLost: p.routes_lost,
    hot: free > 0 && hotAvailable, vsBlitz: p.vs_blitz, vsStunt: p.vs_stunt,
  };
}

/**
 * Gap is specifically better near the goal line: extra defenders on the line
 * create easy down blocks, which is why it shows up around the end zone.
 */
export function runSchemeMultiplier(
  scheme: string, front: string, yardsToEndzone: number, box: number,
): number {
  const s = (RUN_SCHEMES as any)[scheme];
  let m = ((FRONT_VS_SCHEME as any)[front] ?? {})[s.family] ?? 1.0;
  if (s.family === 'gap' && yardsToEndzone <= 5) m *= 1.12;
  if (s.family === 'zone' && box >= 8) m *= 0.93;
  return m;
}

/** A concept beats a COVERAGE. This is how a play call beats a defensive call. */
export function conceptMultiplier(concept: string, shell: string): number {
  const key = (SHELL_KEY as any)[shell] ?? 'cover_3';
  return (CONCEPTS as any)[concept]?.[key] ?? 1.0;
}

/**
 * A static two-high shell that rotates AFTER the snap forces the QB to process
 * once the play has started. Roughly a quarter of snaps carry a real disguise.
 */
export function disguise(shell: string, gmDeception: number, rng: RNG) {
  if (rng.next() > 0.10 + 0.32 * gmDeception) {
    return { shown: shell, actual: shell, fooled: false };
  }
  const pairs: Record<string, string> = {
    cover_3: 'cover_2', cover_1: 'cover_2', cover_4: 'cover_2',
    cover_2: 'cover_3', cover_0: 'cover_2', tampa_2: 'cover_2', cover_6: 'cover_2',
  };
  return { shown: pairs[shell] ?? 'cover_2', actual: shell, fooled: true };
}

/** A good processor is barely fooled; a poor one throws into the rotation. */
export function disguisePenalty(qb: Player, fooled: boolean): number {
  if (!fooled) return 0.0;
  const iq = rate(qb, {
    awareness_rating: 0.65, play_action_rating: 0.15,
    throw_under_pressure_rating: 0.20,
  });
  return clip(0.26 * (1.0 - 1.6 * (iq - AVG)), 0.0, 0.40);
}

/**
 * Show six or seven, drop most, send four from unusual angles. Numerically a
 * standard rush but functionally a blitz - it sits outside any model that only
 * counts rushers. The league LEADER runs this on 37% of snaps, so the average
 * is far lower.
 */
export function simulatedPressure(rng: RNG, gmDeception: number) {
  if (rng.next() < 0.04 + 0.16 * gmDeception) {
    return { sim: true, protectionError: 0.28 };
  }
  return { sim: false, protectionError: 0.0 };
}

export function distBand(ydstogo: number): string {
  if (ydstogo <= 2) return '1-2';
  if (ydstogo <= 4) return '3-4';
  if (ydstogo <= 7) return '5-7';
  if (ydstogo <= 10) return '8-10';
  return '11+';
}

export function passRate(
  down: number, ydstogo: number, scoreDiff: number, yardsToEndzone: number,
  offPers: string, gmPassBias = 0.0,
): number {
  const table = (PASS_RATE as any)[String(Math.trunc(down))] ?? (PASS_RATE as any)['1'];
  let base = table[distBand(ydstogo)];
  // Scores are whole numbers again now that the try is resolved as its own
  // play. The round stays as a guard on any caller passing a float.
  const sd = Math.round(scoreDiff);
  let script = NEUTRAL_SCRIPT as number;
  for (const row of SCRIPT as readonly any[]) {
    if (sd >= row[0] && sd <= row[1]) { script = row[2]; break; }
  }
  base *= script / (NEUTRAL_SCRIPT as number);
  // the red zone compresses: inside the 5 it is 44.5% pass against 59.7% backed up
  if (yardsToEndzone <= 5) base *= 0.75;
  else if (yardsToEndzone <= 10) base *= 0.88;
  else if (yardsToEndzone <= 20) base *= 0.90;
  base += (P_OFF[offPers] ?? P_OFF['11']).run_bias * -0.30;
  return clip(base + gmPassBias, 0.03, 0.98);
}

const PERS_KEYS = Object.keys(PERSONNEL_OFF);
const PERS_W = PERS_KEYS.map(k => P_OFF[k].rate);

/** Full offensive call: personnel, formation, pass or run, and the concept. */
export function callOffense(
  down: number, ydstogo: number, scoreDiff: number, yardsToEndzone: number,
  rng: RNG, gm?: { aggression?: number },
): OffCall {
  const bias = gm?.aggression !== undefined ? (gm.aggression - 0.5) * 0.10 : 0.0;
  const pers = rng.choice(PERS_KEYS, PERS_W);
  const isPass = rng.next() < passRate(down, ydstogo, scoreDiff, yardsToEndzone, pers, bias);
  const shotgun = rng.next() < (isPass ? 0.82 : 0.52);
  const call: OffCall = {
    personnel: pers, shotgun, isPass, motion: false, noHuddle: false,
  };

  if (isPass) {
    // Real rate is 10.2% of ALL plays (~17% of pass plays). An early build
    // gated play action behind a shotgun check that killed 82% of chances.
    call.playAction = rng.next() < (shotgun ? 0.14 : 0.30);
    call.screen = rng.next() < 0.075;
    call.rpo = rng.next() < 0.057;
    if (call.screen) call.concept = 'screen';
    else if (ydstogo >= 12 || (down >= 3 && ydstogo >= 8)) {
      call.concept = rng.choice(['four_verts', 'dagger', 'flood', 'levels', 'scissors']);
    } else if (ydstogo <= 4) {
      call.concept = rng.choice(['slant_flat', 'stick', 'mesh', 'curl_flat']);
    } else {
      call.concept = rng.choice(['mesh', 'levels', 'flood', 'smash', 'curl_flat',
                                 'dagger', 'slant_flat', 'stick']);
    }
    // The CONCEPT sets the shape, but the QB still works a progression and most
    // throws come off the underneath option. Real depth mix is 61.9% short,
    // 23.7% medium, 14.4% deep; keying depth straight off the concept gave
    // 35/48/17 and cost ~10 points of league completion.
    const base = (CONCEPTS as any)[call.concept].depth;
    const r = rng.next();
    if (base === 'deep') call.depth = r < 0.46 ? 'deep' : (r < 0.74 ? 'medium' : 'short');
    else if (base === 'medium') call.depth = r < 0.42 ? 'medium' : (r < 0.93 ? 'short' : 'deep');
    else call.depth = r < 0.86 ? 'short' : (r < 0.98 ? 'medium' : 'deep');
  } else {
    const o = P_OFF[pers];
    const heavy = o.te >= 2 || o.rb >= 2;
    if (yardsToEndzone <= 5 || (ydstogo <= 2 && down >= 3)) {
      call.scheme = rng.choice(['power', 'counter', 'duo', 'trap']);
    } else if (heavy) {
      call.scheme = rng.choice(['power', 'counter', 'duo', 'inside_zone']);
    } else {
      call.scheme = rng.choice(['inside_zone', 'outside_zone', 'stretch',
                                'inside_zone', 'draw']);
    }
  }
  call.motion = rng.next() < 0.365;
  call.noHuddle = rng.next() < 0.085;
  return call;
}

/** Front, personnel, rushers and coverage. */
export function callDefense(
  offCall: OffCall, down: number, ydstogo: number, rng: RNG,
  gm?: { aggression?: number; boardTrust?: number }, yardsToEndzone = 50,
): DefCall {
  const aggr = gm?.aggression ?? 0.5;
  const decep = gm?.boardTrust ?? 0.5;
  const pers = defensivePersonnel(offCall.personnel, down, ydstogo, rng, aggr);
  const dl = P_DEF[pers].dl;
  let front = dl === 4
    ? rng.choice(['4-3 over', '4-3 under', 'nickel_even'])
    : rng.choice(['3-4 one', '3-4 two', 'tite', 'mint']);
  if (front === 'nickel_even') front = '4-3 over';

  // real: 0 blitzers 86.7%, 1 on 9.7%, 2 on 3.1%, 3 on 0.47%
  const r = rng.next();
  let pBlitz = 0.133 * (0.6 + 0.9 * aggr);
  if (down === 3 && ydstogo >= 6) pBlitz *= 1.35;
  let blitzers = 0;
  if (r < pBlitz * 0.73) blitzers = 1;
  else if (r < pBlitz * 0.96) blitzers = 2;
  else if (r < pBlitz) blitzers = 3;

  // A five-man rush is NOT always a blitz: an end drops and a linebacker comes.
  // Real share of pass plays is 19.9% at five rushers but only 9.7% have a
  // charted blitzer. Tying rushers strictly to blitzers put five-man rushes at
  // 8% against a real 20%.
  let rushers = 4 + blitzers;
  if (blitzers === 0) {
    const r2 = rng.next();
    if (r2 < 0.042) rushers = 3;
    else if (r2 < 0.165) rushers = 5;        // exchange rusher, not a blitz
    else if (r2 < 0.195) rushers = 6;
  }

  let shell: string;
  if (blitzers >= 2) shell = rng.choice(['cover_0', 'cover_1', 'cover_3'], [.25, .45, .30]);
  else if (blitzers === 1) shell = rng.choice(['cover_1', 'cover_3', 'cover_2'], [.40, .40, .20]);
  else shell = rng.choice(['cover_3', 'cover_2', 'cover_4', 'cover_1', 'tampa_2', 'cover_6'],
                          [.30, .18, .22, .15, .08, .07]);

  const sim = simulatedPressure(rng, decep);
  if (sim.sim) { rushers = 4; blitzers = 0; }
  const dis = disguise(shell, decep, rng);
  const box = boxCount(pers, front, offCall.personnel, blitzers, rng, yardsToEndzone);
  // rushers tick up near the goal line: 4.68 inside the 5 vs 4.30 at 21-50
  if (yardsToEndzone <= 5 && blitzers === 0 && rng.next() < 0.28) {
    rushers += 1; blitzers = 1;
  }
  return {
    personnel: pers, front, rushers, blitzers, shell: dis.actual,
    shownShell: dis.shown, fooled: dis.fooled, box,
    simPressure: sim.sim, protectionError: sim.protectionError,
    man: dis.actual === 'cover_0' || dis.actual === 'cover_1',
  };
}
