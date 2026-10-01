"""Summarize audit_longitudinal_teams outputs without re-running decisions."""
import argparse
import collections
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('folder')
    args=ap.parse_args()
    root=Path(args.folder)
    snaps=json.loads((root/'snapshots.json').read_text(encoding='utf8'))
    events=[json.loads(s) for s in (root/'events.jsonl').read_text(encoding='utf8').splitlines()]
    moves=[json.loads(s) for s in (root/'moves.jsonl').read_text(encoding='utf8').splitlines()]
    report=dict(stages=[],coaching_changes=[],moves_by_year={},expensive_sign_cut=[],
                low_immediate_gain_signings=[],positive_trade_gains=[],violations=[])
    for s in snaps:
        teams=s['teams']
        if s['label'] in ('initial_cutdown','season_closed','end_offseason') or s['label'].startswith('week_'):
            report['stages'].append(dict(label=s['label'],year=s['year'],week=s['week'],
                games=s['regular_games']+s['playoff_games'],
                active_range=[min(t['active'] for t in teams),max(t['active'] for t in teams)],
                ps_range=[min(t['ps'] for t in teams),max(t['ps'] for t in teams)],
                cap_range=[min(t['full_cap_space'] for t in teams),max(t['full_cap_space'] for t in teams)],
                over_cap=[t['team'] for t in teams if t['full_cap_space']<-.01],
                current_cap_range=[min(t['cap_space'] for t in teams),max(t['cap_space'] for t in teams)],
                current_over_cap=[t['team'] for t in teams if t['cap_space']<-.01],
                score_mean=round(sum(t['score'] for t in teams)/32,3),
                age_mean=round(sum(t['mean_age'] for t in teams)/32,3),
                ovr_mean=round(sum(t['mean_ovr'] for t in teams)/32,3),
                uncovered={t['team']:t['uncovered'] for t in teams if t['uncovered']},
                group_short={t['team']:t['group_short'] for t in teams if t['group_short']},
                position_short={t['team']:t['position_short'] for t in teams if t['position_short']},
                ps_concentration={t['team']:dict(collections.Counter(p['pos'] for p in t['squad_players']))
                                  for t in teams if max(collections.Counter(p['pos'] for p in t['squad_players']).values(),default=0)>=5}))
        # Offseason openings after expiry/retirement are expected, not lineup failures.
        check_packages=s['phase'] in ('regular','playoffs') or s['label']=='end_offseason'
        if s['multiple_owners'] or s['invalid_owners'] or (check_packages and any(t['package_bad'] for t in teams)):
            report['violations'].append(dict(year=s['year'],stage=s['label'],phase=s['phase'],multiple_owners=s['multiple_owners'],
                invalid_owners=s['invalid_owners'],packages={t['team']:t['package_bad'] for t in teams if t['package_bad']}))
        if s['label']=='step_coaching':
            before=next(x for x in reversed(snaps[:snaps.index(s)]) if x['label']=='step_awards')
            prior={t['team']:t for t in before['teams']}
            changed={e['team']:e for e in events if e['year']==s['year'] and e['kind']=='gm_change'}
            for t in teams:
                if t['team'] in changed:
                    b=prior[t['team']]
                    report['coaching_changes'].append(dict(year=s['year'],team=t['team'],old_front=b['front'],
                        new_front=t['front'],old_offense=b['offense'],new_offense=t['offense'],
                        score_before=b['score'],score_after=t['score'],hire=changed[t['team']]))
    for year in sorted({e['year'] for e in events}):
        report['moves_by_year'][year]=dict(collections.Counter(e['kind'] for e in events if e['year']==year))
    kickoffs=[json.loads(s) for s in (root/'kickoffs.jsonl').read_text(encoding='utf8').splitlines()]
    report['kickoffs_by_year']={}
    for year in sorted({k['year'] for k in kickoffs}):
        games=[k for k in kickoffs if k['year']==year]
        report['kickoffs_by_year'][year]=dict(games=len(games),
            over53=[k for k in games if max(k['active'].values())>53],
            under53=[k for k in games if min(k['active'].values())<53])
    report['wire_failures']=[]
    for s in snaps:
        if s['label']!='end_offseason': continue
        for t in s['teams']:
            if t['active']==53 and t['cap_space']>=-.01 and not t['uncovered']: continue
            releases=[e for e in events if e['year']==s['year'] and e.get('audit_stage')=='wire'
                      and e['kind']=='release' and e.get('team')==t['team']]
            report['wire_failures'].append(dict(year=s['year'],team=t['team'],active=t['active'],
                cap_space=t['cap_space'],uncovered=t['uncovered'],group_short=t['group_short'],
                position_short=t['position_short'],releases=releases))
    signs={}
    retained={}
    report['offseason_contract_churn']=[]
    drafted={}
    report['first_camp_draft_cuts']=[]
    for e in events:
        key=(e['year'],e.get('team'),e.get('pid'))
        if e['kind']=='draft': drafted[(e['year'],e['pid'])]=e
        if e['kind']=='sign': signs[key]=e
        if e['kind']=='release' and key in signs and signs[key].get('apy',0)>=4:
            report['expensive_sign_cut'].append(dict(sign=signs[key],release=e))
        offseason=e.get('phase') in ('offseason','free_agency','preseason')
        if offseason and e['kind']=='release' and (e['year'],e.get('pid')) in drafted:
            pick=drafted.pop((e['year'],e['pid']))
            report['first_camp_draft_cuts'].append(dict(draft=pick,release=e))
        if offseason and e['kind'] in ('sign','extension'):
            retained[key]=e
        if offseason and e['kind']=='release' and key in retained:
            contract=retained.pop(key)
            report['offseason_contract_churn'].append(dict(contract=contract,release=e,
                notable=contract.get('apy',0)>=4,
                category='draft' if contract.get('audit_stage')=='step_draft' else
                         'udfa' if contract.get('audit_stage')=='practice_squad.udfa_camp' else
                         'extension' if contract['kind']=='extension' else
                         'other_signing'))
    for m in moves:
        if m['action']=='sign' and m['new_contract']['cap_hit']>=8:
            a=next(iter(m['before']),None)
            if a and m['after'][a]['score']-m['before'][a]['score']<1:
                report['low_immediate_gain_signings'].append(m)
        if m['action']=='trade':
            changes={a:round(m['after'][a]['score']-b['score'],3) for a,b in m['before'].items()}
            if max(changes.values(),default=0)>1:
                report['positive_trade_gains'].append(dict(year=m['year'],week=m['week'],stage=m['stage'],
                    changes=changes,assets=m['assets'],cap_before={a:b['cap_space'] for a,b in m['before'].items()},
                    cap_after={a:b['cap_space'] for a,b in m['after'].items()}))
    for row in report['first_camp_draft_cuts']:
        pick=row['draft']
        end=next((s for s in snaps if s['label']=='end_offseason' and s['year']==pick['year']),None)
        row['destination_at_regular_gate']=None
        if end:
            for team in end['teams']:
                if pick['pid'] in team['roster_ids']:
                    row['destination_at_regular_gate']=dict(team=team['team'],
                        status='IR' if pick['pid'] in team['ir_ids'] else 'active')
                if pick['pid'] in team['ps_ids']:
                    row['destination_at_regular_gate']=dict(team=team['team'],status='PS')
    report['fa_churn_rates']=[]
    for end in (s for s in snaps if s['label']=='end_offseason'):
        year=end['year']
        contracts=[e for e in events if e['year']==year and e['kind']=='sign'
                   and e.get('audit_stage','').startswith('step_fa_') and e.get('apy',0)>=4]
        released={(e.get('team'),e.get('pid')) for e in events if e['year']==year
                  and e['kind']=='release' and e.get('phase') in ('offseason','free_agency','preseason')}
        cut=[e for e in contracts if (e['team'],e['pid']) in released]
        report['fa_churn_rates'].append(dict(year=year,contracts=len(contracts),cuts=len(cut),
            percent=round(100*len(cut)/max(1,len(contracts)),2),
            multiyear_cuts=sum(e['years']>1 for e in cut),definition='FA-phase contracts APY>=4; may include re-signings'))
    (root/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    for k,v in report.items():
        if k in ('stages','coaching_changes'): print(k,json.dumps(v))
        else: print(k,len(v))


if __name__=='__main__': main()
