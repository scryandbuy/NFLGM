"""
HOW A CLUB SPENDS ITS PLAYERS' XP.

Runs at the weekly advance for every AI club, and for any of the user's
players with auto-spend on. XP belongs to the man who earned it, so the
club's choices are about HIM: what to buy, whether to buy a physical,
whether to hold the money for a ceiling unlock.

WHAT TO BUY. Not the single best point. Each attribute in his position's
weight set is drawn with a probability that leans toward weight per XP and
toward the holes in his own profile (his lowest attributes in that set get a
bonus), so he fills out rather than stacking one skill to 99. The GM's
dev_belief sets how sharp that lean is: a believer spreads, a sceptic buys
the sure thing. Physicals enter the draw for men 26 and under at a rate set
by the same belief, and never for anyone older.

WHEN TO SAVE. Only for a ceiling unlock, and only when it is within reach:
the club holds XP when the man is at his ceiling, the GM's patience says he
cares about later, and what the man earns in a month or so would cover the
unlock. A contender in the hunt does not save; the points go on the field
this week. A club out of it saves for its young men.

Nothing here moves a rating except xp.buy and xp.unlock.
"""
import numpy as np
import xp as XP
import targets as TG

YOUNG = 26            # physicals are bought for men this age and under
SAVE_WEEKS = 4        # an unlock within this many weeks of earning is worth saving for


def situation(team, week):
    """Where the club is: 0 = out of it, 1 = contending. Early in the year
    everyone is alive."""
    w, l, t = team.record
    g = w + l + t
    if g < 4:
        return 0.6
    pct = (w + 0.5 * t) / g
    # from .300 to .650 maps onto 0..1
    return float(np.clip((pct - 0.30) / 0.35, 0.0, 1.0))


def _weekly_rate(player):
    """What he has been earning a week this season, from the ledger."""
    led = player.xp_spent.get('_earned', {})
    weeks = max(1, player.xp_spent.get('_weeks', 1))
    return (led.get('game', 0.0) + led.get('snaps', 0.0)) / weeks


def choose_attr(player, gm, rng):
    """One attribute, drawn. None if nothing is buyable."""
    w = TG.DEPTH_WEIGHTS.get(player.pos)
    if not w:
        return None
    belief = getattr(gm, 'dev_belief', 0.5)
    keys, weights = [], []
    vals = {k: player.ratings.get(k, 70.0) for k in w}
    lo, hi = min(vals.values()), max(vals.values())
    for k, wt in w.items():
        if vals[k] >= 99.0:
            continue
        if k in XP.PHYSICAL and player.age > YOUNG:
            continue
        v = wt / XP.cost_per_point(player, k)         # overall per XP
        # a hole in his own profile: up to +60% for his lowest attribute,
        # scaled by how much the GM believes in filling men out
        if hi > lo:
            v *= 1.0 + 0.6 * belief * (hi - vals[k]) / (hi - lo)
        if k in XP.PHYSICAL:
            # The price already says most of it: at 2.5x a physical draws at
            # under half a skill's rate on weight per XP alone, and with the
            # old 0.35-1.0 factor on top the league bought 13 physical points
            # in 3,700. This puts a young man's speed back in the draw at a
            # believer's club without making it a habit.
            v *= 0.7 + 1.1 * belief
        elif k == 'awareness_rating':
            v *= 1.4
        keys.append(k); weights.append(v)
    if not keys:
        return None
    p = np.array(weights) ** (1.0 + 2.0 * (1.0 - belief))   # sceptics sharpen toward the best buy
    p /= p.sum()
    return keys[int(rng.choice(len(keys), p=p))]


def spend_player(player, gm, team, week, rng, verbose=False):
    """Spend one man's XP this week. Returns a list of (kind, attr, cost)."""
    out = []
    if player.xp <= 0:
        return out
    patience = getattr(gm, 'patience', 0.5)
    sit = situation(team, week)
    guard = 0
    # a physical he decided to save for last week comes first, and is held
    # for until it is bought or he ages out of buying physicals
    target = player.xp_spent.get('_saving_for')
    if target:
        if player.age > YOUNG:
            player.xp_spent.pop('_saving_for', None)
        elif XP.buy(player, target) is not None:
            out.append(('buy', target, XP.cost_per_point(player, target)))
            player.xp_spent.pop('_saving_for', None)
        else:
            out.append(('save', target, XP.cost_per_point(player, target) - player.xp))
            return out
    while guard < 200:
        guard += 1
        if XP.at_ceiling(player):
            cost = XP.unlock_cost(player)
            if cost is None:
                break
            if player.xp >= cost:
                XP.unlock(player); out.append(('unlock', None, cost)); continue
            # SAVE, or not. Worth it if he could cover it soon and the club
            # cares about later; a contender would rather have nothing than
            # wait, but at the ceiling there is nothing else to buy anyway.
            weeks_needed = (cost - player.xp) / max(_weekly_rate(player), 1.0)
            if weeks_needed <= SAVE_WEEKS * (0.5 + patience) * (1.5 - sit):
                out.append(('save', None, cost - player.xp))
            break
        attr = choose_attr(player, gm, rng)
        if attr is None:
            break
        cost = XP.buy(player, attr)
        if cost is None and attr in XP.PHYSICAL:
            # He drew speed and cannot afford it this week. XP arrives at a
            # thousand or two a week and was spent down as it came, so a
            # 2.5x point was never affordable at the moment it was drawn:
            # 17 physical points bought in 3,700. If a week or two covers it,
            # the club holds the money and buys it then.
            need = XP.cost_per_point(player, attr) - player.xp
            if need / max(_weekly_rate(player), 1.0) <= 2.0 * (0.5 + patience):
                player.xp_spent['_saving_for'] = attr
                out.append(('save', attr, need))
                break
        if cost is None:
            # could not afford the drawn attribute; try the cheapest skill
            cheap = min((k for k in TG.DEPTH_WEIGHTS[player.pos] if player.ratings.get(k, 70) < 99
                         and not (k in XP.PHYSICAL and player.age > YOUNG)),
                        key=lambda k: XP.cost_per_point(player, k), default=None)
            cost = XP.buy(player, cheap) if cheap else None
            if cost is None:
                break
            attr = cheap
        out.append(('buy', attr, cost))
    return out


def spend_week(league, week, rng, user_team=None, verbose=False):
    """Every AI club, and the user's auto-spend men. Returns {pid: actions}."""
    log = {}
    for abbr, team in league.teams.items():
        gm = team.gm
        for p in team.roster:
            if p.retired:
                continue
            p.xp_spent['_weeks'] = p.xp_spent.get('_weeks', 0) + 1
            if abbr == user_team and not p.xp_spent.get('_auto'):
                continue
            acts = spend_player(p, gm, team, week, rng)
            if acts:
                log[p.pid] = acts
    return log


def set_auto(player, on=True):
    """The user's per-player toggle."""
    player.xp_spent['_auto'] = bool(on)
