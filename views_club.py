from inbox import player_name as inbox_player
from player_background import home_state
from stable import stable_seed
"""
CLUB VIEWS. What the Roster, Player Card, Depth Chart and Practice Squad pages
show, as plain dicts, and the actions their buttons call.
"""
from views import jersey
import numpy as np
from views import club, money, morale_word, player_plate, rail, transaction_when

GROUPS = [('QB', ['QB']), ('HB', ['HB']), ('FB', ['FB']), ('WR', ['WR']), ('TE', ['TE']), ('LT', ['LT']), ('LG', ['LG']), ('C', ['C']), ('RG', ['RG']), ('RT', ['RT']),
          ('LEDG', ['LEDG']), ('DT', ['DT']), ('REDG', ['REDG']), ('MIKE', ['MIKE']), ('WILL', ['WILL']), ('SAM', ['SAM']), ('CB', ['CB']), ('FS', ['FS']), ('SS', ['SS']),
          ('K', ['K']), ('P', ['P']), ('LS', ['LS'])]
OFFENSE = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
# the development tiers by the names the game shows: Normal, Rare, Epic, Legendary
DEV_WORD = {'xfactor': 'Legendary', 'superstar': 'Epic', 'star': 'Rare', 'normal': 'Normal', 'slow': 'Slow'}


def ceiling_read(p):
    """The same scouting estimate everywhere, including room and paid unlocks."""
    estimate = getattr(p, 'potential_range', None)
    if estimate:
        unlocks = int((p.xp_spent or {}).get('_unlocks', 0))
        lo, hi = (min(99, int(v) + unlocks) for v in estimate)
        overall = int(round(p.ovr))
        return dict(ceiling=f'{lo}–{hi}', room=f'{max(0, lo-overall)}–{max(0, hi-overall)}', ceiling_estimated=True)
    pot = getattr(p, 'potential', None)
    return dict(ceiling=round(pot) if pot is not None else None,
                room=max(0, round(pot)-round(p.ovr)) if pot is not None else None, ceiling_estimated=False)
DEV_KEY = {'Legendary': 'xfactor', 'Epic': 'superstar', 'Rare': 'star', 'Normal': 'normal', 'Slow': 'slow'}

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
    if p.out_until is not None: out.append('Out · season' if int(p.out_until) >= 99 else f"Out · back Wk {int(p.out_until) + 1}")
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


def _cut_penalty(league, p):
    now, later, _ = p.contract.release(0, league.post_june1()) if p.contract else (0, 0, 0)
    return dict(penalty=round(now, 1), penalty_next=round(later, 1))


def _cut_penalty_line(penalty):
    return (f"Penalty ${penalty['penalty']:.1f}m this year"
            + (f" and ${penalty['penalty_next']:.1f}m next year" if penalty['penalty_next'] else '') + '.')


def _row(session, league, t, p):
    yrs = p.contract.years if p.contract else 0
    return dict(pid=p.pid, no=jersey(p), name=p.name, pos=p.pos, side=('offense' if p.pos in OFFENSE else 'special' if p.pos in ('K', 'P', 'LS') else 'defense'), age=int(p.age), ovr=round(p.ovr), fit=round(_fit(league, t, p), 1),
                dev=DEV_WORD.get(str(getattr(p, 'dev', 'normal')).lower(), 'Normal'), cond=_cond(session, p), morale=morale_word(p), yrs=yrs,
                hit=round(p.cap_hit(0), 1), **_cut_penalty(league, p), status=_status(league, p, t),
                home_state=home_state(p), season_no=max(1, league.year - (getattr(p, 'entry_year', None) or getattr(p, 'draft_year', None)) + 1) if (getattr(p, 'entry_year', None) or getattr(p, 'draft_year', None)) else None,
                # ratings view
                pot=(ceiling_read(p)['ceiling'] if not p.potential_range else None), pot_range=([min(99, int(v) + int(p.xp_spent.get('_unlocks', 0))) for v in p.potential_range] if p.potential_range else None),
                # stats view: the season line
                stats=_season_line(league, p))


def salaries(session, league, abbr):
    """Contract ledger, using the same charges and release math as transactions."""
    from cap_engine import CAP
    from cap_accounting import pre_roll, next_year_ledger
    t = league.teams[abbr]
    t.sync_cap()
    offset = int(pre_roll(league))
    horizon = max(5, max((p.contract.years + 1 - offset for p in t.roster if p.contract), default=5))
    indices = list(range(offset, offset + horizon))
    rows = []
    for p in t.roster:
        c = p.contract
        if c is None: continue
        annual = []
        for i in indices:
            if i < c.years:
                dead, later, savings = c.release(i, league.post_june1() if i == 0 else True)
                annual.append(dict(base=float(c.base[i]), roster_bonus=float(c.rb[i]), bonus=float(c.bonus_at(i)),
                                   hit=float(c.cap_hit(i)), dead=dead, dead_next=later, savings=savings, void=False))
            elif i == c.years and c.remaining_proration(i):
                # At expiry all remaining void-year bonus accelerates into one charge.
                annual.append(dict(base=0., roster_bonus=0., bonus=float(c.remaining_proration(i)),
                                   hit=float(c.remaining_proration(i)), dead=None, dead_next=None, savings=None, void=True))
            else: annual.append(None)
        tags = []
        if getattr(c, 'rookie', False): tags.append('Rookie Deal')
        if getattr(p, 'fa_class', None) == 'tagged': tags.append('Franchise Tag')
        if c.years - offset == 1: tags.append('Final Year')
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr),
                         left=max(0, c.years-offset), status=' · '.join(tags), annual=annual,
                         unit='OFF' if p.pos in OFFENSE else 'ST' if p.pos in ('K', 'P', 'LS') else 'DEF'))
    years = []
    for j, i in enumerate(indices):
        year = league.year + i
        players = sum(r['annual'][j]['hit'] for r in rows if r['annual'][j])
        dead = float((getattr(t, 'dead_money', {}) or {}).get(year, 0.))
        limit = float(CAP.get(year, t.cap.cap * 1.055 ** i))
        committed = players + dead
        if i == 0:
            limit, committed, dead = t.cap.limit, t.cap.charges(t.phase), t.cap.dead
        elif i == 1:
            limit, committed, _, dead = next_year_ledger(league, t)
            # Expiry acceleration is already shown on the player's row.
            dead -= sum(r['annual'][j]['hit'] for r in rows if r['annual'][j] and r['annual'][j]['void'])
        years.append(dict(year=year, projected=i > 0, players=players, dead=dead,
                          adjustments=committed-players-dead, committed=committed, limit=limit, space=limit-committed))
    return dict(rail=rail(session, league, abbr), club_abbr=abbr, mine=abbr == session.user_team, rows=rows, years=years)


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
                comp=None, epa=m.get('def_epa_per_play'), epa_note=AS.DEF_EPA_NOTE,
                cols=(['Tkl', 'Sacks', 'Pressures', 'Pass Rush Win%', 'FF', AS.DEF_EPA_LABEL] if front else ['Tkl', 'INT', 'PD', 'FF', 'Sacks', AS.DEF_EPA_LABEL]),
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
    return dict(rail=rail(session, league, abbr), groups=groups, count=len(t.active()), cap_total=__import__('views').cap_focus(league,t)['committed'],
                practice=ps, injured=injured, ps_charge=round(PSQ.ps_charge(t), 1), elevations_used=len(getattr(t, '_elevated', []) or []), elevations_max=PSQ.ELEVATIONS_PER_GAME, per_man_max=PSQ.ELEVATIONS_PER_MAN, playoff_elevations=session.stop[0] == 'playoffs',
                ir=[dict(_row(session, league, t, p), ir_week=int(p.xp_spent.get('_ir_week', 0) or 0), returnable=bool(p.xp_spent.get('_ir_return', False)), can_activate=bool(t.activate_from_ir.__doc__) and (league.week or 0) - int(p.xp_spent.get('_ir_week', 0) or 0) >= t.IR_MIN_WEEKS and (p.out_until is None or int(p.out_until) <= (league.week or 0)) and bool(p.xp_spent.get('_ir_return', False))) for p in (getattr(t, 'ir', None) or [])],
                ir_returns_left=t.IR_RETURNS - int(getattr(t, 'ir_returns_used', 0) or 0), week=league.week)


