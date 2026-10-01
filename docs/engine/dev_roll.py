"""One annual development review, before physical regression.

Compare role-appropriate performance with peers, sharing ranks for ties.
Only consecutive, credible poor seasons can cause a demotion. Small samples
are inconclusive; they must not masquerade as evidence of declining talent.
"""
from player_age import review_age
import collections
import numpy as np
import dev_evaluation as DE
import progression_engine as PE


def _pct(vals):
    """0-1 percentile, ties at their mean rank; a singleton is inconclusive."""
    vals = np.asarray(vals)
    if len(vals) <= 1: return np.full(len(vals), .5)
    _, inverse, counts = np.unique(vals, return_inverse=True, return_counts=True)
    starts = np.cumsum(counts) - counts
    return (starts[inverse] + (counts[inverse]-1)/2.) / (len(vals)-1)


def run(league, votes, rng, season=None, verbose=False):
    year = int(season or league.year)
    won = collections.defaultdict(set)
    for award, who in (votes or {}).items():
        if award == 'coty': continue
        for winner in (who if isinstance(who, list) else [who]):
            pid = getattr(winner, 'pid', winner)
            if isinstance(pid, str) and league.player(pid): won[pid].add(award)

    lines = league.stats.get(year, {})
    assessments, ranks = DE.season_comparisons(league, year)

    already_logged = {x.get('pid') for x in league.transactions
                      if x.get('kind') == 'dev_trait' and x.get('year') == year}
    moved = []
    for pid in sorted(set(lines) | set(won)):
        p = league.player(pid)
        if p is None or p.retired: continue
        history = p.xp_spent.get('_dev_review', [])
        if any(r.get('year') == year for r in history) or pid in already_logged: continue
        assessment = assessments.get(pid)
        pr, ex, confidence = ranks.get(pid, (.5, .5, 0.))
        group = assessment['group'] if assessment else p.pos
        prior = next((r for r in reversed(history) if r.get('year') == year-1
                      and r.get('group') == group), {})
        honours = won.get(pid, set())
        credible = bool(assessment and assessment.get('credible', True) and confidence >= .75)
        poor = credible and not honours and pr < .5 and pr < ex-.15
        elite = credible and pr >= .8
        poor_seasons = 1 + int(prior.get('poor_seasons', 0)) if poor else 0
        elite_seasons = 1 + int(prior.get('elite_seasons', 0)) if elite else 0
        c_up, c_down = PE.trait_move_chances(
            p.dev, review_age(p), pr, ex, honours, poor_seasons=poor_seasons,
            elite_seasons=elite_seasons, confidence=confidence)
        before = p.dev
        change = None
        if c_up or c_down:
            roll = rng.random()
            if roll < c_up and p.dev != PE.DEV_ORDER[-1]:
                p.dev = PE.DEV_ORDER[PE.DEV_ORDER.index(p.dev)+1]; change = 'up'
            elif roll > 1-c_down and p.dev != PE.DEV_ORDER[0]:
                p.dev = PE.DEV_ORDER[PE.DEV_ORDER.index(p.dev)-1]; change = 'down'
        if PE.GUARANTEED_UPGRADE & honours:
            reason = 'Major season award: ' + ', '.join(a.upper() for a in sorted(PE.GUARANTEED_UPGRADE & honours))
        elif change == 'down':
            reason = f'{poor_seasons} consecutive credible seasons below role expectations'
        elif honours:
            reason = 'Season honors: ' + ', '.join(a.replace('_', ' ').upper() for a in sorted(honours))
        elif change == 'up':
            reason = 'Sustained elite performance' if elite_seasons >= 2 else 'Breakout performance above role expectations'
        elif not credible:
            reason = 'Insufficient reliable evidence for a downgrade'
        elif poor:
            reason = f'{poor_seasons} consecutive credible season(s) below role expectations'
        else:
            reason = 'Performance does not justify a downgrade'
        record = dict(year=year, group=group, production=round(pr,4), expected=round(ex,4),
                      confidence=round(confidence,4), poor_seasons=0 if change=='down' else poor_seasons,
                      elite_seasons=elite_seasons, previous_dev=before, dev=p.dev,
                      chance_up=round(c_up,6), chance_down=round(c_down,6),
                      awards=sorted(honours), reason=reason)
        if assessment and 'coverage_cells' in assessment:
            record['coverage_evidence'] = dict(
                targets=assessment['opportunities'],
                snaps=float(lines[pid].get('cov_snaps', 0) or 0),
                basis=assessment['basis'], reason=assessment['reason'])
        # Bounded evidence for streaks; full changes remain in transactions.
        p.xp_spent['_dev_review'] = sorted([r for r in history if r.get('year',0)<year]+[record],
                                         key=lambda r:r['year'])[-3:]
        if change:
            moved.append((p, change, pr, ex, sorted(honours)))
            league.log('dev_trait', pid=pid, pos=p.pos, age=round(p.age,1),
                       change=change, previous_dev=before, dev=p.dev,
                       production=round(pr,2), expected=round(ex,2),
                       awards=sorted(honours), reason=reason)
    if verbose:
        print(f"  dev traits: {sum(m[1]=='up' for m in moved)} up, "
              f"{sum(m[1]=='down' for m in moved)} down")
    return moved
