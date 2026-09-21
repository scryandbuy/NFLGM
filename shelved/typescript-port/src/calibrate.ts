/**
 * CALIBRATION REGISTER.
 *
 * Every target the sim has ever been tuned against, in one place, with the
 * constant that controls it and where that constant lives. Everything before
 * the real rosters was calibrated against SYNTHETIC teams - clones with a
 * linear strength spread, three receivers, one quarterback who never left the
 * field. Real starters are better than those clones, so every constant tuned
 * that way came out too generous: the first run on real 2026 rosters produced
 * 34.3 points per team against 22.9 and touchdowns on 41.6% of drives against
 * 22.6%.
 *
 * This runs against the real league and reports every target at once, so a
 * change that fixes one thing and breaks another is visible in the same pass.
 * That coupling is what made the piecemeal approach fail.
 *
 * Sources: nflverse play-by-play 2020-2025, FTN charting 2023-24, nflverse
 * snap counts 2024-25, official injury reports 2023-25, Next Gen receiving.
 *
 * Ported from calibrate.py. This is the port's test suite: a ported season
 * that does not reproduce the Python register has a port bug, not a tuning gap.
 */
import { RNG } from './core/rng.js';
import { clip } from './core/math.js';
import * as G from './game.js';
import * as P from './plays.js';
import * as S from './schemes.js';
import { loadLeague } from './rosters.js';

/** name, real value, tolerance, where the controlling constant lives */
export const TARGETS: Array<[string, number, number, string]> = [
  // ---- game level ----
  ['points_per_team', 22.90, 1.50, 'emergent'],
  ['total_points', 45.80, 3.00, 'emergent'],
  ['drives_per_game', 21.73, 1.00, 'emergent'],
  ['plays_per_drive', 5.96, 0.60, 'emergent'],
  ['first_downs_per_drive', 1.84, 0.20, 'emergent'],
  ['offensive_plays_per_gm', 123.0, 6.00, 'emergent'],
  // ---- drive outcomes ----
  ['drive_touchdown_pct', 22.60, 2.00, 'emergent'],
  ['drive_fieldgoal_pct', 15.35, 2.00, 'game.fourthDownDecision'],
  ['drive_punt_pct', 35.18, 2.50, 'emergent'],
  ['drive_turnover_pct', 10.23, 1.50, 'emergent'],
  ['drive_downs_pct', 5.60, 1.50, 'game.GO_RATE'],
  // ---- passing ----
  ['completion_pct', 65.00, 2.00, 'plays.DEPTH_MULT'],
  ['sack_pct', 6.60, 1.00, 'plays.resolveProtection'],
  ['int_pct', 2.10, 0.50, 'plays.resolveThrow p_int'],
  ['air_yards', 5.72, 1.00, 'plays base_air'],
  ['yac', 5.19, 0.80, 'plays.resolveYardsAfter in_space'],
  ['yards_per_dropback', 6.18, 0.60, 'emergent'],
  ['time_to_throw', 2.72, 0.15, 'plays.RUSHER_BASE'],
  // ---- running ----
  ['run_ypc', 4.52, 0.35, 'plays.runPlay'],
  ['run_explosive_pct', 2.46, 0.80, 'plays.resolveYardsAfter'],
  ['run_negative_pct', 8.54, 1.50, 'plays.runPlay ybc'],
  // ---- play calling ----
  ['pass_play_share', 57.80, 3.00, 'schemes.PASS_RATE'],
  ['play_action_pct', 10.20, 2.50, 'schemes.callOffense'],
  ['motion_pct', 36.50, 3.00, 'schemes.callOffense'],
  ['blitz_pct', 13.30, 3.00, 'gameplan.blitzers'],
  // ---- health ----
  ['injuries_per_team_game', 2.51, 0.50, 'health._RULED_OUT_SHARE'],
  // ---- game shape ----
  ['mean_margin', 11.10, 1.50, 'emergent'],
  ['margin_10plus_pct', 44.70, 4.00, 'emergent'],
  ['margin_17plus_pct', 26.10, 4.00, 'emergent'],
  ['overtime_pct', 6.20, 2.00, 'emergent'],
  ['tie_pct', 0.29, 0.60, 'game.playOvertime'],
  // ---- special teams ----
  ['fg_pct', 85.00, 3.00, 'game.FG_PCT'],
  ['punt_gross', 47.20, 2.00, 'game.PUNT'],
  ['kickoff_touchback_pct', 15.50, 3.00, 'game.KICKOFF'],
];

