"""Unsigned weekly asking-price adjustment, independent of trade valuation."""
from min_salary import player_minimum

WEEKLY_REDUCTION = .05

def factor(league, player):
    if league.phase != 'regular' or player.team or getattr(player, 'fa_class', None) in ('RFA', 'ERFA', 'tendered'):
        return 1.
    start = 1
    # Latest departure resets the clock, including on imported older saves.
    for tx in reversed(getattr(league, 'transactions', ())):
        if tx.get('pid') == player.pid and tx.get('kind') == 'release':
            if tx.get('year') == league.year and tx.get('phase') == 'regular':
                start = max(1, int(tx.get('week') or 1))
            break
    marker = (player.xp_spent or {}).get('_fa_demand_start')
    if marker and marker[0] == league.year:
        start = max(start, marker[1])
    weeks = max(0, min(18, int(league.week or 0)) - start)
    return (1. - WEEKLY_REDUCTION) ** weeks

def asking(league, player, baseline):
    return round(max(player_minimum(league, player),
                     float(baseline) * factor(league, player)), 3)
