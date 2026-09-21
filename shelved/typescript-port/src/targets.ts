/**
 * Targets and depth charts. Ported from targets.py.
 *
 * A quarterback does not throw to whoever is open. He throws to his DESIGNED
 * READ, and openness only sometimes decides it.
 *
 * FTN charting, all dropbacks: first read 53.0%, checkdown 15.2%, designed
 * 11.2%, scramble drill 10.3%, second read 10.3%. Across 45 QBs the first-read
 * rate runs 43.7% to 66.6%.
 *
 * Outcomes differ sharply BY READ: first read 60.7% completion at +0.31 EPA,
 * checkdown 78.1% at -0.04. Working deeper into a progression is WORSE, and
 * the checkdown is a high-completion negative-value play.
 *
 * THE FINDING THAT DRIVES THE DESIGN: research measuring how often a QB throws
 * to the most open receiver found the best in the league at 26.8% and the
 * worst at 13.2%, while that worst QB threw to the LEAST open man 27.5% of the
 * time. With four or five options, random is roughly 20-25%. Even elite
 * quarterbacks are barely better than chance.
 *
 * SEPARATION is anchored to Next Gen tracking: league mean 3.04 yards, range
 * 1.11 to 5.66, TE 3.35, WR 2.93. It trades against depth - under 2.4 yards
 * catches 57.8% at 12.8 air yards, over 3.8 catches 73.0% at 6.5 - but yards
 * per target is nearly FLAT across the range. Getting open buys completion
 * percentage, not production, which is why the best receivers post LOW
 * separation: they draw better corners and win contested.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';
import {
  SEP_MEAN, SEP_MIN, SEP_MAX, SEP_BY_POS, READ_MIX, READ_MODIFIER,
  DEPTH_WEIGHTS, SCHEME_SHIFT, OFF_PACKAGES, DEF_PACKAGES,
} from './tables.js';

export function toYards(sep01: number, pos = 'WR'): number {
  const base = (SEP_BY_POS as any)[pos] ?? SEP_MEAN;
  return clip(base + (sep01 - 0.42) * 3.1, SEP_MIN as number, SEP_MAX as number);
}

export function fromYards(yards: number, pos = 'WR'): number {
  const base = (SEP_BY_POS as any)[pos] ?? SEP_MEAN;
  return clip(0.42 + (yards - base) / 3.1, 0.02, 0.98);
}

export type ReadKind = 'first' | 'second' | 'checkdown' | 'designed' | 'scramble';

/**
 * This quarterback's personal read distribution. Anchored to the league
 * figures and shifted by awareness within the real observed spread - an early
 * build scaled hard enough to push an elite QB to 40% first read, BELOW the
 * league minimum, and his designed rate above the league maximum.
 */
export function readProfile(qb: Player): Record<ReadKind, number> {
  const iq = rate(qb, {
    awareness_rating: .55, play_rec_rating: .20, throw_under_pressure_rating: .25,
  });
  const mob = rate(qb, { speed_rating: .5, agility_rating: .5 });
  const m: Record<string, number> = {
    first: clip(.530 - 0.28 * (iq - AVG), .437, .666),
    second: clip(.103 + 0.20 * (iq - AVG), .058, .163),
    checkdown: clip(.152 - 0.18 * (iq - AVG), .087, .208),
    scramble: clip(.103 + 0.38 * (mob - AVG), .030, .159),
    designed: 0,
  };
  m.designed = Math.max(0.02, 1.0 - (m.first + m.second + m.checkdown + m.scramble));
  const t = m.first + m.second + m.checkdown + m.scramble + m.designed;
  for (const k in m) m[k] /= t;
  return m as Record<ReadKind, number>;
}

export interface TargetPair { receiver: Player; defender: Player; separation?: number; }

/**
 * Who gets the ball. The READ ORDER decides and openness modifies it. Nothing
 * consults a target-share table at any point - the share curve is an OUTCOME
 * of this plus the defence's response to it.
 */