# ------------------------------------------------------------ the card

def attr_cols(p, shift=None, shift_name=None, delta=None):
    """The card's attribute block: three columns (physical, the position's skill group, mental) with the special-teams
    and run-defense extras where they apply. shift marks the user's scheme; delta (key -> points) marks what age
    took, for the Regression page's popup."""
    shift = shift or {}; shift_name = shift_name or {}; delta = delta or {}
    fam = FAM.get(p.pos, 'DB')
    def col(keys):
        out = []
        for k, lab in keys:
            v = p.ratings.get(k)
            if v is None: continue
            row = dict(key=k, label=lab, v=int(round(float(v))), tier=('hi' if v >= 85 else 'md' if v >= 72 else 'lo'), shift=shift.get(k), scheme=shift_name.get(k))
            if k in delta: row['delta'] = int(delta[k])
            out.append(row)
        return out
    phys = dict(title='Physical', rows=col(ATTR['phys']), extra=(dict(title='Special Teams', rows=col(ATTR['st'])) if p.pos in ('WR', 'HB', 'CB', 'FS', 'SS') and col(ATTR['st']) else None))
    if fam == 'DB': skill = dict(title='Coverage', rows=col(ATTR['coverage']), extra=dict(title='Run Defense', rows=col(ATTR['rundef'])))
    elif fam in ('LB', 'DL'): skill = dict(title=SKILL_TITLE.get(fam, 'Skill'), rows=col([k for k in ATTR[fam] if k[0] not in ('tackle_rating', 'hit_power_rating', 'pursuit_rating', 'block_shed_rating')]), extra=dict(title='Run Defense', rows=col(ATTR['rundef'])))
    else: skill = dict(title=SKILL_TITLE.get(fam, 'Skill'), rows=col(ATTR.get(fam, ATTR['DB'])), extra=None)
    return [phys, skill, dict(title='Mental', rows=col(ATTR['mental']), extra=None)]


def card(session, league, pid):
    p = league.player(pid)
    if p is None: return dict(error='no such player')
    t = league.teams.get(p.team) if p.team else None
    user = league.teams[session.user_team]
    # Free agents are evaluated for the viewing club, just like the FA list.
    fit_team = user if t is None or p.pid in league.free_agents else t
    fit = _fit(league, fit_team, p)
    fam = FAM.get(p.pos, 'DB')
    import targets as TG, position_change as PC
    # the shift the user's scheme puts on each attribute, from the scheme's weights at his spot
    # which way your scheme leans on each attribute, tagged with the name of the archetype that asks for it
    shift = {}; shift_name = {}
    try:
        import views_frontoffice as VF, identity_catalog as IC
        ident = VF.club_identity(league, user)
        names = {'offence': IC.ARCHETYPES[ident['offence']]['name'], 'defence': IC.ARCHETYPES[ident['defence']]['name']}
        schemes = getattr(user, 'scheme', None) or {}
        keys = list(schemes.values()) if isinstance(schemes, dict) else ([schemes] if isinstance(schemes, str) else list(schemes))
        for s in keys:
            if p.pos not in TG.SCHEME_DOMAIN.get(s, ()): continue
            for k, v in TG.SCHEME_SHIFT.get(s, {}).items():
                if k in p.ratings and k in TG.DEPTH_WEIGHTS.get(p.pos, {}):
                    shift[k] = shift.get(k, 0.0) + float(v); shift_name[k] = names[TG.SCHEME_SIDE.get(s, 'offence')]
        shift = {k: (1 if v > 0 else -1) for k, v in shift.items() if abs(v) > 1e-9}
    except Exception: pass
    cols = attr_cols(p, shift, shift_name)
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
            try: years.append(dict(year=league.year + i, base=round(c.base[i] + c.rb[i], 1), bonus=round(c.bonus_at(i), 1), hit=round(c.cap_hit(i), 1), penalty=round(c.release(i, league.post_june1())[0], 1), penalty_next=round(c.release(i, league.post_june1())[1], 1)))
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
    market_apy = None; market_quote = None; ext_ask = None
    try:
        import valuation as VAL
        # Pin the comp window so revisiting a card does not redraw its market.
        market_quote = VAL.value_player(league, p, side='team')
        market_apy = round(float(market_quote['apy']), 1) if market_quote and market_quote.get('apy') else None
    except Exception: pass
    try:
        import extensions as EXT
        if _ext_ok(league, p):
            tm = EXT.terms(league, p, np.random.default_rng(stable_seed(p.pid))); ext_ask = round(float(tm['ask']), 1) if tm else None
    except Exception: pass
    # The card's pick range must use the same player/pick prices as Trades.
    interest, market = _market_words(league, p, market_quote)
    S = league.stats.get(league.year, {}).get(p.pid, {}) or {}
    m = getattr(p, 'morale', None)
    # trade value in the scout's words: what the market would pay, and who has asked
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
    h = getattr(p, 'height', None); size = (f"{int(h) // 12}'{int(h) % 12}\" {getattr(p, 'weight', '') or ''}".strip() if h else '')
    drafted = (f"drafted {p.draft_overall}{_ordn(p.draft_overall)} overall, {p.draft_year}" if getattr(p, 'draft_overall', None) else f"drafted round {p.draft_round}, {p.draft_year}" if getattr(p, 'draft_round', None) else 'undrafted')
    if p.team is None:
        # A FREE AGENT HAS NO CLUB'S NUMBERS: no contract, no cap hit, no penalty, no trade interest, nothing on the
        # Contract tab but the market's read of him. A player on the wire still carries his deal for the claiming
        # club, and the card says so.
        years = []; interest = ''; interest_line = ''
        asks = []
    return dict(rail=rail(session, league, session.user_team), pid=p.pid, no=jersey(p), name=p.name, pos=p.pos, age=int(p.age), size=size,
                birth_date=getattr(p, 'birth_date', None), game_date=getattr(league, 'game_date', None),
                team=club(p.team) if p.team else None, home_state=home_state(p), draft=drafted,
                role=role, snaps=snaps, missed=missed, pending=pending, market_apy=market_apy, ext_ask=ext_ask, ext_eligible=_ext_ok(league, p),
                rookie_option=(__import__('extensions').rookie_option_price(league, p) if p.team == session.user_team else None),
                contract_caption=('On the wire; a claiming club inherits his deal' if (p.team is None and p.contract) else 'Free agent; no contract' if p.team is None else (f"Contract signed {getattr(p.contract, 'signed', league.year)} · {p.contract.years + (len(getattr(p.contract, 'base', [])) - p.contract.years if hasattr(p.contract, 'base') else 0)} yrs · ${round(sum(getattr(p.contract, 'base', [])) + getattr(p.contract, 'sb', 0), 1)}m" if p.contract else 'No contract')),
                season_no=max(1, league.year - (getattr(p, 'entry_year', None) or getattr(p, 'draft_year', None)) + 1) if (getattr(p, 'entry_year', None) or getattr(p, 'draft_year', None)) else None,
                ovr=round(p.ovr), fit=round(fit, 1), ceiling=ceiling_read(p)['ceiling'] if ceiling_read(p)['ceiling'] is not None else '—',
                dev=DEV_WORD.get(str(getattr(p, 'dev', 'normal')).lower(), 'Normal'), morale=morale_word(p), morale_v=round(m.value) if m is not None else None,
                contract=(dict(per_year=0.0, years=0, hit=0.0, penalty=0.0, penalty_next=0.0, by_year=[]) if p.team is None else dict(per_year=round(p.apy, 1) if p.contract else 0.0, years=p.contract.years if p.contract else 0, hit=round(p.cap_hit(0), 1), **_cut_penalty(league, p), by_year=years)),
                free_agent=(p.team is None), on_wire=bool(p.team is None and p.contract is not None),
                interest=interest, cols=cols, grades=grades, personality=words, status=_status(league, p, t) if t else '',
                schemes=scheme_rows(p.ratings, p.pos, _club_arch(league, getattr(session, 'user_team', None), p.pos)),
                cond=_cond(session, p), out=p.out_until, season=cur, games=int(S.get('games', 0) or 0), seasons=seasons,
                market=market, interest_line=interest_line, dev_line=dev_line, morale_line=_morale_line(p),
                history=_player_history(league, p),
                actions=dict(mine=(p.team == session.user_team), extend_eligible=_ext_ok(league, p), can_cut=(p.team == session.user_team),
                             ps_ok=(p.team == session.user_team and t is not None and __import__('practice_squad').can_add(t, p)), vested=(int(p.accrued or 0) >= 4),
                             hurt=(p.out_until is not None), on_ir=(t is not None and any(q.pid == p.pid for q in (getattr(t, 'ir', None) or [])))))


