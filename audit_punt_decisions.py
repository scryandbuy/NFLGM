"""Small paired game sample with observed fourth-down decision inputs."""
import argparse
import json
import inspect
from pathlib import Path
import numpy as np
import game
import league
import plays
import season
from calibrate import Collector


def run(output, seeds, checkpoints=()):
    original = game.fourth_down_decision
    signature = inspect.signature(original)
    decisions = []
    def observe(*args, **kwargs):
        values = signature.bind(*args, **kwargs)
        values.apply_defaults()
        row = dict(values.arguments)
        row.pop('rng'); row.pop('rate_fn')
        row['kick_mult'] = game.ENV.kick_mult
        row['kicker'] = dict(row['kicker'] or {})
        choice = original(*args, **kwargs)
        row['choice'] = choice
        decisions.append(row)
        return choice
    game.fourth_down_decision = observe
    collector = Collector()
    scores = []
    try:
        for index, seed in enumerate(seeds):
            if checkpoints:
                from session import Session
                lg = Session.load(Path(checkpoints[index]).read_text(encoding='utf8')).L
            else:
                lg = league.build_league(rng=np.random.default_rng(seed))
            runner = season.SeasonRunner(lg, np.random.default_rng(seed + 1000))
            teams = sorted(lg.teams)
            np.random.default_rng(seed).shuffle(teams)
            for home, away in zip(teams[::2], teams[1::2]):
                result = runner.play(home, away, 1)
                collector.add(result)
                scores.append([home, away, result['home'], result['away']])
                print(len(scores), home, result['home'], result['away'], away, flush=True)
    finally:
        game.fourth_down_decision = original
    metrics = collector.report('Punt decision sample')
    Path(output).write_text(json.dumps(dict(seeds=seeds, games=scores, metrics=metrics,
        decisions=decisions, drives=collector.drives_total), default=lambda x: x.item()), encoding='utf8')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--seeds', nargs='+', type=int, default=[4321, 4331])
    p.add_argument('--checkpoints', nargs='*', default=[])
    a = p.parse_args()
    run(a.out, a.seeds, a.checkpoints)
