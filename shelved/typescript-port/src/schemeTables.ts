/**
 * The scheme layer: what play gets CALLED, before any matchup resolves.
 *
 * Personnel groups, defensive fronts, coverage shells, protections, run
 * schemes and route concepts - plus the real NFL pass rates by down, distance,
 * score and field position. Ported from schemes.py.
 *
 * Every rate here comes from nflverse play-by-play or FTN charting. The
 * calibration that matters: play action 10.2%, motion 36.5%, four rushers 71%
 * of dropbacks, blitz 13.3%, and a run game whose efficiency falls off a cliff
 * as the box fills (6.6 yards a carry against four men, 2.41 against nine).
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';

export const PERSONNEL_OFF = {
  '11': {
    rb: 1,
    te: 1,
    wr: 3,
    rate: 0.595,
    run_bias: -0.1,
    protect: 5,
  },
  '12': {
    rb: 1,
    te: 2,
    wr: 2,
    rate: 0.195,
    run_bias: 0.18,
    protect: 6,
  },
  '21': {
    rb: 2,
    te: 1,
    wr: 2,
    rate: 0.07,
    run_bias: 0.26,
    protect: 6,
  },
  '13': {
    rb: 1,
    te: 3,
    wr: 1,
    rate: 0.03,
    run_bias: 0.4,
    protect: 7,
  },
  '10': {
    rb: 1,
    te: 0,
    wr: 4,
    rate: 0.075,
    run_bias: -0.28,
    protect: 5,
  },
  '22': {
    rb: 2,
    te: 2,
    wr: 1,
    rate: 0.025,
    run_bias: 0.48,
    protect: 7,
  },
  '00': {
    rb: 0,
    te: 0,
    wr: 5,
    rate: 0.01,
    run_bias: -0.45,
    protect: 5,
  },
} as const;

export const PERSONNEL_DEF = {
  base: {
    db: 4,
    lb: 3,
    dl: 4,
    box_bonus: 1.0,
    cover_penalty: 0.1,
  },
  nickel: {
    db: 5,
    lb: 2,
    dl: 4,
    box_bonus: 0.0,
    cover_penalty: 0.0,
  },
  dime: {
    db: 6,
    lb: 1,
    dl: 4,
    box_bonus: -1.0,
    cover_penalty: -0.06,
  },
  heavy: {
    db: 3,
    lb: 4,
    dl: 5,
    box_bonus: 2.0,
    cover_penalty: 0.22,
  },
} as const;

export const FRONTS = {
  '4-3 over': {
    dl: 4,
    gap: 'one',
    edge_set: 'strong',
    run_fit: 1.0,
    rush: 1.0,
  },
  '4-3 under': {
    dl: 4,
    gap: 'one',
    edge_set: 'weak',
    run_fit: 1.02,
    rush: 0.98,
  },
  '3-4 one': {
    dl: 3,
    gap: 'one',
    edge_set: 'both',
    run_fit: 0.96,
    rush: 1.04,
  },
  '3-4 two': {
    dl: 3,
    gap: 'two',
    edge_set: 'both',
    run_fit: 1.06,
    rush: 0.9,
  },
  tite: {
    dl: 3,
    gap: 'two',
    edge_set: 'both',
    run_fit: 1.1,
    rush: 0.86,
  },
  bear: {
    dl: 5,
    gap: 'one',
    edge_set: 'both',
    run_fit: 1.14,
    rush: 1.06,
  },
  'wide 9': {
    dl: 4,
    gap: 'one',
    edge_set: 'both',
    run_fit: 0.9,
    rush: 1.1,
  },
  mint: {
    dl: 3,
    gap: 'two',
    edge_set: 'both',
    run_fit: 1.08,
    rush: 0.88,
  },
} as const;

export const FRONT_VS_SCHEME = {
  tite: {
    zone: 0.84,
    gap: 1.06,
  },
  mint: {
    zone: 0.86,
    gap: 1.05,
  },
  bear: {
    zone: 0.92,
    gap: 0.9,
  },
  '3-4 two': {
    zone: 0.94,
    gap: 1.0,
  },
  'wide 9': {
    zone: 1.08,
    gap: 0.96,
  },
  '4-3 over': {
    zone: 1.0,
    gap: 1.0,
  },
  '4-3 under': {
    zone: 0.98,
    gap: 1.02,
  },
  '3-4 one': {
    zone: 1.02,
    gap: 1.0,
  },
} as const;

export const BOX_YPC = {
  '4': 6.6,
  '5': 5.92,
  '6': 4.76,
  '7': 4.16,
  '8': 3.77,
  '9': 2.41,
  '10': 2.0,
} as const;

export const BOX_NEG = {
  '4': 4.5,
  '5': 5.53,
  '6': 8.2,
  '7': 9.57,
  '8': 11.14,
  '9': 13.76,
  '10': 16.0,
} as const;

export const PROTECTIONS = {
  five: {
    blockers: 5,
    routes_lost: 0,
    vs_stunt: 0.92,
    vs_blitz: 0.85,
  },
  six_bob: {
    blockers: 6,
    routes_lost: 1,
    vs_stunt: 0.96,
    vs_blitz: 1.0,
  },
  six_slide: {
    blockers: 6,
    routes_lost: 1,
    vs_stunt: 1.08,
    vs_blitz: 1.04,
  },
  half_slide: {
    blockers: 6,
    routes_lost: 1,
    vs_stunt: 1.05,
    vs_blitz: 1.06,
  },
  seven: {
    blockers: 7,
    routes_lost: 2,
    vs_stunt: 1.02,
    vs_blitz: 1.16,
  },
  max: {
    blockers: 8,
    routes_lost: 3,
    vs_stunt: 1.0,
    vs_blitz: 1.25,
  },
} as const;

export const RUN_SCHEMES = {
  inside_zone: {
    family: 'zone',
    aim: 'inside',
    cutback: 0.42,
    attr: 'finesse',
  },
  outside_zone: {
    family: 'zone',
    aim: 'outside',
    cutback: 0.55,
    attr: 'finesse',
  },
  stretch: {
    family: 'zone',
    aim: 'wide',
    cutback: 0.6,
    attr: 'finesse',
  },
  power: {
    family: 'gap',
    aim: 'inside',
    cutback: 0.12,
    attr: 'power',
  },
  counter: {
    family: 'gap',
    aim: 'inside',
    cutback: 0.18,
    attr: 'power',
  },
  duo: {
    family: 'gap',
    aim: 'inside',
    cutback: 0.25,
    attr: 'power',
  },
  trap: {
    family: 'gap',
    aim: 'inside',
    cutback: 0.15,
    attr: 'power',
  },
  draw: {
    family: 'zone',
    aim: 'inside',
    cutback: 0.3,
    attr: 'finesse',
  },
} as const;

export const CONCEPTS = {
  mesh: {
    depth: 'short',
    man: 1.28,
    cover_2: 1.1,
    cover_3: 1.08,
    cover_4: 1.12,
    n: 4,
  },
  flood: {
    depth: 'medium',
    man: 0.96,
    cover_2: 1.06,
    cover_3: 1.18,
    cover_4: 1.1,
    n: 3,
  },
  smash: {
    depth: 'short',
    man: 1.02,
    cover_2: 1.2,
    cover_3: 1.02,
    cover_4: 1.14,
    n: 2,
  },
  levels: {
    depth: 'short',
    man: 0.98,
    cover_2: 1.12,
    cover_3: 1.16,
    cover_4: 1.08,
    n: 3,
  },
  dagger: {
    depth: 'medium',
    man: 1.04,
    cover_2: 1.14,
    cover_3: 1.12,
    cover_4: 0.96,
    n: 3,
  },
  four_verts: {
    depth: 'deep',
    man: 1.1,
    cover_2: 1.18,
    cover_3: 1.14,
    cover_4: 0.9,
    n: 4,
  },
  scissors: {
    depth: 'deep',
    man: 1.02,
    cover_2: 0.98,
    cover_3: 1.0,
    cover_4: 1.22,
    n: 2,
  },
  slant_flat: {
    depth: 'short',
    man: 1.14,
    cover_2: 1.02,
    cover_3: 1.06,
    cover_4: 1.0,
    n: 2,
  },
  stick: {
    depth: 'short',
    man: 0.98,
    cover_2: 1.08,
    cover_3: 1.12,
    cover_4: 1.06,
    n: 3,
  },
  curl_flat: {
    depth: 'short',
    man: 0.94,
    cover_2: 1.06,
    cover_3: 1.14,
    cover_4: 1.04,
    n: 3,
  },
  screen: {
    depth: 'short',
    man: 1.2,
    cover_2: 0.94,
    cover_3: 0.92,
    cover_4: 0.9,
    n: 1,
  },
  go: {
    depth: 'deep',
    man: 1.16,
    cover_2: 1.04,
    cover_3: 0.92,
    cover_4: 0.84,
    n: 2,
  },
} as const;

export const SHELL_KEY = {
  cover_0: 'man',
  cover_1: 'man',
  man: 'man',
  cover_2: 'cover_2',
  tampa_2: 'cover_2',
  cover_3: 'cover_3',
  cover_6: 'cover_3',
  cover_4: 'cover_4',
} as const;

export const PASS_RATE = {
  '1': {
    '1-2': 0.256,
    '3-4': 0.308,
    '5-7': 0.352,
    '8-10': 0.478,
    '11+': 0.668,
  },
  '2': {
    '1-2': 0.323,
    '3-4': 0.421,
    '5-7': 0.552,
    '8-10': 0.671,
    '11+': 0.773,
  },
  '3': {
    '1-2': 0.37,
    '3-4': 0.776,
    '5-7': 0.871,
    '8-10': 0.889,
    '11+': 0.834,
  },
  '4': {
    '1-2': 0.387,
    '3-4': 0.888,
    '5-7': 0.906,
    '8-10': 0.937,
    '11+': 0.906,
  },
} as const;

export const SCRIPT = [[-99, -15, 0.7], [-14, -8, 0.659], [-7, -1, 0.595], [0, 0, 0.552], [1, 8, 0.535], [9, 15, 0.492], [16, 99, 0.399]] as const;

export const NEUTRAL_SCRIPT = 0.552;

