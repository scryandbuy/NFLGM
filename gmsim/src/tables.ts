/**
 * Tables for events, targets, gameplans and adjustments.
 *
 * EVENTS come from 6 seasons of real play-by-play (281,339 plays): scrambles
 * 5.12% of dropbacks at 7.00 yards, fumbles 1.499% on runs and 12.528% on
 * sacks, penalties 11.88 per game with 20 types at their real rates.
 *
 * TARGETS come from FTN progression charting: first read 53.0% of dropbacks,
 * checkdown 15.2%, designed 11.2%, scramble drill 10.3%, second read 10.3% -
 * plus Next Gen separation (league mean 3.04 yards, TE 3.35, WR 2.93).
 *
 * ADJUSTMENT costs encode how hard each gameplan parameter is to change
 * mid-game: a dial you turn freely (0.05) up to a wholesale change of identity
 * most coordinators never make (0.75).
 */
export const SCRAMBLE = {
  mean: 7.0,
  sd: 6.07,
  median: 6,
  p10: 1,
  p90: 14,
  max: 61,
  pct_10plus: 0.248,
  pct_20plus: 0.043,
  first_down_rate: 0.483,
} as const;

export const FUMBLE_RATE = {
  run: 0.01499,
  complete_pass: 0.01141,
  sack: 0.12528,
  scramble: 0.01499,
  punt_return: 0.03059,
  kick_return: 0.00684,
} as const;

export const FUMBLE_LOST = {
  run: 0.42,
  complete_pass: 0.483,
  sack: 0.483,
  scramble: 0.42,
  punt_return: 0.358,
  kick_return: 0.487,
} as const;

export const FORCED_SHARE = 0.676;

export const PENALTIES = {
  'Offensive Holding': 2.243,
  'False Start': 2.228,
  'Defensive Pass Interference': 1.045,
  'Defensive Holding': 0.658,
  'Unnecessary Roughness': 0.61,
  'Delay of Game': 0.581,
  'Defensive Offside': 0.544,
  'Roughing the Passer': 0.399,
  'Neutral Zone Infraction': 0.376,
  'Face Mask': 0.294,
  'Illegal Formation': 0.283,
  'Offensive Pass Interference': 0.256,
  'Illegal Contact': 0.241,
  'Illegal Block Above the Waist': 0.226,
  'Illegal Use of Hands': 0.223,
  'Ineligible Downfield Pass': 0.193,
  'Intentional Grounding': 0.161,
  'Defensive Too Many Men on Field': 0.137,
  'Illegal Shift': 0.136,
  'Encroachment': 0.128,
} as const;

export const PEN_INFO = {
  'Offensive Holding': {
    yards: 9.6,
    auto_first: 0.0,
    offense: true,
    phase: 'any',
  },
  'False Start': {
    yards: 4.9,
    auto_first: 0.0,
    offense: true,
    phase: 'pre',
  },
  'Defensive Pass Interference': {
    yards: 15.8,
    auto_first: 0.99,
    offense: false,
    phase: 'pass',
  },
  'Defensive Holding': {
    yards: 4.7,
    auto_first: 0.99,
    offense: false,
    phase: 'any',
  },
  'Unnecessary Roughness': {
    yards: 13.1,
    auto_first: 0.65,
    offense: null,
    phase: 'post',
  },
  'Delay of Game': {
    yards: 4.9,
    auto_first: 0.0,
    offense: true,
    phase: 'pre',
  },
  'Defensive Offside': {
    yards: 4.8,
    auto_first: 0.18,
    offense: false,
    phase: 'pre',
  },
  'Roughing the Passer': {
    yards: 13.2,
    auto_first: 0.96,
    offense: false,
    phase: 'pass',
  },
  'Neutral Zone Infraction': {
    yards: 4.8,
    auto_first: 0.25,
    offense: false,
    phase: 'pre',
  },
  'Face Mask': {
    yards: 13.5,
    auto_first: 0.69,
    offense: null,
    phase: 'any',
  },
  'Illegal Formation': {
    yards: 4.9,
    auto_first: 0.0,
    offense: true,
    phase: 'pre',
  },
  'Offensive Pass Interference': {
    yards: 9.7,
    auto_first: 0.0,
    offense: true,
    phase: 'pass',
  },
  'Illegal Contact': {
    yards: 4.9,
    auto_first: 1.0,
    offense: false,
    phase: 'pass',
  },
  'Illegal Block Above the Waist': {
    yards: 9.3,
    auto_first: 0.0,
    offense: true,
    phase: 'any',
  },
  'Illegal Use of Hands': {
    yards: 6.0,
    auto_first: 0.74,
    offense: null,
    phase: 'any',
  },
  'Ineligible Downfield Pass': {
    yards: 4.9,
    auto_first: 0.0,
    offense: true,
    phase: 'pass',
  },
  'Intentional Grounding': {
    yards: 11.5,
    auto_first: 0.0,
    offense: true,
    phase: 'pass',
  },
  'Defensive Too Many Men on Field': {
    yards: 4.4,
    auto_first: 0.24,
    offense: false,
    phase: 'pre',
  },
  'Illegal Shift': {
    yards: 4.9,
    auto_first: 0.0,
    offense: true,
    phase: 'pre',
  },
  Encroachment: {
    yards: 4.7,
    auto_first: 0.28,
    offense: false,
    phase: 'pre',
  },
} as const;

