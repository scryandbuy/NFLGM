"""
LEAGUE VIEWS. Standings, Schedule, Transactions, Stats, Awards, Coaching, Almanac.
Read-only pages; nothing here changes the league.
"""
from views import STADIUM, club, rail, _points, _form

DIVS = ['AFC East', 'AFC North', 'AFC South', 'AFC West', 'NFC East', 'NFC North', 'NFC South', 'NFC West']


def _state(session):
    """The season runner, or a stand-in built on the league when none is live (after a load, between phases), so
    standings and seeds always compute; the picture used to fall back to a three-club 'in the hunt' list."""
    r = getattr(session, 'runner', None)
    if r is None:
        try:
            import season as SN, numpy as np
            r = SN.SeasonRunner(session.L, np.random.default_rng(0)); r.week = int(getattr(session.L, 'week', 0) or 0)
        except Exception: r = None
    return r


def _years(league):
    """Every season the game has a record of, oldest first, the current year last."""
    ys = {int(league.year)}
    ys |= {int(k) for k in (getattr(league, 'history', {}) or {})}
    ys |= {int(k) for k in (getattr(league, 'standings_history', {}) or {})}
    ys |= {int(k) for k in (getattr(league, 'awards', {}) or {})}
    return sorted(ys)


def _thin_divisions(league, rows):
    """League rows grouped into the eight divisions, each ordered by percentage, for a past season's standings."""
    by = {}
    for r in rows:
        by.setdefault(r.get('division') or league.teams[r['club']['abbr']].division, []).append(r)
    out = []
    for name in sorted(by):
        conf = name.split()[0] if name else ''
        out.append(dict(name=name, conf=conf, rows=sorted(by[name], key=lambda x: -x['pct'])))
    return out


def _past(session, league, abbr, page, year):
    """A past season's page from the snapshot taken at that season's close, with a fresh rail."""
    snap = ((getattr(league, 'history', {}) or {}).get(str(year)) or {}).get(page)
    if snap is None: return None
    out = dict(snap); out['rail'] = rail(session, league, abbr); out['year'] = int(year); out['years'] = _years(league); out['past'] = True
    return out


def standings(session, league, abbr, year=None):
    yr = int(year) if year else int(league.year)
    if yr != int(league.year):
        past = _past(session, league, abbr, 'standings', yr)
        if past is not None:
            if past.get('thin') and not past.get('divisions') and past.get('league_rows'):
                past['divisions'] = _thin_divisions(league, past['league_rows'])      # a snapshot kept before the division cut
            return past
        # no snapshot (a season closed before snapshots existed): the records the league kept
        hist = (getattr(league, 'standings_history', {}) or {}).get(yr) or {}
        rows = []
        for a, r in hist.items():
            if a not in league.teams: continue
            rec = r.get('record') if isinstance(r, dict) else r
            if not isinstance(rec, (list, tuple)): continue
            w_, l_, d_ = (list(rec) + [0, 0, 0])[:3]
            rows.append(dict(club=club(a), record=f"{w_}–{l_}" + (f"–{d_}" if d_ else ''), pct=round((w_ + 0.5 * d_) / max(1, w_ + l_ + d_), 3), division=league.teams[a].division))
        if not rows and yr == int(league.year) - 1:
            # the season closed before its records were kept: the win percentages the teams carried into the new year
            for a, t in league.teams.items():
                pct = getattr(t, 'prev_win_pct', None)
                if pct is None: continue
                w_ = int(round(float(pct) * 17)); rows.append(dict(club=club(a), record=f"{w_}–{17 - w_}", pct=round(float(pct), 3), division=t.division))
        rows.sort(key=lambda x: -x['pct'])
        divs = _thin_divisions(league, rows)
        return dict(rail=rail(session, league, abbr), year=yr, years=_years(league), past=True, thin=True, league_rows=rows, divisions=divs, picture=None, conferences=[], notes=[], games_played=0, week=0)
    r = _state(session)
    st = r.standings() if r is not None else {}
    seeds = {}
    try:
        seeds = r.seeds() if r is not None else {}
    except Exception: seeds = {}
    ranks_prev = getattr(league, '_rank_prev', {}) or {}
    divs = []
    for name in DIVS:
        rows = []
        for t in league.teams.values():
            if t.division != name: continue
            w, l, d = t.record; pf, pa = _points(league, t.abbr)
            s = st.get(t.abbr, {})
            rows.append(dict(club=club(t.abbr), w=w, l=l, t=d, pct=s.get('pct', round((w + 0.5 * d) / max(1, w + l + d), 3)), pf=pf, pa=pa, pd=pf - pa, form=_form(league, t.abbr), me=(t.abbr == abbr), div_rank=s.get('div_rank'),
                            div_rec=_div_record(league, t), arrow=_rank_move(league, t.abbr, s.get('div_rank'))))
        rows.sort(key=lambda x: (x['div_rank'] or 9, -x['pct'], -x['pd']))
        divs.append(dict(name=name, rows=rows))
    picture = []
    for conf in ('AFC', 'NFC'):
        sd = seeds.get(conf) or []
        rows = []
        for i, a in enumerate(sd[:7], 1):
            t = league.teams[a]; w, l, d = t.record
            rows.append(dict(seed=i, club=club(a), record=f"{w}–{l}" + (f"–{d}" if d else ''), bye=(i == 1), div_winner=(i <= 4), me=(a == abbr)))
        # in the hunt: the next three by pct outside the seven
        outside = sorted([t for t in league.teams.values() if t.conf == conf and t.abbr not in sd[:7]], key=lambda t: -(t.record[0] + 0.5 * t.record[2]) / max(1, sum(t.record)))
        hunt = [dict(club=club(t.abbr), record=f"{t.record[0]}–{t.record[1]}" + (f"–{t.record[2]}" if t.record[2] else ''), me=(t.abbr == abbr)) for t in outside[:3]]
        picture.append(dict(conf=conf, seeds=rows, hunt=hunt))
    played = sum(1 for g in league.schedule if g[3] is not None)
    # the conference table, and a tiebreak note for clubs tied on pct within a division
    conf_rows = {}
    S_ = r.season_state() if r is not None else None
    for conf in ('AFC', 'NFC'):
        rows = [x for d in divs for x in d['rows'] if league.teams[x['club']['abbr']].conf == conf]
        sd = seeds.get(conf) or []
        rows = sorted(rows, key=lambda x: (sd.index(x['club']['abbr']) if x['club']['abbr'] in sd else 99, -x['pct'], -x['pd']))
        for x in rows:
            a = x['club']['abbr']
            x['seed'] = (sd.index(a) + 1) if a in sd[:7] else None
            if S_ is not None:
                x['conf_rec'] = _rec_str(S_.conf_rec(a)) if hasattr(S_, 'conf_rec') else None
                x['sov'] = round(S_.sov(a), 3); x['sos'] = round(S_.sos(a), 3)
        conf_rows[conf] = rows
    notes = []
    if S_ is not None:
        for d in divs:
            by_pct = {}
            for x in d['rows']: by_pct.setdefault(x['pct'], []).append(x['club']['abbr'])
            for pct, grp in by_pct.items():
                if len(grp) < 2 or pct == 0: continue
                first = next(x for x in d['rows'] if x['club']['abbr'] in grp)['club']['abbr']
                others = [a for a in grp if a != first]
                h2h = S_.h2h_pct(first, grp)
                if h2h is not None and h2h > 0.5: why = 'head-to-head'
                elif any(abs(S_.sov(first) - S_.sov(a)) > 1e-9 for a in others): why = 'strength of victory'
                elif any(abs(S_.sos(first) - S_.sos(a)) > 1e-9 for a in others): why = 'strength of schedule'
                else: why = 'the later tiebreakers'
                notes.append(f"{d['name']}: {' and '.join(grp)} tied at {pct:.3f}; {first} ahead on {why}.")
    # the whole league by pct, and remember this week's division ranks for next week's arrows
    league_rows = sorted([x for d in divs for x in d['rows']], key=lambda x: (-x['pct'], -x['pd']))
    if getattr(league, '_rank_week', None) != league.week:
        league._rank_prev = {x['club']['abbr']: x['div_rank'] for d in divs for x in d['rows'] if x['div_rank']}; league._rank_week = league.week
    return dict(rail=rail(session, league, abbr), divisions=divs, picture=picture, games_played=played, week=league.week, conferences=conf_rows, notes=notes, league_rows=league_rows, year=int(league.year), years=_years(league))


