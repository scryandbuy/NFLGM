/**
 * Seeded random number generator.
 *
 * WHY THIS COMES FIRST: every module in the sim draws from one of these
 * distributions. If they do not behave like the Python originals, every
 * constant solved during calibration is void - and those constants were
 * fitted against six seasons of real play-by-play, so they are not cheap to
 * re-derive.
 *
 * Python used numpy's Generator (PCG64). JavaScript has no seeded RNG at all,
 * so this implements one. It has to be SEEDED rather than Math.random() for
 * two reasons: a franchise save must replay identically when reloaded, and a
 * calibration run must be reproducible or a regression is invisible.
 *
 * sfc32 is used for the uniform stream: small, fast, passes PractRand, and
 * takes a 128-bit state we can serialise into a save file.
 */

export class RNG {
  private a = 0; private b = 0; private c = 0; private d = 0;
  private spare: number | null = null;   // Box-Muller caches a second normal

  constructor(seed: number | string = 1) {
    let h = typeof seed === 'string' ? RNG.hashString(seed) : (seed >>> 0);
    // scramble the seed into four words so nearby seeds diverge immediately
    for (let i = 0; i < 4; i++) {
      h = (h ^ (h >>> 16)) >>> 0;
      h = Math.imul(h, 0x45d9f3b) >>> 0;
      const v = (h ^ (h >>> 16)) >>> 0;
      if (i === 0) this.a = v; else if (i === 1) this.b = v;
      else if (i === 2) this.c = v; else this.d = v;
    }
    for (let i = 0; i < 12; i++) this.next();   // warm up
  }

  private static hashString(s: string): number {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h >>> 0;
  }

  /** Uniform in [0, 1). The stream everything else is built on. */
  next(): number {
    const t = (this.a + this.b | 0) + this.d | 0;
    this.d = this.d + 1 | 0;
    this.a = this.b ^ (this.b >>> 9);
    this.b = this.c + (this.c << 3) | 0;
    this.c = (this.c << 21) | (this.c >>> 11);
    this.c = this.c + t | 0;
    return (t >>> 0) / 4294967296;
  }

  /** Uniform float in [lo, hi). */
  uniform(lo = 0, hi = 1): number { return lo + (hi - lo) * this.next(); }

  /** Integer in [lo, hi). Matches numpy's integers(lo, hi). */
  integers(lo: number, hi?: number): number {
    if (hi === undefined) { hi = lo; lo = 0; }
    return lo + Math.floor(this.next() * (hi - lo));
  }

  /**
   * Normal, via Box-Muller. Used for yards-before-contact, air yards, and
   * every rating jitter in the sim.
   */
  normal(mean = 0, sd = 1): number {
    if (this.spare !== null) {
      const v = this.spare; this.spare = null;
      return mean + sd * v;
    }
    let u = 0, v = 0, s = 0;
    do {
      u = this.next() * 2 - 1;
      v = this.next() * 2 - 1;
      s = u * u + v * v;
    } while (s >= 1 || s === 0);
    const m = Math.sqrt(-2 * Math.log(s) / s);
    this.spare = v * m;
    return mean + sd * (u * m);
  }

  /** Lognormal. numpy's lognormal(mean, sigma) is exp(normal(mean, sigma)). */
  lognormal(mean = 0, sigma = 1): number {
    return Math.exp(this.normal(mean, sigma));
  }

  /**
   * Gamma(shape, scale) by Marsaglia-Tsang. This is the workhorse for every
   * yardage distribution - yards after contact, punt returns, kick returns -
   * because it gives a right-skewed spread with a long tail, which is the
   * actual shape of football yardage.
   */
  gamma(shape: number, scale = 1): number {
    if (shape < 1) {
      // Johnk's boost for shape < 1
      const u = this.next();
      return this.gamma(1 + shape, scale) * Math.pow(u, 1 / shape);
    }
    const d = shape - 1 / 3;
    const c = 1 / Math.sqrt(9 * d);
    for (;;) {
      let x: number, v: number;
      do { x = this.normal(); v = 1 + c * x; } while (v <= 0);
      v = v * v * v;
      const u = this.next();
      if (u < 1 - 0.0331 * x * x * x * x) return d * v * scale;
      if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) {
        return d * v * scale;
      }
    }
  }

  /** Pick one item by weight. Replaces numpy's choice(list, p=weights). */
  choice<T>(items: readonly T[], weights?: readonly number[]): T {
    if (!weights) return items[this.integers(items.length)];
    let total = 0;
    for (const w of weights) total += w;
    let r = this.next() * total;
    for (let i = 0; i < items.length; i++) {
      r -= weights[i];
      if (r <= 0) return items[i];
    }
    return items[items.length - 1];
  }

  /** Sample k distinct indices, weighted, without replacement. */
  sampleIndices(weights: readonly number[], k: number): number[] {
    const left = weights.map((w, i) => [w, i] as [number, number]);
    const out: number[] = [];
    for (let n = 0; n < k && left.length; n++) {
      let total = 0;
      for (const [w] of left) total += w;
      let r = this.next() * total;
      let pick = left.length - 1;
      for (let i = 0; i < left.length; i++) {
        r -= left[i][0];
        if (r <= 0) { pick = i; break; }
      }
      out.push(left[pick][1]);
      left.splice(pick, 1);
    }
    return out;
  }

  /** Fisher-Yates, in place. Used for scheduling. */
  shuffle<T>(arr: T[]): T[] {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = this.integers(i + 1);
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  /** Serialise the whole state so a franchise save replays identically. */
  getState(): [number, number, number, number] {
    return [this.a, this.b, this.c, this.d];
  }

  setState(s: [number, number, number, number]): void {
    [this.a, this.b, this.c, this.d] = s;
    this.spare = null;
  }
}
