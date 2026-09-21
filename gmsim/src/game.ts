/**
 * The game loop: drives, downs, clock, field position and scoring.
 *
 * Ported from game.py. Every rate comes from nflverse play-by-play: seconds
 * per play type, the fourth-down go table by distance and field zone, field
 * goal percentage by distance, punt and kickoff distributions, and the 2026
 * dynamic kickoff rule.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';

// ============================================================ CLOCK
export const SEC: Record<string, number> = {
  complete: 31.4, incomplete: 10.2, run: 34.7, sack: 30.0, scramble: 34.7,
  punt: 9.4, field_goal: 4.0, kickoff: 5.8, penalty: 14.4,
  interception: 12.0, drop: 10.2, fumble: 12.0,
};
export const QUARTER = 900, HALF = 1800, GAME = 3600;

export function playSeconds(result: string, clockStopped = false, hurry = false): number {
  let s = SEC[result] ?? 25.0;
  if (clockStopped) s = Math.min(s, 8.0);
  if (hurry) s *= 0.55;
  return s;
}

// ============================================================ FOURTH DOWN
/** Real go-for-it rate by distance and field zone. */
export const GO_RATE: Record<string, Record<string, number>> = {
  '1':   { fg_range: .825, midfield: .920, own: .534, backed: .211 },
  '2':   { fg_range: .506, midfield: .705, own: .199, backed: .101 },
  '3-4': { fg_range: .268, midfield: .496, own: .107, backed: .067 },
  '5-7': { fg_range: .120, midfield: .236, own: .083, backed: .048 },
  '8+':  { fg_range: .085, midfield: .116, own: .073, backed: .040 },
};
export const FOURTH_CONV: Record<string, number> = {
  '1': .675, '2': .588, '3-4': .510, '5-7': .442, '8+': .247,
};

export function fourthBand(ydstogo: number): string {
  if (ydstogo <= 1) return '1';
  if (ydstogo <= 2) return '2';
  if (ydstogo <= 4) return '3-4';
  if (ydstogo <= 7) return '5-7';
  return '8+';
}

/** yardline100 = yards to the opponent's end zone. */
export function fourthZone(yardline100: number): string {
  if (yardline100 <= 35) return 'fg_range';
  if (yardline100 <= 50) return 'midfield';
  if (yardline100 <= 70) return 'own';
  return 'backed';
}

export type FourthDecision = 'go' | 'field_goal' | 'punt';

export function fourthDownDecision(
  yardline100: number, ydstogo: number, scoreDiff: number, secsLeft: number,
  rng: RNG, aggression = 0.5,
): FourthDecision {
  const band = fourthBand(ydstogo), zone = fourthZone(yardline100);
  let pGo = GO_RATE[band][zone] * (0.70 + 0.60 * aggression);
  // trailing late, you have no choice
  if (secsLeft < 300 && scoreDiff < 0) pGo = Math.max(pGo, scoreDiff < -8 ? 0.55 : 0.35);
  if (secsLeft < 120 && scoreDiff < 0 && yardline100 > 40) pGo = Math.max(pGo, 0.90);
  if (rng.next() < pGo) return 'go';
  // 45 yards out is a 62-yard attempt. Real clubs kick from about the 38 or
  // closer; allowing 62-yarders put missed FGs at 4.24% against a real 2.66%.
  if (yardline100 <= 38) return 'field_goal';
  if (secsLeft < 10 && yardline100 <= 45) return 'field_goal';
  return 'punt';
}

// ============================================================ FIELD GOALS
/** Re-solved on real kickers, whose ratings sit above the flat-70 test clones. */
export const FG_PCT: Array<[number, number]> = [
  [29, .960], [34, .940], [39, .878], [44, .805], [49, .728], [54, .694], [99, .552],
];

export function fgProbability(distance: number, kicker?: Player): number {
  let base = 0.552;
  for (const [d, p] of FG_PCT) if (distance <= d) { base = p; break; }
  if (kicker) {
    const acc = rate(kicker, { kick_acc_rating: .75, awareness_rating: .25 });
    base *= 1.0 + 0.16 * (acc - AVG);
    if (distance >= 50) {                       // power only matters from distance
      base *= 1.0 + 0.55 * (rate(kicker, { kick_power_rating: 1.0 }) - AVG);
    }
  }
  return clip(base, 0.02, 0.995);
}

export function attemptFieldGoal(yardline100: number, kicker: Player, rng: RNG) {
  const dist = yardline100 + 17;                 // 10 end zone + 7 snap
  const made = rng.next() < fgProbability(dist, kicker);
  return { type: 'field_goal', distance: dist, made, points: made ? 3 : 0 };
}

// ============================================================ PUNTS
/** Real: returned on 35% of punts, mean 11.5 yards WHEN returned, 0.36% score. */
export const PUNT = {
  gross: 47.2, sd: 9.8, touchback: .075, blocked: .0043,
  returnRate: .35, returnMean: 11.5,
};

