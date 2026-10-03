from stable import stable_seed
"""
PERSONALITY.

Four hidden traits on every man, 0-100, drawn once and fixed for his career.
Each multiplies one thing that already exists:

  work_ethic          XP earned, 0.8x to 1.2x. The dev tier is still the ceiling.
  financial_priority  the agent's ask, -5% to +5% of market, and the certainty
                      discount he gives on an extension, which shrinks to
                      nothing for a man who wants every dollar
  loyalty             the extension discount (larger for a loyal man, gone for a
                      mercenary), the offseason request roll (lower for the
                      loyal), and his own club's offer in free agency
  ambition            what he believes he is owed (entitlement), scaled up for
                      the ambitious and down for the content

SEEDED MEN get priors from the record only, never from reputation: a man who
re-signed with his club under the market leans loyal; a man who left for the
top of his position market leans the other way; a man whose rating beats what
his draft slot predicts out-worked his slot. Each prior moves the mean by at
most fifteen points and noise does the rest, so the record tilts a man
without labelling him. Rookies and newgens are a centred draw.

What a club sees is a scout's read with room error; the truth stays hidden.
"""
import numpy as np

TRAITS = ('work_ethic', 'financial_priority', 'loyalty', 'ambition')
MEAN, SD = 50.0, 16.0

WORDS = {
    'work_ethic':         [(70, 'grinder'), (58, 'hard worker'), (42, None), (30, 'coasts'), (0, 'needs pushing')],
    'financial_priority': [(70, 'wants to be paid'), (58, 'money matters'), (42, None), (30, 'not about the money'), (0, 'plays for the love of it')],
    'loyalty':            [(70, 'loyal'), (58, 'settled'), (42, None), (30, 'keeps his options open'), (0, 'follows the money')],
    'ambition':           [(70, 'wants the ball'), (58, 'ambitious'), (42, None), (30, 'team-first'), (0, 'happy in a role')],
}


def reconcile(t, rng):
    """No player carries traits that contradict each other in words. Four independent draws let any pairing land
    on one player, and about one in six read as a contradiction: a player who keeps his options open or follows
    the money while not being about the money; a player who coasts or needs pushing while wanting the ball; a
    player happy in a role who wants every dollar. Each is resolved by moving the trait that makes the smaller
    change, to a value that reads as consistent, with a little noise so the fixes do not all land on one number."""
    t = dict(t)
    # options open / follows the money (loyalty under 42) means money matters at least somewhat
    if t['loyalty'] < 42 and t['financial_priority'] < 42:
        t['financial_priority'] = float(np.clip(rng.normal(58, 7), 42, 97))
    # no effort (work ethic under 42) is not ambitious
    if t['work_ethic'] < 42 and t['ambition'] >= 58:
        t['ambition'] = float(np.clip(rng.normal(49, 5), 42, 57))
    # happy in a role (ambition under 30) does not want every dollar
    if t['ambition'] < 30 and t['financial_priority'] >= 70:
        t['financial_priority'] = float(np.clip(rng.normal(60, 5), 42, 69))
    return t


def conflicts(t):
    """The contradictions reconcile removes, for tests and the load check."""
    out = []
    if t['loyalty'] < 42 and t['financial_priority'] < 42: out.append('options open / not about the money')
    if t['work_ethic'] < 42 and t['ambition'] >= 58: out.append('coasts / ambitious')
    if t['ambition'] < 30 and t['financial_priority'] >= 70: out.append('happy in a role / wants to be paid')
    return out


def draw(rng, priors=None):
    priors = priors or {}
    return reconcile({k: float(np.clip(rng.normal(MEAN + priors.get(k, 0.0), SD), 3, 97)) for k in TRAITS}, rng)


def reconcile_all(league):
    """Players already in a save: resolve any contradiction once, deterministically from the player id."""
    n = 0
    for p in league.players.values():
        t = getattr(p, 'traits', None)
        if t and conflicts(t):
            rng = np.random.default_rng(stable_seed(p.pid))
            p.traits = reconcile(t, rng); n += 1
    return n


def ensure(p, rng):
    if not getattr(p, 'traits', None):
        p.traits = draw(rng)
    ensure_discipline(p)
    return p.traits


def ensure_discipline(p):
    """Persist once, without consuming the league RNG or rerolling old traits."""
    if not getattr(p, 'traits', None):
        p.traits = draw(np.random.default_rng(stable_seed(('personality', p.pid))))
    if 'discipline' not in p.traits:
        p.traits = dict(p.traits)
        rng = np.random.default_rng(stable_seed(('discipline-v1', p.pid)))
        p.traits['discipline'] = float(np.clip(rng.normal(50, 18), 3, 97))
    return discipline(p)


def discipline(p):
    """Read-only neutral fallback for custom players; loading/creation persists it."""
    traits = (p.get('traits') if isinstance(p, dict) else getattr(p, 'traits', None)) or {}
    value = traits.get('discipline', p.get('discipline', 50) if isinstance(p, dict) else 50)
    try:
        value = float(value)
        return max(0., min(100., value)) if np.isfinite(value) else 50.
    except (TypeError, ValueError):
        return 50.


