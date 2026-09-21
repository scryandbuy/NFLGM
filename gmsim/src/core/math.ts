/**
 * The four primitives every matchup in the sim is built from.
 *
 * These are tiny, but they are the contract between a player's attributes and
 * whether he wins a rep. Every constant in the engine - the sack curve, the
 * zone windows, the break-tackle chain - was solved assuming these exact
 * shapes, so they port verbatim rather than being "improved".
 */

/** League-average rate. Everything is centred here. */
export const AVG = 0.70;

export interface Player {
  pid: string;
  pos: string;
  [attr: string]: number | string | undefined;
}

export type Weights = Record<string, number>;

/**
 * Weighted attribute score on 0-1.
 *
 * A missing attribute defaults to 70, which is deliberate: it means a player
 * with a sparse record plays as an average man at that skill rather than as a
 * zero. Real seed data has gaps and this is what keeps them harmless.
 */
export function rate(p: Player | Record<string, any>, weights: Weights): number {
  let sum = 0;
  for (const k in weights) {
    const v = (p as any)[k];
    sum += (typeof v === 'number' ? v : 70) * weights[k];
  }
  return sum / 100.0;
}

/** How far one side beats the other, centred on zero. Feeds logistic rolls. */
export function edge(a: number, b: number, scale = 1.0): number {
  return (a - b) * scale;
}

/**
 * The contest curve. k controls how sharply a small edge becomes a win;
 * every caller passes its own k, solved against real data for that matchup.
 */
export function logistic(x: number, k = 6.0): number {
  return 1.0 / (1.0 + Math.exp(-k * x));
}

export function clip(x: number, lo: number, hi: number): number {
  return x < lo ? lo : x > hi ? hi : x;
}

export function mean(xs: readonly number[]): number {
  if (!xs.length) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}
