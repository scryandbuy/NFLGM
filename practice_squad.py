"""
THE PRACTICE SQUAD, with game-specific cap treatment.

SIZE AND WHO. Sixteen men. Ten of the sixteen must have two or fewer
accrued seasons; up to six can have any amount of experience. (The 17th
International Pathway spot is not modelled.)

PAY. Fixed weekly: $13,750 for two or fewer accrued seasons,
$18,350 for veterans, times eighteen weeks. The game tracks this pay outside
the salary cap. Called up, he signs an active-roster deal at the minimum for
his accrued seasons.

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
from inbox import player_name as inbox_player
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
    """Practice-squad pay is tracked separately and has no cap charge."""
    return 0.0


def is_young(p):
    return (p.accrued or 0) <= 2


def can_add(team, p, *, by_ai=False):
    sq = squad(team)
    if len(sq) >= SIZE: return False
    # one specialist at most: the engine rates kickers and punters in the
    # high 80s, and a squad picked on raw overall carried two punters
    if by_ai and p.pos in ('K', 'P') and any(q.pos in ('K', 'P') for q in sq): return False
    # the real rule is a CAP of six veterans, which leaves ten slots that
    # only young men can fill; a minimum of ten young men is the same thing
    # when the pool is deep and a squad of seven when it is not
    vets = sum(1 for q in sq if not is_young(q))
    if not is_young(p) and vets >= VET_MAX: return False
    return True


# ------------------------------------------------------------ moves
def sign_to_squad(league, abbr, pid):
    team = league.teams[abbr]; p = league.player(pid)
    if (p is None or p.retired or (p.team is not None and p.team != abbr)
            or p in squad(team) or p in (getattr(team, 'ir', None) or [])
            or not can_add(team, p, by_ai=abbr != getattr(league, 'user_team', None))):
        return False
    # A roster demotion can still accelerate contract bonuses into dead cap.
    from cap_accounting import require_squad_room
    try: require_squad_room(league, team, p)
    except ValueError: return False
    if p.team and p.team in league.teams and p in league.teams[p.team].roster:
        league.release(pid, log=False)
    if pid in league.free_agents: league.free_agents.remove(pid)
    # off the wire: a man signed to a squad is not there to be claimed (cutdown-day squads fill from the waiver pool)
    wire = getattr(league, 'waivers', None) or []
    for e in [e for e in wire if e.get('pid') == pid]:
        if getattr(league, 'user_team', None) in e.get('claims', []):
            import inbox as IB
            IB.post(league, 'waiver_notice', f"Claim void: {inbox_player(p)} signed to {abbr}'s squad", f"{inbox_player(p)} ({p.pos}) was signed to {abbr}'s practice squad before the wire cleared. Your claim did not go through.", sender='league')
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
    if p not in squad(team) or p.retired or p.team != abbr or p.out_until is not None: return False
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    c=Contract(years=years,base=[mn]*years,signed=league.year)
    c.base[0]*=max(0,18-team.cap.paid_week)/18; c.pay_start=team.cap.paid_week
    allowed, outgoing = _active_move(league, team, p, c, essential=emergency, action='ps_callup')
    if not allowed: return False
    if outgoing: league.release(outgoing.pid)
    squad(team).remove(p); p.xp_spent.pop('_ps', None); p.team = None
    league.sign(pid, abbr, c, log=False)
    league.log('ps_callup', pid=pid, team=abbr)          # the one line for the move
    return True


def minimum_contract(league, team, player):
    """An unsigned replacement is paid only for the remaining regular season."""
    salary = MS.minimum_salary(player.accrued or 0, CAP.get(league.year, 301.2))
    paid = team.cap.paid_week
    return Contract(years=1, base=[salary * max(0, 18-paid)/18],
                    signed=league.year, pay_start=paid)


def available_free_agents(league):
    """The FA list also contains waived players whose claim period is open."""
    import waivers
    pending = {e['pid'] for e in waivers.pending(league)}
    return [p for pid in league.free_agents if pid not in pending
            for p in [league.player(pid)]
            if p and p.team is None and not p.retired and p.out_until is None]


def _cpu_move_budget(league, team, player, contract, outgoing=None, *, essential=False,
                     action='roster_repair'):
    """Screen the complete CPU move before changing either roster."""
    if team.abbr == getattr(league, 'user_team', None):
        return True
    import financial_plan as FP
    import roster_needs as RN
    group = GROUP_OF.get(player.pos, player.pos)
    shortage = (outgoing is None and len(team.active()) < 53
                or essential_depth(team, week=league.week)['shortages'].get(group, 0) > 0)
    return FP.evaluate(league, team, additions=[(player, contract)],
                       removals=[outgoing.pid] if outgoing else [],
                       gain=RN.move_gain(team, player, outgoing),
                       essential=essential or (player.out_until is None and shortage),
                       action=action)['approved']


def sign_minimum(league, abbr, player, log=True, essential=False):
    """Validate ownership and cap; roster cleanup follows the acquisition."""
    team = league.teams[abbr]
    if player not in available_free_agents(league): return False
    contract = minimum_contract(league, team, player)
    allowed, outgoing = _active_move(league, team, player, contract, essential=essential)
    if not allowed: return False
    if outgoing: league.release(outgoing.pid)
    league.sign(player.pid, abbr, contract, log=log)
    player.xp_spent['_cpu_added'] = [league.year, int(league.week or 0)]
    return True


def minimum_fits(league, team, player, essential=False):
    """Filter unaffordable first choices so a cheaper healthy option is tried."""
    from cap_accounting import require_room
    try:
        require_room(league, team, player.pid, minimum_contract(league, team, player))
    except ValueError:
        return False
    return True


def shunned(p, abbr, league):
    """A club does not sign or claim a man it released in the last eight weeks, and a man released by three clubs
    this season is nobody's first call."""
    rb = (p.xp_spent.get('_released_by') or {}) if hasattr(p, 'xp_spent') else {}
    wk = int(league.week or 0)
    if abbr in rb and 0 <= wk - int(rb[abbr]) <= 8: return True
    if int(p.xp_spent.get('_releases_year', -1) or -1) == league.year and int(p.xp_spent.get('_releases_this_year', 0) or 0) >= 3: return True
    return False


