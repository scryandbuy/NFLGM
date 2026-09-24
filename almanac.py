"""
THE ALMANAC.

What makes year twenty feel like year twenty: the records, the leaders,
the Hall, and who coached where. Kept on the league at the end of each
season from what is already stored (season lines, career lines, awards,
transactions), plus one vote a year.

  league.almanac = {
    'seasons':   {year: {'champion', 'runner_up', 'awards' (by name), 'leaders' (stat -> (pid, value))}},
    'records':   {stat: {'season': (pid, year, value), 'career': (pid, value)}},
    'hall':      [{pid, name, pos, inducted, seasons, awards, why}],
    'ballots':   {year: [(pid, score, inducted)]},
    'coaching':  {abbr: [{name, from, to, record, playoffs, titles}]},
  }

THE HALL. A retired man is eligible the fifth offseason after he stops.
The vote scores a career: seasons as a starter, career value by position
(yards, touchdowns, sacks, interceptions, blocks won on the common scale),
All-Pro teams, the big awards and titles. About two to four a year go in,
which is the real pace, and the score that gets a man in is set by the
class rather than a fixed bar, so a thin year lets fewer in.
"""
import numpy as np, collections

RECORD_STATS = ('pass_yds', 'pass_td', 'rush_yds', 'rush_td', 'rec', 'rec_yds', 'rec_td', 'sacks', 'int_def', 'tackles', 'fg_made', 'pass_def')
LEADER_STATS = RECORD_STATS + ('punt_yds', 'kr_yds')
HALL_WAIT = 5
HALL_PER_YEAR = (2, 4)


def _al(league):
    if not hasattr(league, 'almanac') or league.almanac is None:
        league.almanac = dict(seasons={}, records={}, hall=[], ballots={}, coaching={}, hall_scores={})
    return league.almanac


# ------------------------------------------------------------ the season, filed
def close_season(league, year, post=None, votes=None):
    A = _al(league)
    S = league.stats.get(year, {})
    leaders = {}
    for st in LEADER_STATS:
        best = max(((pid, l.get(st, 0)) for pid, l in S.items()), key=lambda x: x[1], default=None)
        if best and best[1] > 0: leaders[st] = best
    aw = {}
    for k, v in (votes or league.awards.get(year, {}) or {}).items():
        if isinstance(v, list): continue
        p = league.player(v) if isinstance(v, str) else (v if hasattr(v, 'pid') else None)
        pid = p.pid if p is not None else (v if isinstance(v, str) else str(v))
        aw[k] = dict(pid=pid, name=p.name if p else str(v), pos=p.pos if p else None, team=p.team if p else None)
    sb = next((g for g in (getattr(post, 'games', None) or []) if g[0] == 'SB'), None)
    score = (f"{max(sb[4], sb[5])}–{min(sb[4], sb[5])}" if sb else None)
    A['seasons'][year] = dict(champion=getattr(post, 'champion', None), runner_up=_runner_up(post),
                              awards=aw, leaders=leaders, score=score)
    # records
    for st in RECORD_STATS:
        rec = A['records'].setdefault(st, {})
        if st in leaders:
            pid, v = leaders[st]
            if v > rec.get('season', (None, None, -1))[2]: rec['season'] = (pid, year, v)
        best_c = None
        for pid in S:
            p = league.player(pid)
            if p is None: continue
            cv = sum(l.get(st, 0) for l in p.career.values())
            if cv > 0 and (best_c is None or cv > best_c[1]): best_c = (pid, cv)
        if best_c and best_c[1] > rec.get('career', (None, -1))[1]: rec['career'] = best_c
    _coaching_seasons(league, year, post)
    return A['seasons'][year]


def _runner_up(post):
    if post is None or not getattr(post, 'finalists', None): return None
    fin = list(post.finalists.values())
    return next((t for t in fin if t != post.champion), None)


def _coaching_seasons(league, year, post):
    A = _al(league)
    seeds = post.r.seeds() if (post is not None and hasattr(post, 'r')) else {}
    in_playoffs = {t for sd in seeds.values() for t in sd}
    for abbr, team in league.teams.items():
        if team.gm is None: continue
        hist = A['coaching'].setdefault(abbr, [])
        if not hist or hist[-1]['name'] != team.gm.name or hist[-1].get('to') is not None:
            hist.append(dict(name=team.gm.name, frm=year, to=None, w=0, l=0, t=0, playoffs=0, titles=0, seasons=0))
        h = hist[-1]; w, l, t = team.record
        h['w'] += w; h['l'] += l; h['t'] += t; h['seasons'] += 1
        h['playoffs'] += abbr in in_playoffs; h['titles'] += abbr == getattr(post, 'champion', None)


def coach_fired(league, abbr, year):
    """Close the sitting man's line when he goes."""
    hist = _al(league)['coaching'].get(abbr, [])
    if hist and hist[-1].get('to') is None: hist[-1]['to'] = year