def _market_words(league, p, quote):
    """A scout-sized summary of the same dollar prices the trade engine uses."""
    if not quote or not quote.get('apy') or not p.contract:
        return '—', 'No trade market read available.'
    import trade_engine as TE
    cap = float(getattr(getattr(league.teams.get(p.team), 'cap', None), 'cap', TE.CAP))
    row = dict(age=p.age, apy=p.apy, ovr=p.ovr,
               contract_years_left=p.contract_years_left, madden_position=p.pos)
    value = TE.trade_value(row, quote, cap=cap)
    first = TE.pick_price_dollars(16, cap=cap)
    late_first = TE.pick_price_dollars(32, cap=cap)
    second = TE.pick_price_dollars(48, cap=cap)
    third = TE.pick_price_dollars(80, cap=cap)
    if value >= 2 * first:
        label, price = 'Multiple 1sts', 'A package built around multiple first-round picks is the range.'
    elif value >= first:
        label, price = '1st +', 'A first-round pick plus another asset is the range.'
    elif value >= late_first:
        label, price = '1st', 'A first-round pick is in range.'
    elif value >= second:
        label, price = '2nd', 'A second-round pick is in range.'
    elif value >= third:
        label, price = '3rd', 'A third-round pick is in range.'
    elif value > 0:
        label, price = 'Late pick', 'A later pick or a depth swap is the range.'
    else:
        label, price = 'Salary offset', 'His contract may need a salary offset to move.'
    role = 'an elite starter' if p.ovr >= 88 else 'a starter' if p.ovr >= 78 else 'a rotation piece' if p.ovr >= 72 else 'a depth player'
    age = int(p.age)
    stage = 'still coming' if age < 25 else 'in his prime' if age <= 29 else 'on the back half' if age <= 32 else 'near the end'
    ratio = p.apy / max(float(quote['apy']), 0.1)
    deal = 'on a favorable deal' if ratio < 0.80 else 'on a market-level deal' if ratio <= 1.15 else 'on a costly deal'
    return label, f"{role.capitalize()} {stage} {deal}. {price}"


def _morale_line(p):
    m = getattr(p, 'morale', None)
    if m is None: return 'Steady'
    reasons = getattr(m, 'reasons', None) or getattr(m, 'notes', None) or []
    if reasons: return str(reasons[-1])[:60]
    return 'Steady since camp'


def _regression_overalls(record):
    """The report and history show only a drop in the displayed whole OVR."""
    if record.get('before') is None or record.get('after') is None:
        return None
    before, after = int(round(record['before'])), int(round(record['after']))
    return (before, after) if after < before else None


