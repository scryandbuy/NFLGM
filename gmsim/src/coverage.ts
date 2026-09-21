/**
 * Coverage assignment: who covers whom. Ported from coverage.py.
 *
 * Before this existed the engine picked a target at random from the receivers
 * and a defender at random from the secondary, so a tight end could be covered
 * by a corner, a WR1 by a safety, and a linebacker never covered anyone.
 *
 * WHAT THE RESEARCH SAYS:
 *   SIDES ARE THE DEFAULT. Corners hold a side and cover whoever lines up
 *   there. Travelling is the exception.
 *
 *   SHADOWING IS RARE. ESPN, having charted every snap: "There are only a
 *   handful of cornerbacks who shadow No.1 receivers most weeks." Josh Norman,
 *   a premier shadow corner, travelled in roughly half his games across two
 *   seasons. The most-shadowed receiver drew nine shadow games in a season.
 *
 *   YOU ONLY TRAVEL IF THERE IS A GAP. Washington would not travel Norman
 *   against Antonio Brown because they had Bashaud Breeland on the other side.
 *
 *   ZONE NEVER TRAVELS. Nobody is assigned to a man.
 *
 *   THE MISMATCH IS THE POINT. Real separation: TE 3.35 yards, WR 2.93. Tight
 *   ends are not better route runners; they are covered by linebackers and
 *   safeties. That gap needs no special rule - it falls out of the matchup.
 */
import { RNG } from './core/rng.js';
import { AVG, rate, clip, Player } from './core/math.js';

export interface Aligned { player: Player; spot: string; side: 'L' | 'R' | 'C'; }
export interface Pair {
  receiver: Player; defender: Player; spot: string;
  travelled: boolean; kind: string; separation?: number; bracket?: Player | null;
}

/** Where each eligible lines up. Alignment is what the defence reacts to. */
export function receiverAlignment(receivers: Player[]): Aligned[] {
  const out: Aligned[] = [];
  receivers.forEach((r, i) => {
    const pos = r.pos ?? 'WR';
    if (pos === 'TE') out.push({ player: r, spot: 'te', side: i % 2 ? 'R' : 'L' });
    else if (pos === 'HB' || pos === 'RB' || pos === 'FB') out.push({ player: r, spot: 'back', side: 'C' });
    else if (i === 0) out.push({ player: r, spot: 'X', side: 'L' });
    else if (i === 1) out.push({ player: r, spot: 'Z', side: 'R' });
    else out.push({ player: r, spot: 'slot', side: i % 2 ? 'R' : 'L' });
  });
  return out;
}

const COV_W = { man_cover_rating: 0.55, speed_rating: 0.25, press_rating: 0.20 };
const RTE_W = {
  route_run_short_rating: 0.20, route_run_med_rating: 0.25,
  route_run_deep_rating: 0.25, speed_rating: 0.30,
};

/**
 * Does CB1 follow the offence's best receiver? Constants solved against the
 * research: the BEST case - a premier shadow corner against a premier receiver
 * - lands near the ~50% of games the data describes, and that is the CEILING,
 * not the norm. An early build peaked at 85% and travelled 54% of the time on
 * a negligible corner gap.
 */
export function shouldTravel(
  cb1: Player, cb2: Player | null, wr1: Player, isMan: boolean, rng: RNG,
  coachWillingness = 0.5,
): boolean {
  if (!isMan) return false;
  const c1 = rate(cb1, COV_W);
  const c2 = cb2 ? rate(cb2, COV_W) : AVG;
  const w1 = rate(wr1, RTE_W);
  const gap = c1 - c2;
  const threat = w1 - AVG;
  // A real gap is required. Two good corners means you play sides.
  if (gap <= 0.06 || threat <= 0.04) return false;
  const p = (1.35 * (gap - 0.06) + 0.75 * (threat - 0.04))
    * (0.45 + 1.05 * coachWillingness);
  return rng.next() < clip(p, 0, 0.62);
}

/**
 * Which corner holds which side. This is what "playing sides" MEANS - without
 * it the first build handed the best corner to the X receiver on every snap,
 * so CB1 covered WR1 in 100% of games and travel never mattered at all.
 */
