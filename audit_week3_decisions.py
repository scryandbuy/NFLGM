"""Read-only probes for the user GB-CHI Week 3 log; not a saved-game replay."""
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import decisions as D
import events as E
import game as G


def run():
    out = {'limitations': 'Neutral context probes, not the user save or coach. '
           'Decision sweeps enumerate 1000 evenly spaced random thresholds. '
           'Penalty sampling is per check, not complete games; crowd/staff neutral.'}
    dr = G.Drive({}, {}, 58, 1845, 2, 3, np.random.default_rng(1))
    dr.down = 3; dr.togo = 16
    tos = G.Timeouts(); tos.left = {'home': 3, 'away': 1}
    out['halftime_timeouts'] = {}
    for label, plan in [('none', None), ('hurry', {'choice': 'play', 'hurry': True})]:
        out['halftime_timeouts'][label] = G._timeout_call(
            dr, 'complete', {'yards': 12}, tos, 'away', 1800, 45, plan=plan)
    out['ordinary_completion_seconds'] = G.play_seconds('complete')
    out['decision_draws'] = {}
    for aggression in (0., .5, 1.):
        for label, y, need, lead, secs, half in [
            ('halftime', 46, 4, 3, 1811, 11),
            ('late_goal', 2, 2, 7, 108, None),
        ]:
            out['decision_draws'][f'{label}_{aggression}'] = dict(Counter(
                G.fourth_down_decision(y, need, lead, secs,
                    NS(random=lambda v=v: v), aggression=aggression,
                    half_seconds_left=half, is_home=0, timeout_edge=2)
                for v in np.linspace(.0005, .9995, 1000)))
    out['late_goal_values'] = D.fourth_down(7, 108, 2, 2,
        fg_prob=G.fg_probability(19), is_home=0, timeout_edge=2)
    out['delay_checks'] = []
    for awareness in (.6, .787, .9):
        discipline = float(np.clip(.70 + .8 * (awareness - .787), .5, .9))
        probability = .581 / E.SCRIMMAGE_PLAYS_PER_GAME * (1 + 1.6 * (.7 - discipline))
        rng = np.random.default_rng(130); count = 0; trials = 40000
        for _ in range(trials):
            flag = E.penalty_check(rng, discipline=discipline, noise=1., hurry=False)
            count += bool(flag and flag['penalty'] == 'Delay of Game')
        out['delay_checks'].append(dict(defensive_awareness=awareness,
            discipline=discipline, trials=trials, observed_delays=count,
            expected_delays=probability * trials,
            expected_in_66_checks=probability * 66))
    return out


if __name__ == '__main__':
    path = Path(__file__).with_suffix('.json')
    path.write_text(json.dumps(run(), indent=2), encoding='utf-8')
    print(path.name)
