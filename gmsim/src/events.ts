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

/** DPI is a spot foul: median 13 yards, p90 30, max 52, 3.46% go 40+. */
export function dpiYards(rng: RNG): number {
  const d = DPI as any;
  const r = rng.next();
  if (r < 0.50) return Math.max(1, Math.round(rng.uniform(1, d.median ?? 13)));
  if (r < 0.90) return Math.round(rng.uniform(d.median ?? 13, d.p90 ?? 30));
  return Math.round(rng.uniform(d.p90 ?? 30, d.max ?? 52));
}

const PEN_KEYS = Object.keys(PENALTIES);
const PEN_W = PEN_KEYS.map(k => (PENALTIES as any)[k]);

/**
 * A penalty on this snap, or null. An early build filtered on phase in a way
 * that dropped every pre-snap flag, so False Start disappeared entirely.
 */
export function penaltyCheck(
  rng: RNG, opts: { isPass?: boolean; discipline?: number; airYards?: number } = {},
) {
  const { isPass = true, discipline = AVG } = opts;
  const p = (PENALTY_RATE as number) * (1.0 + 1.6 * (AVG - discipline));
  if (rng.next() >= p) return null;
  const kind = rng.choice(PEN_KEYS, PEN_W);
  const info = (PEN_INFO as any)[kind] ?? {};
  let yards = info.yards ?? 5;
  if (kind === 'Defensive Pass Interference') yards = dpiYards(rng);
  return {
    kind, yards, onOffense: !!info.offense,
    // auto_first is a PROBABILITY in the data (0.99 for DPI, 0.0 for holding),
    // not a flag. Treating it as a boolean put automatic first downs at 42.5%
    // against a real 29.9%.
    autoFirst: rng.next() < (info.auto_first ?? 0),
    phase: info.phase ?? 'snap',
  };
}
