"""
Real rosters from the league seed.

Every test to this point used synthetic teams: clones with a linear strength
spread, three receivers, one quarterback who never left the field, and no
positional depth. That is a harness, not a league - it removes mismatch,
removes the tail of every distribution, and makes any calibration suspect.

This builds the 32 real 2026 rosters from league_seed_2026.csv: 2,114 active
players with all 54 Madden attributes, ordered by POSITION-SPECIFIC rating.
"""
import pandas as pd, numpy as np
import os
_D = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(_D, n)
import targets as TG

SEED = _p('league_seed_2026.csv')
RATING_COLS = None


def load_league(path=SEED, scheme=None):
    """Return {team: roster dict} ready for the game loop."""
    global RATING_COLS
    S = pd.read_csv(path, low_memory=False)
    S = S[S.roster == 'active'].copy()
    RATING_COLS = [c for c in S.columns if c.endswith('_rating')
                   and c != 'src_rating']
    league = {}
    for team, grp in S.groupby('team'):
        league[team] = build_roster(grp, scheme)
    return league


def _player(row):
    """One player as the engine wants him: pid, position, and every rating."""
    p = {'pid': str(row['pid']), 'pos': row['madden_position']}
    for c in RATING_COLS:
        v = row.get(c)
        if pd.notna(v):
            p[c] = float(v)
    return p


def build_roster_rows(rows, scheme=None, pins=None):
    """
    Same thing from a LIST OF PLAYER DICTS rather than a dataframe group.

    The live league has no dataframe - it owns Player objects - so a season
    rebuilding its units every week needs this shape. Both paths feed the same
    assembly below, so the depth chart a live team fields is built by exactly
    the same rules as the one the calibration register runs on.
    """
    by_pos = {}
    for r in rows:
        by_pos.setdefault(r.get('pos') or r.get('madden_position'), []).append(r)
    for pos in list(by_pos):
        by_pos[pos] = TG.order_depth(by_pos[pos], pos, scheme)
        if pins and pins.get(pos):
            # the user's order at this spot: the men he named first, in his order, then the rest by the engine's grade
            order = {pid: i for i, pid in enumerate(pins[pos])}
            by_pos[pos] = sorted(by_pos[pos], key=lambda x: order.get(x.get('pid'), 10**6))
    return _assemble(by_pos)


def build_roster(grp, scheme=None):
    """
    A real team. Position groups ordered by position-specific rating, so the
    depth chart reflects who is actually best AT THAT SPOT rather than a blended
    overall.
    """
    by_pos = {}
    for pos, g in grp.groupby('madden_position'):
        by_pos[pos] = TG.order_depth([_player(r) for _, r in g.iterrows()], pos,
                                     scheme)
    return _assemble(by_pos)


def _assemble(by_pos):
    """Position groups -> the eleven-man shape the engine takes."""
    def take(pos, n=None):
        v = by_pos.get(pos, [])
        return v[:n] if n else v

    qbs = take('QB')
    hbs = take('HB') or take('FB')      # the fullback blocks; he carries only when there is no back left (FBs took 1,680 carries in a season once they sat in the rotation)
    wrs = take('WR')
    tes = take('TE')
    # the line in real order: LT LG C RG RT, then everyone else as depth
    ol = (take('LT', 1) + take('LG', 1) + take('C', 1) + take('RG', 1) +
          take('RT', 1))
    ol += [p for pos in ('LT', 'LG', 'C', 'RG', 'RT')
           for p in take(pos)[1:]]
    dl = take('LEDG', 1) + take('DT', 2) + take('REDG', 1)
    dl += [p for pos in ('LEDG', 'DT', 'REDG') for p in take(pos)[1:]]
    lb = take('MIKE') + take('WILL') + take('SAM')
    db = take('CB') + take('FS') + take('SS')

    if not qbs or not ol or not db:
        return None
    # A team can run out of healthy backs in December. Real clubs dress an
    # emergency ball carrier rather than forfeiting, and leaving this None
    # made field_units snap a null player the moment a roster ran thin - which
    # never showed up until rosters went live.
    if not hbs:
        hbs = (take('WR')[-1:] or take('TE')[-1:] or qbs[-1:])
    return dict(
        qb=qbs[0], qbs=qbs[1:],
        rb=(hbs[0] if hbs else None), backs=hbs,
        # the pattern: three receivers, the tight end and the back
        wr=(wrs[:3] + tes[:1] + hbs[:1]),
        extra_blockers=(tes[1:2] + hbs[1:2]),
        ol=ol, dl=dl, lb=lb, db=db,
        k=(take('K', 1) or [None])[0],
        p=(take('P', 1) or [None])[0],
        kr=(wrs[-1] if len(wrs) > 3 else (wrs[0] if wrs else None)),
        depth=by_pos,
    )


def team_strength(roster):
    """A rough overall, for reporting only - never used by the engine."""
    if not roster: return 0.0
    vals = []
    for key, pos in (('qb', 'QB'), ('ol', 'LT'), ('wr', 'WR'),
                     ('dl', 'DT'), ('lb', 'MIKE'), ('db', 'CB')):
        v = roster.get(key)
        if isinstance(v, list) and v:
            vals += [TG.position_score(p, pos) for p in v[:5]]
        elif isinstance(v, dict):
            vals.append(TG.position_score(v, pos))
    return float(np.mean(vals)) if vals else 0.0
