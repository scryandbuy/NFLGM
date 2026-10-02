"""Bounded scenario matrix for the isolated contract-security experiment."""
import json
from collections import Counter
from itertools import product
from pathlib import Path
from dataclasses import replace
import contract_offer_model as M
from test_contract_offer_model import flat


def probe():
    counts = Counter()
    examples = []
    rows = []
    for age, pos, security, money, growth, offset in product(
            (23, 27, 31, 35), ('QB', 'HB', 'WR', 'LT'), (0., .5, 1.),
            (.2, .8), (0., .06), (0, 1, 2)):
        beliefs = M.PlayerBeliefs(age, pos, 20, security, money, growth)
        reference = flat(2, 20, .2, offset)
        for apy, share in product((18., 19., 20.), (.0, .2, .5, .75)):
            offer = flat(5, apy, share, offset)
            result = M.compare(offer, reference, beliefs)
            row = dict(age=age, pos=pos, security=security, money=money,
                       growth=growth, starts_in=offset, apy=apy, bonus_share=share,
                       acceptable=result['acceptable'], value_gap=round(result['value_gap'], 6))
            rows.append(row)
            counts['comparisons'] += 1
            counts['accepted'] += result['acceptable']
            if apy < 20 and result['acceptable']:
                counts['discounted_accepted'] += 1
                counts[f'discounted_accepted_security_{security}'] += 1
                if share == 0: counts['zero_bonus_discounted_accepted'] += 1
            if (age, pos, money, growth, offset, apy) == (27, 'WR', .2, 0., 0, 19.):
                examples.append(row)
    sensitivity = Counter()
    horizon_checks = Counter()
    for age, pos, sec, growth, apy, share in product(
            (23, 27, 31, 35), ('QB', 'HB', 'WR', 'LT'), (0., .5, 1.),
            (0., .06), (18., 19., 20.), (.0, .2, .5, .75)):
        b = M.PlayerBeliefs(age, pos, 20, sec, .5, growth)
        a, ref = flat(5, apy, share), flat(2, 20, .2)
        outcomes = [M.compare(a, ref, replace(b, cap_growth=g))['acceptable'] for g in (0., .04, .08)]
        sensitivity['comparisons'] += 1
        sensitivity['forecast_changes_decision'] += len(set(outcomes)) > 1
        try:
            scores = []
            for horizon in (7, 9, 12):
                M.HORIZON = horizon
                scores.append(M.compare(a, ref, b)['value_gap'])
            horizon_checks['comparisons'] += 1
            horizon_checks['extra_common_years_change_value_gap'] += max(scores) - min(scores) > 1e-9
        finally:
            M.HORIZON = 9
    return dict(status='Isolated integration candidate; constructed economic scenarios', counts=dict(counts),
                sensitivity=dict(sensitivity), horizon_checks=dict(horizon_checks), examples=examples, rows=rows)


if __name__ == '__main__':
    report = probe()
    output = Path(__file__).resolve().parents[2] / 'outputs' / 'contract-security-model-matrix.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
