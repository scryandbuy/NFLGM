"""
CLUB VIEWS. What the Roster, Player Card, Depth Chart and Practice Squad pages
show, as plain dicts, and the actions their buttons call.
"""
import numpy as np
from views import club, money, morale_word, player_plate, rail

GROUPS = [('Quarterbacks', ['QB']), ('Running Backs', ['HB', 'FB']), ('Wide Receivers', ['WR']), ('Tight Ends', ['TE']),
          ('Offensive Line', ['LT', 'LG', 'C', 'RG', 'RT']), ('Defensive Line', ['LEDG', 'DT', 'REDG']), ('Linebackers', ['MIKE', 'WILL', 'SAM']),
          ('Defensive Backs', ['CB', 'FS', 'SS']), ('Specialists', ['K', 'P', 'LS'])]
OFFENSE = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
DEV_WORD = {'xfactor': 'X-Factor', 'superstar': 'Superstar', 'star': 'Star', 'normal': 'Normal', 'slow': 'Slow'}

# attribute groups per position family for the card, in FM's three columns
ATTR = {
    'phys': [('speed_rating', 'Speed'), ('accel_rating', 'Acceleration'), ('agility_rating', 'Agility'), ('change_of_direction_rating', 'Change of Direction'), ('strength_rating', 'Strength'), ('jump_rating', 'Jump'), ('stamina_rating', 'Stamina'), ('injury_rating', 'Injury'), ('tough_rating', 'Toughness')],
    'QB': [('throw_power_rating', 'Arm Strength'), ('throw_acc_short_rating', 'Short Accuracy'), ('throw_acc_mid_rating', 'Medium Accuracy'), ('throw_acc_deep_rating', 'Deep Accuracy'), ('throw_under_pressure_rating', 'Under Pressure'), ('throw_on_run_rating', 'On the Run'), ('play_action_rating', 'Play Action'), ('break_sack_rating', 'Break Sack')],
    'HB': [('carry_rating', 'Carrying'), ('break_tackle_rating', 'Break Tackle'), ('truck_rating', 'Trucking'), ('juke_move_rating', 'Juke'), ('spin_move_rating', 'Spin'), ('stiff_arm_rating', 'Stiff Arm'), ('bcv_rating', 'Vision'), ('catch_rating', 'Catching'), ('pass_block_rating', 'Pass Block')],
    'WR': [('catch_rating', 'Catching'), ('cit_rating', 'Catch in Traffic'), ('spec_catch_rating', 'Spectacular Catch'), ('release_rating', 'Release'), ('route_run_short_rating', 'Short Routes'), ('route_run_med_rating', 'Medium Routes'), ('route_run_deep_rating', 'Deep Routes'), ('bcv_rating', 'Vision'), ('run_block_rating', 'Run Block')],
    'OL': [('pass_block_rating', 'Pass Block'), ('pass_block_power_rating', 'Pass Block Power'), ('pass_block_finesse_rating', 'Pass Block Finesse'), ('run_block_rating', 'Run Block'), ('run_block_power_rating', 'Run Block Power'), ('run_block_finesse_rating', 'Run Block Finesse'), ('lead_block_rating', 'Lead Block'), ('impact_block_rating', 'Impact Block')],
    'DL': [('power_moves_rating', 'Power Moves'), ('finesse_moves_rating', 'Finesse Moves'), ('block_shed_rating', 'Block Shedding'), ('tackle_rating', 'Tackle'), ('hit_power_rating', 'Hit Power'), ('pursuit_rating', 'Pursuit'), ('play_rec_rating', 'Play Recognition')],
    'LB': [('tackle_rating', 'Tackle'), ('hit_power_rating', 'Hit Power'), ('pursuit_rating', 'Pursuit'), ('play_rec_rating', 'Play Recognition'), ('block_shed_rating', 'Block Shedding'), ('zone_cover_rating', 'Zone Coverage'), ('man_cover_rating', 'Man Coverage'), ('power_moves_rating', 'Power Moves')],
    'DB': [('man_cover_rating', 'Man Coverage'), ('zone_cover_rating', 'Zone Coverage'), ('press_rating', 'Press'), ('play_rec_rating', 'Play Recognition'), ('catch_rating', 'Catching'), ('tackle_rating', 'Tackle'), ('hit_power_rating', 'Hit Power'), ('pursuit_rating', 'Pursuit'), ('block_shed_rating', 'Block Shedding')],
    'K': [('kick_power_rating', 'Kick Power'), ('kick_acc_rating', 'Kick Accuracy')],
    'mental': [('awareness_rating', 'Awareness')],
    'st': [('kick_ret_rating', 'Return')],
    'rundef': [('tackle_rating', 'Tackle'), ('hit_power_rating', 'Hit Power'), ('pursuit_rating', 'Pursuit'), ('block_shed_rating', 'Block Shedding')],
    'coverage': [('man_cover_rating', 'Man Coverage'), ('zone_cover_rating', 'Zone Coverage'), ('press_rating', 'Press'), ('play_rec_rating', 'Play Recognition'), ('catch_rating', 'Catching')],
}
FAM = {'HB': 'HB', 'FB': 'HB', 'WR': 'WR', 'TE': 'WR', 'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL', 'LEDG': 'DL', 'DT': 'DL', 'REDG': 'DL',
       'MIKE': 'LB', 'WILL': 'LB', 'SAM': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'K': 'K', 'P': 'K', 'LS': 'OL', 'QB': 'QB'}
