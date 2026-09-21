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
import * as H from './health.js';
import * as GP from './gameplan.js';
import * as AD from './adjust.js';
import * as TG from './targets.js';
import * as E from './events.js';

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

// ============================================================ THE TRY
// A touchdown is six. What follows is a separate decision and a separate play,
// so the extra point can be missed and the two-point try can fail.
//
// The kick is a 33-yard field goal - ball on the 15, seven yards back to the
// hold, ten yards of end zone - so it runs through the same distance curve and
// the same kicker ratings as every other kick rather than a flat league rate.
//
// The two-point try is ONE REAL SNAP from the two, resolved by the same play
// engine as any other goal-line play. The conversion rate is therefore an
// output of the rosters and the red zone physics, not a constant. It is not
// calibrated to the real 47.9% and should not be until the red zone touchdown
// rate is fixed, since both come from the same per-play numbers.

/**
 * Leads (from the scoring team's view, counting the six just scored) where the
 * accepted chart says go for two. Late game only: before the fourth quarter
 * the chart has no opinion and teams kick.
 */
export const TWO_POINT_GO = [-18, -16, -10, -5, -2, 1, 4, 5];

/** Kick or go. The coach's call, not the engine's. */
export function twoPointDecision(leadAfterTd: number, quarter: number): boolean {
  if (quarter < 4) return false;
  return TWO_POINT_GO.includes(Math.round(leadAfterTd));
}

export function attemptExtraPoint(kicker: Player | null | undefined, rng: RNG) {
  const made = rng.next() < fgProbability(33, kicker ?? undefined);
  return { type: 'extra_point', distance: 33, made, points: made ? 1 : 0 };
}

/**
 * One snap from the two. Deliberately NOT fed to state.observe: the adjustment
 * engine reads a rolling four-series window of normal downs, and a goal-line
 * try is not one of those.
 */
