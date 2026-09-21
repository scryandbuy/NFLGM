import { readFileSync } from 'fs';
import * as G from '../src/game.js';
import { OFF_PACKAGES, DEF_PACKAGES } from '../src/tables.js';
import { RNG } from '../src/core/rng.js';
import { Player } from '../src/core/math.js';

const ref = JSON.parse(readFileSync('/tmp/state_py.json', 'utf8'));
const rost = JSON.parse(readFileSync('/tmp/roster_fixture.json', 'utf8')) as G.Roster;
let fails = 0;
const bad = (m: string) => { fails++; if (fails <= 10) console.log('FAIL ' + m); };
function canon(v: any): any {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const o: any = {}; for (const k of Object.keys(v).sort()) o[k] = canon(v[k]); return o;
  }
  return v;
}
const eq = (a: unknown, b: unknown) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
const r10 = (x: number) => +x.toFixed(10);
const rng0 = new RNG(1);

// ---- packageUnits ----
for (const [side, pkg, want] of ref.package as any[]) {
  const r = G.packageUnits(rost, null, rng0, side === 'off', pkg);
  const got = r === null ? null
    : Object.fromEntries(Object.entries(r).map(([k, v]) => [k, v.map(p => p.pid)]));
  if (!eq(got, want)) bad(`packageUnits ${side} ${pkg}\n  got  ${JSON.stringify(canon(got))}\n  want ${JSON.stringify(canon(want))}`);
}
console.log(`packageUnits: ${ref.package.length} cases`);

// ---- sidelineRecovery ----
for (const [snaps, want] of ref.sideline as any[]) {
  const st = new G.TeamState(rost);
  st.cond.cond = { a: 20.0, b: 55.0, c: 99.0 };
  st.sidelineRecovery(snaps);
  const got: Record<string, number> = {};
  for (const k of Object.keys(st.cond.cond).sort()) got[k] = r10(st.cond.cond[k]);
  if (!eq(got, want)) bad(`sidelineRecovery ${snaps}\n  got  ${JSON.stringify(got)}\n  want ${JSON.stringify(want)}`);
}
console.log(`sidelineRecovery: ${ref.sideline.length} cases`);

// ---- endGame ----
for (const [snaps, wSharp, wJaded] of ref.endgame as any[]) {
  const st = new G.TeamState(rost);
  st.snaps = { a: snaps, b: Math.trunc(snaps / 2) };
  st.sharp = { a: 88.0 };
  st.jaded = { b: 0.3 };
  st.endGame(rng0, 45.0, false);
  const gs: Record<string, number> = {}, gj: Record<string, number> = {};
  for (const k of Object.keys(st.sharp).sort()) gs[k] = r10(st.sharp[k]);
  for (const k of Object.keys(st.jaded).sort()) gj[k] = r10(st.jaded[k]);
  if (!eq(gs, wSharp)) bad(`endGame sharp ${snaps}\n  got ${JSON.stringify(gs)} want ${JSON.stringify(wSharp)}`);
  if (!eq(gj, wJaded)) bad(`endGame jaded ${snaps}\n  got ${JSON.stringify(gj)} want ${JSON.stringify(wJaded)}`);
}
console.log(`endGame: ${ref.endgame.length} cases`);

// ---- available ----
{
  const ol = rost.ol as Player[];
  const st = new G.TeamState(rost);
  st.out = new Set([ol[0].pid, ol[2].pid]);
  if (!eq([st.available(ol, 'LT').map(p => p.pid)], ref.available[0])) bad('available partial');
  st.out = new Set(ol.map(p => p.pid));
  if (!eq([st.available(ol, 'LT').map(p => p.pid)], ref.available[1])) bad('available all-out');
  console.log('available: 2 cases');
}

// ---- fieldUnits snap share ----
function sweep(isOff: boolean, packages: string[], want: any, label: string) {
  const rng = new RNG(31);
  const st = new G.TeamState(rost, 0.5, null, {});
  const N = want.n as number;
  for (let i = 0; i < N; i++) {
    G.fieldUnits(rost, st, rng, isOff, packages[i % packages.length]);
    if (i % 2 === 0) st.sidelineRecovery(6);
  }
  const share: Array<[string, number]> = Object.entries(st.snaps)
    .map(([k, v]) => [k, +(v / N).toFixed(4)] as [string, number])
    .sort((a, b) => b[1] - a[1]);
  const conds = Object.values(st.cond.cond);
  const meanCond = conds.reduce((s, x) => s + x, 0) / (conds.length || 1);
  console.log(`\n  ${label}: distinct ts ${Object.keys(st.snaps).length} / py ${want.distinct}, mean condition ts ${meanCond.toFixed(3)} / py ${want.mean_cond}`);
  if (Object.keys(st.snaps).length !== want.distinct) bad(`${label} distinct players`);
  if (Math.abs(meanCond - want.mean_cond) > 3.0) bad(`${label} mean condition`);
  const wantMap = new Map<string, number>(want.top);
  console.log('    pid            ts      py     diff');
  for (const [pid, w] of want.top as Array<[string, number]>) {
    const g = share.find(s => s[0] === pid)?.[1] ?? 0;
    const d = g - w;
    const off_ = Math.abs(d) > 0.030;
    if (off_) bad(`${label} share ${pid}`);
    console.log(`    ${pid.padEnd(12)} ${g.toFixed(4)}  ${w.toFixed(4)}  ${(d >= 0 ? '+' : '') + d.toFixed(4)}${off_ ? '  OFF' : ''}`);
  }
  void wantMap;
}
sweep(true, ['11', '12', '10', '21', '13'], ref.snapshare_off, 'offence');
sweep(false, ['base', 'nickel', 'dime'], ref.snapshare_def, 'defence');

console.log(fails === 0 ? '\nALL MATCH' : `\n${fails} FAILURES`);
