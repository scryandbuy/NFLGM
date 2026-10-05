"""Controlled saved-roster passing audit; no save or production changes.

Run this same file with --engine BASELINE_CHECKOUT and --engine NEW_CHECKOUT.
Independent fixed snap seeds, real saved personnel and coach calls; no season
projection. Candidate routes count only plays reaching target selection, not
routes on earlier sacks/scrambles. Injuries are frozen at saved availability.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', default=str(Path(__file__).parent))
    ap.add_argument('--save', required=True)
    ap.add_argument('--snaps', type=int, default=1000)
    ap.add_argument('--output')
    args = ap.parse_args()
    sys.path.insert(0, args.engine)
    import numpy as np
    import game as G
    import plays as P
    import rosters as R
    import schemes as S
    import targets as T
    import playcall as PC

    data = json.loads(Path(args.save).read_text(encoding='utf-8'))
    players = data['players']
    def roster(abbr, variant='normal', star=None):
        team = data['teams'][abbr]
        rows = []
        for pid in team['roster']:
            p = players[pid]
            if p.get('out_until') is not None or (variant == 'injured' and pid == star):
                continue
            ratings = dict(p['ratings'])
            if variant == 'equal_wr' and p['pos'] == 'WR':
                ratings = dict(players[star]['ratings'])
            rows.append(dict(ratings, pid=pid, pos=p['pos'], traits=p.get('traits') or {}))
        return R.build_roster_rows(rows, team['scheme'], pins=team.get('depth_pins'),
                                  front=team['gm'].get('def_front', '4-3'), box=team['gm'].get('box', .5))
    all_rosters = {t: roster(t) for t in data['teams']}
    PC.calibrate_baselines(all_rosters, P.rate)
    cases = [('SEA','normal','P2265'), ('SEA','bracket','P2265'),
             ('SEA','equal_wr','P2265'), ('SEA','injured','P2265'),
             ('CIN','normal','P0554'), ('CIN','bracket','P0554'),
             ('DAL','normal','P0717')]
    output = []
    for team, variant, star in cases:
        offense = roster(team, variant, star)
        targets, routes, catches, yards, outcomes = Counter(), Counter(), Counter(), Counter(), Counter()
        concepts = Counter()
        original = T.select_target
        def trace(pairs, *a, **kw):
            routes.update(p['receiver'].get('pid') for p in pairs)
            return original(pairs, *a, **kw)
        gm = SimpleNamespace(**data['teams'][team]['gm'])
        with patch.object(T, 'select_target', side_effect=trace):
            for i in range(args.snaps):
                rng = np.random.default_rng(739100 + i)
                opp = ('MIN', 'CAR', 'BUF', 'GB')[i % 4]
                defense = all_rosters[opp]
                dgm = SimpleNamespace(**data['teams'][opp]['gm'])
                down, need, spot = (1,10,65) if i%3==0 else ((2,7,45) if i%3==1 else (3,6,25))
                # Sample the coach's passing calls; this audit holds pass volume
                # constant and does not estimate the coach's run/pass ratio.
                for _ in range(100):
                    oc = S.call_offense(down, need, 0, spot, rng, gm=gm,
                                        secs_left=1800, offense=offense, rate_fn=P.rate)
                    if oc['is_pass']:
                        break
                dc = S.call_defense(oc, down, need, rng, gm=dgm,
                                   yards_to_endzone=spot, defense=defense, rate_fn=P.rate)
                if variant == 'bracket':
                    dc['bracket'] = star
                off, _ = G.field_units(offense, None, rng, True, oc['personnel'])
                deff, _ = G.field_units(defense, None, rng, False, dc['personnel'], dc.get('front_family'))
                result = P._pass_play(off, deff, oc, dc, spot, rng)
                concepts[oc['concept']] += 1
                outcomes[result['type']] += 1
                pid = result.get('target')
                if pid:
                    targets[pid] += 1
                    if result['type'] == 'complete':
                        catches[pid] += 1
                        yards[pid] += result.get('yards', 0)
        assigned = sum(targets.values())
        attempts = sum(outcomes[k] for k in ('complete', 'incomplete', 'drop', 'interception'))
        output.append(dict(team=team, variant=variant, snaps=args.snaps,
            attempts=attempts, assigned_targets=assigned, outcomes=dict(outcomes), concepts=dict(concepts),
            completion_pct=round(100*sum(catches.values())/max(1,attempts),2),
            receiving_yards_per_attempt=round(sum(yards.values())/max(1,attempts),3),
            players=[dict(pid=pid,name=players[pid]['name'],pos=players[pid]['pos'],
                targets=targets[pid],assigned_share=round(100*targets[pid]/max(1,assigned),2),share=round(100*targets[pid]/max(1,attempts),2),
                candidate_routes=routes[pid],targets_per_candidate_route=round(targets[pid]/max(1,routes[pid]),3),
                catches=catches[pid],yards=round(yards[pid],1))
                for pid in sorted(set(routes)|set(targets), key=lambda p:targets[p], reverse=True)]))
    result = dict(engine=str(Path(args.engine).resolve()), seed_start=739100,
                  limitations=__doc__, cases=output)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
    else:
        print(text)


if __name__ == '__main__':
    main()
