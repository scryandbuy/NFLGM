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
            self.status[p.pid] = d
            if d in ('questionable', 'doubtful') and will_play(d, rng):
                # He is going. It costs him, and the club knows it.
                self.playing_hurt[p.pid] = d
                p.out_until = None
                league.log('played_hurt', pid=p.pid, team=team.abbr,
                           listed=d)

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