def _player_history(league, p):
    """Dated moves, XP purchases, regression, and awards for this player."""
    import views_league as VL
    entries = []
    def add(year, order, when, line):
        entries.append((int(year or 0), order, len(entries), dict(when=when, line=line)))
    if getattr(p, 'draft_year', None) and getattr(p, 'draft_round', None):
        add(p.draft_year, -1, str(p.draft_year), f"Drafted {p.draft_overall}{_ordn(p.draft_overall)} overall (round {p.draft_round})" if getattr(p, 'draft_overall', None) else f"Drafted, round {p.draft_round}")
    for x in league.transactions:
        if x.get('kind') == 'dev_trait' and x.get('pid') == p.pid:
            year = x.get('year') or 0
            after = DEV_WORD.get(x.get('dev'), x.get('dev', 'Unknown'))
            before = DEV_WORD.get(x.get('previous_dev'), x.get('previous_dev'))
            outcome = 'upgraded' if x.get('change') == 'up' else 'downgraded'
            line = f"Development {outcome}: " + (f"{before} → {after}" if before else after)
            if x.get('reason'): line += f" · {x['reason']}"
            add(year, 23, f"{year} · Offseason", line)
            continue
        if x.get('kind') == 'regress' and x.get('pid') == p.pid:
            year = x.get('year') or 0
            # Older saves only logged total OVR loss. Use a saved report when
            # available, never reconstruct historical ratings from today's card.
            report = (getattr(league, 'regression', None) or {}).get(str(year), {}).get(p.pid, {})
            # The saved report is the Regression tab's source of truth. CPU
            # players also carry the same before/after snapshots on their event.
            before, after = report.get('before', x.get('before')), report.get('after', x.get('after'))
            if _regression_overalls(dict(before=before, after=after)) is None:
                continue
            line = f"Regression: -{float(x.get('lost', 0)):g} OVR"
            if before is not None and after is not None:
                line += f" ({float(before):g} → {float(after):g})"
            for attr, (b, a) in (x.get('attrs', report.get('attrs', {})) or {}).items():
                delta = round(float(a) - float(b), 1)
                if delta:
                    label = attr.replace('_rating', '').replace('_', ' ').title()
                    line += f" · {label} {delta:+g}"
            add(year, 24, f"{year} · Offseason", line)
            continue
        if x.get('kind') not in VL.TAGS: continue
        if x.get('kind') == 'draft' and getattr(p, 'draft_year', None) and getattr(p, 'draft_round', None): continue
        named = x.get('pid') == p.pid or p.pid in [str(a) for a in (x.get('a_sends') or [])] or p.pid in [str(a) for a in (x.get('b_sends') or [])]
        if not named: continue
        year = x.get('year') or 0; week = x.get('week') or 0
        when = transaction_when(x)
        add(year, int(week) if week else 22, when, VL._tx_line(league, x))

    spent = getattr(p, 'xp_spent', None) or {}
    purchases = spent.get('_purchases') or []
    logged = {}; logged_unlocks = 0
    for purchase in purchases:
        kind = purchase.get('kind'); attr = purchase.get('attr')
        if kind == 'buy' and attr: logged[attr] = logged.get(attr, 0) + 1
        elif kind == 'unlock': logged_unlocks += 1
        else: continue
        year = purchase.get('year') or p.draft_year or 0
        week = purchase.get('week') or 0
        when = transaction_when(purchase) if week else str(year) if purchase.get('year') else 'Earlier XP'
        what = 'Ceiling' if kind == 'unlock' else attr.replace('_rating', '').replace('_', ' ').title()
        cost = purchase.get('cost')
        source = purchase.get('source')
        line = f"Progression: +1 {what}" + (f" · {int(round(cost)):,} XP" if cost is not None else '') + (f" · {source}" if source else '')
        add(year, int(week) if week else 22, when, line)
    # Older saves retain lifetime purchase counts, but not the dates or XP prices.
    for attr, count in spent.items():
        if attr.startswith('_') or not isinstance(count, (int, float)): continue
        earlier = max(0, int(count) - logged.get(attr, 0))
        if earlier:
            what = attr.replace('_rating', '').replace('_', ' ').title()
            add(p.draft_year or 0, 0, 'Earlier XP', f"Progression: +{earlier} {what} · before purchase history")
    earlier_unlocks = max(0, int(spent.get('_unlocks', 0) or 0) - logged_unlocks)
    if earlier_unlocks: add(p.draft_year or 0, 0, 'Earlier XP', f"Progression: +{earlier_unlocks} Ceiling · before purchase history")

    award_names = dict(VL.AWARD_NAMES, sb_mvp='CHAMP MVP', all_pro_1='First-Team All-Pro', all_pro_2='Second-Team All-Pro', pro_bowl='Pro Bowl')
    for year, awards in (getattr(league, 'awards', None) or {}).items():
        for key, winners in (awards or {}).items():
            if key == 'coty': continue
            winners = winners if isinstance(winners, list) else [winners]
            if p.pid in [str(w) for w in winners]:
                add(year, 23, f"{year} · Awards", f"Award: {award_names.get(key, key.replace('_', ' ').title())}")
    return [row for _, _, _, row in sorted(entries, key=lambda e: e[:3])]


