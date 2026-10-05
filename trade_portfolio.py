"""Private opportunity cost of spending a club's remaining draft options.

This is a policy preference, not transaction legality or a replacement for
neutral pick prices. Career draft AV supplies a relative capital index, never
a probability of finding a starter. Coefficients require outcome review; they
are not fitted probabilities or a minimum number of picks a club must keep.
"""
import copy

import draft_plan as DP
import gm_engine as GM
import roster_needs as RN
import trade_engine as TE
from cap_accounting import pre_roll
from cap_engine import CAP, Contract
from ceiling_knowledge import observed_range

HORIZON = 4
REFERENCE_SLOTS = tuple((r - 1) * 32 + 16 for r in range(1, 8))
REFERENCE_AV = sum(TE.PICK_AV[s] for s in REFERENCE_SLOTS)


def _clip(value):
    return max(0., min(1., float(value)))


def _pick_key(pick):
    return int(pick.year), int(pick.round), str(pick.original)


def _pick_row(pick):
    slot = max(1, min(262, int(pick.selection or (int(pick.round)-1)*32+16)))
    return dict(key=_pick_key(pick), year=int(pick.year)+1, slot=slot,
                outcome=TE.PICK_AV[slot])


def _public_signature(player):
    c = getattr(player, 'contract', None)
    return (player.pid, player.pos, float(player.age), float(player.ovr),
            tuple(sorted(player.ratings.items())), getattr(player, 'dev', 'normal'),
            tuple(observed_range(player) or ()),
            int(getattr(c, 'years', 0)), int(getattr(c, 'start_offset', 0)))


def _prospect(league, team, prospect, start):
    """Only scouting information or an already observed prospect view."""
    if prospect is None:
        return None
    scouting = (getattr(league, 'scouting', {}) or {}).get(team.abbr, {})
    if not hasattr(prospect, 'potential') and not hasattr(prospect, 'potential_range'):
        # Draft callers can already supply DP.observed_prospect. Reapplying
        # the scouting errors would turn one public read into a second one.
        view = copy.copy(prospect)
    elif prospect.pid in scouting:
        view = DP.observed_prospect(league, team.abbr, prospect)
    else:
        return None  # a raw unscouted college object is not public evidence
    view.age = float(getattr(view, 'age', 22.))
    view.dev = 'normal'
    view.contract = Contract(4+start, [0.]*(4+start), start_offset=start)
    return view


def _exposures(team, players, start, cache):
    """Weighted football jobs at risk, net of known controlled successors.

Missing jobs remain exposed after exporting a starter. Reserve credit can
cover only one role unit per player, across one deduplicated planning family.
IR returnees remain in the planning roster; no squad promotion is presumed.
"""
    gm = getattr(team, 'gm', None)
    identity = tuple((k, repr(v)) for k,v in sorted(vars(gm).items())) if gm else ()
    key = ('portfolio_roles', team.abbr, start, identity,
           repr(getattr(team, 'scheme', None)), tuple(_public_signature(p) for p in players))
    if key in cache:
        return cache[key]
    proxy = DP._Roster(team, players)
    report = RN.assess(proxy, strict_roles=True)
    rows = list(report['package_assignments']) + [dict(r, weight=1.)
        for r in report['assignments'] if r['role'] in ('K','P','LS')]
    occupied = {}
    for row in rows:
        if row['player'] is not None:
            pid = row['player'].pid
            occupied[pid] = occupied.get(pid, 0.) + float(row['weight'])
    total = sum(float(r['weight']) for r in rows)
    belief = _clip(getattr(gm, 'dev_belief', .5))
    result = []
    for offset in range(HORIZON):
        families = []
        for family in RN.PLANNING_FAMILIES:
            pos = family[0]
            jobs = [r for r in rows if r['sources'][0] in family]
            demand = sum(float(r['weight']) for r in jobs)
            if not demand:
                continue
            bar = 81. if pos == 'QB' else 76.
            exposed = 0.
            incumbents = {}
            for row in jobs:
                p = row['player']
                if p is None:
                    risk = 1.
                else:
                    c = getattr(p, 'contract', None)
                    control = max(0, int(getattr(c,'years',0))-start)
                    # GM.future_need already distinguishes QB aging and uses
                    # positional replaceability. One row is one weighted job.
                    future = GM.future_need({'expiring': {pos: [(p.ovr, control, p.age)]}},
                                            pos, horizon=offset+1)
                    risk = max(_clip((bar-float(row['grade']))/12.), future)
                    incumbents[p.pid] = dict(pid=p.pid, grade=round(float(row['grade']),3),
                                             age=float(p.age), control=control)
                exposed += float(row['weight']) * risk
            successors = []
            for p in players:
                spare = max(0., 1.-occupied.get(p.pid, 0.))
                if p.pos not in family or not spare:
                    continue
                c = getattr(p,'contract',None)
                if int(getattr(c,'years',0))-start <= offset:
                    continue
                if float(p.age)+offset >= (34 if pos=='QB' else 31):
                    continue
                public = copy.copy(p)
                public.contract = copy.copy(c)
                public.contract.years = max(0,c.years-start)
                grade = DP._family_reserve_grade(public,proxy,belief,family)
                # Alternate-package incumbents already cover part of the
                # demand above. Only their unused role capacity can also
                # replace a teammate; a small package role is not a ban.
                cover = _clip((grade-(bar-8.))/8.) * spare
                if cover:
                    successors.append(dict(pid=p.pid, cover=cover,
                        occupied_share=occupied.get(p.pid, 0.), spare_capacity=spare))
            credit = min(exposed, sum(p['cover'] for p in successors))
            families.append(dict(family=list(family), demand=demand,
                gross_exposure=exposed, successor_credit=credit,
                exposure=max(0.,exposed-credit), incumbents=list(incumbents.values()),
                successors=successors))
        result.append(dict(exposure=sum(f['exposure'] for f in families)/max(total,1.),
                           role_demand=total, families=families))
    cache[key] = result
    return result