SKILL_TITLE = {'QB': 'Passing', 'HB': 'Running', 'WR': 'Receiving', 'OL': 'Blocking', 'DL': 'Front', 'LB': 'Defense', 'DB': 'Coverage', 'K': 'Kicking'}


def _fit(league, t, p):
    import gm_engine as GE
    try: return float(GE.scheme_fit(p.ratings, p.pos, t))
    except Exception: return 0.0


def _cond(session, p):
    try:
        st = session.runner.states.get(p.team) if session.runner else None
        return round(float(st.cond.get(p.pid))) if st is not None else 100
    except Exception: return 100


def _status(league, p, t):
    out = []
    if p.out_until is not None: out.append(f"Out · Wk {p.out_until}")
    if p.contract and p.contract.years <= 1: out.append('Final Year')
    import extensions as EXT
    try:
        if EXT.eligible(p, league) and p.contract and p.contract.years >= 2: out.append('Ext. Eligible')
    except Exception: pass
    m = getattr(p, 'morale', None)
    if m is not None and m.value < 25: out.append('Wants Out' if getattr(m, 'requested', False) else 'Unhappy')
    tr = getattr(p, 'transition', None)
    if tr and tr.get('games_left', 0) > 0: out.append(f"Learning {p.pos}")
    return ' · '.join(out)


def _row(session, league, t, p):
    yrs = p.contract.years if p.contract else 0
    return dict(pid=p.pid, no=getattr(p, 'number', None) or '', name=p.name, pos=p.pos, side=('offense' if p.pos in OFFENSE else 'special' if p.pos in ('K', 'P', 'LS') else 'defense'), age=int(p.age), ovr=round(p.ovr), fit=round(_fit(league, t, p), 1),
                dev=DEV_WORD.get(str(getattr(p, 'dev', 'normal')).lower(), 'Normal'), cond=_cond(session, p), morale=morale_word(p), yrs=yrs,
                hit=round(p.cap_hit(0), 1), penalty=round(p.dead_if_cut(0), 1), status=_status(league, p, t),
                college=getattr(p, 'college', None) or '', season_no=(league.year - p.draft_year + 1) if getattr(p, 'draft_year', None) else None,
                # ratings view
                pot=(round(p.potential) if getattr(p, 'potential', None) else None), pot_range=list(getattr(p, 'potential_range', None) or []) or None,
                # stats view: the season line
                stats=_season_line(league, p))