def protected(team, q, league, incoming=None):
    """Men a club does not release to make room: its only kicker, punter or long snapper; a first- or second-round
    pick in his first two seasons; anyone whose release costs more than about two million in dead money."""
    replacing_specialist = (incoming is not None and incoming is not q
        and incoming.pos == q.pos and not incoming.retired and incoming.out_until is None)
    if q.pos in ('K', 'P', 'LS') and not replacing_specialist and sum(1 for x in team.active() if x.pos == q.pos) <= 1: return True
    rd = getattr(q, 'draft_round', None); dy = getattr(q, 'draft_year', None)
    if rd is not None and int(rd) <= 2 and dy is not None and league.year - int(dy) <= 1: return True
    try:
        if float(q.dead_if_cut(0)) > 2.0: return True
    except Exception: pass
    return False


def essential_depth(team, players=None, week=None):
    """Usable backup coverage, distinct from the ideal 53-man roster shape.

    OL and defensive groups permit positional flexibility. Short absences still
    belong to the club; elevations cover them instead of forcing a release.
    """
    import offense_roles as OR
    package = OR.PACKAGES[OR.base_package(getattr(team, 'gm', None))]
    floors = dict(GROUP_MIN, LS=1, TE=max(2, package['TE'] + 1),
                  WR=max(4, package['WR'] + 1))
    players = team.active() if players is None else players
    counts = collections.Counter(GROUP_OF.get(p.pos, p.pos) for p in players
        if not p.retired and (week is None or p.out_until is None
        or int(p.out_until) < 99 and int(p.out_until) - int(week) <= 2))
    return dict(counts=counts, floors=floors,
                shortages={g:n-counts[g] for g,n in floors.items() if counts[g]<n})