export const DPI = {
  mean: 15.3,
  median: 13,
  p75: 21,
  p90: 30,
  p99: 46,
  max: 52,
  pct_20plus: 0.28,
  pct_40plus: 0.034,
} as const;

export const PENALTY_RATE = 0.0703;

export const PENALTIES_PER_GAME = 11.88;

export const PLAYS_PER_GAME = 169.0;

export const SCRAMBLE_RATE_BASE = 0.0512;

export const SEP_BY_POS = {
  WR: 2.93,
  TE: 3.35,
  HB: 3.6,
  FB: 3.6,
} as const;

export const CONCEPT_READS = {
  flood: ['deep', 'medium', 'flat'],
  smash: ['corner', 'hitch'],
  levels: ['deep_in', 'shallow'],
  dagger: ['seam', 'dig', 'check'],
  mesh: ['cross1', 'cross2', 'sit', 'check'],
  four_verts: ['seam1', 'seam2', 'outside', 'check'],
  scissors: ['post', 'corner'],
  slant_flat: ['slant', 'flat'],
  stick: ['stick', 'flat', 'back'],
  curl_flat: ['curl', 'flat', 'check'],
  screen: ['screen'],
  go: ['go', 'check'],
} as const;

export const READ_MIX = {
  first: 0.53,
  second: 0.103,
  checkdown: 0.152,
  designed: 0.112,
  scramble: 0.103,
} as const;

export const READ_MODIFIER = {
  first: {
    comp: 1.0,
    air: 10.9,
    epa: 0.31,
  },
  second: {
    comp: 0.88,
    air: 11.0,
    epa: 0.16,
  },
  checkdown: {
    comp: 1.29,
    air: 0.7,
    epa: -0.04,
  },
  designed: {
    comp: 1.37,
    air: -3.0,
    epa: -0.06,
  },
  scramble: {
    comp: 0.49,
    air: 11.6,
    epa: 0.0,
  },
} as const;