def _ordn(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def _ext_ok(league, p):
    import extensions as EXT
    try: return bool(EXT.eligible(p, league))
    except Exception: return False


# ------------------------------------------------------------ the depth chart
import offense_roles as OR
OFF_BASE = OR.PACKAGES
PACKAGES = {'Base': dict(WR=2, TE=2, HB=1, LB=3, CB=2, S=2), 'Nickel': dict(WR=3, TE=1, HB=1, LB=2, CB=3, S=2), 'Dime': dict(WR=3, TE=1, HB=1, LB=1, CB=4, S=2),
            'Goal Line': dict(WR=1, TE=2, HB=1, FB=1, DT=3, LB=3, CB=2, S=1), 'Third Down': dict(WR=3, TE=1, HB=1, LB=2, CB=3, S=2), 'Two Minute': dict(WR=4, TE=1, HB=1, LB=1, CB=4, S=2)}
# one column a position, grouped by side; the heading is the position, the group is the caption
SIDES = {
    'offense': [('QB', 'QB', 'Quarterback'), ('HB', 'HB', 'Backs'), ('FB', 'FB', 'Backs'), ('WR', 'WR', 'Receivers'), ('TE', 'TE', 'Tight Ends'),
                ('LT', 'LT', 'Line'), ('LG', 'LG', 'Line'), ('C', 'C', 'Line'), ('RG', 'RG', 'Line'), ('RT', 'RT', 'Line')],
    'defense': [('LEDG', 'LEDG', 'Front'), ('DT', 'DT', 'Front'), ('REDG', 'REDG', 'Front'), ('MIKE', 'MIKE', 'Linebackers'), ('WILL', 'WILL', 'Linebackers'), ('SAM', 'SAM', 'Linebackers'),
                ('CB', 'CB', 'Secondary'), ('FS', 'FS', 'Secondary'), ('SS', 'SS', 'Secondary')],
    'specialists': [('K', 'K', 'Specialists'), ('P', 'P', 'Specialists'), ('LS', 'LS', 'Specialists'), ('KR', 'KR', 'Returners'), ('PR', 'PR', 'Returners')],
}
SIDES_OFF_POS = {pos for pos, _, _ in SIDES['offense']}
# how many start at each position, by package
def _starters(pos, pk):
    if pos == 'QB': return 1
    if pos == 'HB': return pk.get('HB', 1)
    if pos == 'FB': return pk.get('FB', 0)
    if pos == 'WR': return pk.get('WR', 3)
    if pos == 'TE': return pk.get('TE', 1)
    if pos in ('LT', 'LG', 'C', 'RG', 'RT'): return 1
    if pos == 'DT': return pk.get('DT', 2)
    if pos in ('LEDG', 'REDG'): return 1
    if pos == 'MIKE': return 1
    if pos == 'WILL': return 1 if pk.get('LB', 2) >= 2 else 0
    if pos == 'SAM': return 1 if pk.get('LB', 2) >= 3 else 0
    if pos == 'CB': return pk.get('CB', 3)
    if pos == 'FS': return 1
    if pos == 'SS': return 1 if pk.get('S', 2) >= 2 else 0
    return 1


def depth(session, league, abbr, package='Base', front_override=None, offense_package=None):
    t = league.teams[abbr]; d = t.depth
    import defense_roles as DR
    front = DR.coach_front(t.gm)
    if getattr(t.gm, 'def_front', '4-3') == 'multiple' and front_override in ('4-3', '3-4'):
        front = front_override
    pk = PACKAGES.get(package, PACKAGES['Nickel'])
    desk = (session.runner.desks.get(abbr) if getattr(session, 'runner', None) is not None else None)
    status = getattr(desk, 'status', {}) if desk is not None else {}
    # the linebackers this package fields, and why
    import targets as TG
    pins = getattr(t, 'depth_pins', None) or {}
    def_depth = {}
    for canonical, men in d.items():
        ranked = sorted(men, key=lambda p: -TG.position_score(p.ratings, canonical, t.scheme))
        order = {pid: i for i, pid in enumerate(pins.get(canonical, []))}
        if order: ranked.sort(key=lambda p: order.get(p.pid, 10**6))
        def_depth[canonical] = ranked
    unavailable = {p.pid for men in d.values() for p in men
                   if not (desk.available(p, league.week) if desk else p.out_until is None)}
    state = session.runner.states.get(abbr) if getattr(session, 'runner', None) is not None else None
    unavailable.update(getattr(state, 'out', ()) or ())
    available_depth = DR.available_depth(def_depth, unavailable)
    lbs = [p for pos_ in ('MIKE', 'WILL', 'SAM') for p in available_depth.get(pos_, [])]
    pkg_key = package.lower().replace(' ', '_')
    lb_choice = {p.pid: why for p, why in TG.package_linebackers(lbs, pkg_key, scheme=getattr(t, 'scheme', None), key=lambda q: q.ratings)}
    import rosters as RO
    pins = getattr(t, 'depth_pins', None) or {}
    def returners(slot):
        candidates = [p for p in t.active() if p.pos in RO.RETURN_POS
                      and p.pid not in unavailable]
        return RO.return_order(candidates, pins, slot, off_depth)[:5]
    off_depth = {}
    for canonical, men in d.items():
        if canonical not in SIDES_OFF_POS:
            continue
        ranked = sorted(men, key=lambda p: -TG.position_score(p.ratings, canonical, t.scheme))
        order = {pid: i for i, pid in enumerate(pins.get(canonical, []))}
        if order:
            ranked.sort(key=lambda p: order.get(p.pid, 10**6))
        off_depth[canonical] = ranked
    off_package = offense_package if offense_package in OR.PACKAGES else OR.base_package(t.gm)
    off_rows = OR.assign(off_depth, off_package)
    off_starters = {p.pid for role, p in off_rows}
    sides = {}
    for side, cols_ in SIDES.items():
        cols = []
        if side == 'defense':
            assigned = DR.assign(available_depth, front, package, pins)
            roles = {}
            for row in assigned:
                role = row['role']
                if role not in roles:
                    roles[role] = dict(group={'dl': 'Front', 'lb': 'Linebackers', 'db': 'Secondary'}[row['group']],
                                       starters=[], reserves=row['reserves'])
                if row['player'] is not None:
                    roles[role]['starters'].append(row['player'])
            cols_ = [({'LE': 'LEDG', 'RE': 'REDG'}.get(role, role) if front == '4-3' else role,
                      DR.role_label(role, front), info['group'],
                      info['starters'] + info['reserves'] +
                      [p for p in DR.role_candidates(def_depth, role, pins) if p.pid in unavailable],
                      len(info['starters']))
                     for role, info in roles.items()]
        else:
            cols_ = [(pos, label, group, None, None) for pos, label, group in cols_]
        for pos, label, group, role_men, role_starters in cols_:
            # Offensive highlights use the selected package; the coach's base remains unchanged.
            men = role_men if role_men is not None else returners(pos) if pos in ('KR', 'PR') else off_depth.get(pos, []) if side == 'offense' else def_depth.get(pos, [])
            n_start = role_starters if role_starters is not None else 1 if pos in ('KR', 'PR') else _starters(pos, pk if side == 'defense' else OFF_BASE.get(getattr(t.gm, 'off_personnel', '11'), OFF_BASE['11']))
            if side == 'offense': n_start = sum(p.pid in off_starters for p in men)
            slots = []
            for i, p in enumerate(men):
                pl = player_plate(p); pl['cond'] = _cond(session, p)
                if side == 'offense': pl['start'] = p.pid in off_starters; pl['why'] = ''
                elif side == 'defense': pl['start'] = i < n_start; pl['why'] = lb_choice.get(p.pid, '')
                else: pl['start'] = i < n_start; pl['why'] = ''
                pl['slot'] = _slot_label(pos, i)
                desig = status.get(p.pid)
                # the week's listing comes first: a Questionable or Doubtful man reads as listed (with the decision if it is
                # yours), a man out longer reads Out with the weeks, a healthy man reads nothing
                pending = bool(desk is not None and p.pid in getattr(desk, 'pending', {}))
                hurt_now = (getattr(desk, 'playing_hurt', {}) or {}).get(p.pid) if desk is not None else None
                if desig in ('questionable', 'doubtful') and (pending or hurt_now or p.out_until is not None): pl['flag'] = desig
                elif p.out_until is not None: pl['flag'] = 'out'
                else: pl['flag'] = None
                weeks_left = (max(1, int(p.out_until) - int(league.week or 0) + 1) if p.out_until is not None and int(p.out_until) < 99 else None)   # out_until is the last week he misses; this week counts
                pl['flag_word'] = (('Out · season' if p.out_until is not None and int(p.out_until) >= 99 else f"Out · {weeks_left} wk{'s' if weeks_left != 1 else ''}" if weeks_left else 'Out') if pl['flag'] == 'out' else pl['flag'].capitalize() if pl['flag'] else '')
                pl['elevated'] = p not in t.roster
                pl['out_week'] = weeks_left
                pl['pending'] = pending
                pl['playing_hurt'] = hurt_now
                if pl['pending'] or (pl['flag'] in ('questionable', 'doubtful')):
                    try:
                        import injury_status as IS; pl['hurt_words'] = IS.hurt_words(league, t, p, desig)
                    except Exception: pl['hurt_words'] = None
                if pl['flag'] in ('questionable', 'doubtful') and not pending and hurt_now is None: pl['flag_word'] = pl['flag'].capitalize() + ' · sits'
                if hurt_now: pl['flag_word'] = ''
                pl['fit'] = round(_fit(league, t, p), 1)
                if pos in ('KR', 'PR'): pl['sub'] = f"{p.pos} · return {round(RO.return_score(p))}"
                slots.append(pl)
            cols.append(dict(pos=pos, title=(DR.role_label(pos, front) if side == 'defense' else label), group=group, slots=slots, on_field=n_start))
        sides[side] = cols
    return dict(rail=rail(session, league, abbr), package=package, packages=list(PACKAGES), sides=sides, pins=getattr(t, 'depth_pins', None) or {},
                offense_package=off_package, offense_base=OR.base_package(t.gm), offense_packages=list(OR.PACKAGES),
                front=front, coach_front=getattr(t.gm, 'def_front', '4-3'),
                available_fronts=(['4-3', '3-4'] if getattr(t.gm, 'def_front', '4-3') == 'multiple' else []),
                defense_shape=DR.shape_label(front, package),
                assistant=(None if front == '3-4' else _package_line(package, lbs, lb_choice, pk)))


def _package_line(package, lbs, lb_choice, pk):
    """One sentence from the assistants on the sub package's call: who plays at linebacker and why."""
    if package == 'Base' or not lbs: return None
    from views import surname, sentence
    on = [p for p in lbs if p.pid in lb_choice]
    mike = next((p for p in on if lb_choice[p.pid] == 'the MIKE'), None)
    others = [p for p in on if p is not mike]
    parts = []
    if mike: parts.append(f"{surname(mike.name)} stays at MIKE")
    seen_why = set()
    for p in others:
        why = lb_choice[p.pid]
        if why in seen_why: parts.append(f"{surname(p.name)} ({p.pos}) with him for the same reason"); continue
        seen_why.add(why)
        role = {'runs and covers': "his coverage and speed are the best of the rest", 'covers better than the MIKE': "he covers better than the MIKE, who sits", 'stops the run': "he is the best run stopper we have", 'the cover man': 'he is our best cover linebacker'}.get(why, why)
        parts.append(f"we start {surname(p.name)} ({p.pos}) because {role}")
    if not others and mike and pk.get('LB', 2) == 1: parts[-1] = f"{surname(mike.name)} is the one linebacker; nobody covers well enough to take his place"
    line = f"In {package}, " + ', and '.join(parts) + '.'
    # who from the base three sits: the first man at WILL and at SAM, if he is not on
    firsts = [next((p for p in lbs if p.pos == spot), None) for spot in ('WILL', 'SAM')]
    sat = [p for p in firsts if p is not None and p.pid not in lb_choice]
    if sat: line += ' ' + ' and '.join(surname(p.name) for p in sat) + (' sits.' if len(sat) == 1 else ' sit.')
    n_cb = pk.get('CB', 3)
    if n_cb >= 4: line += ' Four corners dress; the fourth is the dime back.'
    elif n_cb == 3 and package in ('Nickel', 'Third Down'): line += ' The third corner is the nickel.'
    return sentence(line)


# ------------------------------------------------------------ actions
def _slot_label(pos, i):
    """The real slot names: X / Z / SL for receivers, 1 / 2 / NI for corners, numbers elsewhere."""
    if pos == 'WR': return ['X', 'Z', 'SL'][i] if i < 3 else str(i + 1)
    if pos == 'CB': return ['1', '2', 'NI'][i] if i < 3 else str(i + 1)
    return str(i + 1)


RETURN_SLOTS = ('KR', 'PR')


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


# ============================================================ DEVELOPMENT: the GM spends his men's XP
def development(session, league, abbr, pid):
    """One man's development sheet: his bank, his ceiling and the room under it, every attribute his
    position weighs with the price of the next point, and the ceiling unlock."""
    import xp as XP, targets as TG
    p = league.player(pid); t = league.teams[abbr]
    if p is None or p.team != abbr: return dict(error='not on your roster')
    pot = XP.ceiling(p)
    fam = FAM.get(p.pos, 'DB')
    weights = TG.DEPTH_WEIGHTS.get(p.pos, {})
    labels = {k: l for grp in ATTR.values() for k, l in grp}
    keys = list(dict.fromkeys(list(weights.keys()) + [k for k, _ in ATTR['phys']] + ['awareness_rating'] + [k for k, _ in ATTR.get(fam, [])]))
    rows = []
    for k in keys:
        if k not in p.ratings: continue
        cost = XP.cost_per_point(p, k)
        blocked = ('at 99' if p.ratings[k] >= 99 else 'at his ceiling' if XP.at_ceiling(p, k) else None)
        rows.append(dict(key=k, label=labels.get(k, k.replace('_rating', '').replace('_', ' ').title()), v=int(round(p.ratings[k])), cost=int(round(cost)), weight=round(float(weights.get(k, 0.0)), 2),
                         phys=(k in XP.PHYSICAL or k in XP.TOOLS), afford=(p.xp >= cost), blocked=blocked, bought=int(p.xp_spent.get(k, 0) or 0),
                         gain=round(float(TG.position_score(dict(p.ratings, **{k: p.ratings[k] + 1.0}), p.pos) - p.ovr), 2)))
    rows.sort(key=lambda r: (-r['weight'], r['cost']))
    uc = XP.unlock_cost(p)
    return dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), age=int(p.age), bank=int(round(float(p.xp or 0))), **ceiling_read(p),
                development_age=int(XP.development_age(p)), development_year=getattr(p, 'development_year', None),
                unlock_cost=(int(round(uc)) if uc else None), unlock_ok=(uc is not None and p.xp >= uc and (pot or 0) < 99),
                practice_earned=round(float((p.xp_spent.get('_earned') or {}).get('practice',0))),
                bought=int(XP.points_bought(p)), unlocks=int(p.xp_spent.get('_unlocks', 0) or 0), auto=bool(p.xp_spent.get('_auto', False)), dev=modifier_word(p), rows=rows)