# ------------------------------------------------------------ the Hall
def career_score(league, p):
    """One number for a career, by position, on a common scale where a
    ten-year starter at any spot lands near 100 and the greats near 250."""
    C = p.career or {}
    seasons = len([y for y, l in C.items() if l.get('snaps', 0) >= 400])
    v = 0.0
    for l in C.values():
        v += (l.get('pass_yds', 0) / 400.0 + l.get('pass_td', 0) * 0.8 - l.get('ints', 0) * 0.4
              + l.get('rush_yds', 0) / 120.0 + l.get('rush_td', 0) * 0.9
              + l.get('rec_yds', 0) / 120.0 + l.get('rec_td', 0) * 0.9 + l.get('rec', 0) * 0.05
              + l.get('sacks', 0) * 1.6 + l.get('int_def', 0) * 2.0 + l.get('pass_def', 0) * 0.3 + l.get('tackles', 0) * 0.06
              + l.get('pb_wins', 0) * 0.012 + l.get('fg_made', 0) * 0.35)
    v += seasons * 4.0
    # honours
    honours = 0.0
    for yr, aw in league.awards.items():
        for k, who in (aw or {}).items():
            if isinstance(who, list):
                if p.pid in who and k == 'all_pro_1': honours += 12
                elif p.pid in who and k == 'all_pro_2': honours += 5
            elif who == p.pid:
                honours += {'mvp': 30, 'opoy': 18, 'dpoy': 18, 'oroy': 6, 'droy': 6}.get(k, 4)
    titles = sum(1 for yr, s in _al(league)['seasons'].items() if s.get('champion') and s['champion'] == _team_in(p, yr))
    return dict(score=round(v + honours + 10 * titles, 1), seasons=seasons, honours=round(honours), titles=titles)


def _team_in(p, year):
    l = (p.career or {}).get(year) or {}
    return l.get('team')


def hall_vote(league, year, rng=None):
    """The class: retired men five offseasons out, the top two to four by career score,
    with the floor set by the class (the top man's score times 0.55, and never under 120)."""
    A = _al(league)
    elig = [p for p in league.players.values() if p.retired and getattr(p, 'retired_year', None) == year - HALL_WAIT and p.pid not in {h['pid'] for h in A['hall']}]
    if not elig: A['ballots'][year] = []; return []
    scored = sorted(((p, career_score(league, p)) for p in elig), key=lambda x: -x[1]['score'])
    top = scored[0][1]['score']; floor = max(120.0, 0.55 * top)
    inducted = []
    for p, sc in scored:
        if len(inducted) >= HALL_PER_YEAR[1]: break
        if sc['score'] >= floor or len(inducted) < HALL_PER_YEAR[0] and sc['score'] >= 100.0:
            inducted.append((p, sc))
    A['ballots'][year] = [(p.pid, sc['score'], any(q is p for q, _ in inducted)) for p, sc in scored[:15]]
    for p, sc in inducted:
        A['hall'].append(dict(pid=p.pid, name=p.name, pos=p.pos, inducted=year, seasons=sc['seasons'], honours=sc['honours'],
                              titles=sc['titles'], score=sc['score'], why=_why(league, p, sc)))
        league.log('hall_of_fame', pid=p.pid, name=p.name, pos=p.pos, score=sc['score'])
    return inducted


def _why(league, p, sc):
    C = p.career or {}
    tot = collections.Counter()
    for l in C.values():
        for k in ('pass_yds', 'pass_td', 'rush_yds', 'rush_td', 'rec', 'rec_yds', 'rec_td', 'sacks', 'int_def'):
            tot[k] += l.get(k, 0)
    bits = []
    if tot['pass_yds'] > 20000: bits.append(f"{tot['pass_yds']:,.0f} passing yards and {tot['pass_td']:.0f} touchdowns")
    if tot['rush_yds'] > 6000: bits.append(f"{tot['rush_yds']:,.0f} rushing yards")
    if tot['rec_yds'] > 7000: bits.append(f"{tot['rec']:.0f} catches for {tot['rec_yds']:,.0f} yards")
    if tot['sacks'] > 60: bits.append(f"{tot['sacks']:.0f} sacks")
    if tot['int_def'] > 25: bits.append(f"{tot['int_def']:.0f} interceptions")
    if sc['honours'] >= 30: bits.append('the honours to match')
    if sc['titles']: bits.append(f"{sc['titles']} title{'s' if sc['titles'] > 1 else ''}")
    return '; '.join(bits) or f"{sc['seasons']} seasons as a starter"


# ------------------------------------------------------------ readouts
def career_leaders(league, stat, top=10, active_only=False):
    rows = []
    for p in league.players.values():
        if active_only and p.retired: continue
        v = sum(l.get(stat, 0) for l in (p.career or {}).values())
        if v > 0: rows.append((p, v))
    rows.sort(key=lambda r: -r[1])
    return rows[:top]


def records(league):
    return _al(league)['records']


def coaching_history(league, abbr):
    return _al(league)['coaching'].get(abbr, [])