export function punt(yardline100: number, punter: Player, returner: Player, rng: RNG) {
  if (rng.next() < PUNT.blocked) {
    return { type: 'punt', blocked: true, newYardline: 100 - yardline100 };
  }
  const pwr = rate(punter, { kick_power_rating: .70, kick_acc_rating: .30 });
  const gross = rng.normal(PUNT.gross * (1.0 + 0.30 * (pwr - AVG)), PUNT.sd);
  const land = yardline100 - gross;
  if (land <= 0 || rng.next() < PUNT.touchback) {
    return { type: 'punt', blocked: false, touchback: true, newYardline: 80 };
  }
  let ret = 0;
  if (rng.next() < PUNT.returnRate) {
    const skill = rate(returner, {
      kick_ret_rating: .45, speed_rating: .30, juke_move_rating: .25,
    });
    // shape/scale solved against mean 11.5 and p90 19, with a tail long enough
    // that 0.36% reach the end zone
    ret = Math.max(0, rng.gamma(1.9, 6.05) * (1.0 + 0.9 * (skill - AVG)));
  }
  return {
    type: 'punt', blocked: false, touchback: false,
    gross: Math.round(gross * 10) / 10, ret: Math.round(ret * 10) / 10,
    newYardline: Math.round(clip(100 - land + ret, 1, 99)),
  };
}

// ============================================================ KICKOFFS
/**
 * 2026 DYNAMIC KICKOFF. The rule has changed every year since 2024, so older
 * seasons describe a game that no longer exists: touchbacks ran 73.0% in 2023,
 * 64.2% in 2024, 20.7% in 2025 and 15.5% through the start of 2026.
 *
 * Under the current rule a kick reaching the end zone in the air is a touchback
 * out to the RECEIVING TEAM'S OWN 35 - not the 30. Live 2026 data confirms it:
 * mean drive start after a touchback is the own 35.0.
 */
export const KICKOFF = {
  touchback: .155, returnRate: .799, returnMean: 26.9,
  touchbackTo: 65,                  // receiving team's own 35
  touchbackFrom50: 80,              // own 20, the 2026 anti-loophole rule
  onsideRecovery: .0645,
};

export function kickoff(returner: Player, rng: RNG, from50 = false) {
  if (rng.next() < KICKOFF.touchback) {
    return {
      type: 'kickoff', touchback: true,
      newYardline: from50 ? KICKOFF.touchbackFrom50 : KICKOFF.touchbackTo,
    };
  }
  const skill = rate(returner, {
    kick_ret_rating: .45, speed_rating: .30, juke_move_rating: .25,
  });
  const ret = rng.gamma(2.4, KICKOFF.returnMean / 2.4) * (1.0 + 0.8 * (skill - AVG));
  // the landing zone runs from the goal line to the 20, so a returned kick
  // starts from roughly the 5 and the return is measured from there
  return {
    type: 'kickoff', touchback: false, ret: Math.round(ret * 10) / 10,
    newYardline: clip(100 - (5.0 + ret), 1, 99),
  };
}

// ============================================================ DRIVE
export class Drive {
  yardline: number;
  down = 1; togo = 10;
  plays = 0; firstDowns = 0;
  result: string | null = null;
  points = 0;
  log: any[] = [];
  nextYardline?: number;
  constructor(
    public off: any, public deff: any, startYardline: number,
    public clock: number, public quarter: number, public scoreDiff: number,
  ) { this.yardline = startYardline; }
}

/** Apply yardage, update downs and field position. Whole yards only. */
export function advance(dr: Drive, gained: number): boolean {
  const g = Math.round(gained);
  dr.yardline -= g;
  dr.togo -= g;
  if (dr.yardline <= 0) {
    // Real value of a touchdown including the try is 6.94, not 7.
    dr.result = 'Touchdown'; dr.points = 6.94;
    return true;
  }
  if (dr.yardline >= 100) { dr.result = 'Safety'; dr.points = -2; return true; }
  if (dr.togo <= 0) {
    dr.down = 1; dr.togo = Math.min(10, dr.yardline); dr.firstDowns++;
  } else {
    dr.down++;
  }
  return false;
}

/**
 * Real carry share by rank within a team-season: 48.9 / 22.9 / 11.4 / 6.9 / 3.7.
 * (The third-ranked ball carrier on a typical team is the QUARTERBACK, at 52
 * carries, which scrambles already supply.)
 *
 * Nothing decided this before, so one back took every carry and finished with
 * 462 attempts and 3,788 yards against a real 334 and 1,763.
 */
export const CARRY_SHARE = [0.489, 0.229, 0.114, 0.069, 0.037];

export function pickRunner(
  backs: Player[], out: Set<string> | null, cond: ((pid: string) => number) | null, rng: RNG,
): Player | null {
  if (!backs.length) return null;
  const avail = out ? backs.filter(b => !out.has(b.pid)) : backs;
  const pool = avail.length ? avail : backs;
  const n = Math.min(pool.length, CARRY_SHARE.length);
  const w = CARRY_SHARE.slice(0, n).map((x, i) =>
    cond ? x * (0.35 + 0.65 * (cond(pool[i].pid) / 100)) : x);
  return pool[rng.sampleIndices(w, 1)[0]];
}

/**
 * Eleven men a side. QB + RB + 5 OL + 3 WR/TE on offence; 4 DL + 2 LB + 5 DB in
 * nickel, the league's base defence. An early build fielded five receivers,
 * five linemen and four linebackers every snap - sixteen defenders - which made
 * every backup a starter and flattened the snap distribution completely.
 */
export const OFF_SLOTS: Array<[string, string[]]> = [
  ['ol', ['LT', 'LG', 'C', 'RG', 'RT']], ['wr', ['WR', 'WR', 'WR']],
];
export const DEF_SLOTS: Array<[string, string[]]> = [
  ['dl', ['LEDG', 'DT', 'DT', 'REDG']],
  ['lb', ['MIKE', 'WILL']],
  ['db', ['CB', 'CB', 'CB', 'FS', 'SS']],
];

export const OT_LENGTH = 600;          // one 10-minute period, regular season
export const OT_PLAYOFF_LENGTH = 900;  // 15-minute periods until someone wins
