"""Produce concise, reproducible tables from completed study summaries."""
import collections
import json
import sys
from pathlib import Path


def main():
    root=Path(sys.argv[1])
    lines=['TEAM DECISION STUDY: RESULTS',
           'Frozen production baseline ef4620a. Money in millions.',
           'Planning score is an internal roster metric, not OVR.',
           'Game-count rows include regular season and playoffs.', '']
    for seed in (93030,93031):
        folder=root/f'team-study-{seed}'
        report=json.loads((folder/'summary.json').read_text(encoding='utf8'))
        lines += [f'SEED {seed}',
                  'Year  Stage              Active  PS     Over cap  Score   Age    OVR']
        for s in report['stages']:
            if s['label']=='week_1': continue
            active='-'.join(map(str,s['active_range']))
            ps='-'.join(map(str,s['ps_range']))
            lines.append(f"{s['year']}  {s['label']:<18} {active:<7} {ps:<6} "
                         f"{len(s['current_over_cap']):<9} {s['score_mean']:>6.2f}  "
                         f"{s['age_mean']:>5.2f}  {s['ovr_mean']:>5.2f}")
        lines += ['', 'Actual kickoff counts (games with either team outside 53):']
        for year,g in report['kickoffs_by_year'].items():
            lines.append(f"{year}: {g['games']} games, {len(g['over53'])} over53, "
                         f"{len(g['under53'])} under53. Categories may overlap.")
        lines += ['', 'Final-wire failures:']
        for f in report['wire_failures']:
            lines.append(f"{f['year']} {f['team']}: active {f['active']}, cap {f['cap_space']:+.3f}, "
                         f"wire releases {len(f['releases'])}, uncovered {f['uncovered']}")
        lines += ['', 'First-camp draft cuts by round:']
        years=sorted({x['draft']['year'] for x in report['first_camp_draft_cuts']})
        for year in years:
            rows=[x for x in report['first_camp_draft_cuts'] if x['draft']['year']==year]
            counts=collections.Counter(x['draft']['round'] for x in rows)
            lines.append(f"{year}: " + ', '.join(f'R{r}={counts[r]}' for r in range(1,8)))
            r2=[x for x in rows if x['draft']['round']==2]
            same=sum(bool(x.get('destination_at_regular_gate')) and
                     x['destination_at_regular_gate']['team']==x['draft']['team'] for x in r2)
            lines.append(f'  R2 cuts: {same} stayed in organization; {len(r2)-same} left by final wire.')
        lines += ['', 'FA-phase APY >=4 cut rates (contracts may include re-signings):']
        for r in report['fa_churn_rates']:
            lines.append(f"{r['year']}: {r['cuts']}/{r['contracts']} ({r['percent']:.2f}%), "
                         f"{r['multiyear_cuts']} multiyear cuts.")
        lines += ['', 'Notable offseason contract churn (APY >=4; excluding draft/UDFA):']
        churn=report['offseason_contract_churn']
        for year in sorted({x['contract']['year'] for x in churn}):
            for category in ('other_signing','extension'):
                rows=[x for x in churn if x['contract']['year']==year and
                      x['category']==category and x['notable']]
                now=sum(x['release'].get('dead',0) for x in rows)
                nxt=sum(x['release'].get('dead_next',0) for x in rows)
                lines.append(f'{year} {category}: {len(rows)} cuts, remaining dead {now:.3f} now / {nxt:.3f} next.')
        lines += ['', 'Natural coaching changes:']
        for c in report['coaching_changes']:
            lines.append(f"{c['year']} {c['team']} {c['hire']['hired']}: front "
                         f"{c['old_front']} -> {c['new_front']}, offense "
                         f"{c['old_offense']} -> {c['new_offense']}, immediate score "
                         f"{c['score_before']:.2f} -> {c['score_after']:.2f}")
        lines += ['', 'Transaction event counts by calendar year (types can overlap):']
        for year,counts in report['moves_by_year'].items():
            kinds=('sign','release','extension','franchise_tag','trade','draft','draft_trade',
                   'udfa_sign','waiver_claim','ps_sign','ps_callup','ps_poach','restructure')
            lines.append(f"{year}: " + ', '.join(f'{k}={counts.get(k,0)}' for k in kinds))
        lines += ['', 'Source: '+str(folder), '']
    (root/'TEAM_DECISION_STUDY_RESULTS.txt').write_text('\n'.join(lines)+'\n',encoding='utf8')


if __name__=='__main__': main()
