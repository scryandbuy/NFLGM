import { readFileSync } from 'fs';
import { resolveZone, zoneWindow, ZoneDefender } from '../src/matchups.js';
import { Player } from '../src/core/math.js';
import { RNG } from '../src/core/rng.js';

const ref = JSON.parse(readFileSync('/tmp/zone_py.json', 'utf8'));
let fails = 0;
const bad = (m: string) => { fails++; if (fails <= 10) console.log('FAIL ' + m); };

class FixedRNG { constructor(private v: number) {} next() { return this.v; } }
const fixed = (v: number) => new FixedRNG(v) as unknown as RNG;

const ATTRS = ['route_run_short_rating', 'route_run_med_rating', 'route_run_deep_rating',
  'awareness_rating', 'play_rec_rating', 'zone_cover_rating', 'speed_rating',
  'accel_rating', 'agility_rating', 'throw_acc_short_rating', 'throw_acc_mid_rating',
  'throw_acc_deep_rating', 'throw_under_pressure_rating', 'throw_power_rating'];

function mk(base: number, pid: string): Player {
  const p: any = { pid, pos: 'WR' };
  for (const a of ATTRS) p[a] = base;
  return p as Player;
}

for (const [s, d, want] of ref.zone_window as [string, string, number][]) {
  if (zoneWindow(s, d) !== want) bad(`zoneWindow ${s} ${d}`);
}
console.log(`zoneWindow: ${ref.zone_window.length} cases`);

for (const row of ref.resolve_zone as any[]) {
  const [shell, depth, rlvl, dlvl, qlvl, pres, roll, wComp, wCont, wWin, wP, wDef] = row;
  const rec = mk(rlvl, 'r');
  const d1 = { ...mk(dlvl, 'd1'), dist_to_window: 3 } as ZoneDefender;
  const d2 = { ...mk(dlvl - 10, 'd2'), dist_to_window: 1 } as ZoneDefender;
  const qb = mk(qlvl, 'q');
  const z = resolveZone(rec, [d1, d2], qb, shell, depth, pres, fixed(roll));
  if (z.complete !== wComp || z.contested !== wCont || z.window !== wWin
      || z.p_complete !== wP || z.defender !== wDef) {
    bad(`resolveZone ${shell} ${depth} r${rlvl} d${dlvl} q${qlvl} p${pres} roll${roll}\n  got  ${JSON.stringify(z)}\n  want comp=${wComp} cont=${wCont} win=${wWin} p=${wP} def=${wDef}`);
  }
}
console.log(`resolveZone: ${ref.resolve_zone.length} cases`);
console.log(fails === 0 ? '\nALL MATCH' : `\n${fails} FAILURES`);
