"""
POSITION CHANGES.

A man moves and his card is read for the new job: the ratings already say
how well he would play there, and that part is permanent and free. On top
sits a learning penalty on his skill ratings (never his physicals) that
falls to zero over a set number of games actually played at the new spot.
Adjacent spots cost a point or two for six games, a related job about three
for ten, a different job about five for fourteen. Younger men learn faster,
awareness shortens it, and a full offseason counts as four games.

The depth chart, his card and the game all read the same effective number,
so the cost is visible when the move is made and fades in front of you.
The same call is available to the AI (a new coach converting his misfits)
and to the user (change_position).
"""
from player_age import development_age
import numpy as np

SKILL_EXCLUDE = {'speed_rating', 'accel_rating', 'agility_rating', 'strength_rating',
                 'change_of_direction_rating', 'jump_rating', 'stamina_rating', 'injury_rating',
                 'tough_rating', 'kick_power_rating', 'throw_power_rating'}

# how far a move is: (penalty in points, games to pay it off)
ADJACENT = {frozenset(p) for p in (('SAM', 'WILL'), ('FS', 'SS'), ('LG', 'RG'), ('LEDG', 'REDG'), ('LT', 'RT'), ('HB', 'FB'))}
RELATED = {frozenset(p) for p in (('SAM', 'REDG'), ('SAM', 'LEDG'), ('WILL', 'REDG'), ('WILL', 'LEDG'), ('WILL', 'MIKE'), ('SAM', 'MIKE'),
                                   ('LG', 'C'), ('RG', 'C'), ('LT', 'LG'), ('RT', 'RG'), ('LT', 'RG'), ('RT', 'LG'),
                                   ('CB', 'FS'), ('CB', 'SS'), ('DT', 'LEDG'), ('DT', 'REDG'), ('TE', 'FB'), ('WR', 'TE'))}
COST = {'adjacent': (1.5, 6), 'related': (3.0, 10), 'different': (5.0, 14)}
OFFSEASON_GAMES = 4
SNAPS_FOR_A_GAME = 10


def distance(a, b):
    if a == b: return None
    k = frozenset((a, b))
    if k in ADJACENT: return 'adjacent'
    if k in RELATED: return 'related'
    return 'different'


def change_position(league, pid, new_pos, log=True):
    """Move him. Returns the transition record or None if it is no move."""
    p = league.player(pid)
    d = distance(p.pos, new_pos)
    if d is None:
        return None
    pen, games = COST[d]
    aw = float(p.ratings.get('awareness_rating', 70))
    games = int(round(games * (1.0 + 0.03 * max(0.0, development_age(p) - 25)) * (1.15 - 0.3 * (aw - 60) / 40.0)))
    team = league.teams.get(p.team) if p.team else None
    if team is not None and getattr(team, 'staff', None):
        import staff as ST
        games = int(round(games * ST.tax_mult(team, new_pos)))
    games = max(3, games)
    prior = p.transition
    # a second move before the first is paid off does not stack; the bigger tax stands
    if prior and prior.get('games_left', 0) > 0:
        pen = max(pen, prior['penalty'] * prior['games_left'] / max(1, prior['games_total']))
    p.transition = dict(frm=p.pos, to=new_pos, penalty=float(pen), games_left=games, games_total=games)
    old = p.pos
    p.pos = new_pos
    if log:
        league.log('position_change', pid=pid, team=p.team, frm=old, to=new_pos, penalty=pen, games=games)
    return p.transition


def penalty(p):
    """Points still owed, 0 when he has learned the job."""
    t = getattr(p, 'transition', None)
    if not t or t.get('games_left', 0) <= 0:
        return 0.0
    return float(t['penalty'] * t['games_left'] / max(1, t['games_total']))


def effective_ratings(p):
    """His card with the tax on the skills, for the game and the depth chart."""
    pen = penalty(p)
    if pen <= 0:
        return p.ratings
    return {k: (v - pen if k not in SKILL_EXCLUDE else v) for k, v in p.ratings.items()}


def played(p, snaps):
    """A game with real snaps at the new spot pays a game off."""
    t = getattr(p, 'transition', None)
    if t and t.get('games_left', 0) > 0 and snaps >= SNAPS_FOR_A_GAME:
        t['games_left'] -= 1
        if t['games_left'] <= 0:
            p.transition = None


def offseason(league):
    """Camp counts for four games for every man still learning."""
    for p in league.players.values():
        t = getattr(p, 'transition', None)
        if t and t.get('games_left', 0) > 0:
            t['games_left'] = max(0, t['games_left'] - OFFSEASON_GAMES)
            if t['games_left'] <= 0:
                p.transition = None