def _season_line(league, p, year=None):
    """The season line by position, with the advanced numbers the engine keeps."""
    import advanced_stats as AS
    S = league.stats.get(year or league.year, {}).get(p.pid, {}) or {}
    m = AS.line_metrics(S) if S else {}
    g = int(S.get('games', 0) or 0)
    def f1(x): return f"{x:+.2f}" if x is not None else '—'
    if p.pos == 'QB':
        att = int(S.get('pass_att', 0)); cmp_ = int(S.get('pass_cmp', 0))
        return dict(games=g, line=f"{cmp_}/{att} · {int(S.get('pass_yds', 0))} yds · {int(S.get('pass_td', 0))} TD · {int(S.get('ints', 0))} INT",
                    comp=(round(cmp_ / att * 100) if att else None), epa=m.get('epa_per_dropback'), cpoe=m.get('cpoe'),
                    cols=['C/A', 'Yds', 'TD', 'INT', 'Comp%', 'CPOE', 'EPA/Dropback', 'Sacked'],
                    row=[f"{cmp_}/{att}", int(S.get('pass_yds', 0)), int(S.get('pass_td', 0)), int(S.get('ints', 0)), (f"{cmp_ / att * 100:.0f}%" if att else '—'), (f"{m['cpoe']:+.1f}" if 'cpoe' in m else '—'), f1(m.get('epa_per_dropback')), int(S.get('sacked', 0))])
    if p.pos in ('HB', 'FB'):
        return dict(games=g, line=f"{int(S.get('rush_att', 0))} car · {int(S.get('rush_yds', 0))} yds · {int(S.get('rush_td', 0))} TD · {int(S.get('rec', 0))} rec",
                    comp=None, epa=m.get('epa_per_rush'),
                    cols=['Car', 'Yds', 'YPC', 'TD', 'Rec', 'Rec Yds', 'EPA/Rush', 'EPA/Tgt'],
                    row=[int(S.get('rush_att', 0)), int(S.get('rush_yds', 0)), (f"{S['rush_yds'] / S['rush_att']:.1f}" if S.get('rush_att') else '—'), int(S.get('rush_td', 0)), int(S.get('rec', 0)), int(S.get('rec_yds', 0)), f1(m.get('epa_per_rush')), f1(m.get('rec_epa_per_target'))])
    if p.pos in ('WR', 'TE'):
        tgt = int(S.get('tgt', 0)); rec = int(S.get('rec', 0))
        return dict(games=g, line=f"{rec} rec · {int(S.get('rec_yds', 0))} yds · {int(S.get('rec_td', 0))} TD",
                    comp=(round(rec / tgt * 100) if tgt else None), epa=m.get('rec_epa_per_target'),
                    cols=['Tgt', 'Rec', 'Yds', 'TD', 'Catch%', 'Drops', 'Separation', 'EPA/Tgt'],
                    row=[tgt, rec, int(S.get('rec_yds', 0)), int(S.get('rec_td', 0)), (f"{rec / tgt * 100:.0f}%" if tgt else '—'), int(S.get('drops', 0)), (f"{m['separation']:.1f}" if 'separation' in m else '—'), f1(m.get('rec_epa_per_target'))])
    if p.pos in ('LT', 'LG', 'C', 'RG', 'RT'):
        return dict(games=g, line=f"{int(S.get('snaps', 0))} snaps · {int(S.get('sacks_allowed', 0))} sacks allowed · {int(S.get('pressures_allowed', 0))} pressures",
                    comp=None, epa=None,
                    cols=['Snaps', 'Pass Block Win%', 'Run Block Win%', 'Sacks Allowed', 'Pressures Allowed'],
                    row=[int(S.get('snaps', 0)), (f"{m['pass_block_win_rate']:.0f}%" if 'pass_block_win_rate' in m else '—'), (f"{S['rb_wins'] / S['rb_snaps'] * 100:.0f}%" if S.get('rb_snaps') else '—'), int(S.get('sacks_allowed', 0)), int(S.get('pressures_allowed', 0))])
    if p.pos == 'K':
        return dict(games=g, line=f"{int(S.get('fg_made', 0))}/{int(S.get('fg_att', 0))} FG · long {int(S.get('fg_long', 0))}", comp=None, epa=None,
                    cols=['FG', 'FG%', 'Long', 'XP'], row=[f"{int(S.get('fg_made', 0))}/{int(S.get('fg_att', 0))}", (f"{S['fg_made'] / S['fg_att'] * 100:.0f}%" if S.get('fg_att') else '—'), int(S.get('fg_long', 0)), f"{int(S.get('xp_made', 0))}/{int(S.get('xp_att', 0))}"])
    if p.pos == 'P':
        n = int(S.get('punts', 0))
        return dict(games=g, line=f"{n} punts · {(S.get('punt_yds', 0) / n if n else 0):.1f} avg", comp=None, epa=None,
                    cols=['Punts', 'Gross', 'Net', 'Inside 20', 'Touchbacks'], row=[n, (f"{S['punt_yds'] / n:.1f}" if n else '—'), (f"{S.get('punt_net_yds', 0) / n:.1f}" if n else '—'), int(S.get('punt_in20', 0)), int(S.get('punt_tb', 0))])
    # the defense
    front = p.pos in ('LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM')
    return dict(games=g, line=f"{int(S.get('tackles', 0))} tkl · {float(S.get('sacks', 0) or 0):.1f} sk · {int(S.get('int_def', 0))} INT · {int(S.get('pass_def', 0))} PD",
                comp=None, epa=m.get('def_epa_per_play'),
                cols=(['Tkl', 'Sacks', 'Pressures', 'Pass Rush Win%', 'FF', 'EPA/Play'] if front else ['Tkl', 'INT', 'PD', 'FF', 'Sacks', 'EPA/Play']),
                row=([int(S.get('tackles', 0)), f"{float(S.get('sacks', 0) or 0):.1f}", int(S.get('pressures', 0)), (f"{m['pass_rush_win_rate']:.0f}%" if 'pass_rush_win_rate' in m else '—'), int(S.get('ff', 0)), f1(m.get('def_epa_per_play'))] if front
                     else [int(S.get('tackles', 0)), int(S.get('int_def', 0)), int(S.get('pass_def', 0)), int(S.get('ff', 0)), f"{float(S.get('sacks', 0) or 0):.1f}", f1(m.get('def_epa_per_play'))]))