def penalty_multiplier(p, penalty_name):
    """Relative risk, applied only to a player eligible to commit this foul."""
    strength = {
        'Unnecessary Roughness': .20, 'Unsportsmanlike Conduct': .20,
        'Roughing the Passer': .20, 'Roughing the Kicker': .20,
        'False Start': .10, 'Defensive Offside': .10, 'Offside': .10,
        'Encroachment': .10, 'Neutral Zone Infraction': .10,
        'Offensive Holding': .05, 'Defensive Holding': .05, 'Holding': .05,
        'Return Holding': .05, 'Defensive Pass Interference': .05,
        'Offensive Pass Interference': .05, 'Illegal Contact': .05,
        'Face Mask': .05, 'Illegal Use of Hands': .05, 'Illegal Block in Back': .05,
    }.get(penalty_name, 0.)
    return 1. + strength * (50. - discipline(p)) / 50.


def words(traits):
    out = []
    for k in TRAITS:
        v = traits.get(k, 50)
        for floor, w in WORDS[k]:
            if v >= floor:
                if w: out.append(w)
                break
    return ', '.join(out) if out else 'even-keeled'


# ------------------------------------------------------------ the priors, from the record
def priors_from_record(league, p, slot_expect=None):
    """What the roster data says about a seeded man, as small shifts of the mean."""
    pr = {}
    c = p.contract
    # loyalty and money: how he got his current deal, read against his market
    if c is not None and p.team and p.apy and p.ovr >= 74 and (p.accrued or 0) >= 4:
        try:
            import valuation as VAL
            v = VAL.value_player(league, p, side='team', rng=None)
        except Exception:
            v = None
        if v and v.get('apy'):
            ratio = p.apy / max(1.0, v['apy'])
            same_club = (p.draft_year is not None and getattr(p, 'draft_team', None) in (None, p.team))
            if ratio <= 0.85 and same_club:
                pr['loyalty'] = pr.get('loyalty', 0) + 12; pr['financial_priority'] = pr.get('financial_priority', 0) - 8
            elif ratio >= 1.15:
                pr['financial_priority'] = pr.get('financial_priority', 0) + 10; pr['loyalty'] = pr.get('loyalty', 0) - 6
    # a drafted man still with his club deep into a second contract leans loyal
    if p.draft_year is not None and (p.accrued or 0) >= 6 and getattr(p, 'draft_team', None) in (None, p.team) and c is not None:
        pr['loyalty'] = pr.get('loyalty', 0) + 6
    # work ethic: his rating against what his slot predicted at his age
    if slot_expect is not None and p.draft_overall and (p.accrued or 0) >= 2:
        exp = slot_expect(p.draft_overall, p.age)
        if exp is not None:
            d = float(np.clip((p.ovr - exp) / 2.0, -15, 15))
            pr['work_ethic'] = pr.get('work_ethic', 0) + d
    return pr


def _slot_expect_factory(league):
    """Expected rating by draft slot and age, from the men in this league."""
    men = [p for t in league.teams.values() for p in t.active() if p.draft_overall and (p.accrued or 0) >= 2]
    if len(men) < 200: return None
    xs = np.array([[np.log(p.draft_overall), min(p.age, 31)] for p in men], float)
    ys = np.array([p.ovr for p in men], float)
    A = np.c_[np.ones(len(xs)), xs]
    coef, *_ = np.linalg.lstsq(A, ys, rcond=None)
    def f(slot, age):
        return float(coef[0] + coef[1] * np.log(max(1, slot)) + coef[2] * min(age, 31))
    return f


def assign_all(league, rng):
    """Every man in the league who has no traits yet."""
    se = _slot_expect_factory(league)
    n = 0
    for p in league.players.values():
        if not getattr(p, 'traits', None):
            pri = priors_from_record(league, p, se) if p.team else {}
            p.traits = draw(rng, pri); n += 1
        ensure_discipline(p)
    return n


# ------------------------------------------------------------ the multipliers
def xp_mult(p):
    t = getattr(p, 'traits', None)
    return 1.0 if not t else 0.8 + 0.4 * (t.get('work_ethic', 50) / 100.0)


def ask_mult(p):
    t = getattr(p, 'traits', None)
    return 1.0 if not t else 0.95 + 0.10 * (t['financial_priority'] / 100.0)


def certainty_discount_mult(p):
    """The discount a man gives for money now: none for the man who wants every dollar."""
    t = getattr(p, 'traits', None)
    return 1.0 if not t else float(np.clip(1.6 - 1.4 * (t['financial_priority'] / 100.0), 0.0, 1.5))


def extension_discount(p):
    """A loyal man leaves something on the table to stay; a mercenary leaves nothing."""
    t = getattr(p, 'traits', None)
    return 0.0 if not t else float(np.clip(0.10 * (t['loyalty'] - 50) / 50.0, -0.04, 0.10))


def request_mult(p):
    t = getattr(p, 'traits', None)
    return 1.0 if not t else float(np.clip(1.5 - 1.0 * (t['loyalty'] / 100.0), 0.5, 1.5))


def entitlement_mult(p):
    t = getattr(p, 'traits', None)
    return 1.0 if not t else 0.85 + 0.30 * (t['ambition'] / 100.0)


def own_club_bonus(p):
    """His own club's offer in free agency, as a share of value."""
    t = getattr(p, 'traits', None)
    return 0.0 if not t else float(np.clip(0.08 * (t['loyalty'] - 50) / 50.0, -0.04, 0.08))


def scout_read(p, error_sd, rng):
    """A room's read of his character, with its error."""
    t = ensure(p, rng)
    return {k: float(np.clip(v + rng.normal(0, error_sd * 6), 3, 97)) for k, v in t.items()}