def _div_record(league, t):
    w = l = d = 0
    for (wk, a, h, ap, hp) in league.schedule:
        if ap is None or t.abbr not in (a, h): continue
        opp = h if a == t.abbr else a
        if league.teams[opp].division != t.division: continue
        mine, theirs = (ap, hp) if a == t.abbr else (hp, ap)
        if mine > theirs: w += 1
        elif mine < theirs: l += 1
        else: d += 1
    return f"{w}–{l}" + (f"–{d}" if d else '')


def _rank_move(league, abbr, rank_now):
    """Up or down since last week's standings, kept on the league from week to week."""
    prev = (getattr(league, '_rank_prev', None) or {}).get(abbr)
    if prev is None or rank_now is None: return 0
    return int(prev) - int(rank_now)


def _rec_str(rec):
    try: w, l, t = rec
    except Exception: return None
    return f"{w}–{l}" + (f"–{t}" if t else '')


def team_schedule(session, league, abbr, team=None, year=None):
    team = team or abbr
    yr = int(year) if year else int(league.year)
    if yr != int(league.year):
        # a past season's games for this team, cut from the schedule the history kept
        snap = ((getattr(league, 'history', {}) or {}).get(str(yr)) or {}).get('schedule')
        games = []
        for g in (snap or {}).get('all_games', []):
            if team not in (g['away']['abbr'], g['home']['abbr']): continue
            home = g['home']['abbr'] == team; opp = g['away'] if home else g['home']
            mine, theirs = (g['hp'], g['ap']) if home else (g['ap'], g['hp'])
            games.append(dict(week=g['week'], home=home, opp=opp, done=g['done'], mine=mine, theirs=theirs, result=(None if not g['done'] else 'W' if mine > theirs else 'L' if mine < theirs else 'T'), opp_rec='', box=False))
        # a week the history did not keep (a save from before the bye weeks were kept) shows as such, not as a bye
        kept_weeks = {g['week'] for g in (snap or {}).get('all_games', [])}
        missing_weeks = [w for w in range(1, 19) if w not in kept_weeks] if snap else []
        rec = (getattr(league, 'standings_history', {}) or {}).get(yr, {}).get(team)
        if isinstance(rec, dict): rec = rec.get('record')
        rec_s = (f"{rec[0]}–{rec[1]}" + (f"–{rec[2]}" if len(rec) > 2 and rec[2] else '')) if isinstance(rec, (list, tuple)) else ''
        return dict(rail=rail(session, league, abbr), team=club(team), record=rec_s, games=games, byes=[w for w in range(1, 19) if w not in {g['week'] for g in games} and w not in missing_weeks], not_kept=missing_weeks, clubs=[club(c) for c in sorted(league.teams)], year=yr, years=_years(league), past=True, missing=(snap is None))
    games = []
    for (wk, a, h, ap, hp) in sorted(league.schedule, key=lambda g: g[0]):
        if team not in (a, h): continue
        home = h == team; opp = a if home else h; done = ap is not None
        mine, theirs = (hp, ap) if home else (ap, hp)
        games.append(dict(week=wk, home=home, opp=club(opp), done=done, mine=mine, theirs=theirs, result=(None if not done else 'W' if mine > theirs else 'L' if mine < theirs else 'T'), opp_rec=_rec(league, opp),
                          box=(team == abbr and done and f"{league.year}-{wk}" in (getattr(session, 'gamedays', None) or {}))))
    weeks = {g['week'] for g in games}
    byes = [w for w in range(1, 19) if w not in weeks]
    t = league.teams[team]; w, l, d = t.record
    return dict(rail=rail(session, league, abbr), team=club(team), record=f"{w}–{l}" + (f"–{d}" if d else ''), games=games, byes=byes, clubs=[club(c) for c in sorted(league.teams)], year=int(league.year), years=_years(league), past=False)


