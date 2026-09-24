"""
THE PRACTICE SQUAD, on the real rules (CBA Article 33, 2026).

SIZE AND WHO. Sixteen men. Ten of the sixteen must have two or fewer
accrued seasons; up to six can have any amount of experience. (The 17th
International Pathway spot is not modelled.)

PAY, ON THE CAP. Fixed weekly: $13,750 for two or fewer accrued seasons,
$18,350 for veterans, times eighteen weeks. Practice squad pay counts
against the cap while he is on it; no bonuses, no guarantees. Called up, he
signs an active-roster deal at the minimum for his accrued seasons.

ELEVATIONS. Up to two practice-squad men can be elevated for a game, each
man up to three times a season; a fourth time he has to be signed to the
53. Unlimited in the playoffs. Here a club elevates when a healthy hole at
a position group would otherwise leave it short for the game.

POACHING. Any club may sign another club's practice-squad man straight to
its own 53 at any time, no compensation. It must then keep him on the 53
for three games (a bye counts), it cannot put him on its own squad, and he
cannot be traded in that window. Only active-roster men can be traded.

UNDRAFTED MEN. Every undrafted man goes to the free-agent pool after the
draft. Clubs sign them to camp at the rookie minimum, three years, the
occasional one everybody missed for a little more. Cut-down then sends the
ones who do not make the 53 back through the pool, and the squads are
filled from there, own cuts first.

Rookie contracts are slotted by selection and every pick signs at once;
there are no holdouts.
"""
import numpy as np, collections
from cap_engine import Contract, CAP
import min_salary as MS

SIZE = 16
YOUNG_MIN = 10           # at least ten with <= 2 accrued seasons
VET_MAX = 6
WEEKS = 18
PAY_YOUNG, PAY_VET = 0.01375 * WEEKS, 0.01835 * WEEKS      # $M for the season
ELEVATIONS_PER_GAME, ELEVATIONS_PER_MAN = 2, 3
POACH_LOCK_GAMES = 3
CAMP_UDFA_PER_CLUB = 9   # undrafted men each club brings to camp


# ------------------------------------------------------------ state
def squad(team):
    if not hasattr(team, 'practice_squad') or team.practice_squad is None:
        team.practice_squad = []
    return team.practice_squad


def ps_charge(team):
    """This club's practice-squad pay for the season, on the cap."""
    return round(sum(PAY_VET if (p.accrued or 0) > 2 else PAY_YOUNG for p in squad(team)), 3)


def is_young(p):
    return (p.accrued or 0) <= 2


def can_add(team, p):
    sq = squad(team)
    if len(sq) >= SIZE: return False
    # one specialist at most: the engine rates kickers and punters in the
    # high 80s, and a squad picked on raw overall carried two punters
    if p.pos in ('K', 'P') and any(q.pos in ('K', 'P') for q in sq): return False
    # the real rule is a CAP of six veterans, which leaves ten slots that
    # only young men can fill; a minimum of ten young men is the same thing
    # when the pool is deep and a squad of seven when it is not
    vets = sum(1 for q in sq if not is_young(q))
    if not is_young(p) and vets >= VET_MAX: return False
    return True


# ------------------------------------------------------------ moves
def sign_to_squad(league, abbr, pid):
    team = league.teams[abbr]; p = league.player(pid)
    if p is None or not can_add(team, p):
        return False
    if p.team and p.team in league.teams and p in league.teams[p.team].roster:
        league.release(pid, log=False)
    if pid in league.free_agents: league.free_agents.remove(pid)
    p.team, p.contract = abbr, None          # paid weekly, no contract object
    p.xp_spent['_ps'] = True
    squad(team).append(p)
    league.log('ps_sign', pid=pid, team=abbr)
    return True


def release_from_squad(league, abbr, pid):
    team = league.teams[abbr]; p = league.player(pid)
    if p in squad(team):
        squad(team).remove(p); p.team = None; p.xp_spent.pop('_ps', None)
        if pid not in league.free_agents: league.free_agents.append(pid)
        league.log('ps_release', pid=pid, team=abbr)


def call_up(league, abbr, pid, years=1):
    """To the 53 at the minimum for his accrued seasons."""
    team = league.teams[abbr]; p = league.player(pid)
    if p not in squad(team): return False
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    squad(team).remove(p); p.xp_spent.pop('_ps', None); p.team = None
    _make_room(league, abbr, p)
    league.sign(pid, abbr, Contract(years=years, base=[mn] * years, signing_bonus=0.0, signed=league.year))
    league.log('ps_callup', pid=pid, team=abbr)
    return True


