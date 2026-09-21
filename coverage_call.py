"""
COVERAGE AS A CALL, NOT A FLAG.

The engine carried one boolean - man or zone, for the whole defence, derived
from whether the shell was cover 0 or cover 1. Every real concept was
unreachable with that, because the NUMBER IN A COVERAGE ONLY EVER MEANT HOW
MANY MEN ARE DEEP. What happens underneath is a separate decision, and it can
differ by SIDE OF THE FIELD.

    2-man under (cover 5)   two deep halves, five underneath in MAN
    cover 3 mable           cover 3 to one side, man on the other
    cover 6                 quarter-quarter-half: cover 4 one side, cover 2 the
                            other, which is literally what 4 + 2 means
    palms                   corners read the number two receiver and latch on
                            man inside a zone structure
    fire zone               five rush, three under and three deep behind it,
                            with a lineman dropping

None of those can be said with a boolean.

HOW A CALL GETS CHOSEN, which is the part that matters more than the taxonomy.
Coaches describe it the same way over and over: every call in the book has a
JOB, and one put it bluntly - any call that does not have a specific job gets
thrown out. So the decision here is job first, call second. The job comes from
the situation; which call does that job comes from personnel.

    "If you have three elite corners and the offense has mediocre receivers,
     Cover 0 exploits that."

That is the whole principle. Good corners buy the right to play without help,
which buys extra rushers. A defence with a weak secondary cannot make the same
call no matter how much its coordinator would like to, and this reads the
actual players rather than a tendency slider.

Nothing here forces a call. A job makes some answers likely and others
unavailable, and the coordinator picks inside that.
"""
import numpy as np

# ============================================================ THE CALLS
# deep: how many men are responsible for deep thirds/halves/quarters
# under: 'man', 'zone', or a (left, right) pair for a split-field call
# needs: what the personnel has to support before it is even an option
COVERAGES = {
    'cover_0':   dict(deep=0, under='man',  rush_bonus=2, risk=1.00,
                      needs=dict(corners=0.78)),
    'cover_1':   dict(deep=1, under='man',  rush_bonus=1, risk=0.72,
                      needs=dict(corners=0.70)),
    'cover_1_robber': dict(deep=1, under='man', rush_bonus=0, risk=0.58,
                           needs=dict(corners=0.70)),
    'cover_2':   dict(deep=2, under='zone', rush_bonus=0, risk=0.40,
                      needs=dict()),
    'two_man':   dict(deep=2, under='man',  rush_bonus=0, risk=0.62,
                      needs=dict(corners=0.66)),      # cover 5
    'tampa_2':   dict(deep=2, under='zone', rush_bonus=0, risk=0.36,
                      needs=dict(linebackers=0.72)),  # the mike runs the pole
    'cover_3':   dict(deep=3, under='zone', rush_bonus=0, risk=0.34,
                      needs=dict()),
    'cover_3_mable': dict(deep=3, under=('zone', 'man'), rush_bonus=0,
                          risk=0.48, needs=dict(corners=0.72)),
    'cover_4':   dict(deep=4, under='zone', rush_bonus=0, risk=0.30,
                      needs=dict(safeties=0.68)),
    'cover_6':   dict(deep=3, under=('zone', 'zone'), rush_bonus=0, risk=0.33,
                      needs=dict(), split=('cover_4', 'cover_2')),
    'fire_zone': dict(deep=3, under='zone', rush_bonus=1, risk=0.55,
                      needs=dict()),                  # three under, three deep
}

# ============================================================ THE JOBS
# What the call is for. A coordinator names the job first and the call second.
JOBS = {
    # get off the field: force a decision now and live with the consequences
    'pressure':   ['cover_0', 'cover_1', 'fire_zone', 'two_man'],
    # take away the sticks without giving up the chunk behind it
    'sticks':     ['fire_zone', 'cover_3_mable', 'two_man', 'cover_1_robber'],
    # do not let them behind you - the lead, or long yardage
    'no_chunk':   ['cover_4', 'cover_6', 'tampa_2', 'cover_2'],
    # early down, balanced, make them earn it
    'base':       ['cover_3', 'cover_2', 'cover_4', 'cover_1', 'cover_6'],
    # heavy personnel, keep men near the line
    'run_first':  ['cover_3', 'cover_1', 'cover_4'],
}


def unit_quality(defense, rate_fn):
    """
    What this secondary can actually do, on a 0-1 scale by group.

    The point of reading it: a call is only an option if the players can run
    it. Cover 0 with poor corners is not aggression, it is a touchdown.
    """
    def grp(men, weights):
        if not men:
            return 0.5
        return float(np.mean([rate_fn(m, weights) for m in men[:3]]))

    dbs = defense.get('db', [])
    cbs = [d for d in dbs if d.get('pos') == 'CB'] or dbs[:3]
    sfs = [d for d in dbs if d.get('pos') in ('FS', 'SS')] or dbs[3:5]
    return dict(
        corners=grp(cbs, {'man_cover_rating': .55, 'speed_rating': .25,
                          'press_rating': .20}),
        safeties=grp(sfs, {'zone_cover_rating': .45, 'play_rec_rating': .30,
                           'speed_rating': .25}),
        linebackers=grp(defense.get('lb', []),
                        {'zone_cover_rating': .50, 'play_rec_rating': .30,
                         'speed_rating': .20}))


