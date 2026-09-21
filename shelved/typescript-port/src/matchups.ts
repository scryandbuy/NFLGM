/**
 * Matchup weight tables.
 *
 * Which attributes decide which contest. Every one of the 53 real player
 * ratings is wired into a specific matchup here - a pass rusher's power moves
 * meet a tackle's power pass-blocking, a receiver's release meets a corner's
 * press, and route running is read at the DEPTH the route is actually run.
 *
 * These weights are the reason a player's rating sheet matters at all. Ported
 * verbatim from the Python; changing one silently rebalances the whole engine.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, Player } from './core/math.js';

export type Weights = Record<string, number>;

export const PASS_RUSH = {
  rusher: {
    power: {
      power_moves_rating: 0.45,
      strength_rating: 0.3,
      block_shed_rating: 0.25,
    },
    finesse: {
      finesse_moves_rating: 0.45,
      accel_rating: 0.25,
      agility_rating: 0.15,
      block_shed_rating: 0.15,
    },
    pursuit: {
      pursuit_rating: 0.55,
      speed_rating: 0.45,
    },
  },
  blocker: {
    power: {
      pass_block_power_rating: 0.5,
      strength_rating: 0.3,
      pass_block_rating: 0.2,
    },
    finesse: {
      pass_block_finesse_rating: 0.5,
      agility_rating: 0.25,
      pass_block_rating: 0.25,
    },
  },
} as const;

export const ROUTE = {
  receiver: {
    release: {
      release_rating: 0.55,
      accel_rating: 0.25,
      agility_rating: 0.2,
    },
    short: {
      route_run_short_rating: 0.55,
      change_of_direction_rating: 0.25,
      agility_rating: 0.2,
    },
    medium: {
      route_run_med_rating: 0.55,
      change_of_direction_rating: 0.2,
      speed_rating: 0.25,
    },
    deep: {
      route_run_deep_rating: 0.45,
      speed_rating: 0.4,
      accel_rating: 0.15,
    },
  },
  defenderMan: {
    press: {
      press_rating: 0.55,
      strength_rating: 0.25,
      man_cover_rating: 0.2,
    },
    short: {
      man_cover_rating: 0.5,
      change_of_direction_rating: 0.25,
      agility_rating: 0.25,
    },
    medium: {
      man_cover_rating: 0.5,
      speed_rating: 0.25,
      agility_rating: 0.25,
    },
    deep: {
      man_cover_rating: 0.4,
      speed_rating: 0.45,
      accel_rating: 0.15,
    },
  },
  defender_zone: {
    break: {
      play_rec_rating: 0.4,
      zone_cover_rating: 0.35,
      awareness_rating: 0.25,
    },
    close: {
      speed_rating: 0.45,
      accel_rating: 0.35,
      agility_rating: 0.2,
    },
    contest: {
      zone_cover_rating: 0.45,
      jump_rating: 0.3,
      tackle_rating: 0.25,
    },
  },
  receiver_zone: {
    find_window: {
      route_run_short_rating: 0.25,
      route_run_med_rating: 0.25,
      route_run_deep_rating: 0.2,
      awareness_rating: 0.3,
    },
  },
} as const;

export const THROW = {
  short: {
    throw_acc_short_rating: 0.6,
    awareness_rating: 0.25,
    throw_power_rating: 0.15,
  },
  medium: {
    throw_acc_mid_rating: 0.55,
    throw_power_rating: 0.25,
    awareness_rating: 0.2,
  },
  deep: {
    throw_acc_deep_rating: 0.5,
    throw_power_rating: 0.35,
    awareness_rating: 0.15,
  },
  under_pressure: {
    throw_under_pressure_rating: 0.6,
    break_sack_rating: 0.4,
  },
  on_run: {
    throw_on_run_rating: 1.0,
  },
  play_action: {
    play_action_rating: 1.0,
  },
} as const;

export const CATCH = {
  clean: {
    catch_rating: 0.8,
    awareness_rating: 0.2,
  },
  contested: {
    cit_rating: 0.5,
    spec_catch_rating: 0.3,
    jump_rating: 0.2,
  },
  defender: {
    man_cover_rating: 0.4,
    jump_rating: 0.35,
    press_rating: 0.25,
  },
} as const;

export const YAC = {
  carrier: {
    elusive: {
      juke_move_rating: 0.3,
      agility_rating: 0.2,
      change_of_direction_rating: 0.15,
      spin_move_rating: 0.15,
      break_tackle_rating: 0.2,
    },
    power: {
      truck_rating: 0.3,
      stiff_arm_rating: 0.25,
      strength_rating: 0.2,
      break_tackle_rating: 0.25,
    },
    breakaway: {
      speed_rating: 0.6,
      accel_rating: 0.4,
    },
    vision: {
      bcv_rating: 0.7,
      awareness_rating: 0.3,
    },
  },
  tackler: {
    wrap: {
      tackle_rating: 0.7,
      pursuit_rating: 0.3,
    },
    angle: {
      pursuit_rating: 0.55,
      speed_rating: 0.45,
    },
    impact: {
      hit_power_rating: 0.6,
      tackle_rating: 0.4,
    },
  },
} as const;

export const RUN_BLOCK = {
  blocker: {
    power: {
      run_block_power_rating: 0.5,
      strength_rating: 0.3,
      run_block_rating: 0.2,
    },
    finesse: {
      run_block_finesse_rating: 0.5,
      agility_rating: 0.25,
      run_block_rating: 0.25,
    },
    second: {
      impact_block_rating: 0.5,
      lead_block_rating: 0.3,
      speed_rating: 0.2,
    },
  },
  defender: {
    shed: {
      block_shed_rating: 0.5,
      strength_rating: 0.3,
      power_moves_rating: 0.2,
    },
    fill: {
      play_rec_rating: 0.45,
      pursuit_rating: 0.35,
      awareness_rating: 0.2,
    },
  },
} as const;

export const BALL_SECURITY: Weights = {
  carry_rating: 0.7,
  awareness_rating: 0.3,
};


// ============================================================ ZONE COVERAGE
/**
 * Larger = easier throw. Derived from where each shell is structurally soft:
 * Cover 2 has a seam between the two deep safeties and is beaten by corner
 * routes and four verticals; Cover 3 has one fewer deep defender's worth of
 * width underneath; Cover 0 has no zone at all.
 * Windows are anchored to the REAL completion rate at each throw depth
 * (74.4% short / 56.0% medium / 39.4% deep, over six seasons), then modulated
 * by where each shell is structurally soft. The first build let shell dominate
 * and produced deep completions ABOVE short, which is backwards.
 */
