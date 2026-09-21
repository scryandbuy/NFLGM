import { readFileSync } from 'fs';
import * as A from '../src/adjust.js';
import { RNG } from '../src/core/rng.js';

const ref = JSON.parse(readFileSync('/tmp/adj_py.json', 'utf8'));
let fails = 0;
const bad = (m: string) => { fails++; if (fails <= 15) console.log('FAIL ' + m); };

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
/** Python emits snake_case call keys; the port uses camelCase. */
const KEYMAP: Record<string, string> = { is_pass: 'isPass', keep_in: 'keepIn' };
const reKey = (o: any) => Object.fromEntries(
  Object.entries(o).map(([k, v]) => [KEYMAP[k] ?? k, v]));
const r12 = (x: number) => +x.toFixed(12);

/**
 * Stands in for the Python FixedRNG so the branch under test is the variable.
 * Deliberately NOT a subclass of RNG: RNG's constructor warms the stream by
 * calling next() twelve times, which runs before a subclass field exists.
 */
class FixedRNG {
  private vals: number[]; private i = 0;
  constructor(vals: number[]) { this.vals = vals; }
  next(): number { return this.vals[this.i++ % this.vals.length]; }
  integers(lo: number, _hi?: number): number { return lo; }
}
const fixed = (v: number[]) => new FixedRNG(v) as unknown as RNG;

// ---- conf ----
for (const [n, need, sk, want] of ref.conf as number[][]) {
  if (r12(A.conf(n, need, sk)) !== want) bad(`conf ${n} ${need} ${sk}`);
}
console.log(`conf: ${ref.conf.length} cases`);

// ---- memories, built the same way ----
const P = (d: string): A.PlayCall => ({ isPass: true, depth: d, personnel: '11' });
const R = (s = 'inside_zone'): A.PlayCall => ({ isPass: false, scheme: s, personnel: '12' });
const D = (k: Partial<A.DefCallLike> = {}): A.DefCallLike =>
  ({ rushers: 4, shell: 'cover_3', front: '4-3 over', box: 6, ...k });
const O = (ty: string, y: number, k: Partial<A.Outcome> = {}): A.Outcome =>
  ({ type: ty, yards: y, ...k });

type Triple = [A.PlayCall, A.DefCallLike, A.Outcome];
const rep = (n: number, f: () => Triple): Triple[] =>
  Array.from({ length: n }, f);

const SPECS: Record<string, Triple[][]> = {
  deep_burn: [rep(4, () => [P('deep'), D(), O('complete', 22, { target: 'wr1' })]),
              rep(4, () => [P('deep'), D(), O('complete', 18, { target: 'wr1' })])],
  one_target: [rep(5, () => [P('short'), D(), O('complete', 9, { target: 'wr1' })]),
               rep(5, () => [P('medium'), D(), O('complete', 2, { target: 'wr2' })])],
  run_gash: [rep(4, () => [R(), D(), O('run', 7)]),
             rep(4, () => [R('outside_zone'), D(), O('run', 9)])],
  run_tie: [[...rep(3, () => [R('gap_power'), D(), O('run', 6)] as Triple),
             ...rep(3, () => [R('inside_zone'), D(), O('run', 6)] as Triple)],
            rep(2, () => [R('gap_power'), D(), O('run', 6)])],
  sacked: [[...rep(3, () => [P('medium'), D({ rushers: 6 }), O('sack', -7)] as Triple),
            ...rep(3, () => [P('short'), D(), O('complete', 5, { target: 'te1' })] as Triple)],
           rep(3, () => [P('deep'), D(), O('sack', -9)])],
  predictable: [Array.from({ length: 5 }, (_, i) =>
                  [P('short'), D(), O('complete', 6, { target: `wr${i}` })] as Triple),
                rep(5, () => [P('short'), D(), O('incomplete', 0)])],
  quiet: [[[R(), D(), O('run', 1)]], [[R(), D(), O('run', 2)]]],
  one_series: [rep(9, () => [P('deep'), D(), O('complete', 30, { target: 'wr1' })])],
};

function mk(spec: Triple[][]): A.GameMemory {
  const m = new A.GameMemory();
  for (const series of spec) {
    m.newSeries();
    for (const [pc, dc, oc] of series) m.record(pc, dc, oc);
  }
  return m;
}

// ---- detect ----
for (const name of Object.keys(SPECS)) {
  const m = mk(SPECS[name]);
  for (const sk of [0.1, 0.5, 0.9]) {
    const t = A.detect(m, sk);
    const got: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(t)) {
      got[k] = { kind: v.kind, value: v.value, rate: r12(v.rate), n: v.n,
                 conf: r12(v.conf),
                 share: v.share === undefined ? null : r12(v.share) };
    }
    const want = ref.detect[`${name}|${sk}`];
    if (!eq(got, want)) {
      bad(`detect ${name} ${sk}\n  got  ${JSON.stringify(canon(got))}\n  want ${JSON.stringify(canon(want))}`);
    }
  }
}
console.log(`detect: ${Object.keys(ref.detect).length} cases`);

