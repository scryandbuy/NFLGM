"""
INJURY DESIGNATIONS, PLAYING HURT, AND INJURED RESERVE.

An injury was a number of weeks and nothing else. Real football has a whole
layer on top of that, and it is where most of the interesting decisions live:
a man is listed Questionable, you do not know until Sunday, and if he plays he
is not the player he was.

THE GAME STATUS REPORT. Three designations since 2016, when Probable was
scrapped - 95% of players listed Probable played, so it carried no
information. What is left:

    Out          will not play. No ambiguity.
    Doubtful     unlikely. Tracked play rate about 20-25%.
    Questionable uncertain. Plays roughly 50-70% depending on the injury,
                 and it is deliberately the widest category - league policy
                 says if there is ANY question, list him Questionable.
    (none)       expected to play.

Designations roll over on Wednesday, so a man listed Out on Sunday can open
the next week Questionable or clear entirely.

PLAYING HURT COSTS CONDITION, and it should cost different amounts. A man
listed Questionable who was always going to play gives up almost nothing. A
man who is genuinely hurt and tough enough to go anyway starts the game well
short of fresh - and because condition drives injury risk on a violently
nonlinear curve, he is also far more likely to break down again. That is the
real cost of playing him, and it is a choice rather than a penalty.

INJURED RESERVE, under the current rules:
  - a player on IR comes off the active roster but keeps his salary and
    contract, which is the whole reason the list exists
  - he must miss AT LEAST FOUR GAMES
  - a club may bring back EIGHT players a season
  - a single player may be designated to return twice, each one counting
    against the eight
"""
import numpy as np

# Play rates by designation, from multi-year tracking. Questionable is the
# wide one on purpose.
PLAY_RATE = {'out': 0.0, 'doubtful': 0.22, 'questionable': 0.62, None: 1.0}

# What a man gives up by playing hurt, as a starting condition penalty. It
# scales with how injured he actually is, not with what the club listed him
# as - the designation is what the public knows, the severity is the truth.
COND_PENALTY = {'questionable': 6.0, 'doubtful': 18.0}

# And he is likelier to go down again. Condition already drives injury risk,
# so this is on top of that - the tissue is damaged, not just tired.
REINJURY_MULT = {'questionable': 1.35, 'doubtful': 1.9}

IR_MIN_WEEKS = 4          # he must miss at least four games
IR_RETURNS_PER_TEAM = 8   # a club may bring back eight in a season
IR_DESIGNATIONS_PER_PLAYER = 2


def designation(weeks_left, rng, toughness=0.70):
    """
    What the club lists him as this week.

    Severity decides it, with a toughness nudge: the same hamstring on two
    players is Doubtful for one and Questionable for the other.
    """
    if weeks_left <= 0:
        return None
    if weeks_left >= 3:
        return 'out'
    edge = (toughness - 0.70) * 1.2
    if weeks_left == 2:
        return 'doubtful' if rng.random() > 0.25 + edge else 'out'
    # one week left: the wide band, and league policy says when in doubt,
    # Questionable
    r = rng.random()
    if r < 0.62 + edge:
        return 'questionable'
    return 'doubtful'


def will_play(desig, rng):
    return rng.random() < PLAY_RATE.get(desig, 1.0)


