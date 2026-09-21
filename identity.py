"""
OFFENSIVE IDENTITY.

call_offense never saw the roster. Personnel was a flat random draw, so a club
with two excellent tight ends called 12 personnel exactly as often as one with
none, and a club with a dominant run-blocking line threw as often as a club
that could not block anybody. Every offence in the league played the same way.

Coaches say the opposite of that, repeatedly and bluntly:

    "Choose the run game that best fits your players. Develop a run game that
     fits your kids."
    "Think players, not plays. When the game is on the line you need to get
     the ball to your dudes."
    "You need an identity play you can always run against anyone."

So identity is read from the men on the roster, once, and then the situation
moves it. A club is not its tendencies - it is its players.

WHAT GETS READ, and RUN AND PASS BLOCKING ARE HALF OF IT:

    run_block   the line's run-blocking, which is what actually decides
                whether feeding the back is a plan or a hope
    pass_block  the line's protection, which decides whether you can hold a
                deep concept long enough to throw it
    qb          his accuracy and awareness - a game manager gets a different
                offence from a passer who can carry one
    backs       whether there is a runner worth building around
    tight_ends  two good ones is a personnel grouping, not a preference
    receivers   whether the perimeter can win alone

The blocking ratings already existed and nothing read them outside the play
itself, so a line that could maul people had no effect on what was called.
"""
import numpy as np

OL_RUN = {'run_block_rating': .35, 'run_block_power_rating': .30,
          'run_block_finesse_rating': .20, 'strength_rating': .15}
OL_PASS = {'pass_block_rating': .35, 'pass_block_power_rating': .25,
           'pass_block_finesse_rating': .25, 'awareness_rating': .15}
QB_LEVEL = {'throw_acc_short_rating': .25, 'throw_acc_mid_rating': .25,
            'awareness_rating': .25, 'throw_acc_deep_rating': .15,
            'throw_power_rating': .10}
BACK_LEVEL = {'carry_rating': .25, 'bcv_rating': .25,
              'break_tackle_rating': .25, 'speed_rating': .25}
TE_LEVEL = {'catch_rating': .30, 'run_block_rating': .30,
            'route_run_short_rating': .25, 'speed_rating': .15}
WR_LEVEL = {'route_run_med_rating': .30, 'catch_rating': .25,
            'speed_rating': .25, 'release_rating': .20}


def read_identity(off, rate_fn):
    """
    What this offence actually is, on a 0-1 scale per group.

    Read once from the roster; the situation moves it afterwards. Only the men
    who would play are counted - depth beyond the rotation does not change
    what you are.
    """
    def grp(men, wants, n=3):
        men = [m for m in (men or []) if m]
        if not men:
            return 0.5
        return float(np.mean([rate_fn(m, wants) for m in men[:n]]))

    ol = off.get('ol') or []
    pattern = off.get('wr') or []
    tes = [m for m in pattern if m and m.get('pos') == 'TE']
    wrs = [m for m in pattern if m and m.get('pos') == 'WR']
    backs = [m for m in ([off.get('rb')] + list(off.get('backs') or []))
             if m]
    return dict(
        run_block=grp(ol, OL_RUN, 5),
        pass_block=grp(ol, OL_PASS, 5),
        qb=rate_fn(off['qb'], QB_LEVEL) if off.get('qb') else 0.6,
        backs=grp(backs, BACK_LEVEL, 2),
        tight_ends=grp(tes, TE_LEVEL, 2),
        receivers=grp(wrs, WR_LEVEL, 3))


# THE BASELINE IS THE LEAGUE, NOT A FIXED NUMBER. Centring on a flat 0.70
# made every club above average at everything, because every NFL roster is:
# tight ends ran 0.71 to 0.84 and the personnel weights barely moved. Identity
# is RELATIVE - you are a run team because your line is better than theirs,
# not because it clears some bar.
LEAGUE = dict(run_block=0.82, pass_block=0.80, qb=0.86, backs=0.90,
              tight_ends=0.76, receivers=0.85)