def modifier_word(p):
    try:
        import xp as XP; m = XP.modifier(p); return f"×{m:.2f}"
    except Exception: return ''


def act_buy_point(league, abbr, pid, attr):
    import xp as XP
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    cost = XP.buy(p, attr, year=league.year, week=league.week, source='You')
    if cost is None:
        why = ('he is at 99 there' if p.ratings.get(attr, 0) >= 99 else
               ('he has reached the maximum ceiling; no further attribute purchases are available' if (p.potential or 0) >= 99 else
                'unlock his ceiling before buying more attributes') if XP.at_ceiling(p) else
               'that point would take him past his ceiling' if XP.at_ceiling(p, attr) else 'not enough XP')
        return dict(ok=False, why=why)
    return dict(ok=True, line=f"+1 {attr.replace('_rating', '').replace('_', ' ')} for {int(round(cost)):,} XP. {p.name} is a {round(p.ovr)}.", cost=int(round(cost)), ovr=round(p.ovr, 1))


def act_unlock_ceiling(league, abbr, pid):
    import xp as XP
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    cost = XP.unlock(p, year=league.year, week=league.week, source='You')
    if cost is None: return dict(ok=False, why=('his ceiling is already 99' if (p.potential or 0) >= 99 else 'not enough XP for the unlock'))
    return dict(ok=True, line=f"Ceiling raised by one point for {int(round(cost)):,} XP.")