def _recent_additions(league, team):
    week = int(getattr(league, 'week', 0) or 0)
    recent = {p.pid for p in team.active()
              if (mark := p.xp_spent.get('_cpu_added')) and mark[0] == league.year
              and 0 <= week - int(mark[1]) <= 3}
    recent.update(e.get('pid') for e in getattr(league, 'transactions', ())
        if e.get('team') == getattr(team, 'abbr', None) and e.get('year') == league.year
        and e.get('kind') in ('sign', 'ps_callup', 'ps_poach', 'emergency_sign')
        and 0 <= week - int(e.get('week') or 0) <= 3)
    return recent


def _room_candidates(league, team, p):
    """Preserve needed coverage before comparing possible releases."""
    import roster_needs as RN
    active = team.active()
    before = essential_depth(team, active, league.week)
    group = GROUP_OF.get(p.pos, p.pos)
    repairing = before['shortages'].get(group, 0) > 0
    recent = _recent_additions(league, team)
    report = RN.assess(team)
    starters = {r['player'].pid for r in report['assignments'] if r['player']}
    replace_specialist = p.pos in ('K', 'P', 'LS') and any(
        q.pos == p.pos and q.out_until is None for q in active)
    candidates = []
    for q in active:
        if replace_specialist and q.pos != p.pos: continue
        if q is p or locked(q, league.week) or protected(team, q, league, incoming=p): continue
        # Never dismiss an injured incumbent to cover his temporary absence.
        if q.out_until is not None: continue
        if repairing and q.pid in starters: continue
        if not repairing and q.pid in recent: continue
        after = essential_depth(team, [x for x in active if x is not q] + [p], league.week)
        if any(n > before['shortages'].get(g, 0) for g,n in after['shortages'].items()): continue
        if repairing and after['shortages'].get(group, 0) >= before['shortages'][group]: continue
        candidates.append(q)
    def position_priority(q):
        return 0 if q.pos == p.pos else 1 if GROUP_OF.get(q.pos,q.pos) == group else 2
    if candidates and not repairing:
        # A discretionary upgrade replaces its existing job. Do not turn a
        # rejected price into a search for cuts throughout the entire roster.
        priority = min(map(position_priority, candidates))
        candidates = [q for q in candidates if position_priority(q) == priority]
    candidates.sort(key=lambda q:(q.pid in recent, q.pid in starters,
        position_priority(q),
        q.ovr + 4.0 * float(q.dead_if_cut(0)) + RN.retention_value(team,q), str(q.pid)))
    for q in candidates:
        # An upgrade still needs to improve the actual lineup. Depth repair
        # can legitimately add a weaker backup alongside a strong starter.
        if not repairing and RN.move_gain(team,p,q,baseline=report) <= 0: continue
        yield q


def room_candidate(league, team, p, contract=None):
    """First affordable, coverage-safe departure for the proposed arrival."""
    from cap_accounting import require_room
    contract = contract if contract is not None else minimum_contract(league, team, p)
    for q in _room_candidates(league, team, p):
        try: require_room(league, team, p.pid, contract, release_pid=q.pid)
        except ValueError: continue
        return q
    return None


def _needs_room(league, team, essential=False):
    return len(team.active()) >= 53 and (league.phase in ('regular', 'playoffs')
        or essential and team.abbr != getattr(league, 'user_team', None))


def _active_move(league, team, p, contract, *, essential=False, action='roster_repair'):
    """Allow roster overflow; a CPU club may cut first only to fund the move."""
    from cap_accounting import require_room
    try:
        require_room(league, team, p.pid, contract)
    except ValueError:
        if team.abbr == getattr(league, 'user_team', None): return False, None
        for outgoing in _room_candidates(league, team, p):
            try: require_room(league, team, p.pid, contract, release_pid=outgoing.pid)
            except ValueError: continue
            if _cpu_move_budget(league, team, p, contract, outgoing,
                                essential=essential, action=action):
                return True, outgoing
        return False, None
    return _cpu_move_budget(league, team, p, contract,
                            essential=essential, action=action), None


def _make_room(league, abbr, p):
    """Do not release anyone as a side effect of an acquisition."""
    return True