export const ZONE_WINDOW: Record<string, [number, number, number]> = {
  //          short  medium  deep
  cover_2: [0.56, 0.49, 0.39],   // soft in the deep seam
  cover_3: [0.61, 0.44, 0.29],   // three deep, soft underneath
  cover_4: [0.65, 0.46, 0.23],   // takes away deep, gives up short
  cover_6: [0.60, 0.45, 0.31],   // quarter-quarter-half
  tampa_2: [0.54, 0.40, 0.33],   // MIKE carries the seam
};

/**
 * How many defenders are close enough to contest. A route landing between two
 * zones - the seam - is where zone gets beaten, so fewer contesting defenders.
 */
export const ZONE_DEFENDERS_NEAR: Record<string, number> = {
  cover_2: 1.3, cover_3: 1.5, cover_4: 1.7, cover_6: 1.5, tampa_2: 1.6,
};

const DEPTH_INDEX: Record<string, 0 | 1 | 2> = { short: 0, medium: 1, deep: 2 };

/** Base window for this shell at this route depth. Bigger = easier throw. */
export function zoneWindow(shell: string, depth: string): number {
  const i = DEPTH_INDEX[depth];
  return (ZONE_WINDOW[shell] ?? [0.58, 0.39, 0.27])[i];
}

export interface ZoneDefender extends Player { dist_to_window?: number; }

export interface ZoneResult {
  complete: boolean; contested: boolean; window: number;
  p_complete: number; defender: string | null;
}

/**
 * Zone pass resolution. Two steps, as the football describes it:
 *
 *   1. the shell and the route produce a WINDOW. The receiver's job is only to
 *      FIND it - route IQ, not separation athleticism.
 *   2. the NEAREST defender contests the THROW. He must read it (break), cover
 *      ground (close), then contest at the catch point.
 *
 * The QB is the load-bearing party, which is the whole point of zone: it
 * forces him to be perfect, and a great one shreds it.
 */
export function resolveZone(
  receiver: Player, defenders: ZoneDefender[], qb: Player, shell: string,
  depth: string, pressure: number, rng: RNG,
): ZoneResult {
  let w = zoneWindow(shell, depth);

  // Contests are resolved RELATIVE TO AVERAGE (0.70 on the 0-1 rating scale),
  // not on the absolute rating. An average defender should leave an average
  // window, not eat 40% of it - the first build squeezed every window by the
  // defender's raw rating and collapsed league completion to the 30s.

  // 1. does the receiver find the soft spot at all
  const find = rate(receiver, ROUTE.receiver_zone.find_window);
  w *= 1.0 + 0.45 * (find - AVG);

  // 2. the nearest defender squeezes it. Others are too far to matter, which
  //    is why the seam beats zone.
  let near: ZoneDefender | null = null;
  if (defenders.length) {
    near = defenders[0];
    // Python's min() keeps the FIRST on a tie, so this uses a strict <.
    for (const d of defenders) {
      if ((d.dist_to_window ?? 99) < (near.dist_to_window ?? 99)) near = d;
    }
  }
  if (near !== null) {
    const brk = rate(near, ROUTE.defender_zone.break);
    const cls = rate(near, ROUTE.defender_zone.close);
    const n = ZONE_DEFENDERS_NEAR[shell] ?? 1.5;
    const squeeze = (0.85 * (brk - AVG) + 0.75 * (cls - AVG)) * (n / 1.5);
    w *= 1.0 - squeeze;
  }

  w = Math.max(0.04, Math.min(0.97, w));

  // 3. the throw. Accuracy at this depth, degraded by pressure.
  let acc = rate(qb, (THROW as any)[depth]);
  if (pressure > 0) {
    // a QB with elite under-pressure ability barely degrades; a poor one falls
    // apart. The first build scaled by (1 - ability), which made even heavy
    // pressure worth ~3 points of completion.
    const up = rate(qb, THROW.under_pressure);
    acc *= 1.0 - pressure * (0.42 - 0.34 * (up - AVG));
  }

  // a good enough throw beats the window; a poor one gets contested.
  // 1.26 is solved, not chosen: with the depth-anchored windows above it puts
  // an average QB against an average defender on the real per-depth completion
  // rates (74.4 / 56.0 / 39.4).
  const pComplete = Math.min(0.97, w * 1.26 * (1.0 + 1.15 * (acc - AVG)));
  const roll = rng.next();
  const complete = roll < pComplete;
  const contested = !complete && roll < pComplete + (1.0 - w) * 0.45;
  return {
    complete, contested, window: +w.toFixed(3),
    p_complete: +pComplete.toFixed(3),
    defender: near ? near.pid : null,
  };
}