def act_auto_xp(league, abbr, pid=None, on=True):
    """Auto-spend, one man or the whole roster: the assistants spend his XP each week by the same policy the AI uses."""
    import xp_spend as XS
    t = league.teams[abbr]
    men = [league.player(pid)] if pid else list(t.roster)
    for p in men:
        if p is not None: XS.set_auto(p, bool(on))
    t.xp_auto_all = bool(on) if pid is None else getattr(t, 'xp_auto_all', False)
    return dict(ok=True, line=(f"Auto-spend {'on' if on else 'off'} for {men[0].name}." if pid else f"Auto-spend {'on' if on else 'off'} for the whole roster."))


def act_spend_by_read(league, abbr, pid=None):
    """Spend now, once, by the assistants' read: one man or everyone with XP in the bank."""
    import xp_spend as XS, numpy as np
    t = league.teams[abbr]; rng = np.random.default_rng(stable_seed(abbr + str(league.week)))
    men = [league.player(pid)] if pid else list(t.active())
    n = 0; pts = 0
    for p in men:
        if p is None: continue
        acts = XS.spend_player(p, t.gm, t, league.week or 0, rng, year=league.year, source='Assistant')
        if acts: n += 1; pts += len(acts)
    return dict(ok=True, line=f"{pts} point{'s' if pts != 1 else ''} bought for {n} player{'s' if n != 1 else ''}.")


def progression(session, league, abbr):
    """The roster's development at a glance: bank, points bought this year, ceiling room, auto."""
    import xp as XP
    t = league.teams[abbr]
    rows = []
    for p in sorted(t.active(), key=lambda p: -float(p.xp or 0)):
        cheapest = min((XP.cost_per_point(p, k) for k in p.ratings if k.endswith('_rating') and k not in XP.PHYSICAL and k not in XP.TOOLS), default=None)
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), no=getattr(p, 'number', None), bank=int(round(float(p.xp or 0))), **ceiling_read(p),
                         bought=int(p.xp_spent.get('_bought_season', 0) or 0), career=int(XP.points_bought(p)), auto=bool(p.xp_spent.get('_auto', False)),
                         cheapest=(int(round(cheapest)) if cheapest else None), can_buy=(cheapest is not None and p.xp >= cheapest and not XP.at_ceiling(p)), dev=modifier_word(p)))
    return dict(rail=rail(session, league, abbr), rows=rows, auto_all=bool(getattr(t, 'xp_auto_all', False)), bank_total=sum(r['bank'] for r in rows), idle=sum(1 for r in rows if r['can_buy'] and not r['auto']))


def act_hurt_decision(league, abbr, pid, play=True, session=None):
    """Play or Sit a man listed Questionable or Doubtful."""
    runner = getattr(session, 'runner', None) if session is not None else None
    desk = runner.desks.get(abbr) if runner is not None else None
    p = league.player(pid); t = league.teams[abbr]
    if desk is None or p is None: return dict(ok=False, why='no injury desk this week')
    d = desk.pending.get(pid) or desk.status.get(pid)
    if d not in ('questionable', 'doubtful'): return dict(ok=False, why='he is not listed Questionable or Doubtful')
    if play:
        if str(p.xp_spent.get('_inj_kind') or '') == 'Concussion': return dict(ok=False, why='concussion protocol: he cannot play through it')
        desk.play_through(league, t, p, d); runner.refresh(abbr)
        line = f"{p.name} plays Sunday, listed {d}."
    else:
        desk.sit(p); line = f"{p.name} sits Sunday."
    # the decision item closes
    for m in getattr(league, 'inbox', []):
        if m.get('kind') == 'injury_decision' and (m.get('payload') or {}).get('pid') == pid and m.get('status') in ('unread', 'open'): m['status'] = 'done'
    return dict(ok=True, line=line)


def act_ir(league, abbr, pid, season_ending=False):
    """Place a hurt man on injured reserve: off the 53 now, salary counts in full, back after four weeks if a return is left."""
    t = league.teams[abbr]; p = league.player(pid)
    if p is None or p not in t.roster: return dict(ok=False, why='not on your roster')
    r = t.place_on_ir(p, league.week, season_ending=bool(season_ending))
    if not r.get('ok'): return r
    import inbox as IB
    IB.post(league, 'injury', f"{inbox_player(p)} to injured reserve", f"{inbox_player(p)} ({p.pos}) is on IR" + (' for the season' if not r['returnable'] else f"; he can return after {t.IR_MIN_WEEKS} weeks if he is healthy and a return is left ({t.IR_RETURNS - int(getattr(t, 'ir_returns_used', 0) or 0)} of {t.IR_RETURNS} this season)") + '. His salary counts in full; his roster spot is open.', sender='trainers')
    return dict(ok=True, line=f"{p.name} placed on IR." + ('' if r['returnable'] else ' Out for the season.'), returnable=r['returnable'])


def act_ir_activate(league, abbr, pid):
    t = league.teams[abbr]; p = league.player(pid)
    if p is None: return dict(ok=False, why='no such player')
    r = t.activate_from_ir(p, league.week)
    if not r.get('ok'): return r
    return dict(ok=True, line=f"{p.name} activated from IR. {r['returns_left']} return{'s' if r['returns_left'] != 1 else ''} left this season.")


def act_to_squad(league, abbr, pid):
    """Waive to the practice squad. A man with fewer than four accrued seasons goes through waivers first: he is released
    now and, if no club claims him at the Advance, joins your squad. A vested veteran (four or more) is not subject to
    waivers and goes straight to the squad. The squad must have room for him under its rules."""
    import practice_squad as PSQ
    t = league.teams[abbr]; p = league.player(pid)
    if p is None or p not in t.roster: return dict(ok=False, why='not on your roster')
    if not PSQ.can_add(t, p): return dict(ok=False, why=('the squad is full' if len(PSQ.squad(t)) >= PSQ.SIZE else 'the squad has no room for him under its rules (six veterans at most, one specialist)'))
    penalty = _cut_penalty(league, p)
    penalty_line = _cut_penalty_line(penalty)
    if int(p.accrued or 0) >= 4:
        if not PSQ.sign_to_squad(league, abbr, pid):
            return dict(ok=False, why='Cannot move him to the practice squad: releasing his contract would exceed the cap.')
        return dict(ok=True, line=f"{p.name} to the practice squad. {penalty_line}", now=True, **penalty)
    league.release(pid)
    intent = dict(getattr(league, 'ps_intent', None) or {}); intent[pid] = abbr; league.ps_intent = intent
    import inbox as IB
    IB.post(league, 'waiver_notice', f"{inbox_player(p)} waived for the practice squad", f"{inbox_player(p)} ({p.pos}) has been waived and goes through waivers. If no club claims him by the Advance he is assigned to your practice squad; if a club claims him, he is theirs. {penalty_line}", sender='assistants')
    return dict(ok=True, line=f"{p.name} waived. If he clears at the Advance he joins your practice squad. {penalty_line}", now=False, **penalty)