def poach(league, abbr, pid, week, essential=False):
    """Sign another club's practice-squad man to your 53. Locked for three games."""
    p = league.player(pid)
    if p is None or p.retired or p.out_until is not None: return False
    src = p.team
    if src not in league.teams or src == abbr or p not in squad(league.teams[src]): return False
    team = league.teams[abbr]
    cap = CAP.get(league.year, 301.2)
    mn = MS.minimum_salary(p.accrued or 0, cap)
    c=Contract(years=1,base=[mn*max(0,18-team.cap.paid_week)/18],signed=league.year,pay_start=team.cap.paid_week)
    allowed, outgoing = _active_move(league, team, p, c, essential=essential, action='ps_poach')
    if not allowed: return False
    if outgoing: league.release(outgoing.pid)
    squad(league.teams[src]).remove(p); league.teams[src].sync_cap(); p.xp_spent.pop('_ps', None); p.team = None
    league.sign(pid, abbr, c, log=False)
    p.xp_spent['_poach_lock'] = (week or 0) + POACH_LOCK_GAMES
    league.log('ps_poach', pid=pid, team=abbr, source=src, locked_until=(week or 0) + POACH_LOCK_GAMES)
    return True


def locked(p, week):
    return (p.xp_spent.get('_poach_lock') or -1) > (week or 0)


def elevate(league, abbr, pids, week, playoffs=False):
    """Game-day elevations: the men play this week and go back after."""
    team = league.teams[abbr]; out = []
    for pid in list(dict.fromkeys(pids))[:ELEVATIONS_PER_GAME]:
        if len(getattr(team, '_elevated', []) or []) >= ELEVATIONS_PER_GAME: break
        p = league.player(pid)
        if p not in squad(team) or p.retired or p.out_until is not None: continue
        if p in (getattr(team, '_elevated', []) or []): continue
        n = p.xp_spent.get('_elevations', 0)
        if n >= ELEVATIONS_PER_MAN and not playoffs:
            if call_up(league, abbr, pid): out.append((pid, 'signed'))
            continue
        if not playoffs: p.xp_spent['_elevations'] = n + 1
        team._elevated = getattr(team, '_elevated', []) + [p]
        out.append((pid, 'elevated'))
    return out


def clear_elevations(team):
    team._elevated = []