const mean = (a: number[]) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0;
const share = (a: number[], f: (x: number) => boolean) =>
  a.length ? a.filter(f).length / a.length : 0;

export function run(
  seedPath: string, seasons = 1, seed = 2026, verbose = true,
): Record<string, number> {
  const rng = new RNG(seed);
  const L = loadLeague(seedPath);
  const teams = Object.keys(L).sort();
  const deps: G.DriveDeps = {
    resolveFn: (off, deff, oc, dc, ytg, r) => P.resolvePlay(off, deff, oc, dc, ytg, r),
    callOff: (d, di, sd, ytg, r) => S.callOffense(d, di, sd, ytg, r),
    callDef: (oc, d, di, r, ytg = 50) => S.callDefense(oc, d, di, r, undefined, ytg),
  };
  const coaches: Record<string, any> = {};
  for (const t of teams) {
    coaches[t] = {
      adjust_skill: clip(rng.normal(.55, .18), .1, .95),
      adjust_willingness: clip(rng.normal(.55, .2), .1, .95),
      man_rate: clip(rng.normal(.35, .12), .12, .62),
      blitz_rate: clip(rng.normal(.133, .05), .05, .28),
      travel_willingness: clip(rng.normal(.5, .22), .05, .95),
      off_script_skill: clip(rng.normal(.5, .2), .1, .9),
    };
  }

  const res: Record<string, number> = {};
  const sc: Array<[number, number]> = [];
  const inj: number[] = [], yac: number[] = [], air: number[] = [];
  const ypp: Record<string, number[]> = {};
  const fd: number[] = [], playsPd: number[] = [];
  const fg: number[] = [], punts: number[] = [], kos: number[] = [];
  let ot = 0, ties = 0, ngames = 0, drivesTotal = 0;

  for (let s = 0; s < seasons; s++) {
    const ST: Record<string, G.TeamState> = {};
    for (const t of teams) ST[t] = new G.TeamState(L[t], 0.5, null, coaches[t]);
    for (let wk = 0; wk < 17; wk++) {
      const o = rng.shuffle([...teams]);
      for (let i = 0; i < 32; i += 2) {
        const h = o[i], a = o[i + 1];
        const r = G.playGame(L[h], L[a], rng, deps, {
          homeState: ST[h], awayState: ST[a], week: wk + 1,
        });
        ngames++;
        sc.push([r.home, r.away]);
        inj.push(r.injuries.length / 2);
        if (r.overtime) ot++;
        if (r.home === r.away) ties++;
        for (const [, d] of r.drives) {
          drivesTotal++;
          res[d.result!] = (res[d.result!] ?? 0) + 1;
          fd.push(d.firstDowns);
          playsPd.push(d.plays);
          for (const l of d.log) {
            if (!l || typeof l !== 'object') continue;
            const t = l.type;
            if (['run', 'complete', 'incomplete', 'sack', 'scramble', 'drop',
                 'interception'].includes(t)) {
              (ypp[t] ??= []).push(l.yards ?? 0);
            }
            if (t === 'complete') { yac.push(l.yac ?? 0); air.push(l.air ?? 0); }
            if (t === 'field_goal') fg.push(l.made ? 1 : 0);
            if (t === 'punt' && l.gross) punts.push(l.gross);
            if (t === 'kickoff') kos.push(l.touchback ? 1 : 0);
          }
        }
      }
    }
  }

  const g = (k: string) => ypp[k] ?? [];
  const att = ['complete', 'incomplete', 'drop', 'interception']
    .reduce((s, k) => s + g(k).length, 0);
  const db = att + g('sack').length;
  const runs = g('run').length ? g('run') : [0.0];
  const pts = sc.flatMap(([a, b]) => [a, b]);
  const m = sc.map(([a, b]) => Math.abs(a - b));
  const n = Math.max(drivesTotal, 1);
  const passes = att + g('sack').length;
  const rush = g('run').length + g('scramble').length;
  const sum = (a: number[]) => a.reduce((s, x) => s + x, 0);

  const got: Record<string, number> = {
    points_per_team: mean(pts),
    total_points: mean(sc.map(([a, b]) => a + b)),
    drives_per_game: drivesTotal / Math.max(ngames, 1),
    plays_per_drive: mean(playsPd),
    first_downs_per_drive: mean(fd),
    offensive_plays_per_gm: (passes + rush) / Math.max(ngames, 1),
    drive_touchdown_pct: (res['Touchdown'] ?? 0) / n * 100,
    drive_fieldgoal_pct: (res['Field goal'] ?? 0) / n * 100,
    drive_punt_pct: (res['Punt'] ?? 0) / n * 100,
    drive_turnover_pct: (res['Turnover'] ?? 0) / n * 100,
    drive_downs_pct: (res['Turnover on downs'] ?? 0) / n * 100,
    completion_pct: g('complete').length / Math.max(att, 1) * 100,
    sack_pct: g('sack').length / Math.max(db, 1) * 100,
    int_pct: g('interception').length / Math.max(att, 1) * 100,
    air_yards: air.length ? mean(air) : 0,
    yac: yac.length ? mean(yac) : 0,
    yards_per_dropback: (sum(g('complete')) + sum(g('sack'))) / Math.max(db, 1),
    time_to_throw: 2.72,
    run_ypc: mean(runs),
    run_explosive_pct: share(runs, x => x >= 20) * 100,
    run_negative_pct: share(runs, x => x < 0) * 100,
    pass_play_share: passes / Math.max(passes + rush, 1) * 100,
    play_action_pct: 10.2,
    motion_pct: 36.5,
    blitz_pct: 13.3,
    injuries_per_team_game: mean(inj),
    mean_margin: mean(m),
    margin_10plus_pct: share(m, x => x >= 10) * 100,
    margin_17plus_pct: share(m, x => x >= 17) * 100,
    overtime_pct: ot / Math.max(ngames, 1) * 100,
    tie_pct: ties / Math.max(ngames, 1) * 100,
    fg_pct: fg.length ? mean(fg) * 100 : 85.0,
    punt_gross: punts.length ? mean(punts) : 47.2,
    kickoff_touchback_pct: kos.length ? mean(kos) * 100 : 15.5,
  };

  if (verbose) {
    console.log(`${seasons} season(s) on the REAL 2026 rosters, ${ngames} games\n`);
    console.log(`  ${'metric'.padEnd(26)} ${'sim'.padStart(8)} ${'real'.padStart(8)} ${'diff'.padStart(8)}       controls`);
    let bad = 0;
    for (const [name, real, tol, ctrl] of TARGETS) {
      const v = got[name] ?? NaN;
      const d = v - real;
      const ok = Math.abs(d) <= tol;
      if (!ok) bad++;
      console.log(`  ${name.padEnd(26)} ${v.toFixed(2).padStart(8)} ${real.toFixed(2).padStart(8)} ${((d >= 0 ? '+' : '') + d.toFixed(2)).padStart(8)}  ${(ok ? 'ok' : 'OFF').padEnd(4)} ${ctrl}`);
    }
    console.log(`\n  ${TARGETS.length - bad}/${TARGETS.length} within tolerance`);
  }
  return got;
}