# ------------------------------------------------------------ the AI
FAMILY = {'SAM': ['WILL', 'REDG', 'LEDG', 'MIKE'], 'WILL': ['SAM', 'MIKE', 'REDG', 'LEDG'], 'MIKE': ['WILL', 'SAM'],
          'LEDG': ['REDG', 'SAM', 'DT'], 'REDG': ['LEDG', 'SAM', 'DT'], 'DT': ['LEDG', 'REDG'],
          'FS': ['SS', 'CB'], 'SS': ['FS', 'CB'], 'CB': ['FS', 'SS'],
          'LG': ['RG', 'C', 'LT'], 'RG': ['LG', 'C', 'RT'], 'C': ['LG', 'RG'], 'LT': ['RT', 'LG'], 'RT': ['LT', 'RG'],
          'HB': ['FB'], 'FB': ['HB', 'TE'], 'TE': ['FB']}


def convert_misfits(league, team, rng, min_gain=1.5, verbose=False):
    """
    A new coach looks at each misfit in his two-deep and moves him inside
    the family when the new spot, tax included, grades better under his
    scheme than staying put. Otherwise the man stays where he is and the
    trade engine prices him for someone else.
    """
    import targets as TG
    from gm_engine import scheme_fit
    moves = []
    scheme = team.scheme
    for pos, ps in list(team.depth.items()):
        for p in ps[:2]:
            if scheme_fit(p.ratings, p.pos, team) > -2.0:
                continue
            here = TG.position_score(p.ratings, p.pos, scheme)
            # a star stays: nobody moves an 88 tackle to guard because the
            # blocking scheme changed; the misfits who move are the ones
            # who were not going to start where they are
            if here >= 84.0:
                continue
            best = None
            for alt in FAMILY.get(p.pos, []):
                d = distance(p.pos, alt); pen = COST[d][0] if d else 0.0
                there = TG.position_score({k: (v - pen if k not in SKILL_EXCLUDE else v) for k, v in p.ratings.items()}, alt, scheme)
                # and where the club actually needs a man at that spot
                incumbent = team.depth.get(alt, [])
                need = 1.0 if len(incumbent) < 2 or there > incumbent[min(1, len(incumbent) - 1)].ovr else 0.0
                score = there - here + 1.0 * need
                if score >= min_gain and (best is None or score > best[0]):
                    best = (score, alt, there)
            if best:
                change_position(league, p.pid, best[1])
                moves.append((p.name, pos, best[1], round(best[2] - here, 1)))
    if verbose and moves:
        print(f'  {team.abbr} converts: ' + ', '.join(f'{n} {a}->{b} ({g:+.1f})' for n, a, b, g in moves))
    return moves


def observed_speed_losses(league):
    losses = {}
    for row in league.transactions:
        if row.get('kind') != 'regress' or row.get('year', 0) < league.year - 2:
            continue
        pair = row.get('attrs', {}).get('speed_rating')
        if pair:
            pid = row.get('pid')
            losses[pid] = losses.get(pid, 0.) + max(0., float(pair[0]) - float(pair[1]))
    return losses


