"""
Job security and firing.

Every firing is an INDEPENDENT decision by one team, driven by what has already
happened to that team. There is no league-wide quota and no "N firings per
year" rule. The real base rate - about 6.5 of 32 teams a season, roughly 20% -
is a VALIDATION TARGET, not an input. If the inputs are right it emerges; if it
comes out at 40% the inputs are wrong.

What the last decade of firings actually shows:
  - record alone is weak. Teams fired coaches at 9-8 and at 8-9, and kept
    others at worse marks.
  - REGRESSION is the strongest signal. Every firing profile is framed as a
    fall: 7-9 down to 3-7, 5-11 down to 2-7, 9-7 down to a bad year. Nobody is
    fired for being consistently mediocre; they are fired for getting worse.
  - drought accumulates on its own. Atlanta fired a GM at 8-9 because the
    playoff drought hit eight years.
  - tenure cuts both ways: a third of coaches are gone inside two years; the
    four-plus year group averages 8-8 over their tenure and is removed for a
    sudden downturn, not sustained failure.
  - reputation buys nothing. Stefanski had two Coach of the Year awards and two
    playoff trips and was fired at 5-12.
  - in-season firing is its own path, clustering around week 10 at about 3-7.
"""
import numpy as np

GAMES = 17


def team_evidence(team, *, record=None, history=None, season_year=None):
    """Employment evidence, without changing the other engines' Team.hist prior.

    A full season is an observed record, not a sample needing last year's eight
    extra games. Captured histories retain expectations and QB continuity when
    the calendar resets records or the roster changes. Legacy historical
    contexts without that QB evidence do not borrow a newly acquired starter.
    """
    hist = dict(team.hist() if history is None else history)
    current_year = getattr(getattr(team, 'league', None), 'year', None)
    historical = season_year is not None and current_year is not None and int(season_year) < int(current_year)
    if historical and history is None:
        previous = [h for h in team.history if h.get('year') is not None and int(h['year']) < int(season_year)]
        hist['prev_win_pct'] = max(previous, key=lambda h: int(h['year']))['win_pct'] if previous else None
    if record is None and historical:
        row = next((h for h in reversed(team.history) if h.get('year') == int(season_year)), {})
        record = row.get('record')
    elif record is None:
        record = team.record
    if record is not None:
        w, losses, ties = record
        games = w + losses + ties
        if games and (season_year is not None or games >= GAMES):
            hist['win_pct'] = (w + .5 * ties) / games
    if 'qb_continuity' not in hist:
        qb = team.starter('QB') if not historical else None
        # Existing public age/current-ability rule. It supports continuity;
        # it does not assert statistical improvement or read hidden potential.
        hist['qb_continuity'] = bool(qb and qb.age <= 25 and qb.ovr >= 78)
    return hist


def team_job_security(team):
    """Keep the last hiring/retention assessment until new games supply evidence."""
    gm = getattr(team, 'gm', None)
    if not sum(team.record) and gm is not None:
        return float(np.clip(gm.job_security, .02, .98))
    return job_security(team_evidence(team))


def pressure(hist, roster_pct=0.5, qb_dev=None):
    """
    Accumulated heat on this GM. 0 = untouchable, 1 = gone.
    hist: dict with
        win_pct        this season so far
        prev_win_pct   last season (None if this is year one)
        tenure         full seasons completed in the chair
        playoff_drought years since the team last made the playoffs
        expected_pct   what this roster should win (from roster strength)
    roster_pct: talent level 0-1. A bad record with a bad roster is survivable.
    qb_dev: legacy override for young established starter continuity. When
        omitted, use the same captured public evidence as the owner view.
    """
    w = hist['win_pct']
    prev = hist.get('prev_win_pct')
    ten = hist.get('tenure', 0)
    drought = hist.get('playoff_drought', 0)
    exp = hist.get('expected_pct', 0.35 + 0.30 * roster_pct)

    # 1. record, weakly
    p = max(0.0, (0.50 - w)) * 0.55

    # 2. REGRESSION - the strongest term
    if prev is not None:
        fall = max(0.0, prev - w)
        p += fall * 1.05

    # 3. underperforming the roster you were given
    p += max(0.0, exp - w) * 0.75

    # 4. drought, accumulating on its own
    p += min(0.30, max(0, drought - 1) * 0.050)

    # 5. tenure. year 1-2 is fragile; the middle is judged hardest on results;
    #    long tenure buys patience until a sharp fall.
    if ten == 0:   p *= 0.40          # a first-year coach is nearly untouchable; the real league fires one in twenty
    elif ten == 1: p *= 1.00
    elif ten <= 3: p *= 1.25          # years three and four are judged hardest on results
    elif ten >= 6: p *= 0.70 if (prev is None or prev - w < 0.18) else 1.05

    # 6. continuity around a young established starter buys patience. This
    # existing rule does not establish that his play improved this season.
    if qb_dev is None: qb_dev = hist.get('qb_continuity', False)
    if qb_dev: p *= 0.55

    # Soft saturation, not a hard clip. Clipping at 1.0 meant every severe case
    # pinned at maximum and the tenure multiplier had nothing left to act on -
    # a 12-year coach and a rookie coach both read 97%.
    return float(1.0 - np.exp(-1.25 * max(0.0, p)))

def fire_chance_offseason(hist, roster_pct=0.5, qb_dev=None):
    """Probability this team makes a change after the season."""
    p = pressure(hist, roster_pct, qb_dev)
    # Hysteresis: one bad year rarely ends a tenure on its own. The exponent is
    # what holds the league near its real ~20% turnover without any quota.
    return float(np.clip(p ** 1.95 * 1.25, 0.0, 0.95))

def fire_chance_inseason(hist, week, roster_pct=0.5, qb_dev=None):
    """
    In-season firing is a separate, rarer path that clusters around week 10.
    It needs the season to be visibly gone, not merely disappointing.
    """
    if week < 5: return 0.0
    p = pressure(hist, roster_pct, qb_dev)
    if p < 0.56: return 0.0
    window = np.exp(-0.5 * ((week - 10.5) / 3.2) ** 2)      # peaks at wk 10-11
    return float(np.clip((p - 0.56) * 0.40 * window, 0.0, 0.12))

def job_security(hist, roster_pct=0.5, qb_dev=None):
    """The GM-engine input. 1 = safe, 0 = gone tomorrow."""
    return float(np.clip(1.0 - pressure(hist, roster_pct, qb_dev), 0.02, 0.98))
