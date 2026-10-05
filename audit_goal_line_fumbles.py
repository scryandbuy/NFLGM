"""Bounded opportunity study, not a season calibration or new rate fit."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import game as G


def run(n=10000):
    off = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
               wr=[dict(pid='wr', pos='WR')], te=[], ol=[dict(pid='c', pos='C')])
    deff = dict(dl=[dict(pid='edge', pos='LEDG')], lb=[dict(pid='lb', pos='MIKE')], db=[dict(pid='cb', pos='CB')])
    rows = {}
    cases = dict(contact_score=dict(type='run', yards=3, carrier_pid='rb',
                    pre_goal_contact_yards=2, pre_goal_contact_by='edge'),
                 untouched_score=dict(type='run', yards=3, carrier_pid='rb'),
                 end_zone_catch=dict(type='complete', yards=3, target='wr'),
                 stopped_at_one=dict(type='run', yards=2, carrier_pid='rb', tackler='lb'))
    for name, template in cases.items():
        tally = dict(opportunities=n, fumbles=0, lost=0, touchbacks=0,
                     offensive_recovery_td=0, resulting_td=0)
        for seed in range(n):
            out = copy.deepcopy(template)
            dr = NS(yardline=3., down=1, clock=600., quarter=1)
            G._prepare_scoring_play(dr, out)
            G._prepare_fumble(dr, out, off, deff, np.random.default_rng(seed), lambda *a:.7)
            G._prepare_scoring_play(dr, out)
            for key, flag in [('fumbles','fumble'), ('lost','fumble_lost'), ('touchbacks','touchback'),
                              ('offensive_recovery_td','offensive_fumble_td'), ('resulting_td','touchdown')]:
                tally[key] += int(bool(out.get(flag)))
            assert not (out.get('touchback') and out.get('touchdown'))
            assert not (out.get('offensive_fumble_td') and out.get('fumble_lost'))
            if out.get('fumble_out_of_bounds'): assert not out.get('fumble_recovered_by')
        rows[name] = tally
    return rows


if __name__ == '__main__':
    result = run()
    path = Path('research/goal_line_opportunities_20261005.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