def act_reset_depth(league, abbr, pos=None):
    t = league.teams[abbr]
    if pos: (getattr(t, 'depth_pins', None) or {}).pop(pos, None)
    else: t.depth_pins = {}
    return dict(ok=True)


def act_cut(league, abbr, pid):
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    penalty = _cut_penalty(league, p)
    league.release(pid)
    return dict(ok=True, name=p.name, **penalty)


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
    return dict(ok=ok, name=p.name if p else pid, why=None if ok else 'Call-up unavailable: check squad eligibility, cap space, and open a roster spot if you have 53 active players.')


def act_elevate(league, abbr, pids, week, playoffs=False):
    import practice_squad as PSQ
    t = league.teams[abbr]; already = len(getattr(t, '_elevated', []) or [])
    if already + len(pids) > PSQ.ELEVATIONS_PER_GAME: return dict(ok=False, why=f'only {PSQ.ELEVATIONS_PER_GAME} elevations a game')
    out = PSQ.elevate(league, abbr, list(pids), week, playoffs=playoffs)
    return dict(ok=bool(out), moves=[dict(name=league.player(pid).name, how=how) for pid, how in out], why=None if out else 'nobody eligible')


def act_release_ps(league, abbr, pid):
    import practice_squad as PSQ
    p = league.player(pid); PSQ.release_from_squad(league, abbr, pid)
    return dict(ok=True, name=p.name if p else pid)


# ============================================================ REGRESSION
def regression(session, league, abbr, year=None):
    """What age took, going into next year: only the players who lost overall, with the overall before and after and
    the points lost; for each, his attribute block with the points taken from each attribute (and the awareness and
    recognition he gained), for the popup."""
    from views import rail, club
    store = getattr(league, 'regression', {}) or {}
    years = sorted(int(k) for k in store)
    yr = int(year) if year else (years[-1] if years else int(league.year))
    rec = store.get(str(yr), {}) or {}
    rows = []
    for pid, v in rec.items():
        p = league.player(pid)
        overalls = _regression_overalls(v)
        if overalls is None: continue
        before, after = overalls
        delta = {}
        for k, (b_, a_) in (v.get('attrs') or {}).items():
            d = int(round(a_)) - int(round(b_))
            if d: delta[k] = d
        from types import SimpleNamespace
        # Legacy records kept only changed attributes: show those historical
        # values, never substitute the player's current ratings.
        ratings = v.get('ratings_after')
        if ratings is None:
            ratings = {k: a for k, (b, a) in (v.get('attrs') or {}).items()}
        historical = SimpleNamespace(pos=v.get('pos', p.pos if p else 'UNK'), ratings=ratings)
        cols = attr_cols(historical, delta=delta)
        rows.append(dict(pid=pid, name=v.get('name', p.name if p else str(pid)), pos=historical.pos,
                         age=int(v.get('age', p.age if p else 0)), no=v.get('number', getattr(p, 'number', None)),
                         before=before, after=after, delta=after-before,
                         still_here=bool(p and p.team == abbr and not p.retired),
                         available=p is not None, partial='ratings_after' not in v,
                         cols=cols))

    rows.sort(key=lambda r: (r['delta'], -r['after']))
    return dict(rail=rail(session, league, abbr), club=club(abbr), year=yr, years=years or [yr], rows=rows, hit=len(rows), total_lost=-sum(r['delta'] for r in rows), empty=(not rec))


# ============================================================ SCHEMES ON THE CARD
OFF_POS = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'K', 'P', 'LS'}     # specialists show the offense's seven, all gray


def archetype_keys(entry):
    """An archetype's engine scheme tags on its own side, the same way a club's identity becomes them
    (gm_engine.scheme_of), from the catalog entry's dials alone."""
    import gm_engine as GE, targets as TG
    class _G: pass
    g = _G()
    o = entry.get('offence') or {}; d = entry.get('defence') or {}
    g.off_blocking = o.get('blocking', 'mixed'); g.off_personnel = o.get('personnel', '11'); g.deep = o.get('deep', 0.5)
    g.play_action = o.get('play_action', 0.5); g.motion = o.get('motion', 0.5); g.pass_lean = o.get('pass_lean', 0.5); g.tempo = o.get('tempo', 0.5)
    g.def_front = d.get('front', 'multiple'); g.coverage = d.get('coverage', 0.4); g.box = d.get('box', 0.5); g.blitz = d.get('blitz', 0.4); g.shell = d.get('shell', 0.5)
    side = entry.get('side')
    return [k for k in (GE.scheme_of(g) or []) if not side or TG.SCHEME_SIDE.get(k) == side]


def scheme_rows(ratings, pos, team_key=None):
    """WHERE HE PLAYS BEST. His fit to every archetype on his side, in overall points, banded against his own seven:
    the schemes that suit him most are green, the ones that suit him least red, the rest yellow, and gray where the
    scheme has no effect on his position. The question the section answers is which schemes this player fits, not
    how he ranks against other players in a scheme, so the bands are his and every player has a best fit."""
    import identity_catalog as IC, targets as TG
    side = 'offence' if pos in OFF_POS else 'defence'
    rows = []
    raw = TG.position_score(ratings, pos)
    for key, entry in IC.ARCHETYPES.items():
        if entry.get('side') != side: continue
        tags = [t for t in archetype_keys(entry) if pos in TG.SCHEME_DOMAIN.get(t, ())]
        if not tags:
            rows.append(dict(key=key, name=entry['name'], fit=None, band='none', mine=(key == team_key), words=entry.get('words', ''))); continue
        fit = float(TG.position_score(ratings, pos, tags) - raw)
        rows.append(dict(key=key, name=entry['name'], fit=round(fit, 1), band='avg', mine=(key == team_key), words=entry.get('words', '')))
    live = [r for r in rows if r['fit'] is not None]
    if live:
        fits = sorted(r['fit'] for r in live); n = len(fits)
        lo, hi = fits[0], fits[-1]
        if hi - lo < 0.2:
            for r in live: r['band'] = 'avg'                     # the schemes barely differ for him
        else:
            # near his best is green, near his worst red, the rest yellow; 'near' is a fifth of his own spread
            tol = max(0.3, 0.2 * (hi - lo))
            for r in live:
                r['band'] = 'good' if r['fit'] >= hi - tol else 'bad' if r['fit'] <= lo + tol else 'avg'
    return rows


def _club_arch(league, abbr, pos):
    """The user's club's chosen archetype on this player's side, if it has one."""
    try:
        import views_frontoffice as VF
        ident = VF.club_identity(league, league.teams[abbr]) or {}
        return ident.get('offence' if pos in OFF_POS else 'defence')
    except Exception: return None
