"""Focused route-distance investigation; no tuning or engine mutations.

Uses current GB/DEN rosters, not the user's saved Week 5 roster. Counts are
diagnostic samples, not league calibration or a reproduction of that game.
"""
import json
from collections import Counter
from unittest.mock import patch

import numpy as np
import formations as F
import game as G
import playcall as PC
import plays as P
import rosters as R
import schemes as S


def sample(teams, distance, count=1000):
    rng = np.random.default_rng(930305 + distance)
    calls = Counter()
    outcomes = Counter()
    completions = []
    for _ in range(count):
        oc = S.call_offense(4, distance, -5, distance, rng, secs_left=38,
                            offense=teams['GB'], rate_fn=P.rate)
        calls['all'] += 1
        if not oc['is_pass']:
            calls['run'] += 1
            continue
        calls[oc['depth']] += 1
        calls['screen'] += int(oc['concept'] == 'screen')
        dc = S.call_defense(oc, 4, distance, rng, yards_to_endzone=distance,
                            defense=teams['DEN'], rate_fn=P.rate)
        off, _ = G.field_units(teams['GB'], None, rng, True, oc['personnel'])
        defense, _ = G.field_units(teams['DEN'], None, rng, False, dc['personnel'], dc.get('front_family'))
        result = P._pass_play(off, defense, oc, dc, distance, rng)
        outcomes[result['type']] += 1
        if result['type'] == 'complete':
            completions.append(result)
    return dict(distance=distance, calls=dict(calls), outcomes=dict(outcomes),
                completions=len(completions),
                completions_short=sum(p['yards'] < distance - .01 for p in completions),
                mean_completed_air=round(float(np.mean([p['air'] for p in completions])), 2),
                short_completion_reasons=dict(Counter(
                    f"{p.get('depth')}/{p.get('read')}" for p in completions
                    if p['yards'] < distance - .01)))


def distance_only_probe(teams):
    # Freeze alignment: down/distance currently reach this step. Then vary only
    # the distance needed, keeping the same field, call, coverage and random draws.
    align = F.align
    def same_alignment(*args, **kwargs):
        kwargs.update(down=4, ydstogo=11)
        return align(*args, **kwargs)
    identical = 0
    complete = 0
    with patch.object(F, 'align', side_effect=same_alignment):
        for seed in range(200):
            pair = []
            for need in (3, 16):
                rng = np.random.default_rng(seed)
                oc = dict(is_pass=True, personnel='11', depth='medium', concept='dagger',
                          down=4, ydstogo=need, play_action=False, shotgun=True)
                dc = S.call_defense(oc, 4, 11, rng, yards_to_endzone=30)
                pair.append(P._pass_play(teams['GB'], teams['DEN'], oc, dc, 30, rng))
            identical += int(pair[0] == pair[1])
            complete += int(pair[0]['type'] == 'complete')
    return dict(paired_snaps=200, identical_outcomes=identical, paired_completions=complete)


if __name__ == '__main__':
    teams = R.load_league()
    PC.calibrate_baselines(teams, P.rate)
    print(json.dumps(dict(samples=[sample(teams, 11), sample(teams, 16)],
                         distance_only=distance_only_probe(teams)), indent=2))
