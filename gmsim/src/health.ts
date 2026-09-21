/**
 * Condition, sharpness, jadedness and injuries. Ported from health.py.
 *
 * NFL targets: snap shares from nflverse 2024-25 (C 84.0 down to RB 37.6),
 * 2.51 players ruled out per team per week, injury duration mean 1.50 weeks
 * with 33.3% lasting two or more.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';
import {
  SNAP_INTENSITY, SHARPNESS_DECAY, CONDITION_DECAY, INJURY_SHARE, INJURY_TYPES,
  SIDELINE_RECOVERY, INJURIES_PER_TEAM_WEEK, RULED_OUT_SHARE, COND_REFERENCE,
  DUR_LEAGUE,
} from './healthTables.js';

const SI = SNAP_INTENSITY as any;

/**
 * In-game physical freshness, 0-100. Stamina governs the LOSS rate only.
 * Recovery is governed separately by natural fitness - the two are different
 * attributes and do not trade off.
 */
export class Condition {
  cond: Record<string, number> = {};
  snaps: Record<string, number> = {};
  constructor(public policy = 0.5) {}

  get(pid: string): number { return this.cond[pid] ?? 100.0; }

  play(pid: string, position: string, stamina = 70.0, effort = 1.0): void {
    let cost = (SI[position] ?? 0.80) * effort;
    cost *= 1.0 - 0.45 * ((stamina - 50.0) / 50.0);
    this.cond[pid] = Math.max(0, this.get(pid) - cost * 4.2);
    this.snaps[pid] = (this.snaps[pid] ?? 0) + 1;
  }

  /**
   * A snap on the sideline. Recovery is a FIXED rate - scaling it by the
   * position's intensity made intensity cancel out of the equilibrium
   * entirely, so every position settled at the same 55% snap share.
   */
  rest(pid: string): void {
    this.cond[pid] = Math.min(100, this.get(pid) + SIDELINE_RECOVERY * 4.2);
  }

  /**
   * Rotation is an OUTPUT of condition, never forced by a scheme table. A high
   * trigger means even a low-intensity man eventually needs a breather; at 78
   * the equilibrium was capped for cheap positions and centres played 97.5%.
   */
  needsRest(pid: string, position: string, rng: RNG, stamina = 70.0, qualityGap = 0.0): boolean {
    const c = this.get(pid);
    const trigger = 92.0 - 20.0 * (1.0 - this.policy) - 12.0 * clip(qualityGap, -1, 1);
    if (c >= trigger) return false;
    const p = Math.pow((trigger - c) / Math.max(1, trigger), 0.85);
    return rng.next() < clip(p * 2.2, 0, 0.95);
  }

  resetGame(): void { this.cond = {}; this.snaps = {}; }
}

/** Natural fitness governs the RATE; stamina does not enter. Jadedness slows it. */
export function recoverBetweenGames(
  condition: number, naturalFitness = 70.0, daysRest = 7, jadedness = 0.0,
): number {
  let r = 0.55 + 0.75 * (naturalFitness / 100.0);
  r *= 1.0 - 0.35 * clip(jadedness, 0, 1);
  const gain = (100.0 - condition) * clip(r * (daysRest / 7.0), 0, 1);
  return clip(condition + gain, 0, 100);
}

/** Playing builds match readiness; sitting erodes it. */
export function updateSharpness(sharp: number, snapsPlayed: number, expectedSnaps = 45.0): number {
  if (snapsPlayed >= expectedSnaps * 0.5) {
    return clip(sharp + 9.0 * (snapsPlayed / expectedSnaps), 0, 100);
  }
  return clip(sharp - 7.5 * (1.0 - snapsPlayed / expectedSnaps), 0, 100);
}

