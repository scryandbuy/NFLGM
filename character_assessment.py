"""Scouting knowledge, separate from a player's true attributes and ceiling.

Reads are saved per club. Views never roll new information or expose hidden traits.
Local seeded reads do not perturb the draft, practice, or game random streams.
"""
import copy
import math
import numpy as np
from stable import stable_seed
import personality as PT

KEYS = ('work_ethic', 'discipline')


def migrate(league):
    """Preserve earned knowledge; backfill missing baseline prospect film reads."""
    prospects = {p.pid for p in list(getattr(league, "draft_pool", []) or []) + list(getattr(league, "next_class", []) or [])}
    for abbr, views in (getattr(league, 'scouting', None) or {}).items():
        for pid, view in views.items():
            p = league.players.get(pid)
            if p is None: continue
            data = assessments(view)
            if pid in prospects and 'discipline' not in data:
                saved = (p.xp_spent.get('_character_observations') or {}).get(abbr, {}).get('discipline')
                if saved:
                    data['discipline'] = copy.deepcopy(saved)
                else:
                    from scouting import _power
                    baseline = {}
                    film(p, abbr, baseline, small_school=not _power(p))
                    data['discipline'] = baseline['character_assessments']['discipline']
                    # Display repair must not reprice an already-scouted class.
                    data['discipline']['display_backfill'] = True
            if not data: continue
            view['character_assessments'] = data
            _remember(p, abbr, data)


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
    bank = p.xp_spent.setdefault('_character_observations', {}).setdefault(abbr, {})
    for key, record in reads.items():
        old = bank.get(key)
        error = float(record.get('error', 20))
        old_error = float(old.get('error', 20)) if old else float('inf')
        # Another source cannot erase a more precise earned assessment.
        # At the precision floor, retain updates to the same source's evidence.
        if (old is None or error < old_error or
                error == old_error and record.get('source') == old.get('source')
                and record.get('evidence', 1) >= old.get('evidence', 1)):
            bank[key] = copy.deepcopy(record)


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
    if ('work_ethic' in data and data['work_ethic'].get('stage') != 'background') or room.get('character') == 'none':
        return False
    prior = data.get('work_ethic')
    # The interview is a stronger source than a tentative background note.
    # The visit tightens that read by another 15%, never replacing a more
    # reliable earlier observation with a weaker one.
    # Keep the interview's precision tied to the room's scouting quality.
    # A flat floor made most weak and strong rooms produce the same read.
    # The middle-quality room retains its previous visit precision (6.8
    # after the 15% gain); weaker and stronger rooms diverge around it.
    base_error = 5.0 + .8 * max(0., float(error_sd))
    if room.get('character') == 'sharp': base_error *= .45
    elif room.get('character') == 'tape': base_error *= 1.25
    error = min(base_error, float(prior.get('error', base_error)) if prior else base_error) * .85
    data['work_ethic'] = _read((p.traits or {}).get('work_ethic', 50), error,
        ('work-visit-v1', abbr, p.pid), 'Visit and references')
    # The tape-first room still gets a visit, but puts less weight on references.
    disc_prior = data.get('discipline')
    disc_error = min(max(6., error), float(disc_prior.get('error', error)) if disc_prior else error)
    data['discipline'] = _read(PT.discipline(p), disc_error,
        ('discipline-visit-v1', abbr, p.pid), 'Film and references')
    _remember(p, abbr, data)
    return True