def reset_season(league):
    # IR clears at camp: everyone comes off, the returns count resets, the designations reset
    for t in league.teams.values():
        clear_elevations(t)
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
            IB.post(league, 'club', f"{len(left)} undrafted rookies are on the market", f"{len(left)} undrafted rookies remain unsigned and will sign for the minimum. Sign to the roster or practice squad from Free Agency; the Undrafted filter shows them.", sender='assistants', payload=dict(link='fa', mail_sections=[IB.mail_section('Your scouts’ best available', [[inbox_player(p), p.pos, str(round(view_ovr(league, user, p)))] for p in top], ['Player', 'Position', 'Scouted OVR'])]))
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
        coverage = essential_depth(team, week=wk_)
        for grp, floor in coverage['floors'].items():
            healthy = essential_depth(team, week=wk_)['counts']
            short = floor - healthy.get(grp, 0)
            hard = healthy.get(grp, 0) < HARD_MIN.get(grp, 0)
            if short > 0 and abbr == user and not hard:
                # THE GM'S CLUB IS HIS TO FILL. No automatic call-up: the trainers say who is out, that the chart is
                # short there, and who on the squad (or the street) could cover; the game dresses what he has.
                try:
                    import inbox as IB
                    out_men = [p for p in team.active() if GROUP_OF.get(p.pos, p.pos) == grp and p.out_until is not None]
                    cands = sorted([p for p in squad(team) if GROUP_OF.get(p.pos, p.pos) == grp and p.out_until is None and not p.retired and minimum_fits(league, team, p)], key=lambda p: -p.ovr)
                    fa = sorted([q for q in available_free_agents(league) if q and GROUP_OF.get(q.pos, q.pos) == grp and q.out_until is None and not q.retired and minimum_fits(league, team, q)], key=lambda q: -q.ovr)[:2]
                    key_ = f"short-{grp}-{league.year}-{week}"
                    if not any((mm.get('payload') or {}).get('key') == key_ for mm in getattr(league, 'inbox', [])):
                        sections = [IB.mail_section(title, [[inbox_player(p), p.pos, str(round(p.ovr))] for p in players], ['Player', 'Position', 'OVR']) for title, players in [('Unavailable', out_men[:3]), ('Practice-squad options', cands[:2]), ('Free-agent options', fa)] if players]
                        IB.post(league, 'injury', f"Short at {grp}: {short} below the floor", f"The chart at {grp} is {short} below the number the game needs. Call up or sign before Sunday." + (" Nobody on the squad or the street plays there." if not cands and not fa else ''), sender='trainers', payload=dict(key=key_, link='club:ps' if cands else 'personnel:fa', group=grp, mail_sections=sections))
                except Exception: pass
                continue
            if short > 0 and abbr == user and hard:
                try:
                    import inbox as IB
                    IB.post(league, 'injury', f"Emergency at {grp}: roster help needed", f"The chart at {grp} fell below what the game can dress ({healthy.get(grp, 0)} healthy). An affordable replacement will be sought; check the practice-squad and free-agent pages to resolve any remaining shortage.", sender='trainers', payload=dict(link='club:ps'))
                except Exception: pass
            if abbr != user and getattr(team, '_moved_week', None) == wk_ and not hard:
                continue                                  # one roster addition a week per club, short of an emergency
            while short > 0:
                cands = sorted([p for p in squad(team) if GROUP_OF.get(p.pos, p.pos) == grp
                    and p.out_until is None and not p.retired],
                    key=lambda p: (not minimum_fits(league, team, p, essential=True), -p.ovr))
                best = next((p for p in cands if call_up(league, abbr, p.pid, emergency=True)), None)
                if best is not None:
                    moves.append((abbr, 'callup', best.pid)); team._moved_week = wk_
                else:
                    fa = available_free_agents(league)
                    fa = sorted([p for p in fa if GROUP_OF.get(p.pos, p.pos) == grp
                        and not shunned(p, abbr, league)],
                        key=lambda p: (not minimum_fits(league, team, p, essential=True), -p.ovr))
                    best = next((p for p in fa if sign_minimum(league, abbr, p, log=False, essential=True)), None)
                    if best is None: break
                    team._moved_week = wk_
                    league.log('emergency_sign', pid=best.pid, team=abbr, group=grp)
                    moves.append((abbr, 'emergency', best.pid))
                remaining = essential_depth(team, week=wk_)['shortages'].get(grp, 0)
                if remaining >= short: break  # Never count an exchange as added depth.
                short = remaining
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
            cands = sorted([q for q in squad(team) if q.pos == pos and q.out_until is None and not q.retired and minimum_fits(league, team, q)], key=lambda q: -q.ovr)
            if cands and call_up(league, abbr, cands[0].pid, emergency=True):
                moves.append((abbr, 'callup', cands[0].pid)); added += 1
                current = RN.assess(team); continue
            fa = available_free_agents(league)
            fa = [q for q in fa if q and q.pos == pos and q.out_until is None and not q.retired and not shunned(q, abbr, league) and minimum_fits(league, team, q)]
            if not fa: continue
            best = max(fa, key=lambda q: q.ovr)
            if not sign_minimum(league, abbr, best, log=False, essential=True): continue
            mn = best.apy
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
                cands = sorted([q for q in squad(team) if GROUP_OF.get(q.pos, q.pos) == grp and q.out_until is None and not q.retired and minimum_fits(league, team, q)], key=lambda q: -q.ovr)
                if cands and call_up(league, abbr, cands[0].pid, emergency=True):
                    moves.append((abbr, 'callup', cands[0].pid)); added += 1
                    called_up = True
                    break
                fa = available_free_agents(league)
                fa = [q for q in fa if q and GROUP_OF.get(q.pos, q.pos) == grp and q.out_until is None and not q.retired and not shunned(q, abbr, league) and minimum_fits(league, team, q)]
                if fa:
                    best = max(fa, key=lambda q: q.ovr + 12.0 * needs.get(q.pos, 0.0))
                    break
            if called_up:
                continue
            if best is None:
                break
            if not sign_minimum(league, abbr, best, log=False, essential=True): break
            mn = best.apy
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
        recent = _recent_additions(league, team)
        bottom = sorted([q for q in team.active() if q.pid not in recent and not protected(team, q, league) and not locked(q, week) and q.out_until is None
                         and float(getattr(q, 'apy', 0.0) or 0.0) <= MS.minimum_salary(3, cap) + 0.05], key=value)[:5]
        best = None
        for q in bottom:
            pool = [p for p in fa_all if p.pid in league.free_agents and p.pos == q.pos and not shunned(p, abbr, league)]
            pool += [p for t2, tm in league.teams.items() if t2 != abbr for p in squad(tm)
                     if p.pos == q.pos and not p.retired and p.out_until is None and not shunned(p, abbr, league)]
            if not pool: continue
            p = max(pool, key=lambda x: x.ovr + GE.scheme_fit(x.ratings, x.pos, team))
            gain = (p.ovr + GE.scheme_fit(p.ratings, p.pos, team)) - (q.ovr + GE.scheme_fit(q.ratings, q.pos, team))
            if gain >= SWAP_GAP and (best is None or gain > best[0]):
                best = (gain, q, p)
        if best is None: continue
        gain, q, p = best
        contract = minimum_contract(league, team, p)
        # Another club may already have signed a candidate from the review's
        # cached pool. Validate his current location before releasing our man.
        is_fa = p.pid in league.free_agents
        source = league.teams.get(p.team) if p.team else None
        if not is_fa and (source is None or p not in squad(source)):
            continue
        from cap_accounting import require_room
        try: require_room(league, team, p.pid, contract, release_pid=q.pid)
        except ValueError: continue
        if not _cpu_move_budget(league, team, p, contract, q, action='roster_upgrade'):
            continue
        league.release(q.pid)
        if is_fa:
            league.free_agents.remove(p.pid); p.contract = None
            league.sign(p.pid, abbr, contract)
        else:
            src = p.team; squad(league.teams[src]).remove(p); p.xp_spent.pop('_ps', None); p.team = None
            league.sign(p.pid, abbr, contract, log=False)
            p.xp_spent['_poach_lock'] = int(week or 0) + POACH_LOCK_GAMES
            league.log('ps_poach', pid=p.pid, team=abbr, source=src, locked_until=int(week or 0) + POACH_LOCK_GAMES)
        team._moved_week = int(week or 0)
        moves.append((abbr, 'swap', q.pid, p.pid))
    return moves