def schedule(session, league, abbr, week=None, year=None):
    yr = int(year) if year else int(league.year)
    if yr != int(league.year):
        past = _past(session, league, abbr, 'schedule', yr)
        if past is None: return dict(rail=rail(session, league, abbr), year=yr, years=_years(league), past=True, missing=True, weeks=[], week=0, games=[], mine=[])
        if week is not None:
            # a past season, a chosen week: re-cut from the stored games
            wk = int(week); past['week'] = wk; past['games'] = [g for g in past.get('all_games', []) if g['week'] == wk]
        return past
    weeks = sorted({g[0] for g in league.schedule})
    cur = week or (league.week if league.week and league.week in weeks else (min(weeks) if weeks else 1))
    cur = int(cur)
    games = []
    for (wk, a, h, ap, hp) in league.schedule:
        if wk != cur: continue
        done = ap is not None
        note = ''
        gd = (getattr(session, 'gamedays', None) or {}).get(f"{league.year}-{cur}")
        if done and abbr in (a, h) and gd and gd.get('game'):
            g = gd['game']; note = ('OT · ' if g.get('ot') else '') + ' · '.join(f"{__import__('views').surname(r['name'])} {r['yds']} yds, {r['td']} TD" for r in (g.get('box') or {}).get('passing', [])[:1])
        games.append(dict(away=club(a), home=club(h), ap=ap, hp=hp, done=done, mine=(abbr in (a, h)), winner=(h if done and hp > ap else a if done and ap > hp else None),
                          away_rec=_rec(league, a), home_rec=_rec(league, h), note=note, box=(abbr in (a, h) and done and f"{league.year}-{cur}" in (getattr(session, 'gamedays', None) or {}))))
    games.sort(key=lambda g: (not g['mine'], g['home']['abbr']))
    byes = [club(t) for t in league.teams if not any(t in (g[1], g[2]) for g in league.schedule if g[0] == cur)]
    return dict(rail=rail(session, league, abbr), weeks=weeks, week=cur, games=games, byes=byes, year=int(league.year), years=_years(league))


def schedule_snapshot(session, league, abbr):
    """Every game of the season, week by week, for the history: the past-season schedule page re-cuts from this."""
    weeks = sorted({g[0] for g in league.schedule})
    allg = []
    for (wk, a, h, ap, hp) in sorted(league.schedule, key=lambda g: g[0]):
        done = ap is not None
        allg.append(dict(week=wk, away=club(a), home=club(h), ap=ap, hp=hp, done=done, mine=(abbr in (a, h)), winner=(h if done and hp > ap else a if done and ap > hp else None),
                         away_rec=_rec(league, a), home_rec=_rec(league, h), note='', box=False))
    last = max([w for w in weeks if w <= 18], default=18)
    return dict(weeks=weeks, week=last, games=[g for g in allg if g['week'] == last], all_games=allg, byes=[])


def _rec(league, a):
    w, l, d = league.teams[a].record
    return f"{w}–{l}" + (f"–{d}" if d else '')


TAGS = {'sign': 'Signing', 'release': 'Cut', 'trade': 'Trade', 'draft': 'Draft', 'extension': 'Extension', 'waiver_claim': 'Claim', 'ps_callup': 'Call-Up', 'ir': 'IR', 'gm_change': 'Coaching',
        'retire': 'Retirement', 'fire': 'Fired', 'hire': 'Hired', 'tag': 'Franchise Tag', 'restructure': 'Restructure', 'position_change': 'Position Change', 'hall_of_fame': 'Hall of Fame',
        'season_end': 'Season', 'inbox_trade': 'Trade', 'staff_hire': 'Staff', 'staff_release': 'Staff', 'staff_extend': 'Staff', 'poach': 'Staff', 'ps_sign': 'Practice Squad', 'ps_release': 'Practice Squad'}


GROUP_TAG = {'trade': 'Trades', 'inbox_trade': 'Trades', 'sign': 'Signings', 'ps_sign': 'Practice Squad', 'ps_callup': 'Practice Squad', 'release': 'Cuts', 'ps_release': 'Practice Squad', 'waiver_claim': 'Claims', 'extension': 'Extensions', 'restructure': 'Extensions', 'tag': 'Tags',
             'fire': 'Coaching', 'hire': 'Coaching', 'gm_change': 'Coaching', 'staff_hire': 'Coaching', 'staff_release': 'Coaching', 'staff_extend': 'Coaching', 'poach': 'Coaching', 'retire': 'Other', 'hall_of_fame': 'Other', 'season_end': 'Other', 'position_change': 'Other', 'ir': 'Other', 'draft': 'Other'}


def _asset(league, a):
    """A pid, a DraftPick, or the repr of one, as words."""
    import re
    s = str(a)
    from views import draft_year
    if hasattr(a, 'round') and hasattr(a, 'year'): return f"{draft_year(a.year)} R{a.round}"
    m = re.match(r"DraftPick\(year=(\d+), round=(\d+)", s)
    if m: return f"{draft_year(m.group(1))} R{m.group(2)}"
    p = league.player(s)
    return f"{p.name} ({p.pos})" if p else s


def _num(x):
    try: return int(round(float(x)))
    except Exception: return x


def _tx_line(league, x):
    """'KC Sign: Noah Avinger (WR), 2 yrs at $1.2m': the club, the move, the man. The page draws the club's color in front."""
    k = x.get('kind'); p = league.player(x['pid']) if x.get('pid') else None
    nm = p.name if p else x.get('name', '')
    pos = f" ({p.pos})" if p else ''
    team = x.get('team') or x.get('to') or ''
    if k == 'sign': return f"{team} Sign: {nm}{pos}" + (f", {x['years']} yrs" if x.get('years') else '') + (f" at ${x['apy']:.1f}m" if x.get('apy') else '')
    if k == 'release': return f"{team} Release: {nm}{pos}" + (f", ${x['dead']:.1f}m penalty" if x.get('dead') else '')
    if k in ('trade', 'inbox_trade'):
        a, b = x.get('a') or x.get('buyer', ''), x.get('b') or x.get('seller', league.user_team if hasattr(league, 'user_team') else '')
        return f"{a} Trade: send {', '.join(_asset(league, y) for y in x.get('a_sends', []))} to {b} for {', '.join(_asset(league, y) for y in x.get('b_sends', []))}" if x.get('a_sends') is not None else f"{a} Trade: with {b}"
    if k == 'draft': return f"{team} Draft: {nm}{pos} at {x.get('round', '?')}.{((x.get('selection', 1) - 1) % 32) + 1}"
    if k == 'extension': return f"{team} Extend: {nm}{pos}" + (f", {x['years']} yrs at ${x['apy']:.1f}m" if x.get('apy') else '')
    if k == 'waiver_claim': return f"{team} Claim: {nm}{pos}" + (f" off waivers from {x['from_team']}" if x.get('from_team') else '')
    if k == 'ps_sign': return f"{team} Practice Squad: {nm}{pos}"
    if k == 'ps_release': return f"{team} Practice Squad Release: {nm}{pos}"
    if k == 'ps_callup': return f"{team} Call-Up: {nm}{pos} signed from the practice squad"
    if k == 'retire': return f"{nm}{pos} retires" + (f" at {x['age']}" if x.get('age') else '')
    if k == 'fire': return f"{team} Fire: {x.get('coach', 'their head coach')}"
    if k == 'hire': return f"{team} Hire: {x.get('coach', x.get('name', 'a head coach'))}"
    if k == 'gm_change': return f"{team} Hire: {x.get('hired', 'a head coach')}" + (f", {x['background'].lower()}" if x.get('background') else '')
    if k == 'hall_of_fame': return f"{nm}{pos} elected to the Hall of Fame"
    if k == 'season_end': return f"{x.get('champion', '')} win the Super Bowl"
    if k == 'position_change': return f"{team} Position Change: {nm} to {x.get('to', '')}"
    if k in ('tag', 'franchise_tag'): return f"{team} Tag: {nm}{pos}"
    if k == 'restructure': return f"{team} Restructure: {nm}{pos}"
    if k in ('staff_hire', 'staff_release', 'staff_extend', 'poach'): return f"{team} Staff: {x.get('name', '')}" + (f", {x['why']}" if x.get('why') else '')
    if k == 'ir': return f"{team} IR: {nm}{pos}" + (f", out {int(x.get('weeks'))} weeks" if x.get('weeks') else '')
    return f"{team} {k.replace('_', ' ').title()}: {nm}".strip()


