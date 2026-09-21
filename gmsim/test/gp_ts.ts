import { readFileSync } from 'fs';
import { RNG } from '../src/core/rng.js';
import * as GP from '../src/gameplan.js';

const ref = JSON.parse(readFileSync('/tmp/gp_py.json', 'utf8'));
let fails = 0;
const bad = (m: string) => { fails++; if (fails <= 12) console.log('FAIL ' + m); };

function snap(g: GP.Gameplan) {
  const keys = Object.keys(g.shellWeights).sort();
  return {
    pass_bias: +g.passBias.toFixed(10), box_bias: +g.boxBias.toFixed(10),
    man_rate: +g.manRate.toFixed(10), blitz_rate: +g.blitzRate.toFixed(10),
    tempo: +g.tempo.toFixed(10), protection: g.protection,
    depth_mix: g.depthMix.map(x => +x.toFixed(10)),
    shell: keys.map(k => +g.shellWeights[k].toFixed(10)),
    shell_keys: keys, front: [...g.frontPref], travel: g.travel,
    bracket: g.bracket, nchanges: g.changes.length,
  };
}
// Python's json.dump sorts keys; a raw stringify compare would fail on order
// alone, so canonicalise both sides before comparing.
function canon(v: any): any {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const o: any = {};
    for (const k of Object.keys(v).sort()) o[k] = canon(v[k]);
    return o;
  }
  return v;
}
const eq = (a: unknown, b: unknown) =>
  JSON.stringify(canon(a)) === JSON.stringify(canon(b));

// ---- can_change ----
for (const [p, s, u, want] of ref.can_change as [string, number, number, boolean][]) {
  if (GP.canChange(p, s, u) !== want) bad(`canChange ${p} ${s} ${u}`);
}
console.log(`canChange: ${ref.can_change.length} cases`);

// ---- apply_change ----
const CASES: Array<[string, unknown]> = [
  ['pass_bias', 0.2], ['pass_bias', 0.9], ['box_bias', -0.6], ['man_rate', 0.4],
  ['blitz_rate', -0.5], ['tempo', 0.9], ['protection', 'seven'],
  ['depth_mix', [0.80, 0.16, 0.04]], ['depth_mix', [1.0, 0.0, 0.0]],
  ['shell_weights', { cover_2: .18, cover_4: .16, cover_1: -.08, cover_3: -.10 }],
  ['shell_weights', { cover_0: .06, cover_4: -.99 }],
  ['front_pref', ['bear', 'tite']], ['travel', true], ['bracket', 'p123'],
];
CASES.forEach(([p, v], i) => {
  const [g, ok] = GP.applyChange(new GP.Gameplan(), p, v, 0.95, 1.0);
  const [wp, wok, wsnap] = ref.apply_change[i];
  if (p !== wp) bad(`case order ${i}`);
  if (ok !== wok) bad(`applyChange ok ${p}`);
  if (!eq(snap(g), wsnap)) bad(`applyChange snap ${p}\n  got  ${JSON.stringify(snap(g))}\n  want ${JSON.stringify(wsnap)}`);
});
console.log(`applyChange: ${CASES.length} cases`);

// ---- adjust_plan ----
(ref.adjust_plan as any[]).forEach(([trig, skill, man, wApplied, wSnap]) => {
  const g0 = new GP.Gameplan(); g0.manRate = man;
  const [g, applied] = GP.adjustPlan(
    g0, { works: true, trigger: trig, target: 'p9' }, skill, 0.8, 2);
  if (!eq(applied, wApplied)) bad(`adjustPlan applied ${trig} ${skill} ${man}\n  got ${JSON.stringify(applied)} want ${JSON.stringify(wApplied)}`);
  if (!eq(snap(g), wSnap)) bad(`adjustPlan snap ${trig} ${skill} ${man}\n  got  ${JSON.stringify(snap(g))}\n  want ${JSON.stringify(wSnap)}`);
});
console.log(`adjustPlan: ${ref.adjust_plan.length} cases`);

// ---- distributions ----
const rng = new RNG(5); const g = new GP.Gameplan(); const N = 200000;
const tally = (f: () => string) => {
  const c: Record<string, number> = {};
  for (let i = 0; i < N; i++) { const k = f(); c[k] = (c[k] ?? 0) + 1; }
  for (const k of Object.keys(c)) c[k] = +(c[k] / N).toFixed(4);
  return c;
};
const dists: Array<[string, Record<string, number>]> = [
  ['shell', tally(() => GP.shell(g, rng))],
  ['personnel', tally(() => GP.personnel(g, rng))],
  ['depth', tally(() => GP.depth(g, rng))],
  ['blitzers', tally(() => String(GP.blitzers(g, rng, 3, 8)))],
  ['run_family', tally(() => GP.runFamily(g, rng))],
];
let manN = 0; for (let i = 0; i < N; i++) if (GP.isMan(g, rng)) manN++;
console.log('\n  distribution        ts      py     diff');
for (const [name, got] of dists) {
  const want = ref.dist[name];
  for (const k of Object.keys(want)) {
    const d = (got[k] ?? 0) - want[k];
    const flag = Math.abs(d) > 0.005 ? '  OFF' : '';
    if (flag) bad(`${name}.${k}`);
    console.log(`  ${(name + '.' + k).padEnd(18)} ${(got[k] ?? 0).toFixed(4)}  ${want[k].toFixed(4)}  ${d >= 0 ? '+' : ''}${d.toFixed(4)}${flag}`);
  }
}
const dm = manN / N - ref.dist.is_man;
if (Math.abs(dm) > 0.005) bad('is_man');
console.log(`  ${'is_man'.padEnd(18)} ${(manN / N).toFixed(4)}  ${ref.dist.is_man.toFixed(4)}  ${dm >= 0 ? '+' : ''}${dm.toFixed(4)}`);

console.log(fails === 0 ? '\nALL MATCH' : `\n${fails} FAILURES`);