def roster(session, league, abbr):
    t = league.teams[abbr]
    groups = []
    for title, poss in GROUPS:
        men = [p for p in t.active() if p.pos in poss]
        men.sort(key=lambda p: (poss.index(p.pos), -p.ovr))
        if men: groups.append(dict(title=title, rows=[_row(session, league, t, p) for p in men]))
    import practice_squad as PSQ
    ps = []
    for p in PSQ.squad(t):
        r = _row(session, league, t, p); r['elevations'] = int(p.xp_spent.get('_elevations', 0) or 0); r['elevated_now'] = p in (getattr(t, '_elevated', []) or [])
        ps.append(r)
    injured = [_row(session, league, t, p) for p in t.active() if p.out_until is not None]
    return dict(rail=rail(session, league, abbr), groups=groups, count=len(t.active()), cap_total=round(sum(p.cap_hit(0) for p in t.active()), 1),
                practice=ps, injured=injured, ps_charge=round(PSQ.ps_charge(t), 1), elevations_used=len(getattr(t, '_elevated', []) or []), elevations_max=PSQ.ELEVATIONS_PER_GAME, per_man_max=PSQ.ELEVATIONS_PER_MAN)


# ------------------------------------------------------------ the card
def card(session, league, pid):
    p = league.player(pid)
    if p is None: return dict(error='no such player')
    t = league.teams.get(p.team) if p.team else None
    user = league.teams[session.user_team]
    fit = _fit(league, t, p) if t else 0.0
    fam = FAM.get(p.pos, 'DB')
    import targets as TG, position_change as PC
    # the shift the user's scheme puts on each attribute, from the scheme's weights at his spot
    shift = {}
    try:
        schemes = getattr(user, 'scheme', None) or {}
        keys = list(schemes.values()) if isinstance(schemes, dict) else ([schemes] if isinstance(schemes, str) else list(schemes))
        for s in keys:
            for k, v in TG.SCHEME_SHIFT.get(s, {}).items():
                if k in p.ratings: shift[k] = shift.get(k, 0) + round(float(v) * 20)
        shift = {k: v for k, v in shift.items() if v}
    except Exception: pass
    def col(keys):
        out = []
        for k, lab in keys:
            v = p.ratings.get(k)
            if v is None: continue
            out.append(dict(key=k, label=lab, v=int(round(float(v))), tier=('hi' if v >= 85 else 'md' if v >= 72 else 'lo'), shift=shift.get(k)))
        return out
    phys = dict(title='Physical', rows=col(ATTR['phys']), extra=(dict(title='Special Teams', rows=col(ATTR['st'])) if p.pos in ('WR', 'HB', 'CB', 'FS', 'SS') and col(ATTR['st']) else None))
    if fam == 'DB': skill = dict(title='Coverage', rows=col(ATTR['coverage']), extra=dict(title='Run Defense', rows=col(ATTR['rundef'])))
    elif fam in ('LB', 'DL'): skill = dict(title=SKILL_TITLE.get(fam, 'Skill'), rows=col([k for k in ATTR[fam] if k[0] not in ('tackle_rating', 'hit_power_rating', 'pursuit_rating', 'block_shed_rating')]), extra=dict(title='Run Defense', rows=col(ATTR['rundef'])))
    else: skill = dict(title=SKILL_TITLE.get(fam, 'Skill'), rows=col(ATTR.get(fam, ATTR['DB'])), extra=None)
    cols = [phys, skill, dict(title='Mental', rows=col(ATTR['mental']), extra=None)]
    # positions: his spot and the family he could move to, with his grade at each
    family = PC.FAMILY.get(p.pos, [])
    grades = [dict(pos=p.pos, ovr=round(p.ovr), mine=True)]
    for alt in family:
        try: g = float(TG.position_score(p.ratings, alt, getattr(user, 'scheme', None)))
        except Exception: g = None
        if g is not None: grades.append(dict(pos=alt, ovr=round(g), mine=False, tax=PC.distance(p.pos, alt)))
    # contract by year
    years = []
    if p.contract:
        c = p.contract
        for i in range(c.years):
            try: years.append(dict(year=league.year + i, base=round(c.base[i] + c.rb[i], 1), bonus=round(c.annual_proration if i < c.proration_years else 0.0, 1), hit=round(c.cap_hit(i), 1), penalty=round(c.release(i)[0], 1)))
            except Exception: years.append(dict(year=league.year + i, hit=round(c.cap_hit(i), 1)))
    if p.pos == 'CB':
        try:
            nk = float(TG.position_score(p.ratings, 'CB', ['man']))
            grades.append(dict(pos='Nickel', ovr=round(float(TG.position_score(dict(p.ratings, speed_rating=p.ratings.get('agility_rating', 70)), 'CB', getattr(user, 'scheme', None)))), mine=False, tax=0))
        except Exception: pass
    import personality as PT
    words = PT.words(getattr(p, 'traits', None) or {}) if getattr(p, 'traits', None) else ''
    # role and snaps: where he sits on his club's depth chart, and his share of the club's snaps this season
    role = None; snap_share = None; snaps = None
    if t is not None:
        d = t.depth.get(p.pos, []); idx = next((i for i, q in enumerate(d) if q.pid == p.pid), None)
        if idx is not None: role = f"{p.pos}{idx + 1}"
        S_all = league.stats.get(league.year, {}); mine_snaps = int((S_all.get(p.pid, {}) or {}).get('snaps', 0) or 0)
        side_pos = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
        unit = [q for q in t.roster if (q.pos in side_pos) == (p.pos in side_pos)]
        team_snaps = max((int((S_all.get(q.pid, {}) or {}).get('snaps', 0) or 0) for q in unit if q.pos == ('QB' if p.pos in side_pos else 'MIKE')), default=0)
        if team_snaps: snap_share = round(mine_snaps / team_snaps * 100); snaps = f"{snap_share}% · {mine_snaps} of {team_snaps}"
    missed = sum(1 for h in (getattr(p, 'injury_history', None) or []) for _ in range(int(h.get('weeks', 1) or 1))) if isinstance(getattr(p, 'injury_history', None), list) else 0
    tr = getattr(p, 'transition', None)
    pending = f"Learning {tr.get('to')} · {tr.get('games_left')} games left" if tr and tr.get('games_left', 0) > 0 else 'None pending'
    # the market and the extension ask
    market_apy = None; ext_ask = None
    try:
        import valuation as VAL
        mv = VAL.value_player(league, p, side='buyer'); market_apy = round(float(mv['apy']), 1) if mv and mv.get('apy') else None
    except Exception: pass
    try:
        import extensions as EXT
        if _ext_ok(league, p):
            tm = EXT.terms(league, p, np.random.default_rng(abs(hash(p.pid)) % (2 ** 32))); ext_ask = round(float(tm['ask']), 1) if tm else None
    except Exception: pass
    # trade interest in words, from the market read
    interest = 'Low'
    try:
        import valuation as VAL
        v = VAL.value_player(league, p, side='buyer')
        if v and v.get('apy'): interest = 'High' if p.ovr >= 84 and p.age <= 29 else 'Moderate' if p.ovr >= 76 else 'Low'
    except Exception: pass
    S = league.stats.get(league.year, {}).get(p.pid, {}) or {}
    m = getattr(p, 'morale', None)
    # trade value in the scout's words: what the market would pay, and who has asked
    market = _market_words(league, p, interest)
    asks = [x for x in getattr(league, 'inbox', []) if x.get('kind') == 'trade_offer' and (x.get('payload') or {}).get('gets') and p.pid in [str(a) for a in (x.get('payload') or {}).get('gets', [])]]
    interest_line = (f"{len(asks)} club{'s' if len(asks) != 1 else ''} have asked about him this season." if asks else 'No club has called about him this season.')
    # development: the season's movement and the XP he holds
    career = getattr(p, 'career', {}) or {}
    xp_bank = round(float(getattr(p, 'xp', 0) or 0)); bought = sum(vv for k, vv in (p.xp_spent or {}).items() if not k.startswith('_') and isinstance(vv, (int, float)))
    dev_line = f"{xp_bank:,} XP banked · {int(bought)} points bought in his career"
    seasons = []
    for yr in sorted(career)[-3:]:
        ln = _season_line(league, p, yr); seasons.append(dict(year=yr, team=career[yr].get('team') or '', games=int((career[yr] or {}).get('games', 0) or 0), row=ln['row'], cols=ln['cols']))
    cur = _season_line(league, p)
    h = getattr(p, 'height', None); size = (f"{h // 12}'{h % 12}\" {getattr(p, 'weight', '') or ''}".strip() if h else '')
    drafted = (f"drafted {p.draft_overall}{_ordn(p.draft_overall)} overall, {p.draft_year}" if getattr(p, 'draft_overall', None) else f"drafted round {p.draft_round}, {p.draft_year}" if getattr(p, 'draft_round', None) else 'undrafted')
    return dict(rail=rail(session, league, session.user_team), pid=p.pid, no=getattr(p, 'number', None) or '', name=p.name, pos=p.pos, age=int(p.age), size=size,
                team=club(p.team) if p.team else None, college=getattr(p, 'college', None) or '', draft=drafted,
                role=role, snaps=snaps, missed=missed, pending=pending, market_apy=market_apy, ext_ask=ext_ask, ext_eligible=_ext_ok(league, p),
                contract_caption=(f"Contract signed {getattr(p.contract, 'signed', league.year)} · {p.contract.years + (len(getattr(p.contract, 'base', [])) - p.contract.years if hasattr(p.contract, 'base') else 0)} yrs · ${round(sum(getattr(p.contract, 'base', [])) + getattr(p.contract, 'annual_proration', 0) * getattr(p.contract, 'proration_years', 0), 1)}m" if p.contract else 'No contract'),
                season_no=(league.year - p.draft_year + 1) if getattr(p, 'draft_year', None) else None,
                ovr=round(p.ovr), fit=round(fit, 1), ceiling=(f"{int(p.potential_range[0])}–{int(p.potential_range[1])}" if getattr(p, 'potential_range', None) else (str(round(p.potential)) if getattr(p, 'potential', None) else '—')),
                dev=DEV_WORD.get(str(getattr(p, 'dev', 'normal')).lower(), 'Normal'), morale=morale_word(p), morale_v=round(m.value) if m is not None else None,
                contract=dict(per_year=round(p.apy, 1) if p.contract else 0.0, years=p.contract.years if p.contract else 0, hit=round(p.cap_hit(0), 1), penalty=round(p.dead_if_cut(0), 1), by_year=years),
                interest=interest, cols=cols, grades=grades, personality=words, status=_status(league, p, t) if t else '',
                cond=_cond(session, p), out=p.out_until, season=cur, games=int(S.get('games', 0) or 0), seasons=seasons,
                market=market, interest_line=interest_line, dev_line=dev_line, morale_line=_morale_line(p),
                history=_player_history(league, p),
                actions=dict(mine=(p.team == session.user_team), extend_eligible=_ext_ok(league, p), can_cut=(p.team == session.user_team)))


