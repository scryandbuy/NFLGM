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


def explain_choice(choice, alternatives, context=None):
    """Translate a tactical tradeoff into coaching language, using recorded facts.

    This is presentation only: explanations never change a score or a setting.
    Do not infer a blitz count, coverage failure, or score from missing evidence.
    """
    changes = _directions(choice['changes'])
    key = choice.get('review_key')
    others = {a.get('review_key') for a in alternatives}
    if context and key == 'pressure_defense' and 'run_defense' in others:
        them = context['them']
        pressure = them['sacks'] + them['pressures']
        run_rate = them['run_yds'] / max(1, them['runs'])
        if pressure == 0:
            passing = f"we haven't sacked or pressured their quarterback in {them['passes']} dropbacks"
        else:
            passing = f"we've sacked or pressured their quarterback on only {pressure} of {them['passes']} dropbacks"
        return (f"Their {run_rate:.1f} yards a carry on {them['runs']} runs is a concern, but {passing}. "
                "We need to make him get the ball out sooner. Send extra pressure, even if that means fewer defenders sitting back to play the run.")
    if context and key in ('run_defense', 'pass_defense') and others & {'run_defense', 'pass_defense', 'pressure_defense'}:
        them = context['them']
        run_rate = them['run_yds'] / max(1, them['runs'])
        pass_rate = them['pass_yds'] / max(1, them['passes'])
        if key == 'run_defense':
            return (f"They're getting {run_rate:.1f} yards a carry on {them['runs']} runs. "
                    "Chasing the quarterback or putting more defensive backs on the field leaves that problem exposed. "
                    "Strengthen the front and make them throw to move the ball.")
        return (f"The run defense is allowing {run_rate:.1f} a carry, but their passing game is taking "
                f"{pass_rate:.1f} net yards per dropback across {them['passes']} dropbacks. "
                "We need more coverage help. Add defensive backs and keep two safeties deep, accepting a lighter front against the run.")

    # Keep the winning observation, then explain the tactical consequence. Avoid
    # concatenating every rejected stat line or claiming an adjustment paid off.
    observation = choice['why'].strip().rstrip('.')
    observation = observation[:1].upper() + observation[1:]
    response = None
    if key == 'hurry':
        response = "We need quicker scoring chances. Pick up the pace and throw more, accepting fewer runs and more risk to get back into the game."
    elif key == 'clock_control':
        response = "Make them spend time getting the ball back. Lean on the run and slow the pace; we can give up some attacking opportunities to protect the lead."
    elif choice['changes'].get('protection') in ('six', 'full_slide'):
        response = "Give the quarterback help and an earlier outlet. Sending more receivers out or waiting on longer routes asks the protection to hold up longer than we should."
    elif changes.get('box_bias', 0) > 0:
        response = "Commit another defender to the run and make their quarterback beat us. That leaves less help deep, but sitting back lets them keep leaning on the ground game."
    elif changes.get('shell_lean', 0) > 0 or changes.get('box_bias', 0) < 0:
        response = "Keep the safeties available for the deep routes instead of pulling them toward the line. We can concede a lighter box; biting on the run risks giving up the bigger play."
    elif changes.get('blitz', 0) > 0:
        response = "Make the quarterback release the ball sooner by sending extra pressure. Keeping everyone back gives us more coverage, but also gives his receivers longer to get open."
    elif changes.get('blitz', 0) < 0:
        response = "Keep more defenders behind the rush. Sending extra pressure would take away help where their offense is already finding room."
    elif changes.get('depth_deep', 0) < 0:
        response = "Give the quarterback earlier throws and keep the offense moving. The chance of a big play isn't worth asking him to keep waiting for deeper routes."
    elif changes.get('depth_deep', 0) > 0:
        response = "Take the opportunities downfield. Shortening everything would get the ball out sooner, but we'd be giving up the matchup we want to attack."
    elif changes.get('pass_bias', 0) < 0:
        response = "Lean on the ground game. Throwing more would give us extra chances through the air, but it would take carries away from the matchup we want."
    elif changes.get('pass_bias', 0) > 0:
        response = "Put more of the offense through the passing game. Running more would use more clock, but we'd be asking the ground game to carry too much of the offense."
    elif changes.get('zone_aggression', 0) > 0:
        response = "Contest the shorter routes instead of conceding easy throws underneath. That means accepting more risk behind the coverage."
    elif changes.get('man_rate', 0) > 0:
        response = "Trust our corners in the matchup. Giving them more zone help would take away some of the pressure we can put on the quarterback."
    elif changes.get('screen_boost', 0) < 0:
        response = "Stop spending plays on screens. They're meant to punish pressure, but we need another answer when they aren't producing."
    return observation + '.' + (' ' + response if response else '')


def resolve(candidates, limit=None, context=None):
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
            alternatives[winner].append(items[j])
    result = []
    # Preserve familiar display order, while making the decision order-independent.
    kept = {id(items[i]): i for i in picked}
    for original in candidates:
        i = kept.get(id(original))
        if i is None:
            continue
        row = {k: v for k, v in original.items() if k != '_priority'}
        if alternatives[i]:
            row['alternatives_weighed'] = [dict(text=a['text'], why=a['why']) for a in alternatives[i]]
            row['why'] = explain_choice(original, alternatives[i], context)
        result.append(row)
    return result
