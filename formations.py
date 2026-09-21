"""
FORMATIONS.

A PACKAGE IS WHO IS ON THE FIELD. A FORMATION IS WHERE THEY STAND. Those are
two decisions and the engine collapsed them into one, which is why the X
receiver aligned left on six hundred of six hundred snaps: spot and side came
straight off list order, so the first receiver was always X and always left.
The same two corners therefore split him forever, and whichever of them drew
him collected nearly every pass break-up in the league.

Real football gets its variety here. The same 11 personnel produces a dozen
looks - trips to one side, empty backfield, a tight end split wide, a back in
the slot. And the men are not locked to their position names: a tight end can
align at X, a back can split out, a receiver can go in the backfield.

WHAT A FORMATION IS, here: a list of spots, each with a side and what kind of
player usually fills it. Filling is by FIT rather than by name, so a
quick-but-small receiver lands in the slot and a big one outside, and a tight
end who can run takes a wide spot when the formation asks for one.

Every formation lists which packages can run it, because you cannot line up in
an empty set with two backs on the field.
"""
import numpy as np

# spots: (name, side, wants) - `wants` is the attribute profile that spot
# rewards, and it is what decides WHO goes there rather than a position label.
OUTSIDE = {'speed_rating': .35, 'route_run_deep_rating': .30,
           'release_rating': .20, 'spec_catch_rating': .15}
SLOT = {'route_run_short_rating': .35, 'agility_rating': .30,
        'catch_rating': .20, 'awareness_rating': .15}
INLINE = {'run_block_rating': .40, 'catch_rating': .30,
          'route_run_short_rating': .30}
BACKFIELD = {'carry_rating': .35, 'bcv_rating': .25, 'break_tackle_rating': .20,
             'catch_rating': .20}

FORMATIONS = {
    # --- one back, three receivers ---
    'spread_r':   dict(packages=('11', '10'), weight=1.00, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('slot', 'R', SLOT),
        ('te', 'L', INLINE), ('back', 'C', BACKFIELD)]),
    'spread_l':   dict(packages=('11', '10'), weight=1.00, spots=[
        ('X', 'R', OUTSIDE), ('Z', 'L', OUTSIDE), ('slot', 'L', SLOT),
        ('te', 'R', INLINE), ('back', 'C', BACKFIELD)]),
    'trips_r':    dict(packages=('11', '10'), weight=0.62, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('slot', 'R', SLOT),
        ('slot', 'R', SLOT), ('back', 'C', BACKFIELD)]),
    'trips_l':    dict(packages=('11', '10'), weight=0.62, spots=[
        ('X', 'R', OUTSIDE), ('Z', 'L', OUTSIDE), ('slot', 'L', SLOT),
        ('slot', 'L', SLOT), ('back', 'C', BACKFIELD)]),
    # a back split out is still 11 personnel - the DEFENCE has to notice
    'empty':      dict(packages=('11', '10'), weight=0.28, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('slot', 'L', SLOT),
        ('slot', 'R', SLOT), ('slot', 'R', SLOT)]),

    # --- two tight ends ---
    'ace_twins':  dict(packages=('12',), weight=1.00, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('te', 'R', INLINE),
        ('te', 'R', INLINE), ('back', 'C', BACKFIELD)]),
    'ace_split':  dict(packages=('12',), weight=0.85, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('te', 'L', INLINE),
        ('te', 'R', INLINE), ('back', 'C', BACKFIELD)]),
    # the second tight end flexed out wide - the mismatch look
    'te_flex':    dict(packages=('12',), weight=0.55, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('slot', 'L', SLOT),
        ('te', 'R', INLINE), ('back', 'C', BACKFIELD)]),

    # --- two backs ---
    'i_form':     dict(packages=('21', '22'), weight=1.00, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('te', 'R', INLINE),
        ('back', 'C', BACKFIELD), ('back', 'C', BACKFIELD)]),
    'offset_i':   dict(packages=('21', '22'), weight=0.70, spots=[
        ('X', 'R', OUTSIDE), ('Z', 'L', OUTSIDE), ('te', 'L', INLINE),
        ('back', 'C', BACKFIELD), ('back', 'C', BACKFIELD)]),
    # a back motioned out wide: 21 personnel that looks like 11
    'pony_flex':  dict(packages=('21',), weight=0.40, spots=[
        ('X', 'L', OUTSIDE), ('Z', 'R', OUTSIDE), ('slot', 'R', SLOT),
        ('te', 'L', INLINE), ('back', 'C', BACKFIELD)]),

    # --- heavy ---
    'jumbo':      dict(packages=('13', '22'), weight=1.00, spots=[
        ('X', 'L', OUTSIDE), ('te', 'R', INLINE), ('te', 'R', INLINE),
        ('te', 'L', INLINE), ('back', 'C', BACKFIELD)]),
}


