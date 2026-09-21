import { readFileSync } from 'fs';
import { resolvePlay, OffField, DefField } from '../src/plays.js';
import { RNG } from '../src/core/rng.js';

const ref = JSON.parse(readFileSync('/tmp/play_py.json', 'utf8'));
const fx = JSON.parse(readFileSync('/tmp/play_fixture.json', 'utf8'));
const off = fx.off as OffField, deff = fx.deff as DefField;

// The SAME deterministic grid of calls the Python reference walked, so both
// engines see an identical sequence of situations even though their RNG
// streams differ and no play can be matched one-for-one.
const CALLS: any[] = [];
for (const isPass of [true, false])
  for (const pers of ['11', '12', '10', '21'])
    for (const depth of ['short', 'medium', 'deep'])
      for (const shell of ['cover_2', 'cover_3', 'cover_4', 'tampa_2', 'cover_1'])
        for (const man of [true, false])
          for (const rushers of [4, 5, 6])
            for (const box of [5, 6, 7])
              for (const ytg of [3, 8, 17, 45, 80])
                CALLS.push({
                  isPass, personnel: pers, depth,
                  scheme: isPass ? 'inside_zone' : (box < 7 ? 'inside_zone' : 'power'),
                  concept: 'curl_flat', shotgun: true, motion: false,
                  play_action: false,
                  shell, man, rushers, box, front: '4-3 over', fooled: false, ytg,
                });

const rng = new RNG(99);
const N = ref.n as number;
const counts: Record<string, number> = {};
const yards: Record<string, number[]> = {};
const air: number[] = [], yac: number[] = [], sep: number[] = [], ybc: number[] = [];
for (let i = 0; i < N; i++) {
  const c = CALLS[i % CALLS.length];
  const oc = { isPass: c.isPass, personnel: c.personnel, depth: c.depth,
               scheme: c.scheme, concept: c.concept, shotgun: c.shotgun,
               motion: c.motion, playAction: c.playAction };
  const dc = { shell: c.shell, man: c.man, rushers: c.rushers, box: c.box,
               front: c.front, fooled: c.fooled };
  const o = resolvePlay(off, deff, oc, dc, c.ytg, rng);
  counts[o.type] = (counts[o.type] ?? 0) + 1;
  (yards[o.type] ??= []).push(o.yards ?? 0);
  if (o.touchdown) counts['TD'] = (counts['TD'] ?? 0) + 1;
  if (o.type === 'complete') { air.push(o.air!); yac.push(o.yac!); sep.push(o.separation ?? 0); }
  if (o.type === 'run') ybc.push(o.ybc ?? 0);
}
const mean = (a: number[]) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0;

let fails = 0;
console.log('  metric                  ts        py      diff');
function cmp(name: string, got: number, want: number, tol: number) {
  const d = got - want;
  const off_ = Math.abs(d) > tol;
  if (off_) fails++;
  console.log(`  ${name.padEnd(20)} ${got.toFixed(4).padStart(8)}  ${want.toFixed(4).padStart(8)}  ${(d >= 0 ? '+' : '') + d.toFixed(4)}${off_ ? '  OFF' : ''}`);
}
for (const k of Object.keys(ref.counts)) {
  cmp(`rate.${k}`, (counts[k] ?? 0) / N, ref.counts[k], 0.006);
}
for (const k of Object.keys(ref.mean_yards)) {
  cmp(`yards.${k}`, mean(yards[k] ?? []), ref.mean_yards[k], 0.12);
}
cmp('air', mean(air), ref.air, 0.10);
cmp('yac', mean(yac), ref.yac, 0.10);
cmp('separation', mean(sep), ref.sep, 0.006);
cmp('ybc', mean(ybc), ref.ybc, 0.06);
console.log(fails === 0 ? '\nALL WITHIN TOLERANCE' : `\n${fails} OUT OF TOLERANCE`);