export function selectTarget(
  pairs: TargetPair[], qb: Player, rng: RNG,
  plan?: { targetPriority?: Record<string, number> },
): { receiver: Player | null; defender: Player | null; kind: ReadKind; separation: number } {
  if (!pairs.length) return { receiver: null, defender: null, kind: 'first', separation: 0 };

  const prof = readProfile(qb);
  const kinds = Object.keys(prof) as ReadKind[];
  const kind = rng.choice(kinds, kinds.map(k => prof[k]));

  // THE FIRST READ IS NOT THE SAME MAN EVERY PLAY. Concepts put different
  // receivers first, so the read order is drawn per play with a bias toward the
  // better options. Fixing WR1 as the permanent first read gave him 53% of
  // targets against a real 23.6%.
  const n = pairs.length;
  const w = pairs.map((p, i) => {
    const prio = plan?.targetPriority?.[p.receiver.pid] ?? 0;
    // Real target share by rank: 23.6 / 17.5 / 13.3 / 10.5 / 8.5 - a ratio of
    // about 0.76 between neighbours.
    return (1.0 + 0.55 * prio) * Math.pow(0.76, i);
  });
  const order = rng.sampleIndices(w, n);

  let i: number;
  if (kind === 'checkdown') {
    // the back is the usual outlet but not the only one - always taking the
    // last man gave him 27% of all targets against a real ~10%
    const late = n > 2 ? order.slice(-2) : order;
    i = late[rng.integers(late.length)];
  } else if (kind === 'designed') i = order[0];
  else if (kind === 'second') i = n > 1 ? order[1] : order[0];
  else if (kind === 'scramble') i = order[rng.integers(order.length)];
  else i = order[0];

  // Even the best QBs find the most open man barely more often than chance, so
  // this override must be SMALL and steeply skill-scaled.
  const skill = rate(qb, { awareness_rating: .6, play_rec_rating: .4 });
  if ((kind === 'first' || kind === 'second') && n > 1) {
    if (rng.next() < clip(0.04 + 0.85 * (skill - AVG), 0, 0.26)) {
      let best = 0, bestSep = -1;
      pairs.forEach((p, j) => {
        const s = p.separation ?? 0.42;
        if (s > bestSep) { bestSep = s; best = j; }
      });
      i = best;
    }
  }

  const p = pairs[i];
  return { receiver: p.receiver, defender: p.defender, kind, separation: p.separation ?? 0.42 };
}

export { READ_MODIFIER };

// ============================================================ DEPTH CHARTS
/** How good is he AT THIS SPOT, not overall. */
export function positionScore(player: Player, position: string, scheme?: string | string[]): number {
  const w: Record<string, number> = { ...((DEPTH_WEIGHTS as any)[position] ?? { awareness_rating: 1.0 }) };
  if (scheme) {
    for (const s of (typeof scheme === 'string' ? [scheme] : scheme)) {
      const shift = (SCHEME_SHIFT as any)[s] ?? {};
      for (const k in shift) w[k] = Math.max(0, (w[k] ?? 0) + shift[k]);
    }
  }
  let tot = 0;
  for (const k in w) tot += w[k];
  if (!tot) return 70;
  let sum = 0;
  for (const k in w) sum += ((player as any)[k] ?? 70) * w[k];
  return sum / tot;
}

/** Rank a position group, dropping anyone unavailable. */
export function orderDepth(
  players: Player[], position: string, scheme?: string | string[], unavailable?: Set<string>,
): Player[] {
  return players
    .filter(p => !unavailable || !unavailable.has(p.pid))
    .sort((a, b) => positionScore(b, position, scheme) - positionScore(a, position, scheme));
}

export { OFF_PACKAGES, DEF_PACKAGES };

/** The eleven men this package puts on the field, in depth order. */
export function fieldPackage(
  chart: Record<string, Player[]>, pkg: string, side: 'off' | 'def' = 'off',
): Record<string, Player[]> {
  const spec = (side === 'off' ? OFF_PACKAGES : DEF_PACKAGES) as any;
  const s = spec[pkg] ?? {};
  const out: Record<string, Player[]> = {};
  for (const pos in s) out[pos] = (chart[pos] ?? []).slice(0, s[pos]);
  return out;
}