def _market_words(league, p, interest):
    role = 'a starter' if p.ovr >= 78 else 'a rotation piece' if p.ovr >= 72 else 'a depth player'
    age = 'in his prime' if 25 <= p.age <= 29 else 'still coming' if p.age < 25 else 'on the back half' if p.age <= 32 else 'near the end'
    deal = 'on a fair deal' if p.contract and p.apy <= max(1.5, p.ovr / 10) else 'on a heavy deal' if p.contract else 'without a contract'
    price = {'High': 'Clubs with a hole at the spot would pay a first-round pick and more.', 'Moderate': 'A second- or third-round pick is the range.', 'Low': 'A late pick, or a swap of depth.'}[interest]
    return f"{role.capitalize()} {age} {deal}. {price}"


def _morale_line(p):
    m = getattr(p, 'morale', None)
    if m is None: return 'Steady'
    reasons = getattr(m, 'reasons', None) or getattr(m, 'notes', None) or []
    if reasons: return str(reasons[-1])[:60]
    return 'Steady since camp'


def _player_history(league, p):
    """Every logged move that names him: signings, releases, trades, extensions, tags, position changes, elevations."""
    import views_league as VL
    out = []
    for x in league.transactions:
        if x.get('kind') not in VL.TAGS: continue
        named = x.get('pid') == p.pid or p.pid in [str(a) for a in (x.get('a_sends') or [])] or p.pid in [str(a) for a in (x.get('b_sends') or [])]
        if not named: continue
        out.append(dict(when=f"{x.get('year')}" + (f" · Wk {x['week']}" if x.get('week') else (' · ' + x['phase']) if x.get('phase') else ''), line=VL._tx_line(league, x)))
    if getattr(p, 'draft_year', None) and getattr(p, 'draft_round', None): out.insert(0, dict(when=str(p.draft_year), line=f"Drafted {p.draft_overall}{_ordn(p.draft_overall)} overall (round {p.draft_round})" if getattr(p, 'draft_overall', None) else f"Drafted, round {p.draft_round}"))
    return out[-30:]