def transactions(session, league, abbr, n=150):
    """The most recent n of each group, so a cut-down day's hundreds of squad signings do not push the cuts and claims off the page."""
    rows = []; per = {}
    for x in reversed(league.transactions[-6000:]):
        k = x.get('kind')
        if k not in TAGS: continue
        g = GROUP_TAG.get(k, 'Other')
        if per.get(g, 0) >= n: continue
        per[g] = per.get(g, 0) + 1
        team = x.get('team') or x.get('a') or x.get('buyer') or x.get('to') or ''
        grp = GROUP_TAG.get(k, 'Other')
        link = ('trade' if k in ('trade', 'inbox_trade') else 'contract' if k in ('extension', 'sign', 'tag', 'restructure') else 'carousel' if k in ('fire', 'hire', 'gm_change') else 'card' if x.get('pid') else None)
        rows.append(dict(year=x.get('year'), week=x.get('week'), phase=x.get('phase'), kind=k, tag=TAGS.get(k, k), group=grp, line=_tx_line(league, x), mine=(abbr in (x.get('team'), x.get('a'), x.get('b'), x.get('buyer'), x.get('to'), x.get('from_team'))),
                        pid=x.get('pid'), team=(club(team) if team in league.teams else None), division=(league.teams[team].division if team in league.teams else None), link=link, i=len(rows)))
    return dict(rail=rail(session, league, abbr), rows=rows, groups=['Trades', 'Signings', 'Cuts', 'Claims', 'Practice Squad', 'Extensions', 'Tags', 'Coaching'], my_division=league.teams[abbr].division)


LEADERS = [('Passing Yards', 'pass_yds', 'yds'), ('Passing TD', 'pass_td', 'TD'), ('Rushing Yards', 'rush_yds', 'yds'), ('Rushing TD', 'rush_td', 'TD'), ('Receiving Yards', 'rec_yds', 'yds'), ('Receptions', 'rec', 'rec'),
           ('Sacks', 'sacks', 'sk'), ('Interceptions', 'int_def', 'INT'), ('Tackles', 'tackles', 'tkl'), ('Passes Defensed', 'pass_def', 'PD'), ('Field Goals', 'fg_made', 'FG'), ('Pressures', 'pressures', 'prs')]