def _make_room(league, abbr, p):
    """The 53 is the 53: a call-up or a poach in season releases the worst
    man at his spot, who goes through waivers like anyone else. That is
    where the in-season wire comes from."""
    team = league.teams[abbr]
    if league.phase != 'regular' or len(team.active()) < 53:
        return
    cands = [q for q in team.active() if q.pos == p.pos and not locked(q, league.week)] or \
            [q for q in team.active() if not locked(q, league.week)]
    if cands:
        league.release(min(cands, key=lambda q: q.ovr).pid)


def poach(league, abbr, pid, week):
    """Sign another club's practice-squad man to your 53. Locked for three games."""
    p = league.player(pid)
    src = p.team
    if src is None or src == abbr or p not in squad(league.teams[src]): return False
    squad(league.teams[src]).remove(p); p.xp_spent.pop('_ps', None); p.team = None
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    _make_room(league, abbr, p)
    league.sign(pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year))
    p.xp_spent['_poach_lock'] = (week or 0) + POACH_LOCK_GAMES
    league.log('ps_poach', pid=pid, team=abbr, source=src, locked_until=(week or 0) + POACH_LOCK_GAMES)
    return True


def locked(p, week):
    return (p.xp_spent.get('_poach_lock') or -1) > (week or 0)


def elevate(league, abbr, pids, week, playoffs=False):
    """Game-day elevations: the men play this week and go back after."""
    team = league.teams[abbr]; out = []
    for pid in pids[:ELEVATIONS_PER_GAME]:
        p = league.player(pid)
        if p not in squad(team): continue
        n = p.xp_spent.get('_elevations', 0)
        if n >= ELEVATIONS_PER_MAN and not playoffs:
            call_up(league, abbr, pid)              # fourth time: he is signed
            out.append((pid, 'signed'))
            continue
        p.xp_spent['_elevations'] = n + 1
        team._elevated = getattr(team, '_elevated', []) + [p]
        out.append((pid, 'elevated'))
    return out


def clear_elevations(team):
    team._elevated = []


def reset_season(league):
    for p in league.players.values():
        p.xp_spent.pop('_elevations', None)


# ------------------------------------------------------------ the AI
def udfa_camp(league, rng, verbose=False):
    """After the draft: every undrafted man is in the pool; clubs bring a
    handful each to camp at the rookie minimum, three years. The rare one
    everyone missed (a consensus top-150 man) gets a little more."""
    import scouting as SC
    cap = CAP.get(league.year, 301.2)
    udfa = [league.player(pid) for pid in league.free_agents]
    udfa = [p for p in udfa if p and p.college and p.draft_round is None and p.draft_year == league.year]
    signed = 0
    order = list(league.teams); rng.shuffle(order)
    for abbr in order:
        team = league.teams[abbr]
        view = league.scouting.get(abbr, {}) if getattr(league, 'scouting', None) else {}
        need = collections.Counter()
        for pos, ps in team.depth.items(): need[pos] = len(ps)
        # the club's own read, best first, thin spots first
        cands = sorted(udfa, key=lambda p: -(view.get(p.pid, {}).get('ovr', p.ovr) - 0.8 * need.get(p.pos, 0)))
        took = 0
        for p in cands:
            if took >= CAMP_UDFA_PER_CLUB: break
            if p.team: continue
            mn = MS.minimum_salary(0, cap)
            cons = league.consensus.get(p.pid, {}) if getattr(league, 'consensus', None) else {}
            bonus = 0.15 if cons.get('rank', 999) <= 150 else 0.0
            league.sign(p.pid, abbr, Contract(years=3, base=[mn] * 3, signing_bonus=bonus, signed=league.year))
            league.log('udfa_sign', pid=p.pid, team=abbr, bonus=bonus)
            took += 1; signed += 1
    if verbose:
        print(f'  {signed} undrafted men signed to camp')
    return signed


