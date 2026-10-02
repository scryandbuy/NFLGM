"""Summarize GM decision quality from a completed franchise audit.

This is a diagnostic report, not a pass/fail balance gate. It reads the
observations written by audit_financial_franchise.py and never advances a save.
"""
import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import trade_engine as TE


PICK = re.compile(r"year=(\d+), round=(\d+).*?selection=(\d+|None)")
CORE_NATIVE = ('QB', 'LT', 'LG', 'C', 'RG', 'RT', 'K', 'P', 'LS')


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _pick_price(asset, current_year, cap):
    if not isinstance(asset, str):
        return None
    match = PICK.search(asset)
    if not match or match.group(3) == 'None':
        return None
    earned_year, _round, selection = map(int, match.groups())
    years_out = max(0, earned_year - (current_year - 1))
    return TE.pick_price_dollars(selection, years_out, cap=cap)


def report(folder):
    folder = Path(folder)
    snapshots = json.loads((folder / 'snapshots.json').read_text())
    events = _lines(folder / 'events.jsonl')
    moves = _lines(folder / 'moves.jsonl')
    openings = [row for row in snapshots if row['label'] in ('initial_cutdown', 'end_offseason')]
    opening_rows = []
    by_year = {}
    cap_by_year = {}
    for row in openings:
        teams = row['teams']
        by_year[row['year']] = {team['team']: team for team in teams}
        cap_by_year[row['year']] = teams[0]['cap']
        opening_rows.append(dict(
            year=row['year'], mean_score=round(statistics.mean(t['score'] for t in teams), 3),
            min_score=round(min(t['score'] for t in teams), 3),
            mean_ovr=round(statistics.mean(t['mean_ovr'] for t in teams), 3),
            native_zeros=[dict(team=t['team'], positions=[p for p in CORE_NATIVE
                         if t['counts'].get(p, 0) == 0]) for t in teams
                          if any(t['counts'].get(p, 0) == 0 for p in CORE_NATIVE)],
            uncovered_teams=[t['team'] for t in teams if t['uncovered']],
        ))
    opening_changes = []
    for old_year, new_year in zip(sorted(by_year), sorted(by_year)[1:]):
        old, new = by_year[old_year], by_year[new_year]
        changes = [dict(team=abbr, score_delta=round(new[abbr]['score'] - old[abbr]['score'], 3),
                        ovr_delta=round(new[abbr]['mean_ovr'] - old[abbr]['mean_ovr'], 3))
                   for abbr in old]
        opening_changes.append(dict(from_year=old_year, to_year=new_year,
                                    declined=sum(x['score_delta'] < 0 for x in changes),
                                    worst=sorted(changes, key=lambda x: x['score_delta'])[:5]))

    ordinary = [m for m in moves if m['action'] == 'trade' and m['stage'] == 'trades.run']
    draft = [m for m in moves if m['action'] == 'trade' and m['stage'] == 'step_draft']
    buyer_deltas = []
    trade_rows = []
    for move in ordinary:
        buyer = next(iter(move['assets']))
        delta = move['after'][buyer]['score'] - move['before'][buyer]['score']
        buyer_deltas.append(delta)
        if delta <= 0:
            trade_rows.append(dict(year=move['year'], week=move['week'], buyer=buyer,
                                   delta=round(delta, 3)))
    decisions = [e for e in events if e['kind'] == 'ai_trade_decision']
    near_floor = sum(-1e-6 <= e['package_market'] - e['market_floor'] <= .050001
                     for e in decisions)
    negative_belief = sum(e['buyer_gain'] < 0 or e['seller_gain'] < 0 for e in decisions)

    pure_pick = []
    for move in draft:
        buyer, seller = list(move['assets'])
        sent = move['assets'][buyer]
        received = move['assets'][seller]
        cap = cap_by_year.get(move['year'], TE.CAP)
        sent_prices = [_pick_price(x, move['year'], cap) for x in sent]
        received_prices = [_pick_price(x, move['year'], cap) for x in received]
        if any(x is None for x in sent_prices + received_prices):
            continue
        value_in = sum(received_prices)
        if value_in <= 0:
            continue
        pure_pick.append(dict(year=move['year'], buyer=buyer, seller=seller,
                              sent=round(sum(sent_prices), 2), received=round(value_in, 2),
                              ratio=round(sum(sent_prices) / value_in, 4)))

    same_week_flips = []
    acquired = {}
    for move in ordinary:
        a, b = list(move['assets'])
        for outgoing, receiving in ((a, b), (b, a)):
            for asset in move['assets'][outgoing]:
                if not isinstance(asset, dict):
                    continue
                pid = asset['pid']
                previous = acquired.get(pid)
                if previous and previous[:3] == (outgoing, move['year'], move['week']):
                    same_week_flips.append(dict(pid=pid, team=outgoing, year=move['year'],
                                                week=move['week']))
                acquired[pid] = (receiving, move['year'], move['week'])

    extensions = [e for e in events if e['kind'] == 'extension']
    signs = [e for e in events if e['kind'] == 'sign'
             and str(e.get('audit_stage', '')).startswith('step_fa_')]
    result = dict(
        methodology=json.loads((folder / 'methodology.json').read_text()),
        opening_rosters=opening_rows, opening_changes=opening_changes,
        ordinary_trades=dict(count=len(ordinary), buyer_score_median=round(statistics.median(buyer_deltas), 3)
                             if buyer_deltas else None, buyer_nonpositive=trade_rows,
                             negative_belief=negative_belief, near_market_floor=near_floor,
                             same_week_acquired_player_flips=same_week_flips),
        draft_trades=dict(count=len(draft), priced_pure_pick_count=len(pure_pick),
                          below_half_market=[row for row in pure_pick if row['ratio'] < .5],
                          median_pure_pick_ratio=round(statistics.median(row['ratio'] for row in pure_pick), 4)
                          if pure_pick else None),
        extensions_by_year=dict(Counter(str(e['year']) for e in extensions)),
        free_agency_signs_by_year=dict(Counter(str(e['year']) for e in signs)),
    )
    (folder / 'decision_quality.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    print(json.dumps(report(parser.parse_args().folder), indent=2))