def rel(ident, key):
    return ident.get(key, LEAGUE[key]) - LEAGUE[key]


def run_lean(ident):
    """
    How much this club wants to run, as a shift on the pass rate.

    A line that mauls people and a back worth feeding pull it down; a
    quarterback who can carry an offence and receivers who win pull it up. A
    club that cannot protect ALSO runs more, because it has no choice - which
    is the same reasoning from the other direction.
    """
    run_side = 0.55 * rel(ident, 'run_block') + 0.45 * rel(ident, 'backs')
    pass_side = (0.45 * rel(ident, 'qb') + 0.30 * rel(ident, 'receivers')
                 + 0.25 * rel(ident, 'pass_block'))
    return float(np.clip((pass_side - run_side) * 1.6, -0.18, 0.18))


def personnel_weights(ident, base):
    """
    Which packages this club favours.

    Two good tight ends is a personnel grouping rather than a preference, and
    a club without them cannot pretend otherwise. A dominant run-blocking line
    makes the heavy sets worth using; a poor one makes them a waste of a snap.
    """
    w = dict(base)
    te = rel(ident, 'tight_ends')
    rb = rel(ident, 'run_block')
    wr = rel(ident, 'receivers')
    for k in list(w):
        n_te = int(k[1]) if len(k) >= 2 and k[1].isdigit() else 1
        n_rb = int(k[0]) if k and k[0].isdigit() else 1
        if n_te >= 2:
            w[k] *= float(np.clip(1.0 + 7.0 * te + 3.5 * rb, 0.25, 2.8))
        if n_rb >= 2:
            w[k] *= float(np.clip(1.0 + 5.5 * rb, 0.30, 2.5))
        if n_te <= 1 and n_rb <= 1:
            w[k] *= float(np.clip(1.0 + 5.0 * wr, 0.40, 2.1))
    return w


def qb_latitude(off, rate_fn):
    """
    How much the quarterback is allowed to change at the line.

    The play-calling system decides this in advance, and it is a property of
    the MAN rather than of the coach: an elite passer is trusted to check out
    of a bad call, a game manager runs what he was given. Deliberately NOT a
    guarantee of a better play - he can be bluffed into a worse one, which is
    what a disguised coverage is for.
    """
    if not off.get('qb'):
        return 0.0
    lvl = rate_fn(off['qb'], {'awareness_rating': .55, 'play_rec_rating': .30,
                              'throw_acc_short_rating': .15})
    return float(np.clip((lvl - 0.62) * 2.6, 0.0, 0.85))


if __name__ == '__main__':
    import rosters as R, plays as P
    L = R.load_league()
    print('%-5s %6s %6s %5s %6s %6s %6s  %7s %7s'
          % ('team', 'runblk', 'pasblk', 'qb', 'backs', 'te', 'wr',
             'pass+', 'audible'))
    rows = []
    for t in sorted(L):
        i = read_identity(L[t], P.rate)
        rows.append((run_lean(i), t, i, qb_latitude(L[t], P.rate)))
    rows.sort()
    for lean, t, i, lat in rows[:4] + rows[-4:]:
        print('%-5s %6.2f %6.2f %5.2f %6.2f %6.2f %6.2f  %+6.3f %7.2f'
              % (t, i['run_block'], i['pass_block'], i['qb'], i['backs'],
                 i['tight_ends'], i['receivers'], lean, lat))
    print('\nthe most run-leaning club and the most pass-leaning, by roster')
    base = {'11': .62, '12': .19, '21': .07, '13': .04, '10': .08}
    for lean, t, i, _l in (rows[0], rows[-1]):
        w = personnel_weights(i, base)
        tot = sum(w.values())
        print('  %-4s %s' % (t, ', '.join(
            f'{k} {100*v/tot:.0f}%' for k, v in sorted(w.items()))))
