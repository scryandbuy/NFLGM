/**
 * Scrambles, fumbles and penalties. Ported from events.py.
 *
 * All from 6 seasons of real play-by-play (281,339 plays):
 *   scrambles  5.12% of dropbacks, mean 7.00 yards, never negative,
 *              EPA +0.402 against a sack's -1.791
 *   fumbles    rush 1.499%, complete pass 1.141%, SACK 12.528% - eight times
 *              the rate of a run, which is what makes a strip sack its own
 *              event; recovered by the offence 55.2% of the time
 *   penalties  11.88 per game, mean 8.30 yards, 29.9% automatic first down,
 *              56% on the offence, across 20 types at their real rates
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';
import {
  SCRAMBLE, SCRAMBLE_RATE_BASE, FUMBLE_RATE, FUMBLE_LOST, FORCED_SHARE,
  PENALTIES, PEN_INFO, DPI, PENALTY_RATE,
} from './tables.js';

/**
 * A scramble is what a mobile QB does INSTEAD of taking the sack. Without it
 * every collapsed pocket becomes a sack regardless of who is playing.
 */
export function scrambleChance(qb: Player, pressure: number, timeAvailable: number): number {
  const mob = rate(qb, {
    speed_rating: .40, agility_rating: .30, accel_rating: .15, break_sack_rating: .15,
  });
  let p = SCRAMBLE_RATE_BASE * (1.0 + 3.2 * (mob - AVG));
  p *= 0.55 + 1.30 * pressure;              // he scrambles because he has to
  return clip(p, 0, 0.42);
}

/** Gamma-shaped to the real distribution: mean 7.00, sd 6.07, tail to 61. */
export function resolveScramble(qb: Player, yardsToEndzone: number, rng: RNG) {
  const mob = rate(qb, { speed_rating: .45, accel_rating: .30, agility_rating: .25 });
  const y = clip(rng.gamma(1.33, 5.26) * (1.0 + 0.85 * (mob - AVG)),
                 0, Math.min(yardsToEndzone, (SCRAMBLE as any).max));
  return {
    type: 'scramble', yards: Math.round(y * 10) / 10,
    touchdown: y >= yardsToEndzone, by: qb.pid,
  };
}

/** Ball security against the hit. */
export function fumbleCheck(
  carrier: Player, event: string, rng: RNG, hitPower = 0.70,
): { fumble: true; lost: boolean; forced: boolean; by?: string } | null {
  const base = (FUMBLE_RATE as any)[event] ?? 0.0140;
  const sec = rate(carrier, { carry_rating: .70, awareness_rating: .30 });
  const p = base * (1.0 + 2.4 * (AVG - sec)) * (1.0 + 1.3 * (hitPower - AVG));
  if (rng.next() >= Math.max(0, p)) return null;
  return {
    fumble: true,
    lost: rng.next() < ((FUMBLE_LOST as any)[event] ?? 0.45),
    forced: rng.next() < (FORCED_SHARE as number),
    by: carrier.pid,
  };
}

/**
 * DPI is a SPOT foul and the biggest single swing in the game: mean 15.3,
 * median 13, p90 30, p99 46, max 52. 28% go 20+ yards. The yardage IS roughly
 * where the ball was going, so when the air yards are known they are used
 * directly; otherwise a lognormal solved against median 13 / p90 30 / max 52.
 */
export function dpiYards(rng: RNG, airYards?: number): number {
  const d = DPI as any;
  if (airYards !== undefined) {
    return clip(Math.abs(airYards) + rng.normal(0, 2.5), 1, d.max);
  }
  return clip(rng.lognormal(Math.log(13.0), 0.62), 1, d.max);
}

const PEN_KEYS = Object.keys(PENALTIES);
const PEN_W = PEN_KEYS.map(k => (PENALTIES as any)[k]);

/**
 * These fouls wipe the snap out entirely; everything else is enforced on top
 * of the result. Pre-snap flags nullify by definition.
 */
const NULLIFYING = new Set([
  'Offensive Holding', 'Offensive Pass Interference', 'Illegal Formation',
  'Ineligible Downfield Pass', 'Illegal Block Above the Waist',
]);

export interface Penalty {
  penalty: string; yards: number; onOffense: boolean;
  autoFirst: boolean; nullifies: boolean;
}

/**
 * Returns a penalty or null. discipline is the offending unit's rating on 0-1;
 * the league rate of 7.03% of plays sits at average discipline.
 */
export function penaltyCheck(
  rng: RNG,
  opts: { phase?: string; isPass?: boolean; discipline?: number; airYards?: number } = {},
): Penalty | null {
  const { phase = 'any', isPass = true, discipline = AVG, airYards } = opts;
  const p = (PENALTY_RATE as number) * (1.0 + 1.6 * (AVG - discipline));
  if (rng.next() >= Math.max(0.0, p)) return null;
  // Draw a type. phase='any' means every type is eligible - an early build read
  // it as a filter value, which excluded every PRE-SNAP penalty and so dropped
  // False Start (2.23/gm, the second most common foul in football) entirely.
  // The lost probability mass redistributed onto the rest, putting offensive
  // holding at 4.15/gm against a real 2.24, mean yardage at 10.3 against 8.3,
  // and automatic first downs at 46% against 30%.
  const ok: number[] = [];
  for (let i = 0; i < PEN_KEYS.length; i++) {
    const ph = (PEN_INFO as any)[PEN_KEYS[i]].phase;
    const keep = phase === 'any'
      ? (ph !== 'pass' || isPass)
      : (ph === 'any' || ph === 'post' || ph === phase || (ph === 'pass' && isPass));
    if (keep) ok.push(i);
  }
  if (!ok.length) return null;
  const idx = rng.choice(ok, ok.map(i => PEN_W[i]));
  const name = PEN_KEYS[idx];
  const info = (PEN_INFO as any)[name];

  const yds = name === 'Defensive Pass Interference'
    ? dpiYards(rng, airYards)
    : Math.max(1.0, rng.normal(info.yards, info.yards * 0.22));

  let onOff = info.offense as boolean | null;
  if (onOff === null) {
    // The 56/44 league split is across ALL penalties. The 20 types modelled
    // here already resolve to 6.31/gm offence and 3.53/gm defence, which is
    // 57.5% offence before the either-side fouls are assigned at all - so no
    // value here reaches exactly 56%. The gap is the untracked long tail,
    // which skews defensive. These specific fouls go against the defence more
    // often.
    onOff = rng.next() < 0.18;
  }
  return {
    penalty: name, yards: +yds.toFixed(1), onOffense: Boolean(onOff),
    // auto_first is a PROBABILITY in the data (0.99 for DPI, 0.0 for holding),
    // not a flag. Treating it as a boolean put automatic first downs at 42.5%
    // against a real 29.9%.
    autoFirst: rng.next() < info.auto_first,
    nullifies: info.phase === 'pre' || NULLIFYING.has(name),
  };
}