def pick_job(down, ydstogo, score_diff, secs_left, off_personnel, rng,
             aggression=0.5):
    """
    What this call needs to DO. The situation decides it, not the playbook.
    """
    heavy = off_personnel in ('12', '13', '21', '22')
    late = secs_left is not None and secs_left < 300

    if down == 4 or (down == 3 and ydstogo <= 2):
        return 'pressure' if rng.random() < 0.35 + 0.30 * aggression else 'sticks'
    if down == 3:
        # third and long is where a coordinator is happiest to be aggressive,
        # because a sack or an incompletion both end it
        if ydstogo >= 7:
            return 'sticks' if rng.random() < 0.62 else 'pressure'
        return 'sticks'
    if late and score_diff > 0:
        return 'no_chunk'                 # protecting a lead: nothing behind us
    if ydstogo >= 15:
        return 'no_chunk'
    if heavy and down <= 2:
        return 'run_first'
    return 'base'


def available(job, quality, rng):
    """
    Which calls this defence can actually make for this job.

    A requirement is not a hard gate - a coordinator with mediocre corners will
    still play man occasionally, he just does it less. Falling short makes a
    call unlikely rather than impossible.
    """
    out = []
    for name in JOBS.get(job, JOBS['base']):
        c = COVERAGES[name]
        w = 1.0
        for grp, need in c['needs'].items():
            have = quality.get(grp, 0.6)
            if have < need:
                w *= max(0.08, 1.0 - 3.2 * (need - have))
        out.append((name, w))
    return out


def call_coverage(down, ydstogo, score_diff, secs_left, off_personnel,
                  defense, rate_fn, rng, aggression=0.5, recent=None):
    """
    The whole decision: job from the situation, call from the personnel.

    `recent` is what has been working - a coordinator leans on a call that is
    getting stops and drops one that is not. It is a nudge, never a rule.
    """
    quality = unit_quality(defense, rate_fn)
    job = pick_job(down, ydstogo, score_diff, secs_left, off_personnel, rng,
                   aggression)
    opts = available(job, quality, rng)
    names = [n for n, _w in opts]
    w = np.array([x for _n, x in opts], float)

    # an aggressive coordinator tilts toward the riskier answer for the job
    w *= np.array([1.0 + (COVERAGES[n]['risk'] - 0.5) * (aggression - 0.5) * 1.8
                   for n in names])
    if recent:
        w *= np.array([1.0 + 0.5 * float(recent.get(n, 0.0)) for n in names])
    w = np.clip(w, 1e-6, None)

    name = names[int(rng.choice(len(names), p=w / w.sum()))]
    c = COVERAGES[name]
    return dict(coverage=name, job=job, deep=c['deep'], under=c['under'],
                rush_bonus=c['rush_bonus'], quality=quality)


def under_for_side(call, side):
    """
    Man or zone for THIS side of the field. A split-field call is the whole
    reason this is a function rather than a flag.
    """
    u = call.get('under', 'zone')
    if isinstance(u, tuple):
        return u[0] if side in ('L', 'left') else u[1]
    return u


if __name__ == '__main__':
    import rosters as R, plays as P
    rng = np.random.default_rng(4)
    L = R.load_league()
    import collections
    print('SAME SITUATION, DIFFERENT SECONDARIES\n')
    for team in ('BAL', 'NE', 'CAR'):
        d = L[team]
        q = unit_quality(d, P.rate)
        c = collections.Counter()
        for _ in range(400):
            c[call_coverage(3, 8, 0, 900, '11', d, P.rate, rng,
                            aggression=0.6)['coverage']] += 1
        print('%s  corners %.2f safeties %.2f backers %.2f'
              % (team, q['corners'], q['safeties'], q['linebackers']))
        print('   3rd and 8: %s' % ', '.join(
            f'{k} {100*v/400:.0f}%' for k, v in c.most_common(5)))
    print('\nSAME DEFENCE, DIFFERENT SITUATIONS (BAL)\n')
    d = L['BAL']
    for lab, args in (('1st and 10', (1, 10, 0, 1800, '11')),
                      ('3rd and 2', (3, 2, 0, 1800, '11')),
                      ('3rd and 12', (3, 12, 0, 1800, '11')),
                      ('2nd and 8, up 10, 3 min', (2, 8, 10, 180, '11')),
                      ('1st and 10 vs 12 personnel', (1, 10, 0, 1800, '12'))):
        c = collections.Counter(); jobs = collections.Counter()
        for _ in range(400):
            r = call_coverage(*args, d, P.rate, rng, aggression=0.5)
            c[r['coverage']] += 1; jobs[r['job']] += 1
        print('%-26s job=%-9s %s' % (lab, jobs.most_common(1)[0][0],
              ', '.join(f'{k} {100*v/400:.0f}%' for k, v in c.most_common(4))))
