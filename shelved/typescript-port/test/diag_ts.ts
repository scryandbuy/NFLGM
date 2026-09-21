import { readFileSync } from 'fs';
import { RNG } from '../src/core/rng.js';
import { clip } from '../src/core/math.js';
import * as G from '../src/game.js';
import * as P from '../src/plays.js';
import * as S from '../src/schemes.js';
import { loadLeague } from '../src/rosters.js';

const ref = JSON.parse(readFileSync('/tmp/diag_py.json', 'utf8'));
const rng = new RNG(2026);
const L = loadLeague('/home/claude/data/league_seed_2026.csv');
const teams = Object.keys(L).sort();
const deps: G.DriveDeps = {
  resolveFn: (off, deff, oc, dc, ytg, r) => P.resolvePlay(off, deff, oc, dc, ytg, r),
  callOff: (d, di, sd, ytg, r) => S.callOffense(d, di, sd, ytg, r),
  callDef: (oc, d, di, r, ytg = 50) => S.callDefense(oc, d, di, r, undefined, ytg),
};
const coaches: Record<string, any> = {};
for (const t of teams) coaches[t] = {
  adjust_skill: clip(rng.normal(.55, .18), .1, .95),
  adjust_willingness: clip(rng.normal(.55, .2), .1, .95),
  man_rate: clip(rng.normal(.35, .12), .12, .62),
  blitz_rate: clip(rng.normal(.133, .05), .05, .28),
  travel_willingness: clip(rng.normal(.5, .22), .05, .95),
  off_script_skill: clip(rng.normal(.5, .2), .1, .9),
};
const pts: number[] = [];
const byteam: Record<string, number[]> = {};
let fgatt = 0, fgmade = 0;
const res: Record<string, number> = {};
for (let s = 0; s < 2; s++) {
  const ST: Record<string, G.TeamState> = {};
  for (const t of teams) ST[t] = new G.TeamState(L[t], 0.5, null, coaches[t]);
  for (let wk = 0; wk < 17; wk++) {
    const o = rng.shuffle([...teams]);
    for (let i = 0; i < 32; i += 2) {
      const h = o[i], a = o[i + 1];
      const r = G.playGame(L[h], L[a], rng, deps,
                           { homeState: ST[h], awayState: ST[a], week: wk + 1 });
      pts.push(r.home, r.away);
      (byteam[h] ??= []).push(r.home); (byteam[a] ??= []).push(r.away);
      for (const [, d] of r.drives) {
        res[d.result!] = (res[d.result!] ?? 0) + 1;
        for (const l of d.log) {
          if (l && l.type === 'field_goal') { fgatt++; if (l.made) fgmade++; }
        }
      }
    }
  }
}
const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length;
const sd = (a: number[]) => { const m = mean(a); return Math.sqrt(mean(a.map(x => (x - m) ** 2))); };
const tm = Object.fromEntries(Object.entries(byteam).map(([t, v]) => [t, +mean(v).toFixed(2)]));
const tms = Object.values(tm);
const got = {
  pts_mean: +mean(pts).toFixed(3), pts_sd: +sd(pts).toFixed(3),
  team_mean_sd: +sd(tms).toFixed(3),
  best: Math.max(...tms), worst: Math.min(...tms),
  fg_att_per_game: +(fgatt / 544).toFixed(3),
  fg_pct: +(100 * fgmade / Math.max(fgatt, 1)).toFixed(2),
};
console.log('  metric              ts        py      diff');
for (const k of Object.keys(got) as Array<keyof typeof got>) {
  const d = (got[k] as number) - ref[k];
  console.log(`  ${String(k).padEnd(16)} ${String(got[k]).padStart(8)}  ${String(ref[k]).padStart(8)}  ${(d >= 0 ? '+' : '') + d.toFixed(3)}`);
}
console.log('\n  drive result          ts        py');
for (const k of Object.keys(ref.results)) {
  console.log(`  ${k.padEnd(20)} ${String(res[k] ?? 0).padStart(6)}  ${String(ref.results[k]).padStart(6)}`);
}
