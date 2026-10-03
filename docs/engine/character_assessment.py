"""Scouting knowledge, separate from a player's true attributes and ceiling.

Reads are saved per club. Views never roll new information or expose hidden traits.
Local seeded reads do not perturb the draft, practice, or game random streams.
"""
import math
import numpy as np
from stable import stable_seed
import personality as PT

KEYS = ('work_ethic', 'discipline')


def migrate(league):
    """Retain already-earned legacy knowledge and grades; no new scouting rolls."""
    for abbr, views in (getattr(league, 'scouting', None) or {}).items():
        for pid, view in views.items():
            p = league.players.get(pid)
            if p is None: continue
            data = assessments(view)
            if not data: continue
            view['character_assessments'] = data
            bank = p.xp_spent.setdefault('_character_observations', {}).setdefault(abbr, {})
            for key, record in data.items():
                bank.setdefault(key, record)


def _read(value, error, seed, source, evidence=1):
    rng = np.random.default_rng(stable_seed(seed))
    return dict(value=round(float(np.clip(value + rng.normal(0, error), 0, 100)), 1),
                error=round(float(error), 1), source=source, evidence=evidence)


def assessments(view):
    """Legacy flags retain their old grade adjustment; never subtract it twice."""
    result = dict((view or {}).get('character_assessments') or {})
    if 'work_ethic' not in result and ('character_read' in (view or {}) or
                                     'character' in ((view or {}).get('flags') or [])):
        result['work_ethic'] = dict(value=(view or {}).get('character_read', 30),
                                   error=16., source='Previous visit', evidence=1,
                                   legacy_adjusted='character' in ((view or {}).get('flags') or []))
    return result


def _remember(p, abbr, reads):
    bank = p.xp_spent.setdefault('_character_observations', {})
    bank.setdefault(abbr, {}).update(reads)


def film(p, abbr, view, *, small_school=False):
    """A noisy interpretation of on-field behavior, including for tape-only scouts."""
    data = view.setdefault('character_assessments', {})
    if 'discipline' not in data:
        data['discipline'] = _read(PT.discipline(p), 22 if small_school else 18,
            ('discipline-film-v1', abbr, p.pid), 'Film assessment')
        _remember(p, abbr, {'discipline': data['discipline']})


def visit(p, abbr, view, room, error_sd):
    data = assessments(view)
    view['character_assessments'] = data
    if room.get('character') == 'none': view['character_skipped'] = 'tape'
    # A saved legacy visit is not permission for a fresh read on reload.
    if 'work_ethic' in data or room.get('character') == 'none':
        return False
    error = max(8., float(error_sd) * 1.5)
    if room.get('character') == 'sharp': error *= .45
    data['work_ethic'] = _read((p.traits or {}).get('work_ethic', 50), error,
        ('work-visit-v1', abbr, p.pid), 'Visit and references')
    # References can supplement the film read, but the tape-only room has no references.
    data['discipline'] = _read(PT.discipline(p), max(6., error),
        ('discipline-visit-v1', abbr, p.pid), 'Film and references')
    _remember(p, abbr, data)
    return True


def describe(key, record=None):
    label = 'Work ethic' if key == 'work_ethic' else 'Discipline'
    if not record:
        return dict(key=key, label=label, status='unknown', summary='Not assessed',
                    confidence=None, source=None, explanation='No assessment is available.')
    value, error = float(record.get('value', 50)), float(record.get('error', 20))
    confidence = 'Strong' if error <= 7 else 'Moderate' if error <= 13 else 'Limited'
    low, high = (42, 58) if key == 'work_ethic' else (35, 70)
    status = 'concern' if value < low else 'strength' if value >= high else 'neutral'
    if key == 'work_ethic':
        summary = {'concern': 'Inconsistent preparation', 'strength': 'Strong preparation habits',
                   'neutral': 'No concern identified'}[status]
        explanation = {'concern': 'May earn development XP more slowly than his talent suggests.',
                       'strength': 'Consistent effort may help him earn development XP faster.',
                       'neutral': 'No work-ethic concern identified; this is an assessment, not a guarantee.'}[status]
    else:
        summary = {'concern': 'Avoidable-penalty concerns', 'strength': 'Plays under control',
                   'neutral': 'No concern identified'}[status]
        explanation = {'concern': 'May commit more avoidable penalties when involved in the play.',
                       'strength': 'Shows signs of avoiding unnecessary penalties.',
                       'neutral': 'No discipline concern identified; penalties remain possible.'}[status]
    return dict(key=key, label=label, status=status, summary=summary,
                confidence=confidence, source=record.get('source', 'Scouting assessment'),
                explanation=explanation)


def report(view):
    data = assessments(view)
    rows = [describe(k, data.get(k)) for k in KEYS]
    if rows[0]['status'] == 'unknown' and (view or {}).get('character_skipped') == 'tape':
        rows[0]['explanation'] = 'Your scout trusts the tape and does not assess preparation through interviews or references.'
    return rows


def flags(view):
    labels = {'work_ethic': ('Work ethic concern', 'Strong preparation'),
              'discipline': ('Discipline concern', 'Plays under control')}
    return [labels[r['key']][0 if r['status'] == 'concern' else 1]
            for r in report(view) if r['status'] in ('concern', 'strength')]


def draft_risk(view, gm):
    """Grade-equivalent risk cost for the CPU decision, not a talent downgrade."""
    cost = 0.
    for key, record in assessments(view).items():
        if key not in KEYS or record.get('legacy_adjusted'): continue
        value = float(record.get('value', 50))
        confidence = max(.25, min(1., 1. - float(record.get('error', 20)) / 30.))
        weight = 1.5 if key == 'work_ethic' else .75
        low, high = (42, 58) if key == 'work_ethic' else (35, 70)
        cost += confidence * weight * (max(0., (low-value)/low) - .4*max(0., (value-high)/(100-high)))
    risk = max(0., min(1., float(getattr(gm, 'risk', .5))))
    return cost * (1.5-risk)


def observe_practice(p, abbr, year, week):
    """Three actual participating weeks provide a first team read; no extra XP."""
    records = p.xp_spent.setdefault('_character_practice', {})
    record = records.setdefault(abbr, dict(weeks=0, last=None))
    key = f'{year}:{week}'
    if record['last'] == key: return
    record.update(last=key, weeks=int(record['weeks'])+1)
    n = record['weeks']
    if n < 3: return
    error = max(5., 20. / math.sqrt(n))
    read = _read((getattr(p, 'traits', None) or {}).get('work_ethic', 50), error,
                 ('preparation-experience-v1', abbr, p.pid), 'Team practices', n)
    _remember(p, abbr, {'work_ethic': read})


def player_report(p, abbr, stats=None):
    """Only this club's saved knowledge, never the hidden personality values."""
    data = (p.xp_spent.get('_character_observations') or {}).get(abbr, {})
    rows = [describe(k, data.get(k)) for k in KEYS]
    stats = stats or {}
    opportunities = int(stats.get('penalty_opportunities', 0) or 0)
    if opportunities:
        committed = int(stats.get('penalties_committed', 0) or 0)
        accepted = int(stats.get('penalties_accepted', 0) or 0)
        yards = float(stats.get('penalty_yards', 0) or 0)
        rows[1]['game_record'] = (f'{committed} committed, {accepted} accepted, '
                                  f'{yards:g} enforced yards across {opportunities} eligible play checks this season.')
        # Raw counts alone do not establish character: positions, opponents,
        # staff, and foul opportunities differ. Keep the assessment separate.
    return rows
