"""Player consent for one-year minimum-pay roster repairs.

This does not choose a GM's acquisitions. A willing player's roster value,
funding and alternatives still go through the existing team decision paths.
"""
import copy
from cap_engine import CAP
import min_salary as MS


def minimum_acceptance(league, team, player, *, pool=None):
    import practice_squad as PS
    if player.team is not None:
        # Squad callups/poaches already use the active-minimum agreement.
        return dict(accepts=True, reason='squad_active_contract')
    if PS.shunned(player, team.abbr, league):
        return dict(accepts=False, reason='recent_release')
    import valuation as VAL
    import contract_offer as CO
    import contract_offer_model as MODEL
    salary = MS.minimum_salary(player.accrued or 0, CAP.get(league.year, 301.2))
    quote = VAL.value_player(league, player, side='agent', pool=pool)
    # Use the existing final-wave reservation price. No rating cutoff: a
    # player's actual positional market, age and preferences decide consent.
    ask = max(salary, .55 * quote['apy']) if quote else salary
    # A declined preview must not mutate a free agent or the saved game.
    # profile_for deterministically initializes missing preferences by ID.
    preview = copy.copy(player)
    preview.xp_spent = dict(player.xp_spent or {})
    profile = CO.profile_for(preview)
    beliefs = MODEL.beliefs_from_profile(player, ask, profile)
    # Compare equal one-year, zero-bonus packages on annual terms. Prorating
    # both to zero at Week18 would otherwise make every player "free" to sign.
    result = MODEL.compare(MODEL.OfferCash((salary,), 0.),
                           MODEL.OfferCash((ask,), 0.), beliefs)
    return dict(accepts=result['acceptable'], reason='minimum_accepted' if
                result['acceptable'] else 'seeking_market_contract',
                annual_offer=salary, annual_ask=ask, ratio=result['ratio'])
