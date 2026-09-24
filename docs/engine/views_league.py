"""
LEAGUE VIEWS. Standings, Schedule, Transactions, Stats, Awards, Coaching, Almanac.
Read-only pages; nothing here changes the league.
"""
from views import club, rail, _points, _form

DIVS = ['AFC East', 'AFC North', 'AFC South', 'AFC West', 'NFC East', 'NFC North', 'NFC South', 'NFC West']


def _state(session):
    r = getattr(session, 'runner', None)
    return r


def standings(session, league, abbr):
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
            rows.append(dict(club=club(t.abbr), w=w, l=l, t=d, pct=s.get('pct', round((w + 0.5 * d) / max(1, w + l + d), 3)), pf=pf, pa=pa, pd=pf - pa, form=_form(league, t.abbr), me=(t.abbr == abbr), div_rank=s.get('div_rank')))
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
                x['div_rec'] = _rec_str(S_.div_rec(a)) if hasattr(S_, 'div_rec') else None; x['conf_rec'] = _rec_str(S_.conf_rec(a)) if hasattr(S_, 'conf_rec') else None
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
    return dict(rail=rail(session, league, abbr), divisions=divs, picture=picture, games_played=played, week=league.week, conferences=conf_rows, notes=notes)


def _rec_str(rec):
    try: w, l, t = rec
    except Exception: return None
    return f"{w}–{l}" + (f"–{t}" if t else '')


def team_schedule(session, league, abbr, team=None):
    team = team or abbr
    games = []
    for (wk, a, h, ap, hp) in sorted(league.schedule, key=lambda g: g[0]):
        if team not in (a, h): continue
        home = h == team; opp = a if home else h; done = ap is not None
        mine, theirs = (hp, ap) if home else (ap, hp)
        games.append(dict(week=wk, home=home, opp=club(opp), done=done, mine=mine, theirs=theirs, result=(None if not done else 'W' if mine > theirs else 'L' if mine < theirs else 'T'), opp_rec=_rec(league, opp)))
    weeks = {g['week'] for g in games}
    byes = [w for w in range(1, 19) if w not in weeks]
    t = league.teams[team]; w, l, d = t.record
    return dict(rail=rail(session, league, abbr), team=club(team), record=f"{w}–{l}" + (f"–{d}" if d else ''), games=games, byes=byes, clubs=[club(c) for c in sorted(league.teams)])


def schedule(session, league, abbr, week=None):
    weeks = sorted({g[0] for g in league.schedule})
    cur = week or (league.week if league.week and league.week in weeks else (min(weeks) if weeks else 1))
    cur = int(cur)
    games = []
    for (wk, a, h, ap, hp) in league.schedule:
        if wk != cur: continue
        done = ap is not None
        games.append(dict(away=club(a), home=club(h), ap=ap, hp=hp, done=done, mine=(abbr in (a, h)), winner=(h if done and hp > ap else a if done and ap > hp else None),
                          away_rec=_rec(league, a), home_rec=_rec(league, h)))
    games.sort(key=lambda g: (not g['mine'], g['home']['abbr']))
    byes = [club(t) for t in league.teams if not any(t in (g[1], g[2]) for g in league.schedule if g[0] == cur)]
    return dict(rail=rail(session, league, abbr), weeks=weeks, week=cur, games=games, byes=byes)


def _rec(league, a):
    w, l, d = league.teams[a].record
    return f"{w}–{l}" + (f"–{d}" if d else '')


TAGS = {'sign': 'Signing', 'release': 'Release', 'trade': 'Trade', 'draft': 'Draft', 'extension': 'Extension', 'waiver_claim': 'Waivers', 'ps_callup': 'Call-Up', 'ir': 'Injured Reserve',
        'retire': 'Retirement', 'fire': 'Fired', 'hire': 'Hired', 'tag': 'Franchise Tag', 'restructure': 'Restructure', 'position_change': 'Position Change', 'hall_of_fame': 'Hall of Fame',
        'season_end': 'Season', 'inbox_trade': 'Trade', 'staff_hire': 'Staff', 'staff_release': 'Staff', 'staff_extend': 'Staff', 'poach': 'Staff', 'ps_sign': 'Practice Squad', 'ps_release': 'Practice Squad'}


def _asset(league, a):
    """A pid, a DraftPick, or the repr of one, as words."""
    import re
    s = str(a)
    if hasattr(a, 'round') and hasattr(a, 'year'): return f"{a.year} R{a.round}"
    m = re.match(r"DraftPick\(year=(\d+), round=(\d+)", s)
    if m: return f"{m.group(1)} R{m.group(2)}"
    p = league.player(s)
    return f"{p.name} ({p.pos})" if p else s


def _num(x):
    try: return int(round(float(x)))
    except Exception: return x


