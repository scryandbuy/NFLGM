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