def aging_corner_options(league, team, players=None, *, profile=None, speed_losses=None):
    """Read-only CB/FS/SS comparisons using the complete current secondary.

    Age invites a review, not a conversion. Contract, ratings and roster spots
    stay intact; the alternative is retaining the corner in his current job.
    """
    import copy
    from types import SimpleNamespace
    import roster_needs as RN
    import targets as TG
    active = team.active() if players is None else players
    healthy = [p for p in active if getattr(p, 'out_until', None) is None]
    corners = [p for p in healthy if p.pos == 'CB']
    if len(corners) < 5:
        return []  # retain four available corners for the existing packages
    candidates = [p for p in corners if getattr(p, 'age', 0) >= 28 and not penalty(p)
                  and getattr(p, 'xp_spent', {}).get('_cb_safety_review') != league.year]
    if not candidates: return []
    if profile is None:
        import defense_roles as DR
        profile = DR.planning_profile(getattr(team, 'gm', None))
    if speed_losses is None: speed_losses = observed_speed_losses(league)
    def suitable(p, pos):
        r = p.ratings
        if (r.get('speed_rating', 0) < (72 if pos == 'FS' else 68)
                or r.get('tackle_rating', 0) < (60 if pos == 'FS' else 68)
                or r.get('zone_cover_rating', 0) < 65
                or min(r.get('awareness_rating', 0), r.get('play_rec_rating', 0)) < 65):
            return False
        fit_gain = TG.position_score(r, pos, team.scheme) - TG.position_score(r, 'CB', team.scheme)
        return not (p.age < 30 and speed_losses.get(p.pid, 0.) < 1.0 and fit_gain < 2.0)
    # Most aging corners cannot fill a safety role. Skip the expensive whole
    # secondary comparison when no player passes the same suitability checks.
    if not any(suitable(p, pos) for p in candidates for pos in ('FS', 'SS')):
        return []
    def assess(roster):
        projected = []
        for q in roster:
            if penalty(q):
                q = copy.copy(q)
                q.ratings = effective_ratings(q)
                q.transition = None
            projected.append(q)
        prepared = dict(team=team, grades={q.pid: RN._grade(q, team) for q in projected},
                        profile=profile, role_grades={})
        return RN.assess(team, projected, prepared=prepared)
    baseline = assess(healthy)
    coverage = RN.essential_coverage(team, report=baseline)
    gm = getattr(team, 'gm', None)
    rigidity = float(getattr(gm, 'scheme_rigidity', .5))
    patience = float(getattr(gm, 'patience', .5))
    youth = float(getattr(gm, 'youth', .5))
    options = []
    for p in candidates:
        # Only observed attribute history, never hidden longevity or potential.
        speed_lost = speed_losses.get(p.pid, 0.)
        for pos in ('FS', 'SS'):
            r = p.ratings
            if not suitable(p, pos): continue
            fit_gain = TG.position_score(r, pos, team.scheme) - TG.position_score(r, 'CB', team.scheme)
            trial = copy.copy(p); trial.team = team.abbr
            change_position(SimpleNamespace(player=lambda _: trial, teams=league.teams), p.pid, pos, log=False)
            roster = [trial if q.pid == p.pid else q for q in healthy]
            after = assess(roster)
            if not RN.coverage_not_worse(coverage, RN.essential_coverage(team, report=after)):
                continue
            immediate = after['_package_scores']['defense'] - baseline['_package_scores']['defense']
            if immediate <= 0 or after['score'] <= baseline['score']:
                continue
            # Compare the settled role too, but never borrow future gains to
            # excuse an immediately worse secondary during the learning period.
            learned = copy.copy(trial); learned.transition = None
            settled = assess([learned if q.pid == p.pid else q for q in healthy])
            gain = settled['_package_scores']['defense'] - baseline['_package_scores']['defense']
            threshold = max(.75, 1.5 + 2.0 * rigidity - .5 * patience
                            - .15 * min(5., max(0., p.age - 28)) - .15 * min(3., speed_lost))
            if gain < threshold:
                continue
            before_safeties = {row['player'].pid: row['player'] for row in baseline['assignments']
                               if row['role'] in ('FS', 'SS') and row['player']}
            after_safeties = {row['player'].pid for row in after['assignments']
                              if row['role'] in ('FS', 'SS') and row['player']}
            if p.pid not in after_safeties:
                continue  # no new regular safety job, so retain the corner
            displaced = [q for pid, q in before_safeties.items() if pid not in after_safeties]
            if any(getattr(q, 'age', 22) < 27 and learned.ovr - q.ovr < 3.0 + 2.0 * youth for q in displaced):
                continue
            options.append(dict(player=p, to=pos, immediate_gain=immediate, settled_gain=gain,
                                speed_lost=speed_lost, displaced=[q.pid for q in displaced],
                                threshold=threshold, fit_gain=fit_gain, games=trial.transition['games_total']))
    return sorted(options, key=lambda x: (-x['immediate_gain'], -x['settled_gain'], -x['fit_gain'], x['player'].pid, x['to']))


def projected_secondary(league, team, players, *, profile=None, speed_losses=None):
    """Consider conversions on the explicit roster, never promised acquisitions.

    Used for keeping today's roster and each actual signing/draft/trade option.
    The preview includes the learning tax, while saved positions stay unchanged.
    """
    import copy
    from types import SimpleNamespace
    roster = list(players); moves = []
    while True:
        options = aging_corner_options(league, team, roster, profile=profile, speed_losses=speed_losses)
        if not options: return roster, moves
        chosen = options[0]; trial = copy.copy(chosen['player']); trial.team = team.abbr
        change_position(SimpleNamespace(player=lambda _: trial, teams=league.teams), trial.pid, chosen['to'], log=False)
        # RN's role assignment consumes raw ratings, so preview the same tax
        # that the actual game will apply. Preserve transition for eligibility.
        trial.ratings = effective_ratings(trial)
        trial.transition = dict(trial.transition, penalty=0.)
        trial.xp_spent = dict(trial.xp_spent, _cb_safety_review=league.year)
        roster = [trial if p.pid == trial.pid else p for p in roster]
        moves.append(dict(pid=trial.pid, to=chosen['to'], displaced=chosen['displaced']))


def review_aging_corners(league):
    """Finalize the offseason secondary plan after acquisitions, before cutdown.

    Reassess after each move so two conversions cannot spend the same depth.
    Only labels and the existing learning penalty change: no cut, signing,
    salary reduction, free attribute points, or move of the user's players.
    """
    moves = []
    for abbr, team in sorted(league.teams.items()):
        if abbr == getattr(league, 'user_team', None): continue
        while True:
            options = aging_corner_options(league, team)
            if not options: break
            chosen = options[0]; p = chosen['player']
            change_position(league, p.pid, chosen['to'], log=False)
            p.xp_spent['_cb_safety_review'] = league.year
            league.log('position_change', pid=p.pid, team=abbr, frm='CB', to=chosen['to'],
                       penalty=p.transition['penalty'], games=p.transition['games_total'],
                       reason='Aging corner safety review', age=round(p.age, 1),
                       immediate_gain=round(chosen['immediate_gain'], 2),
                       settled_gain=round(chosen['settled_gain'], 2),
                       displaced=chosen['displaced'], speed_lost=round(chosen['speed_lost'], 1))
            moves.append((p.pid, chosen['to']))
        for p in team.active():
            if p.pos == 'CB' and p.age >= 28:
                p.xp_spent['_cb_safety_review'] = league.year
    return moves
