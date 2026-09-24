"""
GM decision surfaces, part two.

Everything here came out of the research and had nowhere to live yet. As with
gm.py, NOTHING HERE ACTS. Each function answers a question; the acting is done
elsewhere by whoever is running the league year.

Sources for the non-obvious parts are named inline, because several of these
numbers are real CBA mechanics rather than anything I chose.
"""
import numpy as np

CAP = 301.0
GAMES = 17

# ================================================================ franchise tag
# The tag is not primarily a bridge to a long-term deal. Agents describe clubs
# "squatting on their clients for a year, using the tag more as a means of
# protecting an asset than as an actual trigger for a long-term deal." So the
# real question a GM answers is: do I want to DEFER this decision?
def tag_decision(player, val, tag_cost, cap_space, gm, team):
    """
    Returns the ranked options. 'defer' means tag him and shelve the extension;
    'bridge' means tag him intending to get a deal done before July 15.
    """
    g = gm.shift(team)
    worth = val['apy']
    out = {}
    if tag_cost > cap_space:
        return {'let_walk': 1.0}
    # Most tagged players are NOT extended - clubs squat on the asset. Deferring
    # is the DEFAULT, not the fallback, and the first build had extend_now
    # systematically cheapest so every archetype extended.
    out['defer'] = (worth - tag_cost) * 1.0 + 3.2 + (1.0 - g.patience) * 2.4 + g.risk * 1.8
    # tag with intent to get a deal done before July 15
    out['bridge'] = (worth - tag_cost) * 1.10 + 1.4 + g.patience * 2.2
    # extend now, no tag. A long commitment, so it costs conviction, not less money.
    out['extend_now'] = ((worth - tag_cost) * 1.15 + g.patience * 3.0
                         - g.risk * 2.2 - (1.0 - g.contract_focus) * 1.0)
    out['let_walk'] = (tag_cost - worth) * 0.9 + g.contract_focus * 1.5
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))

JULY_15 = 'no multi-year deal is possible after this date; one year only'

def tag_relief_per_missed_week(tag_cost):
    """
    A tagged, unsigned player cannot be fined for missing camp - he has no
    contract - and the club gets 1/18th of the tender back for each regular
    season week he sits out. Le'Veon Bell sat a full year in 2018; before him
    nobody had in twenty years, so this should be rare and possible.
    """
    return round(tag_cost / 18.0, 3)

def holdout_chance(player_gap, morale, trust=1.0):
    """
    player_gap: how far the offer sits below what he believes he is worth, 0-1.
    Holding out is rare. It needs a real gap AND a player already unhappy.
    """
    if player_gap < 0.18: return 0.0
    base = (player_gap - 0.18) * 0.55
    unhappy = max(0.0, (50 - morale) / 50.0)
    return float(np.clip(base * (0.35 + 1.3 * unhappy) * (1.6 - 0.6 * trust), 0.0, 0.55))

# ================================================================ early extension
# "The team shouldn't want to get into a situation next year where they have to
# fall back on the franchise tag." Injury risk is the reason BOTH sides deal.
def extend_early_value(player, val, gm, team, tag_cost):
    """
    Worth extending a year early? He gets security now, you avoid the tag and
    lock a price before he gets more expensive. Both sides are hedging injury.
    """
    g = gm.shift(team)
    rising = max(0.0, (27 - player['age']) / 6.0)          # he will cost more later
    injury_hedge = (1.0 - player.get('availability', 1.0)) * 1.4
    tag_avoided = max(0.0, tag_cost - val['apy']) * 0.8
    discount = val['apy'] * (0.06 + 0.10 * rising)          # he takes less for certainty
    return round(float(rising * 4.0 * g.patience + tag_avoided + discount
                       - injury_hedge * (1.4 - g.risk) * 2.0), 2)

