"""Exact offer packages, persistent preferences, and shared cash assessment."""
import copy
import math
from types import SimpleNamespace
import numpy as np
import contract_offer_model as MODEL
from cap_engine import CAP
from stable import stable_seed


def profile_for(player):
    import negotiation_engine as NE
    if player.xp_spent is None: player.xp_spent = {}
    profile = player.xp_spent.get('_negotiation_profile')
    if profile is None:
        # A separate ID-keyed generator never advances the simulation stream.
        profile = NE.make_profile(dict(age=player.age), np.random.default_rng(stable_seed(player.pid + ':contract-profile-v1')))
        player.xp_spent['_negotiation_profile'] = copy.deepcopy(profile)
    result = copy.deepcopy(profile)
    # Preferences are stable; credibility changes when the club breaks its word.
    # Never let an old cached negotiation profile override persisted morale.
    morale = getattr(player, 'morale', None)
    if morale is not None:
        result['trust'] = max(0.0, min(1.0, float(morale.trust)))
        result['broken'] = len(morale.broken)
    return result


def canonical(league, player, team, offer, kind='fa_offseason'):
    """Resolve defaults once so another club can match exactly this package."""
    import contract_structure as CS
    out = copy.deepcopy(offer)
    apy, years = float(out['apy']), float(out['years'])
    if not math.isfinite(apy) or apy <= 0 or not math.isfinite(years) or int(years) != years or not 1 <= years <= 7:
        raise ValueError('Offer needs positive annual pay and one to seven whole years')
    out.update(apy=apy, years=int(years))
    if kind != 'extension' or player.contract is None or player.contract.years <= 0:
        from min_salary import validate_annual_pay
        validate_annual_pay(league, player, apy, out['years'])
    if out.get('front_load') is None:
        out['front_load'] = CS.choose_shape(team, out['years'])
        if out['front_load'] is None: out['front_load'] = .5
    out['front_load'] = float(out['front_load'])
    if not math.isfinite(out['front_load']) or not 0 <= out['front_load'] <= 1:
        raise ValueError('Payment structure must be between zero and one')
    if out.get('bonus') is None:
        if kind == 'extension':
            out['bonus'] = CS.structure(apy, out['years'], player.pos, CAP.get(league.year, 301.2),
                                        team.gm or SimpleNamespace(restructure_depth=.5),
                                        front_load=out['front_load'])['signing_bonus']
        else:
            import market as MK
            out['bonus'] = MK.signing_terms(league, player, team, apy, out['years'],
                CAP.get(league.year, 301.2), out['front_load'])['signing_bonus']
    out['bonus'] = float(out['bonus'])
    if not math.isfinite(out['bonus']) or not 0 <= out['bonus'] <= apy * years:
        raise ValueError('Signing bonus must be between zero and total new compensation')
    if kind != 'extension' or player.contract is None or player.contract.years <= 0:
        from min_salary import player_minimum
        if out['bonus'] > (apy - player_minimum(league, player, out['years'])) * out['years'] + 1e-9:
            raise ValueError('This signing bonus leaves too little money for the minimum base salaries. Reduce the bonus or raise annual pay.')
    out['promises'] = list(out.get('promises') or [])
    out['package_version'] = 1
    return out


def cash(league, player, team, offer, kind):
    """Use the same builders as signing, including partial-year base salary."""
    if kind == 'extension':
        import extensions as EXT
        c = EXT.build(player, offer['years'], offer['apy'], CAP.get(league.year, 301.2),
                      team.gm, league, front_load=offer['front_load'], bonus=offer['bonus'])
        return MODEL.from_extension(player.contract, c)
    import market as MK
    from cap_accounting import pre_roll
    st = MK.signing_terms(league, player, team, offer['apy'], offer['years'], CAP.get(league.year, 301.2),
                          offer['front_load'], offer['bonus'])
    return MODEL.OfferCash(tuple(st['base']), st['signing_bonus'], int(pre_roll(league)))


def assess(league, player, team, offer, ask, years, kind='fa_offseason', profile=None):
    """Compare to an explicit neutral package at the player's acceptable ask.

    Ask already contains applicable market phase, morale and loyalty effects.
    No hidden ratings, potential, or future simulation outcomes are read.
    """
    import contract_structure as CS
    offer = canonical(league, player, team, offer, kind)
    if kind != 'extension':
        from min_salary import player_minimum
        ask = max(float(ask), player_minimum(league, player, years))
    ref_bonus = CS.structure(ask, years, player.pos, CAP.get(league.year, 301.2),
                            SimpleNamespace(restructure_depth=.5), front_load=.5)['signing_bonus']
    if kind != 'extension':
        import market as MK
        ref_bonus = MK.signing_terms(league, player, team, ask, years,
                                    CAP.get(league.year, 301.2), .5)['signing_bonus']
    reference = dict(apy=ask, years=years, bonus=ref_bonus, front_load=.5, promises=[])
    beliefs = MODEL.beliefs_from_profile(player, ask, profile or profile_for(player))
    proposed, baseline = cash(league, player, team, offer, kind), cash(league, player, team, reference, kind)
    result = MODEL.compare(proposed, baseline, beliefs)
    # Display and decisions use the same bounded equivalent value. The APY
    # reported by the UI is annualized even when this season is partly paid.
    reasons = []
    if proposed.bonus > baseline.bonus + .01: reasons.append('More money secured upfront')
    if offer['years'] > years: reasons.append('Longer commitment delays his next free agency')
    if offer['front_load'] < .4: reasons.append('Later salaries carry more release risk')
    result.update(package=offer, reference_package=reference, reasons=reasons,
                  interest='Terms meet his expectations' if result['acceptable'] else 'Close' if result['ratio'] >= .9 else 'Below his expectations')
    return result


def remember(league, player, contract, apy, market_apy=None):
    """Keep the accepted bargain, not the declining remaining-contract APY."""
    if market_apy is None:
        import valuation as VAL
        value = VAL.value_player(league, player, side='agent', rng=None)
        market_apy = (value or {}).get('apy', apy)
    player.xp_spent['_contract_bargain'] = dict(version=1, signed=contract.signed,
        end_year=league.year + contract.years, annual_pay=float(apy),
        market_apy=max(float(apy), float(market_apy)), cap=CAP.get(league.year, 301.2))


def pay_anchor(league, player):
    memory = (player.xp_spent or {}).get('_contract_bargain')
    if not memory or not player.contract or memory['signed'] != player.contract.signed or league.year >= memory['end_year']:
        return player.apy
    return memory['market_apy'] * CAP.get(league.year, memory['cap']) / max(.01, memory['cap'])
