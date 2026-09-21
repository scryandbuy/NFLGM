/**
 * Condition, sharpness, jadedness and injuries.
 *
 * Architecture follows Football Manager, which models this properly and whose
 * mechanics are documented and tested by its community. NFL data supplies the
 * targets.
 *
 * THREE SEPARATE STATE VARIABLES, not one "fatigue" number: condition is
 * physical freshness now, sharpness is match readiness, jadedness is hidden
 * season-long accumulation.
 *
 * TWO ATTRIBUTES WITH DIFFERENT JOBS: stamina governs condition LOSS during a
 * game and does NOT affect recovery - FM's community tested that explicitly.
 * Natural fitness governs recovery between games.
 *
 * THE KEY INSIGHT: condition mostly drives INJURY RISK; sharpness drives
 * PERFORMANCE. FM players found low-sharpness men play badly while
 * low-condition men mostly just get hurt.
 *
 * THE INJURY CURVE IS VIOLENTLY NONLINEAR. Community testing at a fixed
 * workload found 8 in-match injuries at 100% condition, 20 at 80%, 87 at 60% -
 * roughly 2.4x per 20 points lost, and that is what makes rest a real decision.
 */
export const SNAP_INTENSITY = {
  C: 0.19,
  LG: 0.224,
  RG: 0.224,
  QB: 0.255,
  LT: 0.258,
  RT: 0.258,
  SS: 0.422,
  FS: 0.484,
  CB: 0.536,
  MIKE: 0.742,
  WILL: 0.742,
  SAM: 1.0,
  WR: 0.942,
  DT: 1.105,
  LEDG: 1.169,
  REDG: 1.169,
  TE: 1.257,
  HB: 1.66,
  FB: 2.333,
  K: 0.02,
  P: 0.02,
  LS: 0.02,
} as const;

export const SHARPNESS_DECAY = {
  speed_rating: 0.2,
  accel_rating: 0.35,
  agility_rating: 0.3,
  change_of_direction_rating: 0.35,
  awareness_rating: 0.55,
  catch_rating: 0.45,
  route_run_short_rating: 0.45,
  route_run_med_rating: 0.5,
  route_run_deep_rating: 0.5,
  man_cover_rating: 0.5,
  zone_cover_rating: 0.55,
  play_rec_rating: 0.6,
  throw_acc_short_rating: 0.5,
  throw_acc_mid_rating: 0.55,
  throw_acc_deep_rating: 0.6,
  tackle_rating: 0.4,
  pursuit_rating: 0.35,
  pass_block_rating: 0.45,
  run_block_rating: 0.45,
  block_shed_rating: 0.4,
  power_moves_rating: 0.35,
  finesse_moves_rating: 0.45,
  bcv_rating: 0.5,
  carry_rating: 0.4,
} as const;

export const CONDITION_DECAY = {
  speed_rating: 0.55,
  accel_rating: 0.7,
  agility_rating: 0.6,
  change_of_direction_rating: 0.6,
  jump_rating: 0.55,
  power_moves_rating: 0.5,
  finesse_moves_rating: 0.5,
  pursuit_rating: 0.55,
  strength_rating: 0.3,
} as const;

export const INJURY_SHARE = {
  CB: 0.1427,
  MIKE: 0.0465,
  WILL: 0.0465,
  SAM: 0.0465,
  WR: 0.1324,
  FS: 0.0463,
  SS: 0.0463,
  LT: 0.0454,
  RT: 0.0454,
  DT: 0.0744,
  TE: 0.0691,
  HB: 0.065,
  LEDG: 0.0315,
  REDG: 0.0315,
  LG: 0.0295,
  RG: 0.0295,
  QB: 0.0302,
  C: 0.0217,
  K: 0.0094,
  FB: 0.0067,
  P: 0.0026,
  LS: 0.0009,
} as const;

export const INJURY_TYPES = [['Knee', 0.1826, 1.9], ['Ankle', 0.1451, 1.5], ['Hamstring', 0.1319, 1.6], ['Concussion', 0.0997, 1.3], ['Shoulder', 0.0498, 1.6], ['Calf', 0.0402, 1.5], ['Foot', 0.0393, 1.8], ['Groin', 0.0314, 1.5], ['Neck', 0.0296, 1.4], ['Hip', 0.0284, 1.5], ['Quadricep', 0.0255, 1.4], ['Back', 0.0211, 1.4], ['Pectoral', 0.0155, 2.6], ['Toe', 0.0138, 1.5], ['Elbow', 0.0114, 1.5], ['Hand', 0.0106, 1.4], ['Illness', 0.0182, 1.1], ['Other', 0.1059, 1.5]] as const;

/** Condition regained per snap on the sideline. Solved so emergent snap
 *  shares land ON the real league values rather than 14 points above them. */
export const SIDELINE_RECOVERY = 0.62;

/** Real: players ruled out per team per week (median 2, p90 4, max 9). */
export const INJURIES_PER_TEAM_WEEK = 2.51;

/**
 * The 2.51 figure counts players RULED OUT. Many in-game injuries never reach
 * that. Re-solved three times: once when the roll was wired into a live game
 * (it fires on BOTH sides of every contact play), again once ROTATION went
 * live (fewer contact events per starter), and finally against REAL rosters.
 */
export const RULED_OUT_SHARE = 0.165;

/** The realistic in-game condition the base rate is anchored at. */
export const COND_REFERENCE = 88.0;

/**
 * Durability is measured against the REAL league mean, not the 0.70 midpoint.
 * Actual NFL players average 89 on injury rating, so centring on 70 made every
 * real player read as 38% less injury-prone and pinned the league at 1.2 men
 * out per team per game against a real 2.51.
 */
export const DUR_LEAGUE = 0.87;