# ================================================================ deadline posture
# Four executives asked the same week gave four different answers about whether
# the deadline would be active. The structural reason: with 14 playoff spots,
# most teams do not believe they are out of it. HOLDER is the default.
def deadline_posture(team, gm, week=9):
    """
    Returns (posture, conviction). Most teams hold. Two-win teams can buy; a
    one-win team was floated as a buyer in a real season.
    """
    g = gm.shift(team)
    w = team['win_pct']
    playoff_hope = float(np.clip((w - 0.30) / 0.30, 0.0, 1.0))   # 14 of 32 make it
    buy = playoff_hope * (0.6 + 0.8 * g.aggression) - (1.0 - g.pick_lens) * 0.35
    sell = (1.0 - playoff_hope) * (0.42 + 0.75 * g.patience) + (1.0 - g.pick_lens) * 0.22
    # HOLDING is the default posture, not a tiebreak. With 14 playoff spots most
    # clubs do not believe they are out of it, which is exactly why there are
    # always "too few sellers". The first build had everyone selling at 3-6.
    hold = 0.80 + 0.30 * (1.0 - abs(playoff_hope - 0.5) * 2)
    if g.job_security < 0.35: sell *= 0.45; buy *= 1.35          # cannot afford next year
    scores = {'buy': buy, 'sell': sell, 'hold': hold}
    top = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    return top, round(float(ordered[0] - ordered[1]), 3)

def asking_price_multiplier(gm, team, posture):
    """
    Sellers sit on assets. The Jets were described as "stubborn" with their
    asking prices in a season they plainly should have sold.
    """
    g = gm.shift(team)
    if posture != 'sell': return 1.0
    return round(float(1.0 + g.own_bias - 1.0 + (1.0 - g.aggression) * 0.45), 3)

# ================================================================ waivers
# Fewer than four accrued seasons: waived, and the CONTRACT COMES WITH HIM.
# Four or more: released outright as a free agent, until the trade deadline
# passes, after which everyone goes through waivers.
def subject_to_waivers(accrued_seasons, past_trade_deadline=False):
    return past_trade_deadline or accrued_seasons < 4

def waiver_order(prev_standings, week=None):
    """
    Draft order through week 3, then reverse standings. A team does NOT lose
    its place by claiming - unlike fantasy.
    """
    return list(prev_standings)      # caller supplies the already-sorted order

def claim_value(player, val, gm, team):
    """
    A claim is a valuation decision under a priority constraint you do not
    control. You inherit the salary, so a bad contract is a real deterrent.
    """
    g = gm.shift(team)
    cost = float(player.get('cost', player.get('apy', 0.0)) or 0.0)
    v = val['apy'] - cost * (0.6 + 0.9 * g.contract_focus)
    return round(float(v), 2)

def protect_young_player_by_cutting_veteran(young, veteran):
    """
    The real tactic: a club worried about losing a young player on waivers
    releases a VESTED VETERAN on the bubble instead, because the veteran is not
    subject to waivers and can be brought straight back on the practice squad.
    Returns True if that swap is available.
    """
    return (young.get('accrued', 0) < 4) and (veteran.get('accrued', 0) >= 4)

# ================================================================ practice squad
PS_SIZE = 16
PS_VET_SLOTS = 6            # six may be veterans with no limit on accrued seasons

def ps_poach_cost(player, val, gm, team):
    """
    Poaching is open, but a poached man must go straight onto the 53 AND be
    active for at least three games. That is the price that stops it being free.
    """
    g = gm.shift(team)
    roster_cost = 2.2                      # you must cut someone to make room
    forced_active = 1.4                    # three games you may not want to give
    return round(float(val['apy'] - roster_cost - forced_active * (1.0 - g.aggression)), 2)

# ================================================================ trade then cut
# "The 49ers couldn't find any takers on Ahmad Brooks before letting him go."
# A cut is the FALLBACK when the trade market says zero.
def disposal_path(player, val, gm, team, market_interest):
    """
    market_interest: 0-1, how much the league wants him.
    Order of operations, not a single choice.
    """
    g = gm.shift(team)
    if market_interest > 0.35 and (player['cost'] - player['dead']) > 0:
        return 'shop_first'
    if (player['cost'] - player['dead']) <= 0:
        return 'uncuttable_keep'
    return 'cut'
