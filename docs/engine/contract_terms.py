"""Stable veteran term preferences, separate from salary and bonus proration.

Weights are gameplay distributions around contract_structure's observed market
tiers, not claimed league frequencies. Keep a spread instead of rounding every
player's comparable deals to the same two/three-year mean.
"""
import hashlib
import math
import contract_structure as CS

MAX_OFFER_YEARS = 7  # Existing game offer limit, not an NFL rule.
TERM_WEIGHTS = {
    'min': (.80, .17, .03, 0, 0, 0, 0),
    'depth': (.22, .50, .24, .04, 0, 0, 0),
    'starter': (.08, .20, .43, .23, .06, 0, 0),
    'core': (.02, .08, .32, .38, .20, 0, 0),
    'elite': (0, .03, .17, .43, .37, 0, 0),
}


def preferred_years(player, season, apy, cap, *, extension=False, comp_years=None):
    """Read-only draw keyed to player/season; never consume the simulation RNG.

    Extension years are NEW years after the existing term, not total control.
    Age/position restrict the tail; young franchise QBs can seek six/seven.
    """
    pos, age = player.pos, float(player.age)
    grade = float(player.ovr)
    weights = list(TERM_WEIGHTS[CS.tier_of(apy, cap)])
    if pos == 'QB' and grade >= 88 and age <= 30 and extension:
        weights = [.01, .02, .12, .23, .43, .16, .03]
    end_age = (39 if pos == 'QB' else 40 if pos in ('K', 'P', 'LS') else
               30 if pos in ('HB', 'FB') else 35 if pos in ('LT', 'LG', 'C', 'RG', 'RT', 'TE') else
               32 if pos in ('WR', 'CB') else 34)
    left = int(getattr(getattr(player, 'contract', None), 'years', 0)) if extension else 0
    max_years = min(MAX_OFFER_YEARS, max(1, int(end_age - age + 1 - left)))
    if pos in ('HB', 'FB'): max_years = min(max_years, 4)
    traits = getattr(player, 'traits', None) or {}
    loyalty = float(traits.get('loyalty', 50)) / 100
    money = float(traits.get('financial_priority', 50)) / 100
    for i in range(len(weights)):
        years = i + 1
        if years > max_years:
            weights[i] = 0
            continue
        # Actual comparable terms remain a mild anchor; they do not erase tails.
        if comp_years is not None and math.isfinite(float(comp_years)):
            weights[i] *= math.exp(-abs(years - float(comp_years)) / 5)
        weights[i] *= max(.5, 1 + (loyalty - money) * (years - 3) * .12)
        if extension and age <= 28 and grade >= 85 and years >= 4:
            weights[i] *= 1.25
    total = sum(weights)
    if total <= 0: return 1
    identity = getattr(player, 'pid', getattr(player, 'name', 'player'))
    digest = hashlib.sha256(f'term-v1|{identity}|{season}|{int(extension)}'.encode()).digest()
    ticket = int.from_bytes(digest[:8], 'big') / 2**64 * total
    for i, weight in enumerate(weights):
        ticket -= weight
        if ticket < 0: return i + 1
    return max_years


def term_premium(offered_years, wanted_years):
    """A mismatched term can be bought out with more APY, rather than ignored."""
    gap = int(offered_years) - int(wanted_years)
    return 1.0 + min(.24, abs(gap) * (.03 if gap < 0 else .025))
