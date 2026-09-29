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
CAMP_UDFA_PER_CLUB = 5   # undrafted players each AI club brings to camp; the rest stay on the market for anyone to sign


# ------------------------------------------------------------ state
def squad(team):
    if not hasattr(team, 'practice_squad') or team.practice_squad is None:
        team.practice_squad = []
    return team.practice_squad


def ps_charge(team):
    """This club's practice-squad pay for the season, on the cap."""
    cap = getattr(team, 'cap', None)
    remaining = max(0,18-getattr(cap,'paid_week',0))/18
    return round(getattr(cap,'ps_earned',0.0)+remaining*sum(PAY_VET if (p.accrued or 0) > 2 else PAY_YOUNG for p in squad(team)), 3)


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
    # off the wire: a man signed to a squad is not there to be claimed (cutdown-day squads fill from the waiver pool)
    wire = getattr(league, 'waivers', None) or []
    for e in [e for e in wire if e.get('pid') == pid]:
        if getattr(league, 'user_team', None) in e.get('claims', []):
            import inbox as IB
            IB.post(league, 'waiver_notice', f"Claim void: {p.name} signed to {abbr}'s squad", f"{p.name} ({p.pos}) was signed to {abbr}'s practice squad before the wire cleared. Your claim did not go through.", sender='league')
        wire.remove(e)
    p.team, p.contract = abbr, None          # paid weekly, no contract object
    p.xp_spent['_ps'] = True
    squad(team).append(p)
    team.sync_cap()
    league.log('ps_sign', pid=pid, team=abbr)
    return True


def release_from_squad(league, abbr, pid):
    team = league.teams[abbr]; p = league.player(pid)
    if p in squad(team):
        squad(team).remove(p); p.team = None; p.xp_spent.pop('_ps', None)
        if pid not in league.free_agents: league.free_agents.append(pid)
        team.sync_cap()
        league.log('ps_release', pid=pid, team=abbr)


def call_up(league, abbr, pid, years=1, emergency=False):
    """To the 53 at the minimum for his accrued seasons."""
    team = league.teams[abbr]; p = league.player(pid)
    if p not in squad(team): return False
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    if len(team.active()) >= 53 and league.phase == 'regular' and room_candidate(league, team, p) is None:
        return False                                      # nobody the club would release for him
    c=Contract(years=years,base=[mn]*years,signed=league.year)
    c.base[0]*=max(0,18-team.cap.paid_week)/18; c.pay_start=team.cap.paid_week
    outgoing=room_candidate(league,team,p) if league.phase=='regular' and len(team.active())>=53 else None
    if not emergency:
        from cap_accounting import require_room
        try: require_room(league,team,pid,c,release_pid=outgoing.pid if outgoing else None,ps_pid=pid)
        except ValueError: return False
    squad(team).remove(p); p.xp_spent.pop('_ps', None); p.team = None
    _make_room(league, abbr, p)
    league.sign(pid, abbr, c, log=False)
    league.log('ps_callup', pid=pid, team=abbr)          # the one line for the move
    return True


def shunned(p, abbr, league):
    """A club does not sign or claim a man it released in the last eight weeks, and a man released by three clubs
    this season is nobody's first call."""
    rb = (p.xp_spent.get('_released_by') or {}) if hasattr(p, 'xp_spent') else {}
    wk = int(league.week or 0)
    if abbr in rb and 0 <= wk - int(rb[abbr]) <= 8: return True
    if int(p.xp_spent.get('_releases_year', -1) or -1) == league.year and int(p.xp_spent.get('_releases_this_year', 0) or 0) >= 3: return True
    return False


def protected(team, q, league):
    """Men a club does not release to make room: its only kicker, punter or long snapper; a first- or second-round
    pick in his first two seasons; anyone whose release costs more than about two million in dead money."""
    if q.pos in ('K', 'P', 'LS') and sum(1 for x in team.active() if x.pos == q.pos) <= 1: return True
    rd = getattr(q, 'draft_round', None); dy = getattr(q, 'draft_year', None)
    if rd is not None and int(rd) <= 2 and dy is not None and league.year - int(dy) <= 1: return True
    try:
        if float(q.dead_if_cut(0)) > 2.0: return True
    except Exception: pass
    return False