def _fit(player, wants, rate_fn):
    return rate_fn(player, wants)


def choose_formation(personnel, rng, down=1, ydstogo=10, score_diff=0,
                     secs_left=None, spread_bias=0.0):
    """
    Which look, out of the ones this package can even produce.

    Down and distance move it: third and long pulls toward spread and empty,
    short yardage toward the heavy sets. `spread_bias` is the club's own
    identity, which comes from its roster.
    """
    opts = [(n, f['weight']) for n, f in FORMATIONS.items()
            if personnel in f['packages']]
    if not opts:
        opts = [(n, f['weight']) for n, f in FORMATIONS.items()
                if '11' in f['packages']]
    names = [n for n, _w in opts]
    w = np.array([x for _n, x in opts], float)

    for i, n in enumerate(names):
        spots = FORMATIONS[n]['spots']
        wide = sum(1 for s in spots if s[0] in ('X', 'Z', 'slot'))
        if down >= 3 and ydstogo >= 7:
            w[i] *= 1.0 + 0.22 * (wide - 3)      # spread it out to throw
        if ydstogo <= 2:
            w[i] *= 1.0 - 0.18 * (wide - 3)      # tighten it up to run
        w[i] *= 1.0 + spread_bias * 0.30 * (wide - 3)
    w = np.clip(w, 1e-6, None)
    return names[int(rng.choice(len(names), p=w / w.sum()))]


def align(receivers, personnel, rng, rate_fn, formation=None, **kw):
    """
    Put the eligibles in a formation and return who is standing where.

    Filling is BY FIT, not by position name or list order. A tight end who can
    run takes a wide spot when the formation asks for one; a small quick
    receiver lands in the slot and a big one outside. That is what makes the
    same package produce different matchups.
    """
    if formation is None:
        formation = choose_formation(personnel, rng, **kw)
    spots = FORMATIONS[formation]['spots']
    men = list(receivers)
    out = []
    for name, side, wants in spots:
        if not men:
            break
        sc = [_fit(m, wants, rate_fn) for m in men]
        # the best fit usually, not always - alignment is a call, and a
        # coordinator moves people around on purpose
        s = np.array(sc)
        p = np.exp((s - s.max()) / 0.05)
        i = int(rng.choice(len(men), p=p / p.sum()))
        out.append(dict(player=men.pop(i), spot=name, side=side,
                        formation=formation))
    # anybody left over is in the backfield or on the line
    for m in men:
        out.append(dict(player=m, spot='back', side='C', formation=formation))
    return out


if __name__ == '__main__':
    import collections
    import rosters as R, plays as P
    rng = np.random.default_rng(3)
    L = R.load_league()
    off = L['KC']
    print('X RECEIVER SIDE, 800 snaps of 11 personnel')
    side = collections.Counter(); form = collections.Counter()
    who = collections.Counter()
    for _ in range(800):
        al = align(off['wr'], '11', rng, P.rate)
        for a in al:
            if a['spot'] == 'X':
                side[a['side']] += 1; who[a['player'].get('pos')] += 1
        form[al[0]['formation']] += 1
    print('   side: %s   [was L 800 / R 0]' % dict(side))
    print('   who plays X: %s' % dict(who))
    print('   formations: %s' % {k: round(100 * v / 800) for k, v in form.most_common()})
    print('\nDOWN AND DISTANCE MOVES THE LOOK')
    for lab, d, y in (('1st and 10', 1, 10), ('3rd and 12', 3, 12),
                      ('2nd and 1', 2, 1)):
        c = collections.Counter(choose_formation('11', rng, down=d, ydstogo=y)
                                for _ in range(400))
        print('   %-12s %s' % (lab, ', '.join(
            f'{k} {100*v/400:.0f}%' for k, v in c.most_common(3))))
    print('\n12 PERSONNEL PRODUCES DIFFERENT LOOKS')
    c = collections.Counter(choose_formation('12', rng) for _ in range(400))
    print('   %s' % ', '.join(f'{k} {100*v/400:.0f}%' for k, v in c.most_common()))