# ------------------------------------------------------------ playing hurt, by the injury
# What a man gives up when he plays through it, and the chance it flares. Both by the KIND of
# injury: a hamstring takes his speed, an ankle his change of direction, a shoulder his hands;
# soft tissue goes again far more often than a joint or a shoulder. The sizes are deliberately
# light (a Questionable starter still beats his backup most weeks), and a flare adds one or two
# weeks and never more, so playing hurt cannot end a season.
HIT_MAP = {
    'Hamstring': ['speed_rating', 'accel_rating', 'agility_rating'], 'Calf': ['speed_rating', 'accel_rating', 'agility_rating'],
    'Groin': ['speed_rating', 'accel_rating', 'agility_rating', 'change_of_direction_rating'], 'Quadricep': ['speed_rating', 'accel_rating', 'strength_rating'],
    'Ankle': ['agility_rating', 'change_of_direction_rating', 'jump_rating'], 'Foot': ['agility_rating', 'change_of_direction_rating', 'speed_rating'], 'Toe': ['agility_rating', 'change_of_direction_rating'],
    'Knee': ['speed_rating', 'accel_rating', 'agility_rating', 'change_of_direction_rating', 'jump_rating', 'strength_rating'],
    'Shoulder': ['throw_power_rating', 'throw_acc_short_rating', 'catch_rating', 'cit_rating', 'pass_block_rating', 'run_block_rating', 'tackle_rating', 'hit_power_rating'],
    'Elbow': ['throw_power_rating', 'catch_rating', 'pass_block_rating', 'run_block_rating'], 'Hand': ['catch_rating', 'cit_rating', 'carry_rating', 'pass_block_rating'],
    'Back': ['strength_rating', 'agility_rating', 'throw_power_rating'], 'Hip': ['strength_rating', 'agility_rating', 'speed_rating'], 'Neck': ['tackle_rating', 'hit_power_rating', 'strength_rating'],
    'Pectoral': ['strength_rating', 'pass_block_rating', 'run_block_rating', 'block_shed_rating'], 'Concussion': ['awareness_rating'], 'Illness': ['stamina_rating'], 'Other': ['agility_rating', 'strength_rating'],
}
# points off the affected attributes, (questionable, doubtful); toughness shaves up to 30%
HIT_SIZE = {'Concussion': (1.0, 2.0), 'Illness': (2.0, 4.0)}
HIT_DEFAULT = (3.0, 7.0)
# the chance it flares if he plays, (questionable, doubtful)
RISK = {'Hamstring': (.18, .28), 'Calf': (.16, .26), 'Groin': (.17, .27), 'Quadricep': (.15, .24),
        'Ankle': (.10, .15), 'Foot': (.10, .14), 'Toe': (.08, .12), 'Knee': (.11, .16), 'Hip': (.09, .13), 'Back': (.10, .15),
        'Shoulder': (.04, .07), 'Elbow': (.04, .06), 'Hand': (.03, .05), 'Neck': (.05, .08), 'Pectoral': (.05, .08),
        'Concussion': (0.0, 0.0), 'Illness': (.05, .08), 'Other': (.10, .15)}
FLARE_WEEKS = (1, 2)


def hurt_profile(p, desig):
    """(attribute hits {attr: -points}, flare risk) for this man playing through this week's designation."""
    kind = str(p.xp_spent.get('_inj_kind') or 'Other')
    i = 1 if desig == 'doubtful' else 0
    tough = float(p.ratings.get('tough_rating', 70)) / 100.0
    size = HIT_SIZE.get(kind, HIT_DEFAULT)[i] * (1.0 - 0.30 * max(0.0, min(1.0, (tough - 0.60) / 0.35)))
    hits = {a: -size for a in HIT_MAP.get(kind, HIT_MAP['Other']) if a in p.ratings}
    risk = RISK.get(kind, RISK['Other'])[i]
    if int(p.xp_spent.get(f'_inj_count_{kind}', 0) or 0) >= 2: risk *= 1.5     # the same injury twice this season
    return hits, min(0.6, risk)


def hurt_words(league, team, p, desig):
    """The trainers' sentence: what he gives up, what the risk is, what they would do. No numbers."""
    from views import surname, sentence
    kind = str(p.xp_spent.get('_inj_kind') or 'injury')
    hits, risk = hurt_profile(p, desig)
    d = [q for q in team.depth.get(p.pos, []) if q.pid != p.pid and q.out_until is None]
    backup = d[0] if d else None
    cost = {'Hamstring': 'he will not have his top gear', 'Calf': 'he will not have his top gear', 'Groin': 'he will be a step slow', 'Quadricep': 'he will be a step slow',
            'Ankle': 'his cuts will not be sharp', 'Foot': 'his cuts will not be sharp', 'Toe': 'his cuts will not be sharp', 'Knee': 'he will play well short of himself',
            'Shoulder': 'his hands and his strength at the point will be off', 'Elbow': 'his hands will be off', 'Hand': 'his hands will be off', 'Back': 'his strength will be down', 'Hip': 'he will be stiff',
            'Neck': 'he will not be at full strength', 'Pectoral': 'his strength will be down', 'Concussion': 'he is cleared and should be himself', 'Illness': 'he will tire early'}.get(kind, 'he will play short of himself')
    if risk >= 0.15: risk_w = f"a {kind.lower()} that goes again costs him a couple more weeks, and this one is the kind that goes again"
    elif risk >= 0.07: risk_w = f"there is some risk the {kind.lower()} gets worse, a week or two if it does"
    elif risk > 0: risk_w = f"the risk of making the {kind.lower()} worse is small"
    else: risk_w = 'there is no added risk in playing him'
    if backup is not None:
        gap = p.ovr - backup.ovr
        rec = (f"with {surname(backup.name)} healthy behind him the trainers would sit him" if (gap < 4 or risk >= 0.15 and gap < 8) else f"the trainers would let him go; {surname(backup.name)} is the drop-off")
    else: rec = 'there is nobody behind him, and the trainers would let him go'
    return sentence(f"{surname(p.name)} is {desig} with a {kind.lower()}{', a week from healthy' if desig == 'questionable' else ', two weeks from healthy'}. {cost} Sunday; {risk_w}. {rec}.")