def stats(session, league, abbr, year=None):
    yr = int(year or league.year)
    book = league.stats.get(yr, {}) or {}
    boxes = []
    for title, key, unit in LEADERS:
        rows = sorted(((pid, v) for pid, v in book.items() if v.get(key, 0) > 0), key=lambda kv: -kv[1].get(key, 0))[:8]
        out = []
        for pid, v in rows:
            p = league.player(pid)
            if p is None: continue
            val = v.get(key, 0)
            out.append(dict(pid=pid, name=p.name, pos=p.pos, team=(p.team or ''), v=(round(float(val), 1) if key == 'sacks' else _num(val)), mine=(p.team == abbr)))
        if out: boxes.append(dict(title=title, unit=unit, rows=out))
    years = sorted(set(int(k) for k in league.stats) | {int(league.year)})
    import advanced_stats as AS
    adv = []
    for title, metric, floor, pos, fmt in (('EPA per Dropback', 'epa_per_dropback', 150, ['QB'], 'epa'), ('Completion Over Expected', 'cpoe', 150, ['QB'], 'pct1'), ('EPA per Rush', 'epa_per_rush', 80, ['HB', 'FB'], 'epa'), ('EPA per Target', 'rec_epa_per_target', 40, ['WR', 'TE', 'HB'], 'epa'),
                                            ('Pass Rush Win Rate', 'pass_rush_win_rate', 100, None, 'pct'), ('Pass Block Win Rate', 'pass_block_win_rate', 200, ['LT', 'LG', 'C', 'RG', 'RT'], 'pct'), ('Separation', 'separation', 40, ['WR', 'TE'], 'f1'), ('Defensive EPA per Play', 'def_epa_per_play', 200, None, 'epa_neg')):
        scale = played_share(league, yr)
        try: rows = AS.leaders(league, yr, metric, min_n=max(1, int(floor * scale)), top=8, pos=pos)
        except Exception: rows = []
        if metric == 'def_epa_per_play': rows = sorted(rows, key=lambda r: r[1])[:8]
        out = []
        for p, val, n in rows:
            s = (f"{val:+.2f}" if fmt in ('epa', 'epa_neg') else f"{val:+.1f}" if fmt == 'pct1' else f"{val:.0f}%" if fmt == 'pct' else f"{val:.1f}")
            out.append(dict(pid=p.pid, name=p.name, pos=p.pos, team=(p.team or ''), v=s, n=int(n), mine=(p.team == abbr)))
        unit_word = {'epa_per_dropback': 'dropbacks', 'cpoe': 'attempts', 'epa_per_rush': 'carries', 'rec_epa_per_target': 'targets', 'pass_rush_win_rate': 'rushes', 'pass_block_win_rate': 'blocking snaps', 'separation': 'targets', 'def_epa_per_play': 'plays'}[metric]
        if out: adv.append(dict(title=title, unit=f"min {max(1, int(floor * scale))} {unit_word}", rows=out))
    # the position tables: passing, rushing, receiving, defense, blocking; and the team table
    def table(filt, key, cols):
        out = []
        for pid, ln in sorted(((pid, ln) for pid, ln in book.items() if ln.get(key, 0) > 0), key=lambda kv: -kv[1].get(key, 0))[:40]:
            p = league.player(pid)
            if p is None or not filt(p): continue
            out.append(dict(pid=pid, name=p.name, pos=p.pos, team=(p.team or ''), mine=(p.team == abbr), row=[c(ln) for _, c in cols]))
        return dict(cols=[h for h, _ in cols], rows=out)
    f1 = lambda x: (f"{x:.1f}" if isinstance(x, float) else x)
    tables = dict(
        passing=table(lambda p: p.pos == 'QB', 'pass_att', [('C/A', lambda l: f"{int(l.get('pass_cmp', 0))}/{int(l.get('pass_att', 0))}"), ('Yds', lambda l: int(l.get('pass_yds', 0))), ('TD', lambda l: int(l.get('pass_td', 0))), ('INT', lambda l: int(l.get('ints', 0))), ('Y/A', lambda l: f1(l.get('pass_yds', 0) / max(1, l.get('pass_att', 1)))), ('Sacked', lambda l: int(l.get('sacked', 0))), ('G', lambda l: int(l.get('games', 0)))]),
        rushing=table(lambda p: True, 'rush_att', [('Car', lambda l: int(l.get('rush_att', 0))), ('Yds', lambda l: int(l.get('rush_yds', 0))), ('YPC', lambda l: f1(l.get('rush_yds', 0) / max(1, l.get('rush_att', 1)))), ('TD', lambda l: int(l.get('rush_td', 0))), ('Fum', lambda l: int(l.get('fum', 0))), ('G', lambda l: int(l.get('games', 0)))]),
        receiving=table(lambda p: True, 'rec', [('Tgt', lambda l: int(l.get('tgt', 0))), ('Rec', lambda l: int(l.get('rec', 0))), ('Yds', lambda l: int(l.get('rec_yds', 0))), ('TD', lambda l: int(l.get('rec_td', 0))), ('Y/R', lambda l: f1(l.get('rec_yds', 0) / max(1, l.get('rec', 1)))), ('Drops', lambda l: int(l.get('drops', 0))), ('G', lambda l: int(l.get('games', 0)))]),
        defense=table(lambda p: p.pos in ('LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS'), 'tackles', [('Tkl', lambda l: int(l.get('tackles', 0))), ('Sacks', lambda l: f1(float(l.get('sacks', 0)))), ('Prs', lambda l: int(l.get('pressures', 0))), ('INT', lambda l: int(l.get('int_def', 0))), ('PD', lambda l: int(l.get('pass_def', 0))), ('FF', lambda l: int(l.get('ff', 0))), ('G', lambda l: int(l.get('games', 0)))]),
        blocking=table(lambda p: p.pos in ('LT', 'LG', 'C', 'RG', 'RT'), 'snaps', [('Snaps', lambda l: int(l.get('snaps', 0))), ('PB Win%', lambda l: (f"{l.get('pb_wins', 0) / l['pb_snaps'] * 100:.0f}%" if l.get('pb_snaps') else '—')), ('RB Win%', lambda l: (f"{l.get('rb_wins', 0) / l['rb_snaps'] * 100:.0f}%" if l.get('rb_snaps') else '—')), ('Sacks Allowed', lambda l: int(l.get('sacks_allowed', 0))), ('Pressures Allowed', lambda l: int(l.get('pressures_allowed', 0))), ('G', lambda l: int(l.get('games', 0)))]))
    team_rows = []
    for t in league.teams.values():
        pids = {p.pid for p in t.roster}; L_ = [book.get(pid, {}) for pid in pids]
        pf, pa = _points(league, t.abbr); gp = max(1, sum(t.record))
        pyds = sum(l.get('pass_yds', 0) for l in L_); ryds = sum(l.get('rush_yds', 0) for l in L_); plays = sum(l.get('pass_plays', 0) + l.get('rush_plays', 0) for l in L_); epa = sum(l.get('pass_epa', 0) + l.get('rush_epa', 0) for l in L_)
        sacks = sum(float(l.get('sacks', 0)) for l in L_); tos = sum(l.get('int_def', 0) for l in L_)
        team_rows.append(dict(club=club(t.abbr), mine=(t.abbr == abbr), pf=round(pf / gp, 1), pa=round(pa / gp, 1), ypg=round((pyds + ryds) / gp), pyds=round(pyds / gp), ryds=round(ryds / gp), epa=(round(epa / plays, 2) if plays else 0.0), sacks=round(sacks, 1), ints=int(tos)))
    team_rows.sort(key=lambda r: -r['pf'])
    return dict(rail=rail(session, league, abbr), year=yr, years=years, boxes=boxes, advanced=adv, tables=tables, team=team_rows, week=league.week)


def played_share(league, yr):
    """How far into the season we are, 0 to 1, so the minimums scale with the games played."""
    if yr != league.year: return 1.0
    done = sum(1 for g in league.schedule if g[3] is not None)
    return max(0.06, min(1.0, done / max(1, len(league.schedule))))


AWARD_NAMES = [('mvp', 'Most Valuable Player'), ('opoy', 'Offensive Player of the Year'), ('dpoy', 'Defensive Player of the Year'), ('oroy', 'Offensive Rookie of the Year'), ('droy', 'Defensive Rookie of the Year'),
               ('protector', 'Protector of the Year'), ('coty', 'Coach of the Year'), ('sb_mvp', 'Super Bowl MVP')]


def awards(session, league, abbr, year=None):
    years = sorted(set(league.awards) | {int(league.year)})
    yr = int(year) if year else (max([y for y in years if y in league.awards], default=int(league.year)))
    a = league.awards.get(yr, {}) or {}
    rows = []
    for k, name in AWARD_NAMES:
        v = a.get(k)
        if not v: continue
        if k == 'coty':
            t = league.teams.get(v); rows.append(dict(award=name, code='COTY', name=(t.gm.name if t and t.gm else str(v)), team=club(v) if t else None, pos='HC', mine=(v == abbr), line=(f"{t.record[0]}–{t.record[1]} · Prestige {round(getattr(t.gm, 'prestige', 50))}" if t and t.gm else '')))
        else:
            p = league.player(v)
            if p: rows.append(dict(award=name, code=k.upper().replace('SB_MVP', 'SB MVP'), name=p.name, pos=p.pos, team=(club(p.team) if p.team else None), pid=p.pid, mine=(p.team == abbr), line=(_sb_line(league, p, yr) if k == 'sb_mvp' else _award_line(league, p, yr))))
    def team_list(key):
        out = []
        for pid in a.get(key, []) or []:
            p = league.player(pid)
            if p: out.append(dict(pid=pid, name=p.name, pos=p.pos, team=(club(p.team) if p.team else None), mine=(p.team == abbr)))
        return out
    return dict(rail=rail(session, league, abbr), year=yr, years=years, rows=rows, first=team_list('all_pro_1'), second=team_list('all_pro_2'), pending=(league.year if league.year not in league.awards else None), note=None if a else f"{league.year} Awards Are Voted After Week 18")


