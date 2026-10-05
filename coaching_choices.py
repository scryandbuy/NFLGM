"""Choose a coherent set of coaching recommendations before anyone accepts them.

Scores represent strength of evidence, not probabilities or engine bonuses. Keep
whole recommendations: trimming a bundle can leave its title promising a change
it no longer makes. Compare all compatible combinations, not insertion order.
"""
from functools import lru_cache


def evidence(severity, sample, reference=20):
    """A stronger signal and more observations increase confidence, with a cap."""
    sample = max(0, float(sample))
    return 1.0 + min(4.0, max(0.0, float(severity))) * sample / (sample + reference)


def _directions(changes):
    out = {}
    for key, value in changes.items():
        if key == 'depth_mix':
            for label, delta in zip(('short', 'medium', 'deep'), value):
                out['depth_' + label] = float(delta)
        elif key not in ('protection', 'travel', 'travel_target', 'bracket'):
            out['blitz' if key in ('blitz_rate', 'blitz_lean') else key] = float(value)
    return out


def conflicts(a, b):
    """Opposing instructions for the same unit, including cross-setting intent."""
    if a.get('side') != b.get('side'):
        return False
    ac, bc = a['changes'], b['changes']
    ad, bd = _directions(ac), _directions(bc)
    if any(ad[k] * bd[k] < -1e-10 for k in ad.keys() & bd.keys()):
        return True
    if any(k in ac and k in bc and ac[k] != bc[k]
           for k in ('protection', 'travel', 'travel_target', 'bracket')):
        return True
    # The same safety cannot be the extra box defender and stay deep. These
    # are competing week/half priorities, although individual calls may vary.
    for x, y in ((ad, bd), (bd, ad)):
        if x.get('box_bias', 0) > 0 and y.get('shell_lean', 0) > 0:
            return True
        if x.get('zone_aggression', 0) > 0 and y.get('shell_lean', 0) > 0:
            return True
    return False


def resolve(candidates, limit=None):
    """Maximum evidence among compatible bundles; deterministic and RNG-free.

    At most a few dozen candidates exist. Memoized include/exclude search keeps
    this small and also applies the halftime display limit *after* comparison.
    The caller's records, user selections, and base game plan are never mutated.
    """
    items = sorted(candidates, key=lambda s: (s.get('side', ''), s.get('review_key', ''), s['text']))
    n = len(items)
    if not n:
        return []
    masks = [sum(1 << j for j in range(n) if j != i and conflicts(a, items[j]))
             for i, a in enumerate(items)]
    weights = [max(.001, float(s.get('_priority', 1.0))) for s in items]

    @lru_cache(None)
    def choose(mask, room):
        if not mask or not room:
            return 0.0, ()
        bit = mask & -mask
        i = bit.bit_length() - 1
        rest = mask ^ bit
        skip = choose(rest, room)
        value, chosen = choose(rest & ~masks[i], room - 1)
        take = (value + weights[i], (i,) + chosen)
        if abs(take[0] - skip[0]) < 1e-9:
            return min(take, skip, key=lambda x: x[1])
        return take if take[0] > skip[0] else skip

    _, picked = choose((1 << n) - 1, n if limit is None else max(0, int(limit)))
    selected = set(picked)
    alternatives = {i: [] for i in picked}
    for j in range(n):
        opponents = [i for i in picked if masks[j] & (1 << i)]
        if j not in selected and opponents:
            winner = max(opponents, key=lambda i: weights[i])
            alternatives[winner].append(dict(text=items[j]['text'], why=items[j]['why']))
    result = []
    # Preserve familiar display order, while making the decision order-independent.
    kept = {id(items[i]): i for i in picked}
    for original in candidates:
        i = kept.get(id(original))
        if i is None:
            continue
        row = {k: v for k, v in original.items() if k != '_priority'}
        if alternatives[i]:
            row['alternatives_weighed'] = alternatives[i]
            other = '; '.join(a['why'] for a in alternatives[i])
            row['why'] += f'. We also weighed {other}. On balance, we favor this approach alongside the rest of our plan.'
        result.append(row)
    return result