export const DEPTH_WEIGHTS = {
  QB: {
    throw_acc_short_rating: 0.18,
    throw_acc_mid_rating: 0.18,
    throw_acc_deep_rating: 0.12,
    awareness_rating: 0.22,
    throw_power_rating: 0.1,
    throw_under_pressure_rating: 0.12,
    break_sack_rating: 0.08,
  },
  HB: {
    break_tackle_rating: 0.16,
    speed_rating: 0.18,
    bcv_rating: 0.16,
    juke_move_rating: 0.12,
    carry_rating: 0.12,
    accel_rating: 0.14,
    catch_rating: 0.06,
    pass_block_rating: 0.06,
  },
  WR: {
    route_run_short_rating: 0.16,
    route_run_med_rating: 0.16,
    route_run_deep_rating: 0.14,
    catch_rating: 0.16,
    speed_rating: 0.16,
    release_rating: 0.12,
    cit_rating: 0.1,
  },
  TE: {
    route_run_short_rating: 0.16,
    route_run_med_rating: 0.16,
    catch_rating: 0.2,
    run_block_rating: 0.16,
    pass_block_rating: 0.1,
    speed_rating: 0.12,
    cit_rating: 0.1,
  },
  LT: {
    pass_block_finesse_rating: 0.3,
    pass_block_power_rating: 0.22,
    pass_block_rating: 0.18,
    run_block_rating: 0.16,
    agility_rating: 0.08,
    strength_rating: 0.06,
  },
  RT: {
    pass_block_power_rating: 0.26,
    pass_block_finesse_rating: 0.22,
    pass_block_rating: 0.18,
    run_block_rating: 0.2,
    strength_rating: 0.08,
    agility_rating: 0.06,
  },
  LG: {
    run_block_power_rating: 0.26,
    pass_block_power_rating: 0.22,
    run_block_rating: 0.18,
    pass_block_rating: 0.16,
    strength_rating: 0.12,
    agility_rating: 0.06,
  },
  C: {
    awareness_rating: 0.18,
    run_block_rating: 0.2,
    pass_block_rating: 0.2,
    run_block_power_rating: 0.16,
    strength_rating: 0.14,
    agility_rating: 0.12,
  },
  LEDG: {
    power_moves_rating: 0.24,
    finesse_moves_rating: 0.24,
    block_shed_rating: 0.16,
    accel_rating: 0.14,
    pursuit_rating: 0.12,
    strength_rating: 0.1,
  },
  DT: {
    power_moves_rating: 0.24,
    block_shed_rating: 0.24,
    strength_rating: 0.2,
    finesse_moves_rating: 0.14,
    tackle_rating: 0.1,
    pursuit_rating: 0.08,
  },
  MIKE: {
    play_rec_rating: 0.22,
    tackle_rating: 0.2,
    pursuit_rating: 0.16,
    zone_cover_rating: 0.14,
    awareness_rating: 0.14,
    block_shed_rating: 0.14,
  },
  WILL: {
    pursuit_rating: 0.2,
    speed_rating: 0.16,
    tackle_rating: 0.16,
    man_cover_rating: 0.16,
    zone_cover_rating: 0.16,
    play_rec_rating: 0.16,
  },
  CB: {
    man_cover_rating: 0.26,
    speed_rating: 0.2,
    zone_cover_rating: 0.16,
    press_rating: 0.14,
    accel_rating: 0.12,
    change_of_direction_rating: 0.12,
  },
  FS: {
    zone_cover_rating: 0.24,
    play_rec_rating: 0.2,
    speed_rating: 0.18,
    man_cover_rating: 0.14,
    awareness_rating: 0.14,
    tackle_rating: 0.1,
  },
  SS: {
    tackle_rating: 0.2,
    zone_cover_rating: 0.2,
    hit_power_rating: 0.16,
    play_rec_rating: 0.16,
    man_cover_rating: 0.14,
    pursuit_rating: 0.14,
  },
  K: {
    kick_acc_rating: 0.65,
    kick_power_rating: 0.35,
  },
  P: {
    kick_power_rating: 0.6,
    kick_acc_rating: 0.4,
  },
  RG: {
    run_block_power_rating: 0.26,
    pass_block_power_rating: 0.22,
    run_block_rating: 0.18,
    pass_block_rating: 0.16,
    strength_rating: 0.12,
    agility_rating: 0.06,
  },
  REDG: {
    power_moves_rating: 0.24,
    finesse_moves_rating: 0.24,
    block_shed_rating: 0.16,
    accel_rating: 0.14,
    pursuit_rating: 0.12,
    strength_rating: 0.1,
  },
  SAM: {
    pursuit_rating: 0.2,
    speed_rating: 0.16,
    tackle_rating: 0.16,
    man_cover_rating: 0.16,
    zone_cover_rating: 0.16,
    play_rec_rating: 0.16,
  },
  FB: {
    run_block_rating: 0.4,
    lead_block_rating: 0.3,
    impact_block_rating: 0.2,
    carry_rating: 0.1,
  },
  LS: {
    awareness_rating: 1.0,
  },
} as const;

export const SCHEME_SHIFT = {
  gap: {
    run_block_power_rating: 0.26,
    strength_rating: 0.16,
    run_block_finesse_rating: -0.14,
    agility_rating: -0.1,
  },
  zone: {
    run_block_finesse_rating: 0.28,
    agility_rating: 0.2,
    run_block_power_rating: -0.16,
    strength_rating: -0.12,
  },
  two_gap: {
    strength_rating: 0.24,
    block_shed_rating: 0.18,
    finesse_moves_rating: -0.14,
    accel_rating: -0.1,
  },
  one_gap: {
    accel_rating: 0.18,
    finesse_moves_rating: 0.24,
    strength_rating: -0.14,
  },
  man: {
    man_cover_rating: 0.24,
    press_rating: 0.18,
    zone_cover_rating: -0.14,
  },
  zone_cov: {
    zone_cover_rating: 0.26,
    play_rec_rating: 0.2,
    man_cover_rating: -0.16,
  },
} as const;

