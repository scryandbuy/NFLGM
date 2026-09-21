"""
Coverage assignment.

Who covers whom. Before this, the engine picked a target at random from the
receivers and a defender at random from the secondary, so a tight end could be
covered by a corner, a number one receiver by a safety, and a linebacker never
covered anyone at all. Every pairing was a coin flip.

WHAT THE RESEARCH SAYS:

  SIDES ARE THE DEFAULT. Corners hold a side and cover whoever lines up there.
  Travelling with a receiver is the exception and is treated as a notable
  tactical choice when a team starts doing it.

  SHADOWING IS RARE. ESPN, having charted every snap: "There are only a handful
  of cornerbacks who shadow No.1 receivers most weeks, and you can count on one
  hand those who shadow both the perimeter and the slot." Josh Norman, a
  premier shadow corner, travelled in roughly half his games across two
  seasons. The most-shadowed receiver in a season drew nine shadow games; the
  busiest shadow corner had eleven. In a 17-game season that is a minority.

  YOU ONLY TRAVEL IF THERE IS A GAP. A Washington coordinator explained why he
  would not travel Norman against Antonio Brown: they had another good corner
  in Bashaud Breeland, so they could keep Norman left and Breeland right and
  let each cover Brown when he came to them.

  ZONE NEVER TRAVELS. Same coordinator: "The Redskins will mix in plenty of
  zone coverages in addition to man, so there's no reason for them to move
  corners around all the time." Nobody is assigned to a man in zone.

  THE MISMATCH IS THE POINT. Real separation: TE 3.35 yards, WR 2.93. Tight
  ends are not better route runners; they are covered by linebackers and
  safeties instead of corners. That gap needs no special rule - it falls out
  of the matchup once the assignment is right.
"""
import numpy as np

# Who is responsible for which receiver, by alignment.
SLOT_DEFENDER = 'nickel'          # the fifth DB, a distinct player
TE_DEFENDERS = ['SS', 'FS', 'SAM', 'MIKE', 'WILL']
RB_DEFENDERS = ['MIKE', 'WILL', 'SAM']


def receiver_alignment(receivers, personnel='11', rng=None):
    """
    Where each eligible lines up. X and Z are outside, slot inside, plus the
    tight end and back. Alignment is what the defence actually reacts to.
    """
    rng = rng or np.random.default_rng()
    out = []
    for i, r in enumerate(receivers):
        pos = r.get('pos', 'WR')
        if pos in ('TE',):
            out.append(dict(player=r, spot='te', side='R' if i % 2 else 'L'))
        elif pos in ('HB', 'RB', 'FB'):
            out.append(dict(player=r, spot='back', side='C'))
        elif i == 0:
            out.append(dict(player=r, spot='X', side='L'))
        elif i == 1:
            out.append(dict(player=r, spot='Z', side='R'))
        else:
            out.append(dict(player=r, spot='slot', side='R' if i % 2 else 'L'))
    return out


def should_travel(cb1, cb2, wr1, rate_fn, is_man, rng, coach_willingness=0.5,
                  AVG=0.70):
    """
    Does CB1 follow the offence's best receiver?

    Zone never travels - nobody is assigned to a man. And you only travel when
    there is a real gap between your corners AND the receiver is worth it. A
    coordinator with two good corners simply plays sides and lets each cover
    the man when he comes to them.

    Calibrated so a premier shadow corner against a premier receiver lands near
    the ~50% of games the research describes, and the league-wide rate stays
    far below that.
    """
    if not is_man:
        return False
    c1 = rate_fn(cb1, {'man_cover_rating': .55, 'speed_rating': .25,
                       'press_rating': .20})
    c2 = rate_fn(cb2, {'man_cover_rating': .55, 'speed_rating': .25,
                       'press_rating': .20}) if cb2 else AVG
    w1 = rate_fn(wr1, {'route_run_short_rating': .20, 'route_run_med_rating': .25,
                       'route_run_deep_rating': .25, 'speed_rating': .30})

    gap = c1 - c2                       # how much better is my best corner
    threat = w1 - AVG                   # how dangerous is their best receiver
    # A real gap is required. Two good corners means you play sides and let
    # each cover him when he comes - which is exactly why Washington would not
    # travel Norman against Brown.
    if gap <= 0.06 or threat <= 0.04:
        return False
    # Constants solved against the research: the BEST case - a premier shadow
    # corner against a premier receiver - lands near the ~50% of games the
    # data describes, and that is the ceiling, not the norm. The first build
    # peaked at 85% and travelled 54% of the time on a negligible corner gap.
    p = (1.35 * (gap - 0.06) + 0.75 * (threat - 0.04)) * \
        (0.45 + 1.05 * coach_willingness)
    return rng.random() < float(np.clip(p, 0.0, 0.62))


