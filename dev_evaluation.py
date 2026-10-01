"""Role-aware season evidence for development, independent of awards voting.

Scores compare players in the returned group, never across groups. They are
rates already: callers must NOT divide them by snaps again. Confidence measures
participation, not certainty that the metric captures all football performance.
The participation floors are conservative game-design thresholds, not fitted
real-world benchmarks. Missing coverage and long-snapper outcomes cannot support
demotion; a quiet coverage box score is not proof of poor coverage.
"""
import math


def _g(line, key):
    try:
        value = float(line.get(key, 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _n(line, key):
    return max(0.0, _g(line, key))


def _rate(line, made, attempts):
    return min(1.0, _n(line, made) / attempts) if attempts else 0.0


def _result(score, group, opportunities, confidence, basis, reason='', reliable=True):
    confidence = max(0.0, min(1.0, confidence))
    if not math.isfinite(score):
        return None
    return dict(score=float(score), group=group, opportunities=float(opportunities),
                confidence=confidence, credible=bool(reliable and confidence >= .75),
                basis=basis, reason=reason)


def _blocking(line):
    """Existing line-efficiency math, normalized over observed components only."""
    pb, rb = _n(line, 'pb_snaps'), _n(line, 'rb_snaps')
    weight, score = 0.0, 0.0
    if pb:
        score += (100 * _rate(line, 'pb_wins', pb)
                  - 260 * (3 * _n(line, 'sacks_allowed')
                           + _n(line, 'pressures_allowed')) / pb)
        weight += 100
    if rb:
        score += 45 * _rate(line, 'rb_wins', rb)
        weight += 45
    return (score / weight * 100 if weight else 0.0), pb, rb


def _production(line):
    return (_g(line, 'rush_yds') + _g(line, 'rec_yds')
            + 20 * (_n(line, 'rush_td') + _n(line, 'rec_td'))
            + 2.5 * _n(line, 'rec') - 25 * max(_n(line, 'fumbles_lost'),
                                             _n(line, 'fum_lost')))


# Numeric counters merge through the existing per-game/season stat books.
COVERAGE_BUCKETS = tuple(f'{mode}_{depth}' for mode in ('man', 'zone')
                         for depth in ('short', 'medium', 'deep'))
COVERAGE_OUTCOMES = ('completions', 'air_yards', 'td', 'explosive', 'pd', 'ints')
# A grading scale, not a claimed real-world coverage formula. Compare only
# within the same role and depth/mode bucket; higher costs mean worse results.
COVERAGE_COSTS = dict(completions=1., air_yards=.08, td=2., explosive=1., pd=-.5, ints=-2.)


def coverage_assessment(p, line):
    snaps = _n(line, 'cov_snaps')
    cells = {}
    for bucket in COVERAGE_BUCKETS:
        prefix = 'cov_' + bucket + '_'
        targets = _n(line, prefix + 'targets')
        if not targets:
            continue
        cell = {key: _n(line, prefix + key) for key in COVERAGE_OUTCOMES}
        # Missing or malformed partial records cannot support demotion.
        if any(prefix + key not in line for key in COVERAGE_OUTCOMES):
            return None
        if any(cell[key] > targets for key in ('completions','td','explosive','pd','ints')):
            return None
        cell['targets'] = targets
        cells[bucket] = cell
    targets = sum(c['targets'] for c in cells.values())
    if snaps < 100 or targets < 10 or targets > snaps:
        return None
    roles = {role: _n(line, 'cov_' + role + '_snaps')
             for role in ('outside', 'slot', 'safety')}
    role = max(roles, key=roles.get)
    if roles[role] < .6 * snaps:
        role = 'mixed'
    family = 'CB' if p.pos == 'CB' else 'S'
    out = _result(0., family + ':coverage:' + role, targets,
                  min(snaps / 500., targets / 60.),
                  'Individual coverage outcomes adjusted for role, depth and man/zone',
                  'Awaiting comparable coverage evidence', reliable=False)
    out['coverage_cells'] = cells
    return out


def calibrate_coverage(assessments):
    """Compare each target bucket to other players doing the same job.

    Leave the evaluated player out of the baseline. Sparse or missing buckets
    cannot establish a poor season. Never use shared team EPA as individual blame.
    This only changes assessments; no ratings, RNG, or historical stats change.
    """
    groups = {}
    for pid, row in assessments.items():
        if 'coverage_cells' in row:
            groups.setdefault(row['group'], []).append((pid, row))
    for peers in groups.values():
        for pid, row in peers:
            total = sum(c['targets'] for c in row['coverage_cells'].values())
            observed, score = 0., 0.
            for bucket, cell in row['coverage_cells'].items():
                others = [r['coverage_cells'][bucket] for other, r in peers
                          if other != pid and bucket in r['coverage_cells']]
                n = sum(c['targets'] for c in others)
                if len(others) < 4 or n < 100:
                    continue
                expected = sum(COVERAGE_COSTS[k] * sum(c[k] for c in others) / n
                               for k in COVERAGE_OUTCOMES)
                actual = sum(COVERAGE_COSTS[k] * cell[k] for k in COVERAGE_OUTCOMES)
                score += expected * cell['targets'] - actual
                observed += cell['targets']
            row['score'] = 100. * score / observed if observed else 0.
            completeness = observed / total if total else 0.
            row['confidence'] = min(row['confidence'], completeness)
            row['credible'] = row['confidence'] >= .75 and completeness >= .8
            row['reason'] = ('' if row['credible'] else
                             'Insufficient targets, coverage snaps or comparable role evidence')


def assessment(p, line):
    """Return role score + evidence, or None when the season cannot be assessed.

Uses only statistics recorded by the engine. ``credible`` additionally gates
demotion; coverage-production proxies may support conservative upgrades only.
No ratings, age, development trait, team record or awards enter the score.
"""
    pos = str(getattr(p, 'pos', '')).upper()
    pos = {'RB': 'HB', 'LE': 'LEDG', 'RE': 'REDG'}.get(pos, pos)
    if not line or pos == 'LS':
        return None  # No individual snapping outcomes are recorded yet.

    if pos == 'QB':
        att = _n(line, 'pass_att')
        plays = _n(line, 'pass_plays') + _n(line, 'rush_plays')
        if att < 60:
            return None
        if plays >= 80 and 'pass_epa' in line:
            # pass_plays already includes scrambles; rush_plays is designed runs.
            return _result(100 * (_g(line, 'pass_epa') + _g(line, 'rush_epa')) / plays,
                           'QB:epa', plays, plays / 450, 'EPA per quarterback involvement')
        plays = att + _n(line, 'sacked') + _n(line, 'rush_att')
        if plays < 80:
            return None
        score = (_g(line, 'pass_yds') + 20 * _n(line, 'pass_td')
                 - 45 * _n(line, 'ints') + _g(line, 'rush_yds')
                 + 20 * _n(line, 'rush_td')
                 - 25 * max(_n(line, 'fumbles_lost'), _n(line, 'fum_lost'))) / plays
        return _result(score, 'QB:box', plays, plays / 450,
                       'Box production per quarterback involvement',
                       'Legacy fallback; evaluated separately from EPA seasons')

    if pos in ('LT', 'LG', 'C', 'RG', 'RT'):
        score, pb, rb = _blocking(line)
        reps = pb + rb
        if reps < 100:
            return None
        group = 'OT' if pos in ('LT', 'RT') else 'OG' if pos in ('LG', 'RG') else 'C'
        # Avoid mixing a run-only specialist with a fully observed tackle.
        mode = 'balanced' if pb >= 30 and rb >= 30 else 'pass' if pb >= rb else 'run'
        confidence = reps / 700
        if mode != 'balanced':
            confidence = min(.65, confidence)
        return _result(score, group + ':' + mode, reps, confidence,
                       'Blocking efficiency per recorded rep',
                       '' if mode == 'balanced' else 'Only one blocking phase has sufficient evidence',
                       reliable=mode == 'balanced')

    if pos == 'FB':
        block, pb, rb = _blocking(line)
        blocks = pb + rb
        touches = _n(line, 'rush_att') + _n(line, 'tgt')
        reps = blocks + touches
        if reps < 40:
            return None
        # A blocker with few touches is graded on his actual blocking work.
        # Scaling touch production to a 0-100-like range keeps role mix bounded.
        score = (block * blocks + 10 * _production(line)) / reps
        complete = pb >= 30 and rb >= 30
        confidence = min(reps / 200, 1.0 if complete else .65)
        return _result(score, 'FB', reps, confidence,
                       'Recorded blocking and touch production',
                       '' if complete else 'Lead run-blocking outcomes are incomplete; limited role evidence',
                       reliable=complete)

    if pos in ('HB', 'WR', 'TE'):
        snaps = _n(line, 'snaps')
        touches = _n(line, 'rush_att') + _n(line, 'tgt')
        if snaps < 100 or touches < 15:
            return None
        full_snaps, full_touches = {'HB': (450, 150), 'WR': (650, 80), 'TE': (600, 60)}[pos]
        confidence = min(snaps / full_snaps, touches / full_touches)
        blocks = _n(line, 'pb_snaps') + _n(line, 'rb_snaps')
        blocking_te = pos == 'TE' and blocks >= max(60, touches)
        if blocking_te:
            # Receiving production alone cannot establish a blocking TE's decline.
            confidence = min(.65, confidence)
        return _result(100 * _production(line) / snaps, pos, snaps, confidence,
                       'Offensive production per snap',
                       ('Blocking-heavy tight end; receiving production is incomplete role evidence'
                        if blocking_te else 'Production proxy; confidence also requires recorded touches'),
                       reliable=not blocking_te)

    if pos in ('LEDG', 'REDG', 'DE', 'DT', 'MIKE', 'WILL', 'SAM', 'LB', 'CB', 'FS', 'SS'):
        # Use one exposure count, never sum two copies of the same defensive play.
        snaps = _n(line, 'def_plays') or _n(line, 'snaps')
        if snaps < 100:
            return None
        tackles, sacks = _n(line, 'tackles'), _n(line, 'sacks')
        pd, ints, ff = _n(line, 'pass_def'), _n(line, 'int_def'), _n(line, 'ff')
        if pos in ('CB', 'FS', 'SS'):
            coverage = coverage_assessment(p, line)
            if coverage is not None:
                return coverage
            score = 100 * (3 * pd + 8 * ints + 3 * ff + .2 * tackles) / snaps
            return _result(score, 'CB' if pos == 'CB' else 'S', snaps,
                           min(.65, snaps / 750), 'Ball-production proxy per defensive play',
                           'No individual coverage targets or allowed outcomes; quiet coverage is not poor coverage',
                           reliable=False)
        if pos in ('MIKE', 'WILL', 'SAM', 'LB'):
            score = 100 * (.6 * tackles + 3 * sacks + _n(line, 'pressures')
                           + 3 * pd + 8 * ints + 4 * ff) / snaps
            return _result(score, 'LB', snaps, snaps / 700,
                           'Defensive production per play')
        score = 100 * (3 * sacks + _n(line, 'pressures') + .6 * tackles + 4 * ff) / snaps
        rush_reps = _n(line, 'pr_reps')
        group = 'DT' if pos == 'DT' else 'EDGE'
        if rush_reps >= 40:
            score += 30 * _rate(line, 'pr_wins', rush_reps)
            return _result(score, group + ':rush', snaps,
                           min(snaps / 600, rush_reps / 250),
                           'Defensive production and pass-rush win rate')
        return _result(score, group + ':box', snaps, min(.65, snaps / 600),
                       'Defensive production per play', 'Insufficient pass-rush reps', reliable=False)

    if pos == 'K':
        fg, xp = _n(line, 'fg_att'), _n(line, 'xp_att')
        kicks = fg + xp
        if fg < 6 or kicks < 12:
            return None
        # Actual successes per attempted scoring point; no one-off long-kick bonus.
        made = 3 * min(fg, _n(line, 'fg_made')) + min(xp, _n(line, 'xp_made'))
        return _result(100 * made / (3 * fg + xp), 'K', kicks,
                       min(kicks / 50, fg / 25), 'Made scoring points per attempted point',
                       'Kick-distance and weather-adjusted attempt data are unavailable')

    if pos == 'P':
        punts = _n(line, 'punts')
        if punts < 8 or 'punt_net_yds' not in line:
            return None
        score = (_g(line, 'punt_net_yds') / punts
                 + 8 * _rate(line, 'punt_in20', punts) - 4 * _rate(line, 'punt_tb', punts))
        return _result(score, 'P', punts, punts / 50,
                       'Net punt yardage with placement rates',
                       'Field-position-adjusted punt opportunity data are unavailable')
    return None


def season_comparisons(league, year):
    """Shared role/grade comparisons for development and the season review.

    Read-only: the caller decides whether evidence warrants an action.
    """
    from collections import defaultdict
    import numpy as np
    groups, assessments, ranks = defaultdict(list), {}, {}
    for pid, line in league.stats.get(year, {}).items():
        p = league.player(pid)
        if p is None or p.retired: continue
        result = assessment(p, line)
        if result is not None:
            assessments[pid] = result
            groups[result['group']].append(p)
    calibrate_coverage(assessments)
    def percentile(values):
        if len(values) <= 1: return np.full(len(values), .5)
        _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
        starts = np.cumsum(counts) - counts
        return (starts[inverse] + (counts[inverse] - 1) / 2.) / (len(values) - 1)
    for players in groups.values():
        production = percentile([assessments[p.pid]['score'] for p in players])
        expected = .5 + .7 * (percentile([p.ovr for p in players]) - .5)
        peer_confidence = min(1., max(0., (len(players) - 1) / 3.))
        for p, actual, expectation in zip(players, production, expected):
            confidence = min(1., max(0., assessments[p.pid]['confidence'])) * peer_confidence
            ranks[p.pid] = (.5 + (float(actual) - .5) * confidence, float(expectation), confidence)
    return assessments, ranks