export const OFF_PACKAGES = {
  '11': {
    WR: 3,
    TE: 1,
    HB: 1,
  },
  '12': {
    WR: 2,
    TE: 2,
    HB: 1,
  },
  '21': {
    WR: 2,
    TE: 1,
    HB: 2,
  },
  '13': {
    WR: 1,
    TE: 3,
    HB: 1,
  },
  '10': {
    WR: 4,
    TE: 0,
    HB: 1,
  },
  '22': {
    WR: 1,
    TE: 2,
    HB: 2,
  },
  '00': {
    WR: 5,
    TE: 0,
    HB: 0,
  },
} as const;

export const DEF_PACKAGES = {
  base: {
    CB: 2,
    FS: 1,
    SS: 1,
    LB: 3,
    DL: 4,
  },
  nickel: {
    CB: 3,
    FS: 1,
    SS: 1,
    LB: 2,
    DL: 4,
  },
  dime: {
    CB: 4,
    FS: 1,
    SS: 1,
    LB: 1,
    DL: 4,
  },
  heavy: {
    CB: 2,
    FS: 1,
    SS: 0,
    LB: 4,
    DL: 5,
  },
} as const;

export const SEP_MEAN = 3.04;

export const SEP_SD = 0.57;

export const SEP_MIN = 1.11;

export const SEP_MAX = 5.66;

export const COST = {
  pass_bias: 0.05,
  depth_mix: 0.1,
  tempo: 0.12,
  target_priority: 0.1,
  protection: 0.15,
  blitz_rate: 0.18,
  box_bias: 0.18,
  personnel_mix: 0.25,
  shell_weights: 0.3,
  travel: 0.35,
  bracket: 0.3,
  man_rate: 0.55,
  front_pref: 0.7,
  run_scheme_mix: 0.75,
} as const;

export const COUNTER_TO_PLAN = {
  pass_deep: [['shell_weights', {
    cover_2: 0.18,
    cover_4: 0.16,
    cover_1: -0.08,
    cover_3: -0.1,
  }], ['box_bias', -0.1]],
  pass_medium: [['shell_weights', {
    cover_3: 0.14,
    tampa_2: 0.12,
    cover_1: -0.1,
  }]],
  pass_short: [['shell_weights', {
    cover_1: 0.16,
    cover_0: 0.06,
    cover_4: -0.12,
  }], ['man_rate', 0.12], ['box_bias', 0.08]],
  target: [['bracket', 'TARGET'], ['travel', true], ['shell_weights', {
    cover_2: 0.12,
    cover_4: 0.1,
  }]],
  run: [['box_bias', 0.22], ['front_pref', ['bear', 'tite']]],
  protection: [['protection', 'seven'], ['depth_mix', [0.8, 0.16, 0.04]]],
  predictable: [['pass_bias', 0.0]],
} as const;

export const TRENDS = ['pass_depth', 'run_direction', 'target_concentration', 'personnel', 'tempo', 'protection', 'front_success', 'coverage_success'] as const;

export const COUNTERS = {
  pass_deep: {
    shell_to: ['cover_2', 'cover_4'],
    box: -0.6,
    cost: 'run_game',
    desc: 'drop the safeties, take away the top',
  },
  pass_medium: {
    shell_to: ['cover_3', 'tampa_2'],
    box: -0.3,
    cost: 'run_game',
    desc: 'more zone underneath',
  },
  pass_short: {
    shell_to: ['cover_1', 'cover_0'],
    box: 0.4,
    cost: 'deep_ball',
    desc: 'press and squeeze the quick game',
  },
  target: {
    bracket: true,
    shell_to: ['cover_2', 'cover_4'],
    box: -0.8,
    cost: 'other_receivers',
    desc: 'shadow and bracket the man beating us',
  },
  run: {
    box: 1.4,
    front_to: ['bear', 'tite', '4-3 under'],
    cost: 'play_action',
    desc: 'walk a safety down, heavier front',
  },
  protection: {
    offense: true,
    keep_in: 1,
    depth_to: 'short',
    cost: 'routes',
    desc: 'keep a back in, get the ball out',
  },
  predictable: {
    offense: true,
    force_mix: true,
    cost: null,
    desc: 'break our own tendency before they read it',
  },
} as const;

export const MIN_SERIES = 2;

export const MIN_EVENTS = 5;