def fill_squads(league, rng, verbose=False):
    """After cut-down: own cuts first, then the pool. Young men to the ten
    young slots, the best available veterans to the six."""
    cuts = collections.defaultdict(list)
    for x in league.transactions:
        if x.get('kind') == 'release' and x.get('year') == league.year:
            p = league.player(x['pid'])
            if p and p.team is None and not p.retired and p.pid in league.free_agents:
                cuts[x['team']].append(p)
    pool_ids = set(league.free_agents)
    total = 0
    order = list(league.teams); rng.shuffle(order)
    for abbr in order:
        team = league.teams[abbr]
        # ranked on the common scale across positions, not raw overall
        import draft as DFT
        scale = DFT.position_scale(league)
        rank = lambda p: DFT.common_scale(p.ovr, p.pos, scale) + (3.0 if is_young(p) else 0.0)
        own = sorted({p.pid: p for p in cuts.get(abbr, [])}.values(), key=lambda p: -rank(p))
        for p in own:
            if p.pid in pool_ids and sign_to_squad(league, abbr, p.pid):
                pool_ids.discard(p.pid); total += 1
        if len(squad(team)) < SIZE:
            rest = sorted((league.player(pid) for pid in list(pool_ids) if league.player(pid)), key=lambda p: -rank(p))
            for p in rest:
                if len(squad(team)) >= SIZE: break
                if p is None or p.retired: continue
                if sign_to_squad(league, abbr, p.pid):
                    pool_ids.discard(p.pid); total += 1
    if verbose:
        sizes = [len(squad(t)) for t in league.teams.values()]
        print(f'  squads filled: {total} signed, sizes min {min(sizes)} max {max(sizes)}')
    return total


GROUP_MIN = {'QB': 2, 'HB': 2, 'WR': 4, 'TE': 2, 'OL': 7, 'DL': 6, 'LB': 4, 'DB': 7, 'K': 1, 'P': 1}
GROUP_OF = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL', 'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL',
            'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'FB': 'HB'}


def keep_groups_whole(league, rng, week):
    """No club dresses without a line. A group below its floor of healthy men
    calls up from the squad, then signs from the pool, at that group."""
    import min_salary as MS
    from cap_engine import CAP, Contract
    moves = []
    for abbr, team in league.teams.items():
        healthy = collections.Counter(GROUP_OF.get(p.pos, p.pos) for p in team.active() if p.out_until is None)
        for grp, floor in GROUP_MIN.items():
            short = floor - healthy.get(grp, 0)
            while short > 0:
                cands = [p for p in squad(team) if GROUP_OF.get(p.pos, p.pos) == grp]
                if cands:
                    best = max(cands, key=lambda p: p.ovr); call_up(league, abbr, best.pid); moves.append((abbr, 'callup', best.pid))
                else:
                    fa = [league.player(pid) for pid in league.free_agents]
                    fa = [p for p in fa if p and GROUP_OF.get(p.pos, p.pos) == grp and p.out_until is None and not p.retired]
                    if not fa: break
                    best = max(fa, key=lambda p: p.ovr)
                    _make_room(league, abbr, best)
                    mn = MS.minimum_salary(best.accrued or 0, CAP.get(league.year, 301.2))
                    if best.pid in league.free_agents: league.free_agents.remove(best.pid)
                    best.contract = None
                    league.sign(best.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year))
                    league.log('emergency_sign', pid=best.pid, team=abbr, group=grp)
                    moves.append((abbr, 'emergency', best.pid))
                short -= 1
    return moves


def weekly(league, rng, week, user_team=None):
    """
    In season, every week: clubs short of healthy men at a group elevate two
    for the game or call one up; and a club with a hole may poach another's
    squad man to its 53 when nothing on its own squad fits. Rare.
    """
    import contracts as CT
    moves = keep_groups_whole(league, rng, week)
    for abbr, team in league.teams.items():
        clear_elevations(team)
        healthy = [p for p in team.active() if p.out_until is None]
        if len(healthy) >= 46:
            continue
        short = 46 - len(healthy)
        # groups missing men
        by_pos = collections.Counter(p.pos for p in healthy)
        want = sorted(squad(team), key=lambda p: -p.ovr)
        picks = [p.pid for p in want if by_pos.get(p.pos, 0) < {'QB': 2, 'HB': 2, 'WR': 5, 'TE': 2, 'CB': 4, 'DT': 3}.get(p.pos, 2)][:short]
        if picks:
            moves += [(abbr, 'elevate', x) for x in elevate(league, abbr, picks, week)]
        elif abbr != user_team and rng.random() < 0.25:
            # nothing at home fits: look at everyone else's squad for the thinnest spot
            thin = min(by_pos, key=by_pos.get) if by_pos else None
            cands = [p for t2, tm in league.teams.items() if t2 != abbr for p in squad(tm) if p.pos == thin]
            if cands:
                p = max(cands, key=lambda p: p.ovr)
                if team.cap_space > MS.minimum_salary(p.accrued or 0, CAP.get(league.year, 301.2)):
                    poach(league, abbr, p.pid, week); moves.append((abbr, 'poach', p.pid))
    return moves