def _tx_line(league, x):
    k = x.get('kind'); p = league.player(x['pid']) if x.get('pid') else None
    nm = p.name if p else x.get('name', '')
    pos = f" ({p.pos})" if p else ''
    team = x.get('team') or x.get('to') or ''
    if k == 'sign': return f"{team} sign {nm}{pos}" + (f", {x['years']} yrs" if x.get('years') else '') + (f" at ${x['apy']:.1f}m" if x.get('apy') else '')
    if k == 'release': return f"{team} release {nm}{pos}" + (f", ${x['dead']:.1f}m penalty" if x.get('dead') else '')
    if k in ('trade', 'inbox_trade'):
        a, b = x.get('a') or x.get('buyer', ''), x.get('b') or x.get('seller', league.user_team if hasattr(league, 'user_team') else '')
        return f"{a} and {b} make a trade" + (f": {a} send {', '.join(_asset(league, y) for y in x.get('a_sends', []))} for {', '.join(_asset(league, y) for y in x.get('b_sends', []))}" if x.get('a_sends') else '')
    if k == 'draft': return f"{team} draft {nm}{pos} at {x.get('round', '?')}.{((x.get('selection', 1) - 1) % 32) + 1}"
    if k == 'extension': return f"{team} extend {nm}{pos}" + (f", {x['years']} yrs at ${x['apy']:.1f}m" if x.get('apy') else '')
    if k == 'waiver_claim': return f"{team} claim {nm}{pos} off waivers" + (f" from {x['from_team']}" if x.get('from_team') else '')
    if k == 'ps_callup': return f"{team} call up {nm}{pos} from the practice squad"
    if k == 'retire': return f"{nm}{pos} retires" + (f" at {x['age']}" if x.get('age') else '')
    if k == 'fire': return f"{team} fire {x.get('coach', 'their head coach')}"
    if k == 'hire': return f"{team} hire {x.get('coach', x.get('name', 'a head coach'))}"
    if k == 'hall_of_fame': return f"{nm}{pos} elected to the Hall of Fame"
    if k == 'season_end': return f"{x.get('champion', '')} win the Super Bowl"
    if k == 'position_change': return f"{team} move {nm} to {x.get('to', '')}"
    if k == 'tag': return f"{team} tag {nm}{pos}"
    return f"{k.replace('_', ' ')}: {nm} {team}".strip()


def transactions(session, league, abbr, n=150):
    rows = []
    for x in reversed(league.transactions[-2000:]):
        k = x.get('kind')
        if k not in TAGS: continue
        rows.append(dict(year=x.get('year'), week=x.get('week'), phase=x.get('phase'), kind=k, tag=TAGS[k], line=_tx_line(league, x), mine=(abbr in (x.get('team'), x.get('a'), x.get('b'), x.get('buyer'), x.get('to'), x.get('from_team'))), pid=x.get('pid')))
        if len(rows) >= n: break
    return dict(rail=rail(session, league, abbr), rows=rows, tags=sorted(set(TAGS.values())))


LEADERS = [('Passing Yards', 'pass_yds', 'yds'), ('Passing TD', 'pass_td', 'TD'), ('Rushing Yards', 'rush_yds', 'yds'), ('Rushing TD', 'rush_td', 'TD'), ('Receiving Yards', 'rec_yds', 'yds'), ('Receptions', 'rec', 'rec'),
           ('Sacks', 'sacks', 'sk'), ('Interceptions', 'interceptions', 'INT'), ('Tackles', 'tackles', 'tkl'), ('Passes Defensed', 'pass_def', 'PD'), ('Field Goals', 'fg_made', 'FG'), ('Pressures', 'pressures', 'prs')]


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
    years = sorted(league.stats)
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
    return dict(rail=rail(session, league, abbr), year=yr, years=years, boxes=boxes, advanced=adv)


def played_share(league, yr):
    """How far into the season we are, 0 to 1, so the minimums scale with the games played."""
    if yr != league.year: return 1.0
    done = sum(1 for g in league.schedule if g[3] is not None)
    return max(0.06, min(1.0, done / max(1, len(league.schedule))))


AWARD_NAMES = [('mvp', 'Most Valuable Player'), ('opoy', 'Offensive Player of the Year'), ('dpoy', 'Defensive Player of the Year'), ('oroy', 'Offensive Rookie of the Year'), ('droy', 'Defensive Rookie of the Year'),
               ('protector', 'Protector of the Year'), ('coty', 'Coach of the Year'), ('sb_mvp', 'Super Bowl MVP')]