def background(p, abbr, view, room, error_sd, evidence):
    """Tentative season references and film, weaker than an in-person visit.

    The noise direction stays fixed as evidence grows; no independent rerolls.
    Stronger previously earned evidence and legacy adjustments remain intact.
    """
    data = assessments(view)
    view['character_assessments'] = data
    n = max(1, int(evidence))
    mode = room.get('character', 'normal')
    if mode == 'none':
        view['character_skipped'] = 'tape'
    else:
        error = max(14., 22. / math.sqrt(1. + .25 * (n - 1)))
        error *= .75 if mode == 'sharp' else 1.2 if mode == 'tape' else 1.
        error += max(0., float(error_sd) - 3.) * .4
        old = data.get('work_ethic')
        if old is None or (old.get('stage') == 'background' and error < old.get('error', 99)):
            data['work_ethic'] = _read((p.traits or {}).get('work_ethic', 50), error,
                ('work-background-v1', abbr, p.pid), 'Background cross-check', n)
            data['work_ethic']['stage'] = 'background'
    error = max(12., 17. / math.sqrt(1. + .15 * (n - 1)))
    old = data.get('discipline')
    if old is None or error < old.get('error', 99):
        data['discipline'] = _read(PT.discipline(p), error,
            ('discipline-film-v1', abbr, p.pid), 'Film cross-check', n)
    _remember(p, abbr, data)


def area_report(p, abbr, view, room, quality):
    """One coarse background summary, separate from a football cross-check.

    Existing stronger/legacy knowledge wins. This broad first pass remains
    Limited even with a Character Judge; visits and focused work refine it.
    """
    data = assessments(view)
    if room.get('character') == 'none' or 'work_ethic' in data:
        return False
    error = 26. - 4. * max(0., min(1., float(quality)))
    if room.get('character') == 'sharp': error *= .85
    elif room.get('character') == 'tape': error += 4.
    read = _read((p.traits or {}).get('work_ethic', 50), error,
                 ('work-background-v1', abbr, p.pid), 'Area background report')
    read['stage'] = 'background'
    data['work_ethic'] = read
    view['character_assessments'] = data
    _remember(p, abbr, {'work_ethic': read})
    return True


def describe(key, record=None):
    label = 'Work Ethic' if key == 'work_ethic' else 'Discipline'
    if not record:
        return dict(key=key, label=label, status='unknown', summary='Not assessed',
                    confidence=None, source=None, explanation='')
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
                       'neutral': 'No discipline concern identified.'}[status]
    if record.get('stage') == 'background':
        explanation = 'Tentative background read. ' + explanation
    return dict(key=key, label=label, status=status, summary=summary,
                confidence=confidence, source=record.get('source', 'Scouting assessment'),
                explanation=explanation)


def report(view):
    data = assessments(view)
    rows = [describe(k, data.get(k)) for k in KEYS]
    if rows[0]['status'] == 'unknown' and (view or {}).get('character_skipped') == 'tape':
        rows[0]['explanation'] = 'Your scout trusts the tape and does not assess preparation through interviews or references.'
    return rows


def board_flags(view):
    """Display earned strengths and concerns at their saved confidence level."""
    labels = {'work_ethic': {'concern': 'Work ethic concern', 'strength': 'Strong preparation'},
              'discipline': {'concern': 'Discipline concern', 'strength': 'Plays under control'}}
    return {labels[r['key']][r['status']]: r['confidence'] + ' Confidence'
            for r in report(view) if r['status'] in ('concern', 'strength') and r['confidence']}


def flags(view):
    labels = {'work_ethic': ('Work ethic concern', 'Strong preparation'),
              'discipline': ('Discipline concern', 'Plays under control')}
    data = assessments(view)
    out = []
    for r in report(view):
        if r['confidence'] != 'Strong' or r['status'] not in ('concern', 'strength'):
            continue
        record = data[r['key']]
        value, error = float(record['value']), float(record['error'])
        low, high = (42, 58) if r['key'] == 'work_ethic' else (35, 70)
        # A precise but borderline read is still not a confident conclusion.
        if r['status'] == 'concern' and value + 2 * error < low:
            out.append(labels[r['key']][0])
        elif r['status'] == 'strength' and value - 2 * error >= high:
            out.append(labels[r['key']][1])
    return out


def draft_risk(view, gm):
    """Grade-equivalent risk cost for the CPU decision, not a talent downgrade."""
    cost = 0.
    for key, record in assessments(view).items():
        if key not in KEYS or record.get('legacy_adjusted') or record.get('display_backfill'): continue
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
    return [describe(k, data.get(k)) for k in KEYS]