def corner_sides(cbs, rng, left_pref=None):
    """
    Which corner holds which side. This is what "playing sides" MEANS, and
    without it the first build simply handed the best corner to the X receiver
    on every snap - so CB1 covered WR1 in 100% of games and travel never
    mattered at all.
    """
    if not cbs: return {}
    if left_pref is None:
        left_pref = rng.random() < 0.5
    out = {'L': cbs[0] if left_pref else (cbs[1] if len(cbs) > 1 else cbs[0]),
           'R': (cbs[1] if len(cbs) > 1 else cbs[0]) if left_pref else cbs[0]}
    return out


def assign_coverage(aligned, defense, def_call, rng, rate_fn,
                    coach_willingness=0.5, travel=None, sides=None):
    """
    Pair every eligible receiver with the defender responsible for him.

    Returns a list of dicts: receiver, defender, and the leverage of that
    matchup. In zone the 'defender' is the nearest man to the window rather
    than an assignment, which the zone resolver then uses.
    """
    cbs = [d for d in defense.get('db', []) if d.get('pos', 'CB') == 'CB'] \
          or defense.get('db', [])[:3]
    safs = [d for d in defense.get('db', []) if d.get('pos') in ('FS', 'SS')] \
           or defense.get('db', [])[3:5] or defense.get('db', [])[-2:]
    lbs = defense.get('lb', [])
    is_man = def_call.get('man', False)

    # does the top corner travel with their best man
    if travel is None and cbs and aligned:
        wr1 = next((a['player'] for a in aligned if a['spot'] == 'X'), None)
        travel = should_travel(cbs[0], cbs[1] if len(cbs) > 1 else None, wr1,
                               rate_fn, is_man, rng, coach_willingness) \
                 if wr1 is not None else False

    # corners hold a side unless one of them is travelling
    sides = sides or corner_sides(cbs, rng)
    pairs, used = [], set()

    def take(pool, prefer=None):
        for d in pool:
            pid = id(d)
            if pid not in used:
                used.add(pid); return d
        return pool[-1] if pool else None

    for a in aligned:
        spot = a['spot']
        if spot in ('X', 'Z'):
            if spot == 'X' and travel and cbs:
                d = cbs[0]                      # my best man follows him
                used.add(id(d))
                trav = True
            else:
                # whoever holds that side of the field
                d = sides.get(a['side'], cbs[0] if cbs else None)
                if d is not None and id(d) in used:
                    d = take([c for c in cbs if id(c) not in used] or cbs)
                elif d is not None:
                    used.add(id(d))
                trav = False
            pairs.append(dict(receiver=a['player'], defender=d, spot=spot,
                              travelled=trav, kind='cb'))
        elif spot == 'slot':
            # the slot draws the NICKEL - a different player with different
            # attributes, not whichever corner happened to be picked
            pool = [c for c in cbs if id(c) not in used] or safs or cbs
            d = take(pool)
            pairs.append(dict(receiver=a['player'], defender=d, spot=spot,
                              travelled=False, kind='nickel'))
        elif spot == 'te':
            # safety or linebacker by personnel. THIS is where the real
            # TE-vs-LB mismatch lives; no special rule needed.
            pool = (safs if rng.random() < 0.58 else lbs) or safs or lbs or cbs
            d = take(pool)
            kind = 'safety' if d in safs else 'lb'
            pairs.append(dict(receiver=a['player'], defender=d, spot=spot,
                              travelled=False, kind=kind))
        else:                                   # back out of the backfield
            pool = [l for l in lbs if id(l) not in used] or lbs or safs
            d = take(pool)
            pairs.append(dict(receiver=a['player'], defender=d, spot=spot,
                              travelled=False, kind='lb'))
    return pairs, bool(travel)


def bracket_target(pairs, bracket_pid, safs):
    """
    A bracketed receiver gets a second man over the top. The adjustment engine
    decides WHO gets bracketed; this applies it.
    """
    if not bracket_pid: return pairs
    for p in pairs:
        if p['receiver'].get('pid') == bracket_pid:
            p['bracket'] = safs[0] if safs else None
    return pairs