def assess(league, team, outgoing=(), incoming=(), *, cache=None,
           prospect=None, consumed_pick=None):
    """Return nonnegative marginal portfolio cost and four horizon diagnostics.

Items are player ids or DraftPick objects. The optional cache belongs to one
unchanged negotiation; nothing is attached to the league or saved players.
Prospect coverage uses public scouting; consumed_pick cannot remain capital.
No outgoing owned pick means no spending surcharge. This never vetoes a deal.
"""
    cache = {} if cache is None else cache
    outgoing, incoming = tuple(outgoing), tuple(incoming)
    start = int(pre_roll(league))
    first_year = int(league.year)+start
    gm = getattr(team,'gm',None)
    if gm is not None and hasattr(gm,'shift') and hasattr(team,'ctx'):
        gm = gm.shift(team.ctx())
    trait = lambda name, default=.5: _clip(getattr(gm,name,default))
    # Policy weights, not empirical likelihoods: patient/secure GMs look
    # farther ahead; urgent or risk-seeking GMs tolerate more lost options.
    # Normalize time weights so a career outcome is not charged four times.
    horizon = (trait('patience')+trait('job_security',.6))/2.
    discount = .55+.40*horizon
    raw_weights = [discount**i for i in range(HORIZON)]
    weights = [w/sum(raw_weights) for w in raw_weights]
    preference = .5+.4*trait('patience')+.4*(1-trait('risk'))+.2*(1-trait('aggression'))
    lens = 1-trait('board_trust',1-trait('pick_lens'))
    # A reference draft is only a normalization unit, never a pick target.
    cap = float(getattr(getattr(team,'cap',None),'cap',CAP.get(league.year,TE.CAP)))
    reference_value = sum(TE.pick_belief_dollars(s,cap=cap,lens=lens) for s in REFERENCE_SLOTS)
    current = {_pick_key(p):p for p in getattr(team,'picks',())
               if p.used_on is None and p.owner==team.abbr and int(p.year)+1>=first_year}
    sent = {_pick_key(p) for p in outgoing if not isinstance(p,str)}
    after_picks = {key:p for key,p in current.items() if key not in sent}
    for p in incoming:
        if not isinstance(p,str) and p.used_on is None and int(p.year)+1>=first_year:
            after_picks[_pick_key(p)] = p
    if consumed_pick is not None:
        after_picks.pop(_pick_key(consumed_pick),None)
    before_players = DP.projected_players(team)
    sent_players = {p for p in outgoing if isinstance(p,str)}
    roster = {p.pid:p for p in before_players if p.pid not in sent_players}
    for pid in incoming:
        if isinstance(pid,str):
            p = league.player(pid)
            if p is not None and not getattr(p,'retired',False) and getattr(p,'contract',None):
                roster[p.pid] = p
    rookie = _prospect(league,team,prospect,start)
    if rookie is not None:
        roster[rookie.pid] = rookie
    before_roles = _exposures(team,before_players,start,cache)
    after_roles = _exposures(team,list(roster.values()),start,cache)
    stock = lambda picks: tuple(sorted((_pick_key(p),p.selection) for p in picks.values()))
    spending = bool(sent.intersection(current))
    key = ('portfolio_cost',first_year,id(before_roles),id(after_roles),
           stock(current),stock(after_picks),tuple(weights),reference_value,preference,spending)
    if key in cache:
        return cache[key]
    def project(picks, roles):
        inventory = [_pick_row(p) for p in picks.values()]
        result = []
        for i, role in enumerate(roles):
            year = first_year+i
            usable = [p for p in inventory if p['year']<=year<p['year']+4]
            capital = sum(p['outcome'] for p in usable)/REFERENCE_AV
            exposure = role['exposure']
            risk = reference_value*exposure**2/(exposure+capital) if exposure else 0.
            result.append(dict(year=year,weight=weights[i],exposure=exposure,
                capital=capital,option_risk=risk,picks=usable,**{k:v for k,v in role.items() if k!='exposure'}))
        return result
    before,after = project(current,before_roles),project(after_picks,after_roles)
    old = sum(r['weight']*r['option_risk'] for r in before)
    new = sum(r['weight']*r['option_risk'] for r in after)
    result = dict(cost=round(max(0.,new-old)*preference,6) if spending else 0.,
                before=before,after=after,reference_value=reference_value,
                gm_weight=preference,before_risk=old,after_risk=new,
                policy='marginal_draft_options')
    cache[key] = result
    return result