def room_candidate(league, team, p):
    """Who goes when the club needs a spot for p: the least valuable unprotected man at p's position, then on
    p's side of the ball, then anywhere. Value is his grade less the dead money his release would cost."""
    def value(q):
        try: dead = float(q.dead_if_cut(0))
        except Exception: dead = 0.0
        return float(q.ovr) - 4.0 * dead
    wk = league.week
    pools = ([q for q in team.active() if q.pos == p.pos], [q for q in team.active() if GROUP_OF.get(q.pos, q.pos) == GROUP_OF.get(p.pos, p.pos)], list(team.active()))
    for pool in pools:
        cands = [q for q in pool if q is not p and not locked(q, wk) and not protected(team, q, league)]
        if cands: return min(cands, key=value)
    return None


def _make_room(league, abbr, p):
    """The 53 is the 53: a call-up or a poach in season releases a man, who goes through waivers like anyone
    else. That is where the in-season wire comes from. Returns False when no acceptable man exists, and the move
    that needed the spot does not happen."""
    team = league.teams[abbr]
    if league.phase != 'regular' or len(team.active()) < 53:
        return True
    q = room_candidate(league, team, p)
    if q is None: return False
    league.release(q.pid)
    return True


def poach(league, abbr, pid, week):
    """Sign another club's practice-squad man to your 53. Locked for three games."""
    p = league.player(pid)
    src = p.team
    if src is None or src == abbr or p not in squad(league.teams[src]): return False
    team = league.teams[abbr]
    if len(team.active()) >= 53 and league.phase == 'regular' and room_candidate(league, team, p) is None: return False
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    c=Contract(years=1,base=[mn*max(0,18-team.cap.paid_week)/18],signed=league.year,pay_start=team.cap.paid_week)
    outgoing=room_candidate(league,team,p) if league.phase=='regular' and len(team.active())>=53 else None
    from cap_accounting import require_room
    try: require_room(league,team,pid,c,release_pid=outgoing.pid if outgoing else None)
    except ValueError: return False
    squad(league.teams[src]).remove(p); league.teams[src].sync_cap(); p.xp_spent.pop('_ps', None); p.team = None
    _make_room(league, abbr, p)
    league.sign(pid, abbr, c, log=False)
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
            if call_up(league, abbr, pid): out.append((pid, 'signed'))
            continue
        p.xp_spent['_elevations'] = n + 1
        team._elevated = getattr(team, '_elevated', []) + [p]
        out.append((pid, 'elevated'))
    return out


def clear_elevations(team):
    team._elevated = []


def reset_season(league):
    # IR clears at camp: everyone comes off, the returns count resets, the designations reset
    for t in league.teams.values():
        for p in list(getattr(t, 'ir', None) or []):
            p.xp_spent.pop('_ir_week', None); p.xp_spent.pop('_ir_return', None); p.xp_spent['_ir_desig'] = 0
            if p.out_until == 99: p.out_until = None
        t.ir = []; t.ir_returns_used = 0
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
    user = getattr(league, 'user_team', None)
    for abbr in order:
        if abbr == user: continue                      # the user signs whom he wants, from the Free Agency page
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
        print(f'  {signed} undrafted players signed to camp')
    # the rest are on the market, and the GM hears it
    try:
        import inbox as IB
        left = [p for p in udfa if not p.team]
        if user and left:
            top = sorted(left, key=lambda p: -p.ovr)[:5]
            IB.post(league, 'club', f"{len(left)} undrafted rookies are on the market", f"The clubs brought their camp bodies in; {len(left)} undrafted rookies are still unsigned and will sign for the minimum. Your scouts' best of them: " + ', '.join(f"{p.name} ({p.pos}, {round(view_ovr(league, user, p))})" for p in top) + ". Sign anyone to the roster or the practice squad from Free Agency; the Undrafted filter shows them.", sender='assistants', payload=dict(link='fa'))
    except Exception as e:
        import sys; print('udfa note failed:', e, file=sys.stderr)
    return signed


def view_ovr(league, abbr, p):
    v = (getattr(league, 'scouting', None) or {}).get(abbr, {}).get(p.pid)
    return float(v['ovr']) if v and v.get('ovr') else float(p.ovr)