export function cornerSides(cbs: Player[], rng: RNG, leftPref?: boolean): Record<string, Player> {
  if (!cbs.length) return {};
  const lp = leftPref ?? rng.next() < 0.5;
  const a = cbs[0], b = cbs.length > 1 ? cbs[1] : cbs[0];
  return lp ? { L: a, R: b } : { L: b, R: a };
}

/** Pair every eligible receiver with the defender responsible for him. */
export function assignCoverage(
  aligned: Aligned[], defense: { db?: Player[]; lb?: Player[] },
  defCall: { man?: boolean }, rng: RNG, coachWillingness = 0.5,
  travelIn?: boolean, sidesIn?: Record<string, Player>,
): { pairs: Pair[]; travelled: boolean } {
  const db = defense.db ?? [];
  const cbs = db.filter(d => (d.pos ?? 'CB') === 'CB');
  const corners = cbs.length ? cbs : db.slice(0, 3);
  const safs = db.filter(d => d.pos === 'FS' || d.pos === 'SS');
  const safeties = safs.length ? safs : db.slice(-2);
  const lbs = defense.lb ?? [];
  const isMan = !!defCall.man;

  let travel = travelIn;
  if (travel === undefined && corners.length && aligned.length) {
    const wr1 = aligned.find(a => a.spot === 'X')?.player;
    travel = wr1
      ? shouldTravel(corners[0], corners.length > 1 ? corners[1] : null, wr1,
                     isMan, rng, coachWillingness)
      : false;
  }

  const sides = sidesIn ?? cornerSides(corners, rng);
  const pairs: Pair[] = [];
  const used = new Set<Player>();

  const take = (pool: Player[]): Player => {
    for (const d of pool) if (!used.has(d)) { used.add(d); return d; }
    return pool.length ? pool[pool.length - 1] : ({} as Player);
  };

  for (const a of aligned) {
    const spot = a.spot;
    if (spot === 'X' || spot === 'Z') {
      let d: Player; let trav = false;
      if (spot === 'X' && travel && corners.length) {
        d = corners[0]; used.add(d); trav = true;           // my best man follows him
      } else {
        d = sides[a.side] ?? corners[0];                    // whoever holds that side
        if (d && used.has(d)) d = take(corners.filter(c => !used.has(c)).length
          ? corners.filter(c => !used.has(c)) : corners);
        else if (d) used.add(d);
      }
      pairs.push({ receiver: a.player, defender: d, spot, travelled: trav, kind: 'cb' });
    } else if (spot === 'slot') {
      // the slot draws the NICKEL - a different player with different
      // attributes, not whichever corner happened to be picked
      const pool = corners.filter(c => !used.has(c));
      pairs.push({
        receiver: a.player, spot, travelled: false, kind: 'nickel',
        defender: take(pool.length ? pool : (safeties.length ? safeties : corners)),
      });
    } else if (spot === 'te') {
      // safety or linebacker by personnel. THIS is where the real TE-vs-LB
      // mismatch lives; no special rule needed.
      const useSaf = rng.next() < 0.58;
      const pool = (useSaf ? safeties : lbs).length
        ? (useSaf ? safeties : lbs)
        : (safeties.length ? safeties : (lbs.length ? lbs : corners));
      const d = take(pool);
      pairs.push({
        receiver: a.player, defender: d, spot, travelled: false,
        kind: safeties.includes(d) ? 'safety' : 'lb',
      });
    } else {                                                // back out of the backfield
      const pool = lbs.filter(l => !used.has(l));
      pairs.push({
        receiver: a.player, spot, travelled: false, kind: 'lb',
        defender: take(pool.length ? pool : (lbs.length ? lbs : safeties)),
      });
    }
  }
  return { pairs, travelled: !!travel };
}

/**
 * A bracketed receiver gets a second man over the top. The adjustment engine
 * decides WHO gets bracketed; this applies it.
 */
export function bracketTarget(pairs: Pair[], bracketPid: string | null, safs: Player[]): Pair[] {
  if (!bracketPid) return pairs;
  for (const p of pairs) {
    if (p.receiver.pid === bracketPid) p.bracket = safs.length ? safs[0] : null;
  }
  return pairs;
}