// ---- respond ----
let ri = 0;
for (const name of Object.keys(SPECS)) {
  const m = mk(SPECS[name]);
  for (const sk of [0.1, 0.5, 0.9]) {
    const tr = A.detect(m, sk);
    for (const r0 of [0.0, 0.3, 0.99]) {
      const c = A.respond(tr, sk, 0.6, fixed([r0, r0]));
      const got = c === null ? null
        : { trigger: c.trigger, target: c.target, works: Boolean(c.works),
            cost: c.cost, confidence: r12(c.confidence) };
      const [wn, wsk, wr0, want] = ref.respond[ri++];
      if (wn !== name || wsk !== sk || wr0 !== r0) bad(`respond order ${ri}`);
      if (!eq(got, want)) {
        bad(`respond ${name} ${sk} ${r0}\n  got  ${JSON.stringify(canon(got))}\n  want ${JSON.stringify(canon(want))}`);
      }
    }
  }
}
console.log(`respond: ${ref.respond.length} cases`);

// ---- apply ----
let ai = 0;
for (const trig of Object.keys(A.COUNTERS).sort()) {
  const base = { ...A.COUNTERS[trig], works: true, trigger: trig,
                 target: 'wr1', confidence: 0.5 } as A.Adjustment;
  for (const r0 of [0.0, 0.6, 0.99]) {
    const d = A.applyDefensive(D(), base, fixed([r0]));
    const o = A.applyOffensive({ isPass: true, depth: 'medium' } as A.PlayCall,
                               base, fixed([r0]));
    const [wt, wr0, wd, wo] = ref.apply[ai++];
    if (wt !== trig || wr0 !== r0) bad(`apply order ${ai}`);
    if (!eq(d, wd)) bad(`applyDefensive ${trig} ${r0}\n  got  ${JSON.stringify(canon(d))}\n  want ${JSON.stringify(canon(wd))}`);
    if (!eq(o, reKey(wo))) bad(`applyOffensive ${trig} ${r0}\n  got  ${JSON.stringify(canon(o))}\n  want ${JSON.stringify(canon(wo))}`);
  }
  const fail = { ...base, works: false } as A.Adjustment;
  const [wt2, , wd2, wo2] = ref.apply[ai++];
  if (wt2 !== trig + '|fails') bad(`apply fail order ${ai}`);
  const d2 = A.applyDefensive(D(), fail, fixed([0.0]));
  const o2 = A.applyOffensive({ isPass: true, depth: 'medium' } as A.PlayCall,
                              fail, fixed([0.0]));
  if (!eq(d2, wd2)) bad(`applyDefensive fails ${trig}`);
  if (!eq(o2, reKey(wo2))) bad(`applyOffensive fails ${trig}`);
}
console.log(`apply: ${ref.apply.length} cases`);

// ---- cheater ----
(ref.cheater as any[]).forEach(([trig, want], i) => {
  const c = { ...A.COUNTERS[trig], works: true, trigger: trig,
              target: null, confidence: 0.5 } as A.Adjustment;
  const got = A.cheaterAvailable(c);
  if (!eq(got, want)) bad(`cheater ${trig} ${i}`);
});
console.log(`cheater: ${ref.cheater.length} cases`);

// ---- script ----
for (const [skill, wantSeq] of ref.script as any[]) {
  const s = new A.Script(Array.from({ length: 20 }, (_, i) => i), 15, skill);
  const downs: Array<[number, number]> = [[1, 10], [2, 7], [3, 5], [1, 10],
                                          [1, 2], [2, 16], [1, 10], [2, 8]];
  const seq: unknown[] = [];
  for (let k = 0; k < 3; k++) {
    for (const [down, ytg] of downs) {
      seq.push([s.nextCall(down, ytg), s.used, s.active,
                r12(s.performanceModifier())]);
    }
  }
  if (!eq(seq, wantSeq)) {
    bad(`script ${skill}\n  got  ${JSON.stringify(seq)}\n  want ${JSON.stringify(wantSeq)}`);
  }
}
console.log(`script: ${ref.script.length} cases`);

// ---- rounding ----
for (const [v, want] of ref.round as number[][]) {
  if (A.pyRound(v) !== want) bad(`pyRound ${v}: got ${A.pyRound(v)} want ${want}`);
}
console.log(`pyRound: ${ref.round.length} cases`);

console.log(fails === 0 ? '\nALL MATCH' : `\n${fails} FAILURES`);