def awards(session, league, abbr, year=None):
    years = sorted(league.awards)
    yr = int(year) if year else (years[-1] if years else league.year)
    a = league.awards.get(yr, {}) or {}
    rows = []
    for k, name in AWARD_NAMES:
        v = a.get(k)
        if not v: continue
        if k == 'coty':
            t = league.teams.get(v); rows.append(dict(award=name, name=(t.gm.name if t and t.gm else str(v)), team=club(v) if t else None, pos='HC', mine=(v == abbr)))
        else:
            p = league.player(v)
            if p: rows.append(dict(award=name, name=p.name, pos=p.pos, team=(club(p.team) if p.team else None), pid=p.pid, mine=(p.team == abbr)))
    def team_list(key):
        out = []
        for pid in a.get(key, []) or []:
            p = league.player(pid)
            if p: out.append(dict(pid=pid, name=p.name, pos=p.pos, team=(p.team or ''), mine=(p.team == abbr)))
        return out
    return dict(rail=rail(session, league, abbr), year=yr, years=years, rows=rows, first=team_list('all_pro_1'), second=team_list('all_pro_2'), note=None if a else 'Awards are voted after the season.')


def coaching(session, league, abbr):
    import firing_model as FM, coaching_pool as CP, almanac as AL
    seats = []
    for t in league.teams.values():
        h = t.hist(); sec = FM.job_security(h)
        seats.append(dict(club=club(t.abbr), coach=(t.gm.name if t.gm else ''), prestige=round(getattr(t.gm, 'prestige', 50)) if t.gm else None, tenure=int(h.get('tenure') or 0),
                          seat=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), security=round(sec, 2), me=(t.abbr == abbr),
                          record=_rec(league, t.abbr), history=[dict(name=x.get('name'), frm=x.get('from'), to=x.get('to'), record=x.get('record')) for x in AL.coaching_history(league, t.abbr)[-3:] if x.get('name')]))
    seats.sort(key=lambda s: s['security'])
    pool = []
    for g in CP.pool(league)[:12]:
        hr = getattr(g, 'hc_record', None) or {}
        pool.append(dict(name=g.name, prestige=round(getattr(g, 'prestige', 50)), background=getattr(g, 'background', ''), seasons=hr.get('seasons', 0), win_pct=hr.get('win_pct'), playoffs=hr.get('playoffs', 0)))
    return dict(rail=rail(session, league, abbr), seats=seats, pool=pool, carousel_open=(league.phase != 'regular'))


def almanac(session, league, abbr):
    import almanac as AL
    al = AL._al(league)
    seasons = []
    for yr, s in sorted(al['seasons'].items(), reverse=True):
        aw = s.get('awards', {}) or {}
        mvp = aw.get('mvp'); mvp = (mvp.get('name') if isinstance(mvp, dict) else mvp); mvp = None if mvp in (None, 'None', '') else mvp
        seasons.append(dict(year=yr, champion=club(s['champion']) if s.get('champion') in league.teams else None, runner_up=club(s['runner_up']) if s.get('runner_up') in league.teams else None,
                            mvp=mvp, mine=(s.get('champion') == abbr)))
    records = []
    names = dict(pass_yds='Passing Yards', pass_td='Passing TD', rush_yds='Rushing Yards', rush_td='Rushing TD', rec='Receptions', rec_yds='Receiving Yards', rec_td='Receiving TD', sacks='Sacks', int_def='Interceptions', tackles='Tackles', fg_made='Field Goals', pass_def='Passes Defensed')
    for stat, rec in al['records'].items():
        s = rec.get('season'); c = rec.get('career')
        sp = league.player(s[0]) if s else None; cp = league.player(c[0]) if c else None
        records.append(dict(stat=names.get(stat, stat), season=(dict(name=sp.name, year=s[1], v=(round(float(s[2]), 1) if stat == 'sacks' else _num(s[2]))) if sp else None), career=(dict(name=cp.name, v=(round(float(c[1]), 1) if stat == 'sacks' else _num(c[1]))) if cp else None)))
    hall = [dict(name=h.get('name'), pos=h.get('pos'), inducted=h.get('inducted'), seasons=h.get('seasons'), why=h.get('why', '')) for h in reversed(al['hall'])]
    careers = []
    for title, stat in (('Passing Yards', 'pass_yds'), ('Passing TD', 'pass_td'), ('Rushing Yards', 'rush_yds'), ('Receiving Yards', 'rec_yds'), ('Receptions', 'rec'), ('Sacks', 'sacks'), ('Interceptions', 'int_def'), ('Tackles', 'tackles')):
        rows = AL.career_leaders(league, stat, top=8)
        careers.append(dict(title=title, rows=[dict(pid=p.pid, name=p.name, pos=p.pos, v=(round(float(x), 1) if stat == 'sacks' else int(x)), active=(not p.retired), mine=(p.team == abbr)) for p, x in rows]))
    ledger = []
    for a in sorted(league.teams):
        for x in AL.coaching_history(league, a):
            if x.get('name'): ledger.append(dict(club=club(a), name=x['name'], frm=x.get('from'), to=x.get('to'), record=x.get('record'), current=(x.get('to') is None)))
    ledger.sort(key=lambda x: (x['frm'] or 0), reverse=True)
    return dict(rail=rail(session, league, abbr), seasons=seasons, records=records, hall=hall, careers=careers, ledger=ledger, note=None if (seasons or hall or records) else 'The almanac fills as seasons close.')