def _sb_line(league, p, yr):
    """The Super Bowl MVP's line from THAT game (week 22 of the year), not his season."""
    key = next((k for k in (getattr(league, 'game_stats', {}) or {}) if k.startswith(f'{yr}-22-') and p.pid in league.game_stats[k]), None)
    l = league.game_stats[key][p.pid] if key else {}
    if not l: return _award_line(league, p, yr)
    if p.pos == 'QB': return f"{int(l.get('pass_cmp', l.get('cmp', 0)) or 0)}/{int(l.get('pass_att', l.get('att', 0)) or 0)}, {int(l.get('pass_yds', 0)):,} yds, {int(l.get('pass_td', 0))} TD, {int(l.get('ints', 0))} INT"
    if p.pos in ('HB', 'FB'): return f"{int(l.get('rush_att', 0))} car, {int(l.get('rush_yds', 0))} yds, {int(l.get('rush_td', 0))} TD" + (f", {int(l.get('rec', 0))} rec, {int(l.get('rec_yds', 0))} yds" if l.get('rec') else '')
    if p.pos in ('WR', 'TE'): return f"{int(l.get('rec', 0))} rec, {int(l.get('rec_yds', 0))} yds, {int(l.get('rec_td', 0))} TD"
    if p.pos in ('LT', 'LG', 'C', 'RG', 'RT'): return f"{int(l.get('snaps', 0))} snaps, {int(l.get('pb_wins', 0))} of {int(l.get('pb_snaps', 0))} pass blocks won"
    if p.pos in ('LEDG', 'REDG', 'DT'): return f"{float(l.get('sacks', 0) or 0):.1f} sacks, {int(l.get('pressures', 0))} pressures, {int(l.get('tackles', 0))} tkl"
    return f"{int(l.get('tackles', 0))} tkl, {float(l.get('sacks', 0) or 0):.1f} sk, {int(l.get('int_def', 0))} INT, {int(l.get('pass_def', 0))} PD"


def _award_line(league, p, yr):
    l = league.stats.get(yr, {}).get(p.pid, {}) or (getattr(p, 'career', {}) or {}).get(yr, {}) or {}
    if p.pos == 'QB': return f"{int(l.get('pass_yds', 0)):,} yds, {int(l.get('pass_td', 0))} TD, {int(l.get('ints', 0))} INT"
    if p.pos in ('HB', 'FB'): return f"{int(l.get('rush_att', 0))} car, {int(l.get('rush_yds', 0)):,} yds, {int(l.get('rush_td', 0))} TD"
    if p.pos in ('WR', 'TE'): return f"{int(l.get('rec', 0))} rec, {int(l.get('rec_yds', 0)):,} yds, {int(l.get('rec_td', 0))} TD"
    if p.pos in ('LT', 'LG', 'C', 'RG', 'RT'): return (f"{l.get('pb_wins', 0) / l['pb_snaps'] * 100:.0f}% pass block win" if l.get('pb_snaps') else f"{int(l.get('snaps', 0))} snaps")
    if p.pos in ('LEDG', 'REDG', 'DT'): return f"{float(l.get('sacks', 0)):.1f} sacks, {int(l.get('pressures', 0))} pressures"
    return f"{int(l.get('tackles', 0))} tkl, {int(l.get('int_def', 0))} INT, {int(l.get('pass_def', 0))} PD"


def coaching(session, league, abbr):
    import firing_model as FM, coaching_pool as CP, almanac as AL
    seats = []
    for t in league.teams.values():
        h = t.hist(); sec = FM.job_security(h)
        notes = []
        if int(h.get('playoff_drought') or 0) >= 2: notes.append(f"Missed {'twice' if h['playoff_drought'] == 2 else str(h['playoff_drought']) + ' years'} running")
        if float(getattr(t, 'owner_patience', 0.5)) >= 0.65 and t.record[0] < t.record[1]: notes.append('Owner wants a rebuild')
        if float(getattr(t, 'owner_patience', 0.5)) <= 0.35 and t.record[0] < t.record[1]: notes.append('Owner wants results now')
        seats.append(dict(club=club(t.abbr), coach=(t.gm.name if t.gm else ''), prestige=round(getattr(t.gm, 'prestige', 50)) if t.gm else None, tenure=int(h.get('tenure') or 0), note=' · '.join(notes),
                          seat=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), security=round(sec, 2), me=(t.abbr == abbr),
                          record=_rec(league, t.abbr), history=[dict(name=x.get('name'), frm=x.get('from'), to=x.get('to'), record=x.get('record')) for x in AL.coaching_history(league, t.abbr)[-3:] if x.get('name')]))
    seats.sort(key=lambda s: s['security'])
    pool = []
    for g in CP.pool(league)[:12]:
        hr = getattr(g, 'hc_record', None) or {}
        pool.append(dict(name=g.name, prestige=round(getattr(g, 'prestige', 50)), background=getattr(g, 'background', ''), seasons=hr.get('seasons', 0), win_pct=hr.get('win_pct'), playoffs=hr.get('playoffs', 0)))
    carousel = []
    for x in league.transactions:
        if x.get('kind') == 'gm_change' and x.get('year') in (league.year, league.year - 1):
            carousel.append(dict(year=x.get('year'), club=club(x['team']), hired=x.get('hired'), background=x.get('background'), win_pct=x.get('win_pct')))
    return dict(rail=rail(session, league, abbr), seats=seats, pool=pool, carousel_open=(league.phase in ('offseason', 'free_agency', 'draft')), carousel=carousel[::-1], note=('Owners Decide After Week 18' if league.phase in ('regular', 'preseason') else 'The carousel is turning'))