/** The player as he actually is right now. */
export function applyState(player: Player, condition = 100.0, sharpness = 100.0): Player {
  const p: any = { ...player };
  if (sharpness < 99.0) {
    const s = (100.0 - sharpness) / 100.0;
    for (const k in SHARPNESS_DECAY) {
      if (typeof p[k] === 'number') {
        p[k] = Math.max(20, p[k] * (1.0 - 0.30 * (SHARPNESS_DECAY as any)[k] * s));
      }
    }
  }
  if (condition < 85.0) {
    const c = (85.0 - condition) / 85.0;
    for (const k in CONDITION_DECAY) {
      if (typeof p[k] === 'number') {
        p[k] = Math.max(20, p[k] * (1.0 - 0.26 * (CONDITION_DECAY as any)[k] * c));
      }
    }
  }
  return p;
}

/**
 * Hidden, slow to build and slow to shed. High natural fitness slows it. This
 * is what makes a heavy workload cost something in December rather than
 * September.
 */
export function updateJadedness(
  jaded: number, snapsPlayed: number, naturalFitness = 70.0,
  expectedSnaps = 45.0, bye = false,
): number {
  if (bye) return clip(jaded - 0.12, 0, 1);
  const load = snapsPlayed / Math.max(1, expectedSnaps);
  const gain = 0.020 * load * (1.0 - 0.55 * (naturalFitness - 50.0) / 50.0);
  return clip(jaded + gain - 0.006, 0, 1);
}

/**
 * FM community testing at fixed workload: 100% condition produced 8 in-match
 * injuries, 80% produced 20, 60% produced 87. Roughly 2.4x per 20 points lost,
 * and the nonlinearity is the point.
 */
export function conditionInjuryMultiplier(condition: number): number {
  return Math.exp(0.0603 * (100.0 - condition));
}

export function injuryChance(
  player: Player, position: string, contact: number, condition = 100.0,
  jaded = 0.0, snapsPerGame = 65.0,
): number {
  const base = (INJURIES_PER_TEAM_WEEK / (snapsPerGame * 2.0))
    * (((INJURY_SHARE as any)[position] ?? 0.04) / 0.045)
    * RULED_OUT_SHARE / conditionInjuryMultiplier(COND_REFERENCE);
  const dur = rate(player, { injury_rating: 0.60, tough_rating: 0.40 });
  let p = base * (1.0 + 2.0 * (DUR_LEAGUE - dur)) * (0.5 + 1.0 * contact);
  p *= conditionInjuryMultiplier(condition);
  p *= 1.0 + 0.45 * jaded;
  return clip(p, 0, 0.10);
}

export interface Injury {
  player?: string; position: string; kind: string; weeksOut: number;
  seasonEnding: boolean; irEligible: boolean; week?: number;
}

const IT = (INJURY_TYPES as readonly any[]).map(t => t as [string, number, number]);
const IT_NAMES = IT.map(t => t[0]);
const IT_WEIGHTS = IT.map(t => t[1]);
const IT_SEV: Record<string, number> = Object.fromEntries(IT.map(t => [t[0], t[2]]));

export function rollInjury(
  player: Player, position: string, contact: number, rng: RNG,
  condition = 100.0, jaded = 0.0, snapsPerGame = 65.0,
): Injury | null {
  if (rng.next() >= injuryChance(player, position, contact, condition, jaded, snapsPerGame)) {
    return null;
  }
  const kind = rng.choice(IT_NAMES, IT_WEIGHTS);
  const sev = IT_SEV[kind];
  const r = rng.next();
  let weeks: number;
  if (r < 0.667) weeks = 1;
  else if (r < 0.880) weeks = 2;
  else if (r < 0.969) weeks = 3;
  else if (r < 0.997) weeks = rng.integers(4, 6);
  else weeks = rng.integers(6, 17);
  weeks = Math.max(1, Math.round(weeks * (0.92 + 0.16 * (sev - 1.5))));
  return {
    player: player.pid, position, kind, weeksOut: weeks,
    seasonEnding: weeks >= 8, irEligible: weeks >= 4,
  };
}

export function outThisWeek(injuries: Injury[], week: number): Set<string> {
  const out = new Set<string>();
  for (const i of injuries) {
    if (i.week !== undefined && i.week <= week && week < i.week + i.weeksOut) {
      if (i.player) out.add(i.player);
    }
  }
  return out;
}
