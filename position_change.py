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
    games = int(round(games * (1.0 + 0.03 * max(0.0, p.age - 25)) * (1.15 - 0.3 * (aw - 60) / 40.0)))
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