def almanac(session, league, abbr):
    import almanac as AL
    al = AL._al(league)
    seasons = []
    for yr, s in sorted(al['seasons'].items(), reverse=True):
        aw = s.get('awards', {}) or {}
        mvp = aw.get('mvp'); mvp = (mvp.get('name') if isinstance(mvp, dict) else mvp); mvp = None if mvp in (None, 'None', '') else mvp
        seasons.append(dict(year=yr, champion=club(s['champion']) if s.get('champion') in league.teams else None, runner_up=club(s['runner_up']) if s.get('runner_up') in league.teams else None,
                            mvp=mvp, mine=(s.get('champion') == abbr), score=s.get('score')))
    records = []
    names = dict(pass_yds='Passing Yards', pass_td='Passing TD', rush_yds='Rushing Yards', rush_td='Rushing TD', rec='Receptions', rec_yds='Receiving Yards', rec_td='Receiving TD', sacks='Sacks', int_def='Interceptions', tackles='Tackles', fg_made='Field Goals', pass_def='Passes Defensed')
    for stat, rec in al['records'].items():
        s = rec.get('season'); c = rec.get('career')
        sp = league.player(s[0]) if s else None; cp = league.player(c[0]) if c else None
        records.append(dict(stat=names.get(stat, stat), season=(dict(name=sp.name, year=s[1], team=((getattr(sp, 'career', {}) or {}).get(s[1], {}) or {}).get('team') or sp.team or '', v=(round(float(s[2]), 1) if stat == 'sacks' else _num(s[2]))) if sp else None), career=(dict(name=cp.name, team=(cp.team or (f"Retired {cp.retired_year}" if getattr(cp, 'retired_year', None) else '')), active=(not cp.retired), v=(round(float(c[1]), 1) if stat == 'sacks' else _num(c[1]))) if cp else None)))
    hall = []
    for h in reversed(al['hall']):
        p = league.player(h.get('pid')); clubs = []; yrs = []
        for yr_, ln in sorted((getattr(p, 'career', {}) or {}).items()) if p else []:
            if ln.get('team') and ln['team'] not in clubs: clubs.append(ln['team'])
            yrs.append(yr_)
        span = (f"{min(yrs)}–{max(yrs)}" if yrs else '')
        hall.append(dict(name=h.get('name'), pos=h.get('pos'), inducted=h.get('inducted'), seasons=h.get('seasons'), why=h.get('why', ''), clubs=' · '.join(league.teams[c].name if c in league.teams else c for c in clubs), span=span, first_ballot=(getattr(p, 'retired_year', None) is not None and h.get('inducted') == getattr(p, 'retired_year', 0) + AL.HALL_WAIT)))
    nxt = league.year + 1
    ballot = sorted([p for p in league.players.values() if p.retired and getattr(p, 'retired_year', None) == nxt - AL.HALL_WAIT and p.pid not in {h.get('pid') for h in al['hall']}], key=lambda p: -sum((getattr(p, 'career', {}) or {}).get(y, {}).get('games', 0) for y in (getattr(p, 'career', {}) or {})))
    next_ballot = dict(year=nxt, names=[p.name for p in ballot[:5]])
    careers = []
    for title, stat in (('Passing Yards', 'pass_yds'), ('Passing TD', 'pass_td'), ('Rushing Yards', 'rush_yds'), ('Receiving Yards', 'rec_yds'), ('Receptions', 'rec'), ('Sacks', 'sacks'), ('Interceptions', 'int_def'), ('Tackles', 'tackles')):
        rows = AL.career_leaders(league, stat, top=8)
        careers.append(dict(title=title, rows=[dict(pid=p.pid, name=p.name, pos=p.pos, v=(round(float(x), 1) if stat == 'sacks' else int(x)), active=(not p.retired), mine=(p.team == abbr)) for p, x in rows]))
    ledger = []
    for a in sorted(league.teams):
        for x in AL.coaching_history(league, a):
            if x.get('name'): ledger.append(dict(club=club(a), name=x['name'], frm=x.get('from'), to=x.get('to'), record=x.get('record'), current=(x.get('to') is None)))
    ledger.sort(key=lambda x: (x['frm'] or 0), reverse=True)
    return dict(rail=rail(session, league, abbr), seasons=seasons, records=records, hall=hall, careers=careers, ledger=ledger, next_ballot=next_ballot, note=None if (seasons or hall or records) else 'The almanac fills as seasons close.')


# ============================================================ THE TEAM PAGE
def team_page(session, league, me_abbr, abbr):
    """One club at a glance: record and place, the unit ranks, the coaches, the top five, the cap this year and
    next, and the trading block (the men the club would move). Your own club shows the same page."""
    import staff as ST, trades as TR, valuation as VAL, numpy as np
    from views import rail, _division_place
    from cap_engine import CAP
    t = league.teams[abbr]; me = league.teams[me_abbr]
    w, l = t.record[0], t.record[1]; d = t.record[2] if len(t.record) > 2 else 0
    try: ranks = ST.unit_ranks(league, league.year).get(abbr, {})
    except Exception: ranks = {}
    staff = {role: (dict(name=c.name, rating=round(c.rating), specialty=c.specialty) if c else None) for role, c in (getattr(t, 'staff', None) or {}).items()}
    top = [dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), age=int(p.age), apy=round(p.apy, 1), yrs=(p.contract.years if p.contract else 0), no=getattr(p, 'number', None)) for p in sorted(t.active(), key=lambda p: -p.ovr)[:5]]
    from views import next_year_cap
    limit_next, committed_next, _ro, _dn = next_year_cap(league, t)
    # the block: the men this club would move, in the trade engine's own read
    block = []
    try:
        rng = np.random.default_rng(abs(hash(abbr + str(league.week))) % (2 ** 32)); pool = VAL.pool_from_league(league)
        sur, needs = TR.surplus_and_needs(league, t, pool, rng)
        import views_personnel as VP
        for x in sur[:8]:
            p = league.player(x['pid'])
            if p is None: continue
            block.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), age=int(p.age), apy=round(p.apy, 1), yrs=(p.contract.years if p.contract else 0), why=VP._surplus_why(league, t, x)))
        needs = sorted(needs)
    except Exception:
        needs = []
    from views import club
    import practice_squad as PSQ
    return dict(rail=rail(session, league, me_abbr), club=club(abbr), mine=(abbr == me_abbr), record=f"{w}–{l}" + (f"–{d}" if d else ''), place=_division_place(league, abbr), division=t.division,
                ranks=dict(offense=ranks.get('oc'), defense=ranks.get('dc'), kicking=ranks.get('st')), coach=dict(name=t.gm.name if t.gm else '', prestige=round(getattr(t.gm, 'prestige', 0) or 0), background=getattr(t.gm, 'background', ''), personnel=getattr(t.gm, 'off_personnel', '')) if t.gm else None,
                staff=staff, identity=_identity_names(league, t), top=top, cap=dict(space=round(t.cap_space, 1), limit=round(CAP.get(league.year, 301.2), 1), committed_next=committed_next, limit_next=limit_next), block=block, needs=needs,
                roster_n=len(t.active()), ps_n=len(PSQ.squad(t)), ir_n=len(getattr(t, 'ir', None) or []), clubs=[club(c) for c in sorted(league.teams)])