def playing_hurt_penalty(desig):
    """(starting condition penalty, re-injury multiplier)."""
    return COND_PENALTY.get(desig, 0.0), REINJURY_MULT.get(desig, 1.0)


def ir_eligible(weeks_out):
    return weeks_out >= IR_MIN_WEEKS


class InjuryDesk:
    """
    One club's injury paperwork for a season: who is listed as what, who is on
    IR, and how many returns are left.
    """

    def __init__(self):
        self.status = {}        # pid -> designation this week
        self.ir = {}            # pid -> week placed
        self.designated = {}    # pid -> times designated to return
        self.returns_used = 0
        self.playing_hurt = {}  # pid -> designation he played through
        self.pending = {}       # the user's men awaiting Play or Sit

    # ---- weekly ------------------------------------------------------
    def set_week(self, league, team, week, rng):
        """
        Wednesday. Re-list everyone, decide who is going on IR, and decide
        which of the hurt are playing anyway.
        """
        self.status = {}
        self.playing_hurt = {}
        for p in list(team.roster):
            if p.out_until is None:
                continue
            left = max(0, int(p.out_until) - week + 1)
            if left <= 0:
                p.out_until = None
                continue

            # ---- IR ----
            # A long injury goes on the list: it frees a roster spot and he
            # keeps his money. Only worth doing if the club can still bring
            # somebody back, or if he is gone for the year anyway.
            on_ir = any(q.pid == p.pid for q in (getattr(team, 'ir', None) or []))
            if (not on_ir and ir_eligible(left) and team.abbr != getattr(league, 'user_team', None)
                    and int(p.xp_spent.get('_ir_desig', 0) or 0) < IR_DESIGNATIONS_PER_PLAYER):
                r = team.place_on_ir(p, week, season_ending=(left >= 14))
                if r.get('ok'):
                    self.status[p.pid] = 'ir'
                    league.log('ir', pid=p.pid, team=team.abbr, weeks=left)
                    continue
            if on_ir:
                self.status[p.pid] = 'ir'
                continue

            tough = float(p.ratings.get('tough_rating', 70)) / 100.0
            d = designation(left, rng, tough)
            # concussion protocol: never better than Doubtful the first week, and never played through
            if str(p.xp_spent.get('_inj_kind') or '') == 'Concussion' and d == 'questionable' and left >= 1 and int(p.xp_spent.get('_inj_week', 0) or 0) >= week - 1: d = 'doubtful'
            self.status[p.pid] = d
            if d in ('questionable', 'doubtful'):
                if team.abbr == getattr(league, 'user_team', None):
                    # THE GM DECIDES. The item sits in the inbox until Sunday; unanswered, the trainers call it.
                    self.pending[p.pid] = d
                    try:
                        import inbox as IB
                        IB.post(league, 'injury_decision', f"{p.name}: play or sit?", hurt_words(league, team, p, d), sender='trainers', payload=dict(pid=p.pid, listed=d, link=f'player:{p.pid}'), expires_week=week + 1)
                    except Exception: pass
                    continue
                if self._ai_plays(team, p, d, rng):
                    self.play_through(league, team, p, d)

    def _ai_plays(self, team, p, d, rng):
        """Expected value, not a coin flip: he plays when his hit-adjusted grade still beats the backup
        and the flare is not likely; a concussion never plays."""
        if str(p.xp_spent.get('_inj_kind') or '') == 'Concussion': return False
        hits, risk = hurt_profile(p, d)
        import targets as TG
        adj = TG.position_score(dict(p.ratings, **{a: p.ratings[a] + v for a, v in hits.items()}), p.pos)
        dd = [q for q in team.depth.get(p.pos, []) if q.pid != p.pid and q.out_until is None]
        backup = dd[0].ovr if dd else 40.0
        edge = adj - backup
        if edge <= 0.5: return False
        if risk >= 0.25 and edge < 6: return rng.random() < 0.3
        return rng.random() < 0.85

    def play_through(self, league, team, p, d):
        """He is going. It costs him on the field and it can flare."""
        self.playing_hurt[p.pid] = d
        self.pending.pop(p.pid, None)
        p.xp_spent['_hurt_desig'] = d; p.xp_spent['_hurt_until'] = p.out_until
        p.out_until = None
        league.log('played_hurt', pid=p.pid, team=team.abbr, listed=d)

    def sit(self, p):
        self.pending.pop(p.pid, None)

    def resolve_pending(self, league, team, rng):
        """Sunday morning: whatever the GM left unanswered, the trainers call by the real play rates."""
        for pid, d in list(self.pending.items()):
            p = league.player(pid)
            if p is None: self.pending.pop(pid, None); continue
            if will_play(d, rng): self.play_through(league, team, p, d)
            else: self.pending.pop(pid, None)

    def flare(self, league, team, week, rng):
        """After the game: a man who played hurt may have made it worse. One or two weeks, never more."""
        out = []
        for pid, d in list(self.playing_hurt.items()):
            p = league.player(pid)
            if p is None: continue
            hits, risk = hurt_profile(p, d)
            if rng.random() < risk:
                weeks = int(rng.integers(FLARE_WEEKS[0], FLARE_WEEKS[1] + 1))
                p.out_until = week + 1 + weeks
                league.log('aggravation', pid=pid, team=team.abbr, weeks=weeks, injury=p.xp_spent.get('_inj_kind'))
                out.append((p, weeks))
        return out

    def activate_from_ir(self, league, team, week):
        """
        Bring back whoever has served his four games, while returns remain.
        """
        back = []
        if team.abbr == getattr(league, 'user_team', None): return back        # the GM activates his own
        for p in list(getattr(team, 'ir', None) or []):
            r = team.activate_from_ir(p, week)
            if r.get('ok'):
                back.append(p); self.status.pop(p.pid, None)
                league.log('ir_return', pid=p.pid, team=team.abbr, returns_left=r.get('returns_left'))
        return back

    def available(self, player, week):
        """Is he on the field this Sunday?"""
        if player.pid in self.ir:
            return False
        if player.pid in self.playing_hurt:
            return True
        return player.out_until is None

    def condition_hit(self, pid):
        """What he starts the game at, and how much likelier he is to break."""
        d = self.playing_hurt.get(pid)
        if d is None:
            return 0.0, 1.0
        return playing_hurt_penalty(d)

    def report(self):
        """The Friday game status report."""
        out = {'out': [], 'doubtful': [], 'questionable': [], 'ir': []}
        for pid, d in self.status.items():
            if d in out:
                out[d].append(pid)
        return out


if __name__ == '__main__':
    rng = np.random.default_rng(3)
    print('designation by weeks remaining, 2000 draws each:')
    for wl in (1, 2, 3, 5):
        import collections
        c = collections.Counter(designation(wl, rng) for _ in range(2000))
        tot = sum(c.values())
        print('  %d week(s) left: %s' % (wl, ', '.join(
            f'{k} {100*v/tot:.0f}%' for k, v in c.most_common())))
    print('\nplay rates: questionable %.0f%%, doubtful %.0f%%, out %.0f%%'
          % (100 * PLAY_RATE['questionable'], 100 * PLAY_RATE['doubtful'],
             100 * PLAY_RATE['out']))
    print('playing hurt costs: questionable -%.0f condition and %.2fx injury '
          'risk; doubtful -%.0f and %.2fx'
          % (COND_PENALTY['questionable'], REINJURY_MULT['questionable'],
             COND_PENALTY['doubtful'], REINJURY_MULT['doubtful']))
