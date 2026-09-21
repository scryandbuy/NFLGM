import { readFileSync } from 'fs';
import { loadLeague } from '../src/rosters.js';
import { Player } from '../src/core/math.js';
const ref = JSON.parse(readFileSync('/tmp/league_py.json', 'utf8'));
const L = loadLeague('/home/claude/data/league_seed_2026.csv');
let fails = 0, checks = 0;
const bad = (m: string) => { fails++; if (fails <= 8) console.log('FAIL ' + m); };
const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const rteams = Object.keys(ref).sort(), lteams = Object.keys(L).sort();
if (!eq(rteams, lteams)) bad('team list');
for (const t of rteams) {
  const r = L[t], w = ref[t];
  for (const k of ['qb', 'rb', 'k', 'p', 'kr']) {
    checks++;
    const got = (r as any)[k] ? ((r as any)[k] as Player).pid : null;
    if (got !== w[k]) bad(`${t}.${k}: ${got} vs ${w[k]}`);
  }
  for (const k of ['qbs', 'backs', 'wr', 'extra_blockers', 'ol', 'dl', 'lb', 'db']) {
    checks++;
    const got = (((r as any)[k] ?? []) as Player[]).map(p => p.pid);
    if (!eq(got, w[k])) bad(`${t}.${k}\n  got  ${got.join(',')}\n  want ${(w[k] as string[]).join(',')}`);
  }
  const gd: Record<string, string[]> = {};
  for (const [pos, v] of Object.entries(r.depth ?? {})) gd[pos] = (v as Player[]).map(p => p.pid);
  checks++;
  const sortKeys = (o: any) => Object.fromEntries(Object.keys(o).sort().map(k => [k, o[k]]));
  if (!eq(sortKeys(gd), sortKeys(w.depth))) bad(`${t}.depth`);
}
console.log(`${rteams.length} teams, ${checks} group comparisons`);
console.log(fails === 0 ? 'ALL MATCH' : `${fails} FAILURES`);
