"""Assignment-aware award evidence. Never draws from the simulation RNG.

The reference is an 80 in each relevant blocking attribute, at every position.
Replace only the evaluated blocker; retain his actual opponent, teammates,
help, quarterback and protection call. This measures execution above the
same reference standard, rather than above the player's own ability.
"""
import math
from functools import lru_cache

import numpy as np

REFERENCE = .80
RUSH_SIGMA = .26
RUN_SIGMA = .10


_NODES, _WEIGHTS = np.polynomial.legendre.leggauss(96)


def _distribution(t, mean):
    """Lognormal density and survival; vector erf approximation <1.5e-7."""
    z = np.log(t / mean) / RUSH_SIGMA
    x = np.abs(z) / math.sqrt(2.)
    a = 1. / (1. + .3275911 * x)
    erfc = (((((1.061405429*a - 1.453152027)*a + 1.421413741)*a
               - .284496736)*a + .254829592)*a) * np.exp(-x*x)
    survival = .5 * np.where(z >= 0., erfc, 2. - erfc)
    density = np.exp(-.5*z*z) / (t * RUSH_SIGMA * math.sqrt(2.*math.pi))
    return density, survival


def run_expectation(resistance, threshold):
    """The live run contest's Gaussian roll, with only our blocker replaced."""
    return .5 * (1. + math.erf((REFERENCE - resistance - threshold) / (RUN_SIGMA * math.sqrt(2.))))


def protection_evidence(model, threshold, time_scale=1., hold=0.,
                        sack_k=25., sack_scale=1., hot=False):
    """Expected wins and actual-bookkeeping losses for each contested blocker.

    A retained helper is evaluated with the real primary blocker still in
    place. His reference replacement changes only his contribution to help.
    This prevents a weak helper borrowing his primary's individual excellence.
    Sack/pressure expectation includes the entire rush, since the fastest
    arrival determines those events. Unblocked rushers remain fixed at .6s.
    """
    if not model or not model['evaluations']:
        return []
    return list(_protection_evidence(tuple(model['means']), tuple(model['free']),
        tuple(model['evaluations']), model['qb_scale'], threshold, time_scale,
        hold, sack_k, sack_scale, hot))


@lru_cache(maxsize=512)
def _protection_evidence(means, free, evaluations, qb_scale, threshold,
                         time_scale, hold, sack_k, sack_scale, hot):
    # Integrate the distribution of the fastest arrival analytically across
    # the other rushers. One-dimensional quadrature avoids sampling noise
    # and large per-play arrays. Split at the pressure and win boundaries.
    pressure_cut = (2.72 * (.65 + (.20 if hot else 0.)) / time_scale) / qb_scale
    cap_cut = (math.log(max(1e-12, sack_k*sack_scale)/.85)/2.4 + hold) / (time_scale*qb_scale)
    upper = .6 if free else max(16., max(means, default=4.)*4.)
    cuts = sorted({.35, upper, *[x for x in (threshold, pressure_cut, cap_cut) if .35 < x < upper]})
    t = np.concatenate([lo + (_NODES+1.)*(hi-lo)/2. for lo,hi in zip(cuts,cuts[1:])])
    weights = np.concatenate([_WEIGHTS*(hi-lo)/2. for lo,hi in zip(cuts,cuts[1:])])
    def probabilities(arrival):
        time = np.round(arrival*qb_scale, 2)*time_scale
        pressure = np.clip((2.72-time)/2.72 + (.20 if hot else 0.), 0., 1.)
        sacks = np.clip(sack_k*np.exp(-2.4*(time-hold))*sack_scale, 0., .85)
        if hot: sacks *= .35
        return sacks, np.where(pressure >= .35, 1., sacks)
    sacks, pressured = probabilities(t)
    distributions = {j: _distribution(t, mean) for j, mean in enumerate(means) if j not in free}
    atoms = {j: float(_distribution(np.asarray(.6), means[j])[1]) for j in distributions} if free else {}
    rows = []
    for pid, index, reference_mean, primary in evaluations:
        own_pdf, own_survival = _distribution(t, reference_mean)
        other_survival = np.ones_like(t)
        hazard = np.zeros_like(t)
        atom_survival = 1.
        for j, (pdf, survival) in distributions.items():
            if j == index: continue
            other_survival *= survival
            hazard += pdf / np.maximum(survival, 1e-300)
            if free: atom_survival *= atoms[j]
        other_pdf = other_survival * hazard
        win = .5 * math.erfc(math.log(threshold / reference_mean) / (RUSH_SIGMA * math.sqrt(2.)))
        # Either our contest arrives first, or another arrives while our
        # own block also loses before the win threshold.
        joint_loss = own_pdf*other_survival + other_pdf*np.maximum(0., own_survival-win)
        expected_pressure = float(np.sum(weights*(t < threshold)*joint_loss*pressured))
        expected_sack = float(np.sum(weights*own_pdf*other_survival*sacks)) if primary else 0.
        if free:
            own_at_free = float(_distribution(np.asarray(.6), reference_mean)[1])
            expected_pressure += atom_survival*max(0., own_at_free-win)*float(probabilities(np.asarray(.6))[1])
        rows.append((pid, win, expected_pressure, expected_sack))
    return tuple(rows)


def line_score(line):
    """Observed-minus-expected work, plus unchanged legacy-only evidence.

    100 is the common reference score, not an OVR. The original 100/45
    phase weights and 3:1 sack/pressure penalty remain. Historical reps with
    no matchup evidence retain their old contribution; no history is inferred.
    """
    get = lambda k: float(line.get(k, 0) or 0)
    pb, rb = get('pb_snaps'), get('rb_snaps')
    if pb < 150:
        return None
    n = min(pb, max(0., get('pb_eval_snaps')))
    m = min(rb, max(0., get('rb_eval_snaps')))
    # Start with the exact legacy formula, then replace measured assignment
    # expectations with the shared reference. With complete evidence the
    # score is 100 + observed performance minus expected performance.
    score = (100. * get('pb_wins') - 260. * (3. * get('sacks_allowed') + get('pressures_allowed'))) / pb
    if n:
        score += (100. * (n - get('pb_expected_wins'))
                  + 260. * (3. * get('pb_expected_sacks') + get('pb_expected_pressures'))) / pb
    if rb:
        score += 45. * (get('rb_wins') - (get('rb_expected_wins') if m else 0.)) / rb
    return score