def weekly(league, rng, week, user_team=None, playoffs=None):
    """
    In season, every week: clubs short of healthy players at a group elevate two
    for the game or call one up; and a club with a hole may poach another's
    squad man to its 53 when nothing on its own squad fits. Rare.
    """
    import contracts as CT
    if playoffs is None: playoffs = league.phase == 'playoffs'
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
        want = sorted((p for p in squad(team) if p.out_until is None and not p.retired), key=lambda p: -p.ovr)
        picks = [p.pid for p in want if by_pos.get(p.pos, 0) < {'QB': 2, 'HB': 2, 'WR': 5, 'TE': 2, 'CB': 4, 'DT': 3}.get(p.pos, 2)][:short]
        if picks:
            moves += [(abbr, 'elevate', x) for x in elevate(league, abbr, picks, week,
                                                         playoffs=playoffs)]
        elif abbr != user_team and rng.random() < 0.25:
            # nothing at home fits: look at everyone else's squad for the thinnest spot
            thin = min(by_pos, key=by_pos.get) if by_pos else None
            cands = [p for t2, tm in league.teams.items() if t2 != abbr for p in squad(tm) if p.pos == thin]
            if cands:
                p = max(cands, key=lambda p: p.ovr)
                if poach(league, abbr, p.pid, week, essential=True):
                    moves.append((abbr, 'poach', p.pid))
    return moves
