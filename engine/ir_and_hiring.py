"""
Injured reserve and hiring.

Both are real, specified systems rather than judgment calls, so the rules below
are the CBA's and the pipeline is what the last hiring cycle actually did.
As everywhere else: these answer questions, they do not act.
"""
import numpy as np

# ================================================================ injured reserve
IR_RETURN_SLOTS = 8          # per season; 10 if the club makes the playoffs
IR_RETURNS_PER_PLAYER = 2    # each use still counts against the eight
IR_MIN_GAMES = 4             # GAMES, not weeks - a bye gives no relief
PRESEASON_IR_RECALLS = 2     # 2025 rule change: two men placed on IR at cutdown
                             # may still come back
PS_ELEVATIONS = 3            # regular-season gameday call-ups per player,
                             # without taking a 53-man spot

class IRBook:
    """
    Tracks a club's designated-to-return budget. The budget is the interesting
    part: eight slots is a genuine resource a GM has to allocate across a season
    he cannot see the end of.
    """
    def __init__(self, playoffs_expected=False):
        self.slots = IR_RETURN_SLOTS + (2 if playoffs_expected else 0)
        self.used = 0
        self.per_player = {}

    def can_designate(self, pid):
        return (self.used < self.slots
                and self.per_player.get(pid, 0) < IR_RETURNS_PER_PLAYER)

    def designate(self, pid):
        if not self.can_designate(pid): return False
        self.used += 1
        self.per_player[pid] = self.per_player.get(pid, 0) + 1
        return True

    @property
    def left(self): return self.slots - self.used

def ir_eligible_to_return(placed_week, current_week, before_53_set=False,
                          preseason_recalls_used=0):
    """
    Four GAMES must elapse. A man put on IR before the 53 is set is done for the
    year, except that two per club may now be recalled.
    """
    if before_53_set:
        return preseason_recalls_used < PRESEASON_IR_RECALLS
    return (current_week - placed_week) >= IR_MIN_GAMES

def ir_decision(player, team, gm, book, weeks_left, in_contention):
    """
    Should this man take one of the eight slots? Spending a slot in week 6 on a
    depth player is why clubs run out in December.
    """
    g = gm.shift(team)
    if not book.can_designate(player['pid']): return 0.0
    scarcity = 1.0 - (book.left / max(1, book.slots))       # slots get precious
    worth = player['value_to_team']
    games_back = max(0, weeks_left - IR_MIN_GAMES)
    urgency = (0.35 + 0.9 * in_contention) * (games_back / 17.0)
    return round(float(worth * urgency - scarcity * 6.0 * (1.0 - g.aggression)), 2)

def ir_cap_note():
    """A man on IR does NOT count against the 53, but his salary DOES count
    against the cap. Placing him frees a roster spot, never money."""
    return dict(counts_against_roster=False, counts_against_cap=True)

# ================================================================ hiring
# Every 2026 GM hire came from the same pipeline: assistant GMs and VPs of
# player personnel. Head coaches come from coordinators and from the recycled
# pool. Recycling is the important part - Stefanski was fired by Cleveland and
# hired by Atlanta in the same cycle; Harbaugh and McCarthy were rehired too.
PIPELINE = {
    'assistant_gm':      0.38,
    'vp_player_personnel': 0.22,
    'director_scouting': 0.14,
    'recycled':          0.26,      # previously fired, carrying his archetype
}

# What a club reaches for depends on the hole it is in. These are the league's
# revealed habits, not a rule anyone wrote down.
def hire_weights(team_state):
    """
    team_state: dict with win_pct, playoff_drought, has_young_qb, cap_health
    Returns a weighting over GM archetypes.
    """
    w = dict(analytics=1.0, traditional=1.0, gunslinger=1.0,
             hoarder=1.0, win_now=1.0, developer=1.0, balanced=1.4)
    if team_state['win_pct'] <= 0.35:
        w['developer'] *= 2.1; w['hoarder'] *= 1.8; w['analytics'] *= 1.6
        w['win_now'] *= 0.35; w['gunslinger'] *= 0.6
    if team_state['win_pct'] >= 0.60:
        w['win_now'] *= 2.2; w['gunslinger'] *= 1.7; w['traditional'] *= 1.3
        w['developer'] *= 0.5; w['hoarder'] *= 0.4
    if team_state.get('playoff_drought', 0) >= 6:
        w['analytics'] *= 1.5; w['traditional'] *= 0.6    # what we did is not working
    if team_state.get('has_young_qb'):
        w['developer'] *= 1.9; w['win_now'] *= 0.7
    if team_state.get('cap_health', 0.5) < 0.3:
        w['analytics'] *= 1.6; w['hoarder'] *= 1.4; w['gunslinger'] *= 0.4
    return w

def hire_gm(team_state, pool, rng, make_gm_fn):
    """
    pool: list of previously-fired GM objects available for rehire.
    Returns (gm, source). A recycled man keeps his archetype and his tenure
    resets to 0, so he does not inherit the last regime's convictions either.
    """
    w = hire_weights(team_state)
    archetypes = list(w); probs = np.array([w[a] for a in archetypes], float)
    probs /= probs.sum()
    want = rng.choice(archetypes, p=probs)

    source = rng.choice(list(PIPELINE), p=list(PIPELINE.values()))
    if source == 'recycled' and pool:
        # prefer a fired man whose archetype matches what the club wants
        match = [g for g in pool if g.name == want]
        pick = rng.choice(match) if match else rng.choice(pool)
        pool.remove(pick)
        pick.tenure = 0
        pick.job_security = float(np.clip(rng.normal(.70, .12), .35, .95))
        return pick, 'recycled'

    g = make_gm_fn(rng, want)
    g.tenure = 0
    # a first-time hire gets a longer leash than a retread
    g.job_security = float(np.clip(rng.normal(.78, .10), .45, .97))
    return g, source