export function attemptTwoPoint(
  offense: Roster, defense: Roster, rng: RNG, resolveFn: any,
  callOff: any, callDef: any,
  offState: TeamState | null = null, defState: TeamState | null = null,
) {
  const oc = callOff(1, 2, 0, 2, rng);
  const dc = callDef(oc, 1, 2, rng, 2);
  let [offF] = fieldUnits(offense, offState, rng, true, oc.personnel);
  const [defF] = fieldUnits(defense, defState, rng, false, dc.personnel);
  if (!oc.isPass) {
    const backs = (offense.backs ?? (offense.rb ? [offense.rb] : [])).filter(Boolean) as Player[];
    const rb = pickRunner(backs, offState ? offState.out : null,
                          offState ? (pid: string) => offState.cond.get(pid) : null, rng);
    if (rb !== null) offF = { ...offF, rb };
  }
  const out = resolveFn(offF, defF, oc, dc, 2, rng);
  const t = out.type;
  const good = (t === 'run' || t === 'complete' || t === 'scramble')
    && Number(out.yards ?? 0) >= 2.0;
  return { type: 'two_point', play: t, made: good, points: good ? 2 : 0 };
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
  tryResult: any = null;
  cheaters?: string[];
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
    // Six. The try is resolved at the end of runDrive, where the kicker and
    // the play engine are both in scope.
    dr.result = 'Touchdown'; dr.points = 6;
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

// ============================================================ TEAM STATE
export interface Roster {
  qb: Player; qbs?: Player[]; rb: Player | null; backs?: Player[];
  wr: Player[]; extra_blockers?: Player[];
  ol: Player[]; dl: Player[]; lb: Player[]; db: Player[];
  k?: Player | null; p?: Player | null; kr?: Player | null;
  depth?: Record<string, Player[]>;
  [k: string]: unknown;
}

/**
 * Live health for one team. Condition and injuries were built but nothing
 * called them, so nobody tired, nobody rotated and nobody got hurt during an
 * actual game. This is what connects them.
 */
export class TeamState {
  plan: GP.Gameplan;
  coach: GP.Coach;
  scheme?: string;
  mem: AD.GameMemory;
  script: AD.Script;
  lastAdjustment: AD.Adjustment | null = null;   // what the OTHER side just did
  chart: Record<string, Player[]> | null = null;
  cond: H.Condition;
  sharp: Record<string, number> = {};   // pid -> 0-100, carries between games
  jaded: Record<string, number> = {};   // pid -> 0-1, carries across a season
  injuries: H.Injury[] = [];            // this game's injuries
  out: Set<string> = new Set();         // unavailable right now
  snaps: Record<string, number> = {};
  lastSnaps: Record<string, number> = {};

  constructor(
    public roster: Roster, policy = 0.5,
    plan: GP.Gameplan | null = null, coach: GP.Coach | null = null,
    scheme?: string,
  ) {
    this.plan = plan ?? GP.basePlan(coach);
    this.coach = coach ?? {};
    this.scheme = scheme;
    this.mem = new AD.GameMemory();
    // Walsh's opener, run before the defence can counter. Off-script
    // performance is measurably worse for some callers: Shanahan's 2022 49ers
    // had +0.32 passing EPA on script and -0.10 off it.
    this.script = new AD.Script(
      null,
      Math.trunc(Number(this.coach.script_length ?? 15)),
      Number(this.coach.off_script_skill ?? 0.5));
    this.cond = new H.Condition(policy);
  }

  /** Men at this position who are not hurt, deepest-first order kept. */
  available(group: Player[], _position?: string): Player[] {
    const ok = group.filter(p => !this.out.has(p.pid));
    return ok.length ? ok : [...group];
  }

  /**
   * Who takes this snap. Walks the depth chart until someone is fresh enough
   * to go - which is what actually produces rotation.
   */
  pick(group: Player[], position: string, rng: RNG,
       staminaKey = 'stamina_rating'): [Player, number] {
    const men = this.available(group, position);
    for (let rank = 0; rank < men.length; rank++) {
      const p = men[rank];
      const pid = p.pid ?? `${position}${rank}`;
      const gap = (rank === 0 && men.length > 1) ? 0.6 : 0.0;
      if (!this.cond.needsRest(pid, position, rng,
                               Number(p[staminaKey] ?? 70.0), gap)) {
        return [p, rank];
      }
    }
    return [men[men.length - 1], men.length - 1];
  }

  snap(player: Player, position: string, onField = true): void {
    const pid = player.pid ?? position;
    if (onField) {
      this.cond.play(pid, position, Number(player.stamina_rating ?? 70.0));
      this.snaps[pid] = (this.snaps[pid] ?? 0) + 1;
    } else {
      this.cond.rest(pid);
    }
  }

  /** The player as he actually is: condition and sharpness applied. */
  state(player: Player, position: string): Player {
    const pid = player.pid ?? position;
    return H.applyState(player, this.cond.get(pid), this.sharp[pid] ?? 100.0);
  }

  hurt(player: Player, position: string, contact: number, rng: RNG,
       week = 1): H.Injury | null {
    const pid = player.pid ?? position;
    // A man already ruled out cannot be hurt again. Without this the same back
    // was injured three times in one game.
    if (this.out.has(pid)) return null;
    const inj = H.rollInjury(player, position, contact, rng,
                             this.cond.get(pid), this.jaded[pid] ?? 0.0);
    if (inj) {
      inj.week = week;
      this.injuries.push(inj);
      this.out.add(pid);
    }
    return inj;
  }

  /** Order every position group by POSITION-SPECIFIC rating. */
  rebuildChart(): Record<string, Player[]> {
    const groups: Record<string, Player[]> = {};
    const pairs: Array<[string, string]> = [
      ['wr', 'WR'], ['ol', 'LT'], ['dl', 'DT'], ['lb', 'MIKE'], ['db', 'CB'],
    ];
    for (const [key, pos] of pairs) {
      const g = this.roster[key] as Player[] | undefined;
      if (g) groups[key] = TG.orderDepth(g, pos, this.scheme, this.out);
    }
    this.chart = groups;
    return groups;
  }

  /**
   * This unit is OFF THE FIELD while the other side plays. Real players
   * recover on the bench between series; without this, condition collapsed to
   * a mean of 53 by the end of a game - with some men at zero - which drove
   * the injury multiplier to 16.7x and produced 4-5 men ruled out per team per
   * game against a real 2.51.
   */
  sidelineRecovery(snaps = 30): void {
    const extra = Math.trunc(Math.max(0, Math.trunc(snaps * 0.55)) / 6);
    for (const pid of Object.keys(this.cond.cond)) {
      this.cond.rest(pid);
      for (let i = 0; i < extra; i++) this.cond.rest(pid);
    }
  }

  newSeries(): void { this.mem.newSeries(); }

  observe(offCall: AD.PlayCall, defCall: AD.DefCallLike, outcome: AD.Outcome): void {
    this.mem.record(offCall, defCall, outcome);
  }

  /** Read the trends and modify THE PLAN. Returns what changed. */
  adjust(quarter = 1, rng?: RNG): string[] {
    const skill = Number(this.coach.adjust_skill ?? 0.5);
    const aggr = Number(this.coach.adjust_willingness ?? 0.5);
    const trends = AD.detect(this.mem, skill);
    const ctr = AD.respond(trends, skill, aggr, rng ?? new RNG(Math.random() * 2 ** 32));
    if (!ctr) return [];
    const [plan, applied] = GP.adjustPlan(this.plan, ctr, skill, 0.55, quarter);
    this.plan = plan;
    if (applied.length) this.lastAdjustment = ctr;
    return applied;
  }

  /** Recovery, sharpness and jadedness roll forward between games. */
  endGame(_rng: RNG, expectedSnaps = 45.0, bye = false): void {
    this.lastSnaps = { ...this.snaps };     // keep the game log readable
    for (const [pid, n] of Object.entries(this.snaps)) {
      this.sharp[pid] = H.updateSharpness(this.sharp[pid] ?? 100.0, n, expectedSnaps);
      this.jaded[pid] = H.updateJadedness(this.jaded[pid] ?? 0.0, n, 70.0,
                                          expectedSnaps, bye);
    }
    this.cond.resetGame();
    this.snaps = {};
    this.injuries = [];
  }
}

// ============================================================ FIELDING A SNAP
export const POS_KEY: Record<string, string> = {
  WR: 'wr', TE: 'wr', HB: 'wr', CB: 'db', FS: 'db', SS: 'db', LB: 'lb', DL: 'dl',
};

/**
 * Which men the PACKAGE puts on the field. This is the piece fatigue alone
 * cannot produce: five DBs play every snap in nickel, so without packages the
 * top five are permanently starters and the sixth never appears.
 */
export function packageUnits(
  roster: Roster, _state: TeamState | null, _rng: RNG,
  isOffense: boolean, pkg: string,
): Record<string, Player[]> | null {
  const spec = (isOffense ? (TG.OFF_PACKAGES as any) : (TG.DEF_PACKAGES as any))[pkg];
  if (!spec) return null;
  const out: Record<string, Player[]> = {};
  if (isOffense) {
    const pool = [...(roster.wr ?? [])];
    const wrs = pool.filter(p => p.pos === 'WR');
    const tes = [...pool.filter(p => p.pos === 'TE'),
                 ...(roster.extra_blockers ?? []).filter(p => p.pos === 'TE')];
    const hbsRaw = pool.filter(p => p.pos === 'HB' || p.pos === 'RB' || p.pos === 'FB');
    const hbs = hbsRaw.length ? hbsRaw : (roster.rb ? [roster.rb] : []);
    const chosen = [...wrs.slice(0, spec.WR ?? 3), ...tes.slice(0, spec.TE ?? 1),
                    ...hbs.slice(0, Math.max(0, (spec.HB ?? 1) - 1))];
    out['wr'] = chosen.length ? chosen : pool.slice(0, 3);
  } else {
    const db = [...(roster.db ?? [])];
    const cbs = db.filter(d => d.pos === 'CB');
    const saf = db.filter(d => d.pos === 'FS' || d.pos === 'SS');
    out['db'] = [...cbs.slice(0, spec.CB ?? 3),
                 ...saf.slice(0, (spec.FS ?? 1) + (spec.SS ?? 1))];
    out['lb'] = [...(roster.lb ?? [])].slice(0, spec.LB ?? 2);
    out['dl'] = [...(roster.dl ?? [])].slice(0, spec.DL ?? 4);
  }
  return out;
}

/**
 * Put eleven men on the field for this snap, honouring condition and injuries.
 * Anyone not selected recovers. This is where rotation actually happens - the
 * depth chart is walked until someone is fresh enough.
 */
export function fieldUnits(
  roster: Roster, state: TeamState | null, rng: RNG,
  isOffense: boolean, pkg?: string,
): [any, Record<string, string>] {
  if (state === null) return [roster, {}];
  // the package decides WHO is eligible this snap; condition then decides
  // which of them actually goes
  const pk = pkg ? packageUnits(roster, state, rng, isOffense, pkg) : null;
  let rost: Roster = roster;
  if (pk) rost = { ...roster, ...pk };

  const out: any = { ...rost };
  const positions: Record<string, string> = {};
  const slots = isOffense ? OFF_SLOTS : DEF_SLOTS;

  if (isOffense) {
    for (const key of ['qb', 'rb'] as const) {
      if (rost[key] === undefined || rost[key] === null) continue;
      const pos = key === 'qb' ? 'QB' : 'HB';
      let p = rost[key] as Player;
      // an injured starter yields to the backup - real leagues carry ~2.4 QBs
      // taking meaningful snaps, which is most of why the real QB15-to-QB25
      // distribution falls off a cliff
      if (key === 'qb' && state.out.has(p.pid)) {
        const bench = rost.qbs ?? [];
        const alt = bench.find(q => !state.out.has(q.pid));
        if (alt !== undefined) p = alt;
      }
      state.snap(p, pos, true);
      out[key] = state.state(p, pos);
      positions[p.pid] = pos;
    }
  }

  for (const [key, poslist] of slots) {
    const group = (rost[key] as Player[] | undefined) ?? [];
    if (!group.length) continue;
    // Walk the depth chart IN ORDER, skipping men who need rest and men
    // already on the field for another slot. Rotating the list per slot - what
    // the first build did - gave every player a turn as the starter and
    // produced a completely flat snap distribution.
    const avail = state.available(group, poslist[0]);
    const used = new Set<string>();
    const chosen: Player[] = [];
    for (const pos of poslist.slice(0, Math.min(poslist.length, avail.length))) {
      let pickd: Player | null = null;
      for (let rank = 0; rank < avail.length; rank++) {
        const p = avail[rank];
        if (used.has(p.pid)) continue;
        const gap = rank < poslist.length ? 0.6 : 0.0;
        if (!state.cond.needsRest(p.pid, pos, rng,
                                  Number(p.stamina_rating ?? 70.0), gap)) {
          pickd = p; break;
        }
      }
      if (pickd === null) {
        pickd = avail.find(p => !used.has(p.pid)) ?? avail[avail.length - 1];
      }
      used.add(pickd.pid);
      state.snap(pickd, pos, true);
      chosen.push(state.state(pickd, pos));
      positions[pickd.pid] = pos;
    }
    for (const p of group) {
      if (!used.has(p.pid)) state.snap(p, poslist[0], false);
    }
    out[key] = chosen;
  }
  return [out, positions];
}

// ============================================================ THE DRIVE LOOP
export interface DriveDeps {
  resolveFn: (off: any, deff: any, oc: any, dc: any, ytg: number, rng: RNG) => any;
  callOff: (down: number, ydstogo: number, sd: number, ytg: number, rng: RNG) => any;
  callDef: (oc: any, down: number, ydstogo: number, rng: RNG, ytg?: number) => any;
}

/**
 * Play a full possession. resolveFn is plays.resolvePlay; callOff and callDef
 * are the scheme-layer callers.
 */
export function runDrive(
  offense: Roster, defense: Roster, startYardline: number, clock: number,
  quarter: number, scoreDiff: number, rng: RNG, deps: DriveDeps,
  aggression = 0.5, book: { record: (out: any, off: any, deff: any, rng: RNG) => void } | null = null,
  offState: TeamState | null = null, defState: TeamState | null = null,
  week = 1,
): Drive {
  const { resolveFn, callOff, callDef } = deps;
  const dr = new Drive(offense, defense, startYardline, clock, quarter, scoreDiff);
  // Adjustment happens AFTER EACH SERIES, which is what the coaches describe:
  // "If you wait until halftime to make your adjustments, you're too late."
  for (const st of [offState, defState]) {
    if (st === null) continue;
    st.newSeries();
    // Adjustment is considered every series but does not fire every series.
    // Calling it unconditionally on ~11 drives produced 5.56 plan changes per
    // team per game against the ~3 the standalone calibration targeted.
    if (Math.random() < 0.55) st.adjust(quarter);
  }

  while (dr.result === null) {
    if (dr.clock <= 0) { dr.result = 'End of half'; break; }
    if (dr.plays > 25) { dr.result = 'End of half'; break; }

    // ---- fourth down is a decision, not a play ----
    if (dr.down === 4) {
      const dec = fourthDownDecision(dr.yardline, dr.togo, dr.scoreDiff,
                                     dr.clock, rng, aggression);
      if (dec === 'field_goal') {
        const fg = attemptFieldGoal(dr.yardline, offense.k as Player, rng);
        dr.clock -= playSeconds('field_goal');
        dr.result = fg.made ? 'Field goal' : 'Missed field goal';
        dr.points = fg.points; dr.log.push(fg); break;
      }
      if (dec === 'punt') {
        const p = punt(dr.yardline, offense.p as Player, defense.kr as Player, rng);
        dr.clock -= playSeconds('punt');
        dr.result = 'Punt'; dr.log.push(p);
        dr.nextYardline = p.newYardline; break;
      }
    }

    // ---- a real play ----
    // Pass the REAL down. The first build sent down=1 on fourth down, so a team
    // going for it on 4th-and-8 called a first-down run and failed, putting
    // turnovers on downs at 21.6% against a real 5.6%.
    // yardsToEndzone must never round DOWN to zero. The first build passed
    // int(yardline), so a ball at the 0.4 gave the resolver a zero-yard field,
    // every gain capped at 0.0, and the offence physically could not score -
    // touchdowns came out at 2.1% against a real 22.6%.
    const ytgI = Math.max(1, Math.ceil(dr.yardline));
    const togoI = Math.max(1, Math.ceil(dr.togo));
    const oc = callOff(dr.down, togoI, dr.scoreDiff, ytgI, rng);
    const dc = callDef(oc, dr.down, togoI, rng, ytgI);

    // The opener. A situation - usually third down - forces him off it.
    let scriptMod = 1.0;
    if (offState !== null) {
      offState.script.nextCall(dr.down, Math.trunc(dr.togo), rng);
      scriptMod = offState.script.performanceModifier();
    }

    // Overlay the gameplans. Everything downstream reads THE PLAN, so an
    // adjustment made three series ago is still in force now.
    if (offState !== null && offState.plan !== null) {
      const pl = offState.plan;
      oc.personnel = GP.personnel(pl, rng);
      oc.plan = pl;
      oc.travelWillingness = Number(offState.coach.travel_willingness ?? 0.5);
      if (oc.isPass) {
        oc.depth = GP.depth(pl, rng);
      } else {
        oc.scheme = GP.runFamily(pl, rng) === 'zone' ? 'inside_zone' : 'power';
      }

      // THE CHEATER PLAY. An adjustment vacates something, and that something
      // is the answer: "once a cheater play is used to reset the defense, the
      // play-caller can revert back". Anticipating the adjustment rather than
      // merely identifying it is what separates callers, so this is gated on
      // the caller's skill.
      const their = defState !== null ? defState.lastAdjustment : null;
      const ch = AD.cheaterAvailable(their);
      if (ch && rng.next() < 0.20 + 0.55 * Number(offState.coach.adjust_skill ?? 0.5)) {
        if (ch.call === 'run') {
          oc.isPass = false; oc.scheme = 'inside_zone';
        } else if (ch.call === 'deep') {
          oc.isPass = true; oc.depth = 'deep'; oc.concept = 'four_verts';
        } else if (ch.call === 'play_action') {
          oc.isPass = true; oc.playAction = true; oc.depth = 'medium';
        } else if (ch.call === 'other_target') {
          oc.avoid_bracket = true;
        }
        oc.cheater = ch.call;
        dr.cheaters = [...(dr.cheaters ?? []), ch.call];
        if (defState !== null) defState.lastAdjustment = null;   // the reset
      }
    }
    if (defState !== null && defState.plan !== null) {
      const dp = defState.plan;
      dc.shell = GP.shell(dp, rng);
      dc.man = GP.isMan(dp, rng);
      dc.blitzers = GP.blitzers(dp, rng, dr.down, Math.trunc(dr.togo));
      dc.rushers = 4 + dc.blitzers;
      dc.box = clip((dc.box ?? 6) + AD.pyRound(dp.boxBias * 4), 4, 10);
      if (dp.frontPref.length) dc.front = dp.frontPref[0];
      dc.bracket = dp.bracket;
      dc.travel = dp.travel;
    }

    // penalties resolve before the snap can count
    const pen = E.penaltyCheck(rng, { isPass: oc.isPass });
    if (pen && pen.nullifies) {
      dr.clock -= playSeconds('penalty');
      if (pen.onOffense) {
        dr.yardline = Math.min(99, dr.yardline + pen.yards);
        dr.togo += pen.yards;
      } else {
        const gained = Math.min(pen.yards, dr.yardline - 1);
        if (pen.autoFirst) {
          dr.yardline -= gained;
          dr.down = 1; dr.togo = Math.min(10, dr.yardline); dr.firstDowns++;
        } else {
          dr.yardline -= gained; dr.togo -= gained;
          if (dr.togo <= 0) {
            dr.down = 1; dr.togo = Math.min(10, dr.yardline); dr.firstDowns++;
          }
        }
      }
      dr.log.push({ type: 'penalty', ...pen });
      continue;
    }

    // field the units for THIS snap - condition, injuries and rotation
    let [offF] = fieldUnits(offense, offState, rng, true, oc.personnel);
    const [defF, defPos] = fieldUnits(defense, defState, rng, false, dc.personnel);

    // the back who actually carries it
    if (!oc.isPass) {
      const backs = (offense.backs ?? (offense.rb ? [offense.rb] : []))
        .filter(Boolean) as Player[];
      const rb = pickRunner(backs, offState ? offState.out : null,
                            offState ? (pid: string) => offState.cond.get(pid) : null,
                            rng);
      if (rb !== null) offF = { ...offF, rb };
    }

    let out = resolveFn(offF, defF, oc, dc, ytgI, rng);
    if (scriptMod !== 1.0 && out.yards) {
      out.yards = +(out.yards * scriptMod).toFixed(1);
    }
    dr.plays++;
    dr.log.push(out);
    if (book !== null) book.record(out, offF, defF, rng);
    for (const st of [offState, defState]) {
      if (st !== null) st.observe(oc, dc, out);
    }

    // injuries attach to contact events
    if (offState !== null
        && ['run', 'complete', 'sack', 'scramble'].includes(out.type)) {
      const contact = (out.type === 'run' || out.type === 'sack') ? 0.9 : 0.7;
      // the man who actually took the snap, not the depth-chart starter
      const carrier = (out.type === 'sack' || out.type === 'scramble') ? offF.qb
        : out.type === 'run' ? offF.rb : offF.wr[0];
      const cpos = (out.type === 'sack' || out.type === 'scramble') ? 'QB'
        : out.type === 'run' ? 'HB' : 'WR';
      offState.hurt(carrier, cpos, contact, rng, week);
    }
    if (defState !== null && (out.type === 'run' || out.type === 'complete')) {
      const pool = [...defF.db, ...defF.lb, ...defF.dl];
      const d = pool[rng.integers(0, pool.length)];
      defState.hurt(d, defPos[d.pid] ?? 'CB', 0.8, rng, week);
    }

    let t = out.type;
    // a collapsed pocket is not automatically a sack - a mobile QB runs
    if (t === 'sack') {
      if (rng.next() < E.scrambleChance(offense.qb, 1.0, 1.4)) {
        out = E.resolveScramble(offense.qb, ytgI, rng);
        t = 'scramble'; dr.log[dr.log.length - 1] = out;
      }
    }

    if (t === 'interception') {
      dr.clock -= playSeconds('interception'); dr.result = 'Turnover'; break;
    }

    // fumbles attach to the event that produced them
    const ev = ({ complete: 'complete_pass', run: 'run', sack: 'sack',
                  scramble: 'scramble' } as any)[t];
    if (ev) {
      const carrier = (ev === 'sack' || ev === 'scramble') ? offense.qb
        : ev === 'run' ? (offense.rb as Player) : offense.wr[0];
      const fum = E.fumbleCheck(carrier, ev, rng);
      if (fum && fum.lost) {
        dr.clock -= playSeconds('fumble'); dr.result = 'Turnover'; break;
      }
    }

    dr.clock -= playSeconds(t, false, dr.clock < 120 && dr.scoreDiff < 0);
    const scored = advance(dr, out.yards ?? 0.0);
    if (scored) break;
    if (dr.down > 4) { dr.result = 'Turnover on downs'; break; }
  }

  if (dr.result === null) dr.result = 'End of half';

  // ---- the try, once the touchdown is on the board ----
  if (dr.result === 'Touchdown') {
    const t = twoPointDecision(dr.scoreDiff + 6, dr.quarter)
      ? attemptTwoPoint(offense, defense, rng, resolveFn, deps.callOff,
                        deps.callDef, offState, defState)
      : attemptExtraPoint(offense.k, rng);
    dr.points += t.points;
    dr.tryResult = t;
    dr.log.push(t);
  }
  return dr;
}

/**
 * 2026 NFL overtime (Rule 16).
 *
 *   - one 10-minute period in the regular season; 15-minute periods in the
 *     postseason, repeated until someone wins
 *   - BOTH teams get an opening opportunity to possess, even if the first team
 *     scores a touchdown. This changed in 2025; before that an opening TD
 *     ended it.
 *   - after both opportunities, a lead wins; still tied and time remaining
 *     means sudden death
 *   - the regular-season period does NOT extend to let the second team finish,
 *     so the clock can expire before it even possesses
 *   - a safety by the KICKING team on the receiving team's initial possession
 *     ends the game immediately
 *   - the regular season can end in a tie. Real rate: 0.29% of games. Overtime
 *     itself is reached in 6.2% of games.
 */
export function playOvertime(
  home: Roster, away: Roster, score: { home: number; away: number },
  rng: RNG, deps: DriveDeps,
  homeState: TeamState | null = null, awayState: TeamState | null = null,
  week = 1, playoffs = false, first: 'home' | 'away' = 'away',
): [{ home: number; away: number }, Array<[string, Drive]>, string] {
  let clock = playoffs ? OT_PLAYOFF_LENGTH : OT_LENGTH;
  let pos: 'home' | 'away' = first;
  const had = { home: false, away: false };
  const drives: Array<[string, Drive]> = [];
  let start = kickoff((pos === 'away' ? home : away).kr as Player, rng).newYardline;

  while (clock > 0) {
    const off = pos === 'home' ? home : away;
    const deff = pos === 'home' ? away : home;
    const oSt = pos === 'home' ? homeState : awayState;
    const dSt = pos === 'home' ? awayState : homeState;
    const other: 'home' | 'away' = pos === 'home' ? 'away' : 'home';
    const sd = score[pos] - score[other];

    // Overtime is played with maximum aggression - nobody protects a lead,
    // everyone goes for it on fourth down. Ties are real but rare: 0.29% of
    // all games, roughly 1 in 20 overtimes.
    const dr = runDrive(off, deff, start, clock, 5, sd, rng, deps, 0.98,
                        null, oSt, dSt, week);
    drives.push([pos, dr]);
    clock = Math.max(0.0, dr.clock);
    had[pos] = true;

    if (dr.points > 0) {
      score[pos] += dr.points;
    } else if (dr.points < 0) {
      // a safety by the kicking team on the receiving team's FIRST possession
      // ends it immediately - the one exception to both teams getting the ball
      score[other] += 2;
      if (!had[other]) return [score, drives, 'safety_walkoff'];
    }

    // both have possessed: a lead wins, otherwise sudden death
    if (had.home && had.away && score.home !== score.away) {
      return [score, drives, 'decided'];
    }

    if (dr.result === 'Touchdown' || dr.result === 'Field goal') {
      start = kickoff(deff.kr as Player, rng).newYardline;
    } else if (dr.result === 'Punt') {
      start = dr.nextYardline ?? 75;
    } else if (dr.result === 'Turnover' || dr.result === 'Turnover on downs') {
      start = clip(100 - dr.yardline, 1, 99);
    } else {
      start = 75;
    }
    pos = other;
  }

  if (playoffs) {                    // the postseason never ties
    return playOvertime(home, away, score, rng, deps, homeState, awayState,
                        week, true, first);
  }
  return [score, drives, score.home === score.away ? 'tie' : 'decided'];
}

export interface GameResult {
  home: number; away: number;
  drives: Array<[string, Drive]>;
  injuries: H.Injury[];
  overtime: string | null;
}

/** A full 60-minute game. Returns the score and every drive. */
export function playGame(
  home: Roster, away: Roster, rng: RNG, deps: DriveDeps,
  opts: {
    homeAggr?: number; awayAggr?: number;
    book?: { record: (out: any, off: any, deff: any, rng: RNG) => void } | null;
    homeState?: TeamState | null; awayState?: TeamState | null;
    week?: number; playoffs?: boolean;
  } = {},
): GameResult {
  const { homeAggr = 0.5, awayAggr = 0.5, book = null,
          homeState = null, awayState = null, week = 1, playoffs = false } = opts;
  let score = { home: 0, away: 0 };
  const drives: Array<[string, Drive]> = [];
  let clock = GAME, quarter = 1;
  let pos: 'home' | 'away' = 'away';           // away receives first
  let start = kickoff(home.kr as Player, rng).newYardline;
  let drSnaps: number | null = null;

  while (clock > 0) {
    const off = pos === 'home' ? home : away;
    const deff = pos === 'home' ? away : home;
    const other: 'home' | 'away' = pos === 'home' ? 'away' : 'home';
    const sd = score[pos] - score[other];
    const aggr = pos === 'home' ? homeAggr : awayAggr;

    const oSt = pos === 'home' ? homeState : awayState;
    const dSt = pos === 'home' ? awayState : homeState;
    // the unit that just came off recovers while the other side plays
    if (dSt !== null) dSt.sidelineRecovery(drSnaps ?? 30);
    const dr = runDrive(off, deff, start, clock, quarter, sd, rng, deps, aggr,
                        book, oSt, dSt, week);
    drSnaps = dr.plays;
    if (oSt !== null) oSt.sidelineRecovery(dr.plays);
    drives.push([pos, dr]);
    clock = Math.max(0.0, dr.clock);
    quarter = Math.min(4, Math.floor((GAME - clock) / QUARTER) + 1);

    if (dr.points > 0) score[pos] += dr.points;
    else if (dr.points < 0) score[other] += 2;

    // where the next possession starts
    if (dr.result === 'Touchdown' || dr.result === 'Field goal') {
      start = kickoff(deff.kr as Player, rng).newYardline;
    } else if (dr.result === 'Punt') {
      start = dr.nextYardline ?? 75;
    } else if (dr.result === 'Turnover' || dr.result === 'Turnover on downs') {
      start = clip(100 - dr.yardline, 1, 99);
    } else if (dr.result === 'Missed field goal') {
      start = clip(100 - dr.yardline - 8, 1, 99);
    } else {
      start = 75;
    }
    pos = other;
  }

  // overtime
  let ot: string | null = null;
  if (score.home === score.away) {
    const first: 'home' | 'away' = rng.next() < 0.5 ? 'away' : 'home';
    const [s2, otDrives, res] = playOvertime(home, away, score, rng, deps,
                                             homeState, awayState, week,
                                             playoffs, first);
    score = s2; ot = res;
    drives.push(...otDrives);
  }

  const inj: H.Injury[] = [];
  for (const st of [homeState, awayState]) {
    if (st !== null) { inj.push(...st.injuries); st.endGame(rng); }
  }
  return { home: score.home, away: score.away, drives, injuries: inj, overtime: ot };
}

// ============================================================ STAT ATTRIBUTION
// Every play already names its contributors, so accumulation is nearly free.
export interface StatLine {
  pass_att: number; pass_cmp: number; pass_yds: number; pass_td: number;
  ints: number; sacked: number;
  rush_att: number; rush_yds: number; rush_td: number;
  tgt: number; rec: number; rec_yds: number; rec_td: number; drops: number;
  tackles: number; sacks: number; int_def: number; pressures: number; ff: number;
  fum: number; fum_lost: number;
}

/** Accumulates individual lines across plays, games and a season. */
export class StatBook {
  p: Record<string, StatLine> = {};

  private get(pid: string): StatLine {
    let s = this.p[pid];
    if (!s) {
      s = {
        pass_att: 0, pass_cmp: 0, pass_yds: 0, pass_td: 0, ints: 0, sacked: 0,
        rush_att: 0, rush_yds: 0, rush_td: 0,
        tgt: 0, rec: 0, rec_yds: 0, rec_td: 0, drops: 0,
        tackles: 0, sacks: 0, int_def: 0, pressures: 0, ff: 0,
        fum: 0, fum_lost: 0,
      };
      this.p[pid] = s;
    }
    return s;
  }

  record(out: any, off: any, deff: any, rng: RNG): void {
    const t = out.type;
    const qb = off.qb?.pid ?? 'QB';
    if (t === 'complete' || t === 'incomplete' || t === 'drop' || t === 'interception') {
      const s = this.get(qb); s.pass_att++;
      const wr = out.target ?? off.wr[0]?.pid ?? 'WR1';
      const w = this.get(wr); w.tgt++;
      if (t === 'complete') {
        s.pass_cmp++; s.pass_yds += out.yards;
        w.rec++; w.rec_yds += out.yards;
        if (out.touchdown) { s.pass_td++; w.rec_td++; }
      } else if (t === 'drop') {
        w.drops++;
      } else if (t === 'interception') {
        s.ints++;
        this.get(out.by ?? deff.db[0]?.pid ?? 'DB1').int_def++;
      }
    } else if (t === 'sack') {
      this.get(qb).sacked++;
      const d = this.get(out.by ?? deff.dl[0]?.pid ?? 'DL1');
      d.sacks += 1.0; d.tackles++;
    } else if (t === 'scramble') {
      const s = this.get(qb); s.rush_att++; s.rush_yds += out.yards;
      if (out.touchdown) s.rush_td++;
    } else if (t === 'run') {
      const s = this.get(off.rb?.pid ?? 'RB1');
      s.rush_att++; s.rush_yds += out.yards;
      if (out.touchdown) s.rush_td++;
    }
    // a tackle is credited on any play that ends in the field of play
    if ((t === 'run' || t === 'complete' || t === 'scramble') && !out.touchdown) {
      const pool = [...deff.db, ...deff.lb, ...deff.dl];
      const tk = pool[rng.integers(0, pool.length)];
      this.get(tk?.pid ?? 'D?').tackles++;
    }
  }
}