def fill_squads(league, rng, verbose=False):
    """After cut-down: own cuts first, then the pool. Young players to the ten
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
# below this the game cannot dress a side at all; the user's club is filled automatically only here, with a note
HARD_MIN = {'QB': 1, 'HB': 1, 'WR': 3, 'TE': 1, 'OL': 5, 'DL': 4, 'LB': 3, 'DB': 5, 'K': 1, 'P': 1}
GROUP_OF = {'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL', 'LEDG': 'DL', 'REDG': 'DL', 'DT': 'DL',
            'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'FB': 'HB'}


def keep_groups_whole(league, rng, week):
    """No club dresses without a line. A group below its floor of healthy men
    calls up from the squad, then signs from the pool, at that group."""
    import min_salary as MS
    import roster_needs as RN
    from cap_engine import CAP, Contract
    moves = []
    user = getattr(league, 'user_team', None)
    for abbr, team in league.teams.items():
        wk_ = int(week or 0)
        # a man out two weeks or less still counts as the club's man: the game-day elevation covers him, and nobody
        # releases a player to cover a fortnight (that was the weekly backup-quarterback carousel)
        healthy = collections.Counter(GROUP_OF.get(p.pos, p.pos) for p in team.active() if p.out_until is None or (int(p.out_until) < 99 and int(p.out_until) - wk_ <= 2))
        for grp, floor in GROUP_MIN.items():
            short = floor - healthy.get(grp, 0)
            hard = healthy.get(grp, 0) < HARD_MIN.get(grp, 0)
            if short > 0 and abbr == user and not hard:
                # THE GM'S CLUB IS HIS TO FILL. No automatic call-up: the trainers say who is out, that the chart is
                # short there, and who on the squad (or the street) could cover; the game dresses what he has.
                try:
                    import inbox as IB
                    out_men = [p for p in team.active() if GROUP_OF.get(p.pos, p.pos) == grp and p.out_until is not None]
                    cands = sorted([p for p in squad(team) if GROUP_OF.get(p.pos, p.pos) == grp], key=lambda p: -p.ovr)
                    fa = sorted([q for q in (league.player(pid) for pid in league.free_agents) if q and GROUP_OF.get(q.pos, q.pos) == grp and q.out_until is None and not q.retired], key=lambda q: -q.ovr)[:2]
                    who = ', '.join(f"{p.name} ({p.pos})" for p in out_men[:3]) or 'injuries'
                    cover = (f"On the practice squad: {', '.join(f'{p.name} ({p.pos}, {round(p.ovr)})' for p in cands[:2])}." if cands else '') + (f" On the street: {', '.join(f'{q.name} ({q.pos}, {round(q.ovr)})' for q in fa)}." if fa else '')
                    key_ = f"short-{grp}-{league.year}-{week}"
                    if not any((mm.get('payload') or {}).get('key') == key_ for mm in getattr(league, 'inbox', [])):
                        IB.post(league, 'injury', f"Short at {grp}: {short} below the floor", f"With {who} out, the chart at {grp} is {short} below the number the game needs. {cover or 'Nobody on the squad or the street plays there.'} Call up or sign before Sunday, or the game dresses what you have.", sender='trainers', payload=dict(key=key_, link='club:ps' if cands else 'personnel:fa', group=grp))
                except Exception: pass
                continue
            if short > 0 and abbr == user and hard:
                try:
                    import inbox as IB
                    IB.post(league, 'injury', f"Emergency at {grp}: the trainers filled it", f"The chart at {grp} fell below what the game can dress ({healthy.get(grp, 0)} healthy). The best player available was called up so a team could take the field; the practice-squad and free-agent pages are yours for anything more.", sender='trainers', payload=dict(link='club:ps'))
                except Exception: pass
            if abbr != user and getattr(team, '_moved_week', None) == wk_ and not hard:
                continue                                  # one roster addition a week per club, short of an emergency
            while short > 0:
                cands = [p for p in squad(team) if GROUP_OF.get(p.pos, p.pos) == grp]
                if cands:
                    best = max(cands, key=lambda p: p.ovr)
                    if not call_up(league, abbr, best.pid, emergency=True): break
                    moves.append((abbr, 'callup', best.pid)); team._moved_week = wk_
                else:
                    fa = [league.player(pid) for pid in league.free_agents]
                    fa = [p for p in fa if p and GROUP_OF.get(p.pos, p.pos) == grp and p.out_until is None and not p.retired and not shunned(p, abbr, league)]
                    if not fa: break
                    best = max(fa, key=lambda p: p.ovr)
                    if len(team.active()) >= 53 and room_candidate(league, team, best) is None: break
                    _make_room(league, abbr, best); team._moved_week = wk_
                    mn = MS.minimum_salary(best.accrued or 0, CAP.get(league.year, 301.2))
                    if best.pid in league.free_agents: league.free_agents.remove(best.pid)
                    best.contract = None
                    league.sign(best.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year), log=False)   # logged once, below, with the reason
                    league.log('emergency_sign', pid=best.pid, team=abbr, group=grp)
                    moves.append((abbr, 'emergency', best.pid))
                short -= 1
    # THE ROSTER STAYS FULL. A club that put players on injured reserve fell to 47 or 48 and stayed there, and a spot
    # could lose every healthy body while its group still counted enough: the floors above are by group. Real clubs
    # fill the same week, from the practice squad first and the street second. AI clubs only; the GM's club is his.
    for abbr, team in league.teams.items():
        if abbr == user: continue
        wk_ = int(week or 0); added = 0
        floors, group_floors = RN.roster_floors(team)
        shape = dict(SHAPE, WR=max(SHAPE['WR'], floors['WR']),
                     TE=max(SHAPE['TE'], floors['TE']),
                     DL=group_floors['DL'], LB=group_floors['LB'])
        # 1. Cover this coach's actual roles before adding general depth.
        current = RN.assess(team, [p for p in team.active() if p.out_until is None
                                  or (int(p.out_until) < 99 and int(p.out_until) - wk_ <= 2)])
        for pos in sorted(RN.POSITIONS, key=lambda x: -current['needs'].get(x, 0.0)):
            if added >= 2: break
            if current['needs'].get(pos, 0.0) < 0.75: break
            grp = GROUP_OF.get(pos, pos)
            cands = sorted([q for q in squad(team) if q.pos == pos], key=lambda q: -q.ovr)
            if cands and call_up(league, abbr, cands[0].pid, emergency=True):
                moves.append((abbr, 'callup', cands[0].pid)); added += 1
                current = RN.assess(team); continue
            fa = [league.player(pid) for pid in league.free_agents]
            fa = [q for q in fa if q and q.pos == pos and q.out_until is None and not q.retired and not shunned(q, abbr, league)]
            if not fa: continue
            best = max(fa, key=lambda q: q.ovr)
            if len(team.active()) >= 53 and room_candidate(league, team, best) is None: continue
            _make_room(league, abbr, best)
            mn = MS.minimum_salary(best.accrued or 0, CAP.get(league.year, 301.2))
            if best.pid in league.free_agents: league.free_agents.remove(best.pid)
            best.contract = None
            league.sign(best.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year), log=False)   # logged once, below, with the reason
            league.log('sign', pid=best.pid, team=abbr, apy=mn, years=1)
            moves.append((abbr, 'sign', best.pid)); added += 1
            current = RN.assess(team)
        # 2. back to 53: the thinnest group against a normal 53-man shape gets the body
        while len(team.active()) < 53 and added < 2:
            counts = collections.Counter(GROUP_OF.get(p.pos, p.pos) for p in team.active() if p.out_until is None or (int(p.out_until) < 99 and int(p.out_until) - wk_ <= 2))
            needs = RN.assess(team)['needs']
            order = sorted(shape, key=lambda g: ((shape[g] - counts.get(g, 0)) / shape[g]
                                + max((needs.get(p, 0.0) for p in RN.GROUPS.get(g, (g,))), default=0.0)),
                           reverse=True)
            best = None
            called_up = False
            for grp in order:
                cands = sorted([q for q in squad(team) if GROUP_OF.get(q.pos, q.pos) == grp], key=lambda q: -q.ovr)
                if cands and call_up(league, abbr, cands[0].pid, emergency=True):
                    moves.append((abbr, 'callup', cands[0].pid)); added += 1
                    called_up = True
                    break
                fa = [league.player(pid) for pid in league.free_agents]
                fa = [q for q in fa if q and GROUP_OF.get(q.pos, q.pos) == grp and q.out_until is None and not q.retired and not shunned(q, abbr, league)]
                if fa:
                    best = max(fa, key=lambda q: q.ovr + 12.0 * needs.get(q.pos, 0.0))
                    break
            if called_up:
                continue
            if best is None:
                break
            mn = MS.minimum_salary(best.accrued or 0, CAP.get(league.year, 301.2))
            if best.pid in league.free_agents: league.free_agents.remove(best.pid)
            best.contract = None
            league.sign(best.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year), log=False)   # logged once, below, with the reason
            league.log('sign', pid=best.pid, team=abbr, apy=mn, years=1)
            moves.append((abbr, 'sign', best.pid)); added += 1
    return moves


SHAPE = {'QB': 3, 'HB': 4, 'WR': 6, 'TE': 3, 'OL': 9, 'DL': 9, 'LB': 6, 'DB': 10, 'K': 1, 'P': 1}   # a normal 53 by group (the long snapper rides with the specialists)


SWAP_GAP = 3.0                 # the newcomer must grade three points better at the spot


def roster_review(league, rng, week, user_team=None):
    """THE HOUSEKEEPING. Once every four weeks an AI club looks at its bottom five by value and at the best
    unsigned men and other clubs' squad men at those positions, and makes at most one swap: the newcomer at
    least three points better, the outgoing man free to cut (a minimum deal, no dead money, not a recent
    high pick, not the only specialist), and the club not having moved already this week. Real clubs make
    about one such move a month; the released man goes through waivers like anyone else."""
    import gm_engine as GE
    moves = []
    if league.phase != 'regular' or not (1 <= int(week or 0) <= 17): return moves
    cap = CAP.get(league.year, 301.2)
    fa_all = [league.player(pid) for pid in league.free_agents]
    fa_all = [p for p in fa_all if p is not None and not p.retired and p.out_until is None]
    for abbr, team in league.teams.items():
        if abbr == user_team or team.gm is None: continue
        if (int(week or 0) + (sum(map(ord, abbr)) % 4)) % 4 != 0: continue          # each club's review month falls on a different week
        if getattr(team, '_moved_week', None) == int(week or 0): continue
        if len(team.active()) < 50: continue
        def value(q):
            try: dead = float(q.dead_if_cut(0))
            except Exception: dead = 0.0
            return float(q.ovr) - 4.0 * dead
        bottom = sorted([q for q in team.active() if not protected(team, q, league) and not locked(q, week) and q.out_until is None
                         and float(getattr(q, 'apy', 0.0) or 0.0) <= MS.minimum_salary(3, cap) + 0.05], key=value)[:5]
        best = None
        for q in bottom:
            pool = [p for p in fa_all if p.pos == q.pos and not shunned(p, abbr, league)]
            pool += [p for t2, tm in league.teams.items() if t2 != abbr for p in squad(tm) if p.pos == q.pos and not shunned(p, abbr, league)]
            if not pool: continue
            p = max(pool, key=lambda x: x.ovr + GE.scheme_fit(x.ratings, x.pos, team))
            gain = (p.ovr + GE.scheme_fit(p.ratings, p.pos, team)) - (q.ovr + GE.scheme_fit(q.ratings, q.pos, team))
            if gain >= SWAP_GAP and (best is None or gain > best[0]):
                best = (gain, q, p)
        if best is None: continue
        gain, q, p = best
        mn = MS.minimum_salary(p.accrued or 0, cap)
        if team.cap_space < mn + 0.2: continue
        league.release(q.pid)
        if p.pid in league.free_agents:
            league.free_agents.remove(p.pid); p.contract = None
            league.sign(p.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year))
        else:
            src = p.team; squad(league.teams[src]).remove(p); p.xp_spent.pop('_ps', None); p.team = None
            league.sign(p.pid, abbr, Contract(years=1, base=[mn], signing_bonus=0.0, signed=league.year), log=False)
            p.xp_spent['_poach_lock'] = int(week or 0) + POACH_LOCK_GAMES
            league.log('ps_poach', pid=p.pid, team=abbr, source=src, locked_until=int(week or 0) + POACH_LOCK_GAMES)
        team._moved_week = int(week or 0)
        moves.append((abbr, 'swap', q.pid, p.pid))
    return moves


def weekly(league, rng, week, user_team=None):
    """
    In season, every week: clubs short of healthy players at a group elevate two
    for the game or call one up; and a club with a hole may poach another's
    squad man to its 53 when nothing on its own squad fits. Rare.
    """
    import contracts as CT
    moves = keep_groups_whole(league, rng, week)
    moves += roster_review(league, rng, week, user_team=user_team)
    for abbr, team in league.teams.items():
        clear_elevations(team)
        healthy = [p for p in team.active() if p.out_until is None]
        if len(healthy) >= 46:
            continue
        short = 46 - len(healthy)
        # groups missing players
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