def _ordn(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def _ext_ok(league, p):
    import extensions as EXT
    try: return bool(EXT.eligible(p, league))
    except Exception: return False


# ------------------------------------------------------------ the depth chart
PACKAGES = {'Base': dict(WR=2, TE=2, HB=1, LB=3, CB=2, S=2), 'Nickel': dict(WR=3, TE=1, HB=1, LB=2, CB=3, S=2), 'Dime': dict(WR=3, TE=1, HB=1, LB=1, CB=4, S=2),
            'Goal Line': dict(WR=1, TE=2, HB=1, FB=1, LB=3, CB=2, S=2), 'Third Down': dict(WR=3, TE=1, HB=1, LB=2, CB=3, S=2), 'Two Minute': dict(WR=4, TE=1, HB=1, LB=1, CB=4, S=2)}
# one column a position, grouped by side; the heading is the position, the group is the caption
SIDES = {
    'offense': [('QB', 'QB', 'Quarterback'), ('HB', 'HB', 'Backs'), ('FB', 'FB', 'Backs'), ('WR', 'WR', 'Receivers'), ('TE', 'TE', 'Tight Ends'),
                ('LT', 'LT', 'Line'), ('LG', 'LG', 'Line'), ('C', 'C', 'Line'), ('RG', 'RG', 'Line'), ('RT', 'RT', 'Line')],
    'defense': [('LEDG', 'LE', 'Front'), ('DT', 'DT', 'Front'), ('REDG', 'RE', 'Front'), ('MIKE', 'MIKE', 'Linebackers'), ('WILL', 'WILL', 'Linebackers'), ('SAM', 'SAM', 'Linebackers'),
                ('CB', 'CB', 'Secondary'), ('FS', 'FS', 'Secondary'), ('SS', 'SS', 'Secondary')],
    'specialists': [('K', 'K', 'Specialists'), ('P', 'P', 'Specialists'), ('LS', 'LS', 'Specialists')],
}
# how many start at each position, by package
def _starters(pos, pk):
    if pos == 'QB': return 1
    if pos == 'HB': return pk.get('HB', 1)
    if pos == 'FB': return pk.get('FB', 0)
    if pos == 'WR': return pk.get('WR', 3)
    if pos == 'TE': return pk.get('TE', 1)
    if pos in ('LT', 'LG', 'C', 'RG', 'RT'): return 1
    if pos == 'DT': return 2
    if pos in ('LEDG', 'REDG'): return 1
    if pos == 'MIKE': return 1
    if pos == 'WILL': return 1 if pk.get('LB', 2) >= 2 else 0
    if pos == 'SAM': return 1 if pk.get('LB', 2) >= 3 else 0
    if pos == 'CB': return pk.get('CB', 3)
    if pos in ('FS', 'SS'): return 1
    return 1


def depth(session, league, abbr, package='Nickel'):
    t = league.teams[abbr]; d = t.depth
    pk = PACKAGES.get(package, PACKAGES['Nickel'])
    desk = (session.runner.desks.get(abbr) if getattr(session, 'runner', None) is not None else None)
    status = getattr(desk, 'status', {}) if desk is not None else {}
    # the linebackers this package fields, and why
    import targets as TG
    lbs = [p for pos_ in ('MIKE', 'WILL', 'SAM') for p in d.get(pos_, []) if p.out_until is None]
    pkg_key = package.lower().replace(' ', '_')
    lb_choice = {p.pid: why for p, why in TG.package_linebackers(lbs, pkg_key, scheme=getattr(t, 'scheme', None), key=lambda q: q.ratings)}
    sides = {}
    for side, cols_ in SIDES.items():
        cols = []
        for pos, label, group in cols_:
            men = d.get(pos, []); n_start = _starters(pos, pk); slots = []
            for i, p in enumerate(men):
                pl = player_plate(p); pl['cond'] = _cond(session, p)
                if pos in ('MIKE', 'WILL', 'SAM'): pl['start'] = p.pid in lb_choice; pl['why'] = lb_choice.get(p.pid, '')
                else: pl['start'] = i < n_start; pl['why'] = ''
                pl['slot'] = _slot_label(pos, i)
                desig = status.get(p.pid)
                pl['flag'] = 'out' if p.out_until is not None else (desig if desig in ('questionable', 'doubtful') else None)
                pl['flag_word'] = ('Out' if pl['flag'] == 'out' else pl['flag'].capitalize() if pl['flag'] else '')
                pl['fit'] = round(_fit(league, t, p), 1)
                slots.append(pl)
            cols.append(dict(pos=pos, title=label, group=group, slots=slots, on_field=n_start))
        sides[side] = cols
    return dict(rail=rail(session, league, abbr), package=package, packages=list(PACKAGES), sides=sides, pins=getattr(t, 'depth_pins', None) or {})


# ------------------------------------------------------------ actions
def _slot_label(pos, i):
    """The real slot names: X / Z / SL for receivers, 1 / 2 / NI for corners, numbers elsewhere."""
    if pos == 'WR': return ['X', 'Z', 'SL'][i] if i < 3 else str(i + 1)
    if pos == 'CB': return ['1', '2', 'NI'][i] if i < 3 else str(i + 1)
    return str(i + 1)


def act_set_depth(league, abbr, pos, pids):
    t = league.teams[abbr]; order = t.set_depth_order(pos, list(pids))
    return dict(ok=True, pos=pos, order=order)


def act_fill_by_fit(league, abbr):
    """Order every position the way the engine grades men AT THAT SPOT in the club's scheme (position_score), and pin it."""
    import targets as TG
    t = league.teams[abbr]; t.depth_pins = {}
    for pos, men in t.depth.items():
        scored = sorted(men, key=lambda p: -float(TG.position_score(p.ratings, pos, t.scheme)))
        t.depth_pins[pos] = [p.pid for p in scored]
    return dict(ok=True, line='Ordered by fit at each spot.')


def act_reset_depth(league, abbr, pos=None):
    t = league.teams[abbr]
    if pos: (getattr(t, 'depth_pins', None) or {}).pop(pos, None)
    else: t.depth_pins = {}
    return dict(ok=True)


def act_cut(league, abbr, pid):
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    pen = round(p.dead_if_cut(0), 1)
    league.release(pid)
    return dict(ok=True, name=p.name, penalty=pen)


def act_position_change(league, abbr, pid, new_pos):
    import position_change as PC
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    tr = PC.change_position(league, pid, new_pos)
    if tr is None: return dict(ok=False, why='that move is not one he can make')
    return dict(ok=True, name=p.name, to=new_pos, penalty=tr['penalty'], games=tr['games_left'])


def act_call_up(league, abbr, pid):
    import practice_squad as PSQ
    p = league.player(pid); ok = bool(PSQ.call_up(league, abbr, pid))
    return dict(ok=ok, name=p.name if p else pid, why=None if ok else 'he is not on your practice squad')


def act_elevate(league, abbr, pids, week):
    import practice_squad as PSQ
    t = league.teams[abbr]; already = len(getattr(t, '_elevated', []) or [])
    if already + len(pids) > PSQ.ELEVATIONS_PER_GAME: return dict(ok=False, why=f'only {PSQ.ELEVATIONS_PER_GAME} elevations a game')
    out = PSQ.elevate(league, abbr, list(pids), week)
    return dict(ok=bool(out), moves=[dict(name=league.player(pid).name, how=how) for pid, how in out], why=None if out else 'nobody eligible')


def act_release_ps(league, abbr, pid):
    import practice_squad as PSQ
    p = league.player(pid); PSQ.release_from_squad(league, abbr, pid)
    return dict(ok=True, name=p.name if p else pid)