def _identity_names(league, t):
    try:
        import views_frontoffice as VF, identity_catalog as IC
        ident = VF.club_identity(league, t)
        return dict(offense=IC.ARCHETYPES[ident['offence']]['name'], defense=IC.ARCHETYPES[ident['defence']]['name'])
    except Exception:
        return dict(offense='', defense='')


def bracket(session, league, abbr, year=None):
    """The playoff bracket as a tree: each conference's bye, three wild card games, two divisional games and the
    championship, the Super Bowl in the middle with its site. Live while the postseason runs; the last finished
    bracket after it; before the playoffs, the field as the standings would seed it; a past year's from the history."""
    import postseason as PS, standings_and_seeding as SS
    yr = int(year) if year else int(league.year)
    if yr != int(league.year):
        past = _past(session, league, abbr, 'bracket', yr)
        if past is not None: return past
        post_last = getattr(session, 'post', None)
        if not (post_last is not None and getattr(post_last, 'champion', None) and yr == int(league.year) - 1):
            return dict(rail=rail(session, league, abbr), year=yr, years=_years(league), past=True, missing=True, live=False, started=False, confs=[], final=None, champion=None, sb=None, note='No bracket is kept for that season.')
        post = post_last            # the season just closed: the bracket the close left behind
    else:
        post = getattr(session, 'post_live', None) or getattr(session, 'post', None)
        if post is not None and getattr(post, 'champion', None) and int(getattr(post, 'year', 0) or 0) != int(league.year) and getattr(session, 'post_live', None) is None:
            # the last season's finished bracket belongs to its own year; this year's is empty until its field is set
            post = None
        if post is None and (league.phase not in ('regular',) or not league.week):
            return dict(rail=rail(session, league, abbr), year=yr, years=_years(league), past=False, missing=True, live=False, started=False, confs=[], final=None, champion=None, sb=None, note=f'The {yr} bracket is set after Week 18.')
    started = bool(post is not None and getattr(post, 'seeds', None))
    if not started:
        r = _state(session)
        try: seeds = {c: list(sd)[:7] for c, sd in (r.seeds() if r is not None else {}).items()}
        except Exception: seeds = {}
        games = []; alive_now = {t for sd in seeds.values() for t in sd}; champion = None
    else:
        seeds = {c: list(sd) for c, sd in post.seeds.items()}
        games = list(getattr(post, 'games', []) or [])
        alive_now = {t for al in getattr(post, 'alive', {}).values() for t in al.values()} | set(getattr(post, 'conf_champs', {}).values())
        champion = post.champion
        if champion: alive_now = {champion}
    seed_of = {t: i + 1 for sd in seeds.values() for i, t in enumerate(sd)}
    def game_row(rnd, conf, home, away, hs=None, as_=None):
        return dict(round=rnd, conf=conf, home=club(home), away=club(away), hs=hs, as_=as_, done=hs is not None,
                    winner=(home if (hs or 0) >= (as_ or 0) else away) if hs is not None else None, me=(abbr in (home, away)),
                    home_seed=seed_of.get(home), away_seed=seed_of.get(away), home_record=_rec(league, home), away_record=_rec(league, away), stadium=STADIUM.get(home, ''))
    confs = []
    for conf, sd in seeds.items():
        by_seed = {i + 1: t for i, t in enumerate(sd)}
        rounds = {}
        prev_done = True
        for rnd in ('WC', 'DIV', 'CONF'):
            played = [game_row(rnd, c, h, a, hs, as_) for (r_, c, h, a, hs, as_) in games if r_ == rnd and c == conf]
            if rnd == 'WC' and not played:
                pending = [game_row('WC', conf, by_seed[hi], by_seed[lo]) for hi, lo in SS.wc_matchups(sd) if hi in by_seed and lo in by_seed]
            else:
                # a round's matchups show only once the round before it is complete; until then it is to be decided
                pending = [game_row(rnd, c, h, a) for (c, h, a) in (post.matchups(rnd) if started and not played and champion is None and prev_done else []) if c == conf]
            need = {'WC': 3, 'DIV': 2, 'CONF': 1}[rnd]
            prev_done = len(played) >= need
            gs = played or pending
            # wild card in seed order (2v7, 3v6, 4v5); divisional with the top seed's game first, so the tree reads top-down
            if rnd == 'WC': gs.sort(key=lambda g: (g['home_seed'] or 9))
            elif rnd == 'DIV': gs.sort(key=lambda g: min(g['home_seed'] or 9, g['away_seed'] or 9))
            rounds[rnd] = gs
        bye = by_seed.get(1)
        confs.append(dict(conf=conf, bye=(dict(club=club(bye), seed=1, record=_rec(league, bye), me=(bye == abbr), alive=(bye in alive_now)) if bye else None),
                          wc=rounds['WC'], div=rounds['DIV'], conf_game=(rounds['CONF'][0] if rounds['CONF'] else None),
                          champ=club(post.conf_champs[conf]) if started and (getattr(post, 'conf_champs', {}) or {}).get(conf) else None))
    order = {'AFC': 0, 'NFC': 1}; confs.sort(key=lambda c: order.get(c['conf'], 9))
    sb = [game_row('SB', c, h, a, hs, as_) for (r_, c, h, a, hs, as_) in games if r_ == 'SB']
    if not sb and started and champion is None and len(getattr(post, 'conf_champs', {}) or {}) == 2: sb = [game_row('SB', c, h, a) for (c, h, a) in post.matchups('SB')]
    site = PS.sb_venue(league)
    return dict(rail=rail(session, league, abbr), year=yr, years=_years(league), live=(started and champion is None), started=started, confs=confs, final=(sb[0] if sb else None),
                champion=(club(champion) if champion else None), site=site, note=(None if started else 'The field as it stands. The bracket is set after Week 18.'))


def _rec(league, t):
    w, l, d = league.teams[t].record
    return f"{w}–{l}" + (f"–{d}" if d else '')


def _seed_of(post, t):
    for c, sd in (getattr(post, 'seeds', {}) or {}).items():
        if t in sd: return list(sd).index(t) + 1
    return None
