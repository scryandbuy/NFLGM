"""Paired CPU-board audit on identical rosters, prospects and football reads.

Runs the baseline draft/scouting functions from a named Git revision locally.
Trade attempts are disabled only for isolated one-pick CPU execution probes.
This is decision sensitivity evidence, not longitudinal draft calibration.
"""
import argparse
import copy
import json
import subprocess
import time
import types
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
import character_assessment as CA
import draft as D
import draft_day as DD
import scouting as SC
import spring as SP
from league import DraftPick, League
from session import Session


def historical_module(revision, filename):
    text=subprocess.check_output(['git','show',f'{revision}:{filename}']).decode('utf-8')
    m=types.ModuleType('audit_baseline_'+filename[:-3]);exec(compile(text,filename,'exec'),m.__dict__)
    return m


def talent(L):
    return {p.pid:(dict(p.ratings),p.dev,p.potential,p.potential_range,p.xp,dict(p.traits)) for p in L.draft_pool}


def football(view):
    return {k:v for k,v in view.items() if k not in ('character_assessments','character_skipped')}


def pick_probe(L,abbr,slot,taken,level,baseline):
    selected=[]
    for before in (True,False):
        clone=copy.deepcopy(L)
        obj=DD.Draft(clone,np.random.default_rng(71),clone.year,user_team=None,auto_pick=True,level=level)
        obj.picks=[DraftPick(clone.year,max(1,(slot-1)//32+1),abbr,abbr,selection=slot)]
        obj.i=0;obj.taken=set(taken)
        with patch.object(obj,'_maybe_trade',return_value=None):
            if before:
                with patch.object(D,'board',baseline.board): result=obj.sim_pick()
            else:result=obj.sim_pick()
        assert result[0]=='pick'
        p=result[3];assert p.team==abbr and obj.picks[0].used_on==p.pid
        selected.append(p.pid)
    return selected


def run(seeds,baseline):
    started=time.perf_counter();base=historical_module(baseline,'draft.py');base_scout=historical_module(baseline,'scouting.py')
    result={'baseline_revision':subprocess.check_output(['git','rev-parse',baseline],text=True).strip(),
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'method':'Same football reads, rosters and available prospects for baseline/new boards. Independent pick snapshots, not a simulated draft or season. Isolated CPU pick probes disable trade attempts.',
            'seeds':seeds,'slots':[20,100,200],'classes':[],'board_cases':[],'cpu_pick_probes':[]}
    for seed in seeds:
        s=Session.new('GB',seed=seed);L=s.L;L.draft_pool=list(L.next_class);L.next_class=[]
        L.user_team=None;L.set_phase('offseason')
        old=copy.deepcopy(L);truth=talent(L)
        r0=np.random.default_rng(seed+1000);r1=np.random.default_rng(seed+1000)
        base_scout.scout(old,r0);SC.scout(L,r1)
        assert r0.bit_generator.state==r1.bit_generator.state
        assert old.consensus==L.consensus
        for a,views in L.scouting.items():
            for pid,v in views.items():assert football(v)==old.scouting[a][pid]
        assert truth==talent(L)
        # Real automatic scouting visits, with the actual seeded scout traits.
        SP.visits(L,np.random.default_rng(seed+2000))
        assert truth==talent(L)
        grade_snapshot=copy.deepcopy(L.scouting)
        rng_state=copy.deepcopy(s.rng.bit_generator.state)
        level=D.league_starter_level(L)
        class_result={'seed':seed,'prospects':len(L.draft_pool),'teams':len(L.teams),
                      'scouting_rng_identical':True,'football_reads_identical_before_visits':True,
                      'room_modes':dict(Counter(SC.room(t)['character'] for t in L.teams.values())),
                      'knowledge':dict(Counter((key,read['source']) for views in L.scouting.values() for v in views.values() for key,read in CA.assessments(v).items()))}
        class_result['knowledge']={f'{k[0]} / {k[1]}':n for k,n in class_result['knowledge'].items()}
        concerns=[]
        for a,views in L.scouting.items():
            for pid,v in views.items():concerns.append(4*CA.draft_risk(v,L.teams[a].gm))
        class_result['effective_slot_adjustment']={'min':min(concerns),'max':max(concerns),'mean':float(np.mean(concerns)),
                                                   'p95':float(np.quantile(concerns,.95))}
        for i,a in enumerate(sorted(L.teams)):
            for slot in result['slots']:
                # Remove the same consensus-leading players to inspect later
                # decision points; keep exactly the same roster in both arms.
                taken={p.pid for p in sorted(L.draft_pool,key=lambda p:L.consensus[p.pid]['rank'])[:slot-1]}
                before=base.board(L,a,slot,level,taken);after=D.board(L,a,slot,level,taken)
                b,aft=before[0][1],after[0][1];before_rank={p.pid:j+1 for j,(_,p) in enumerate(before)}
                changed=b.pid!=aft.pid
                result['board_cases'].append({'seed':seed,'team':a,'slot':slot,'changed':changed,
                    'before':b.pid,'after':aft.pid,'after_baseline_rank':before_rank[aft.pid],
                    'before_grade':L.scouting[a][b.pid]['ovr'],'after_grade':L.scouting[a][aft.pid]['ovr'],
                    'before_risk':CA.draft_risk(L.scouting[a][b.pid],L.teams[a].gm),
                    'after_risk':CA.draft_risk(L.scouting[a][aft.pid],L.teams[a].gm),
                    'top10_overlap':len({p.pid for _,p in before[:10]}&{p.pid for _,p in after[:10]})})
                if slot==20 and i%4==0:
                    picks=pick_probe(L,a,slot,taken,level,base)
                    assert picks==[b.pid,aft.pid]
                    result['cpu_pick_probes'].append({'seed':seed,'team':a,'before':picks[0],'after':picks[1]})
        assert grade_snapshot==L.scouting and truth==talent(L)
        assert rng_state==s.rng.bit_generator.state
        # Persist through the actual league save/load, then verify the same
        # knowledge and several full boards, not merely the risk helper.
        loaded=League.load(json.loads(json.dumps(L.to_dict(),default=lambda x:x.item() if hasattr(x,'item') else list(x))))
        for a in ('GB','MIN','KC','DEN'):
            for pid,v in L.scouting[a].items():assert CA.assessments(loaded.scouting[a][pid])==CA.assessments(v)
            expected=[(v,p.pid) for v,p in D.board(L,a,100,level,set())]
            actual=[(v,p.pid) for v,p in D.board(loaded,a,100,level,set())]
            assert actual==expected
        class_result['save_reload_boards_equal']=True
        result['classes'].append(class_result)
        print(f'Seed {seed}: {len(L.draft_pool)} prospects, 32 rooms, 96 paired boards, 8 CPU pick pairs passed.',flush=True)
    cases=result['board_cases'];changed=[c for c in cases if c['changed']]
    result['summary']={'paired_board_cases':len(cases),'changed_top_choices':len(changed),
                       'change_share':len(changed)/len(cases),'cpu_pick_pairs':len(result['cpu_pick_probes']),
                       'mean_top10_overlap':float(np.mean([c['top10_overlap'] for c in cases])),
                       'max_baseline_rank_of_new_choice':max(c['after_baseline_rank'] for c in cases),
                       'max_observed_grade_sacrifice':max((c['before_grade']-c['after_grade'] for c in changed),default=0),
                       'changed_choices_with_lower_character_cost':sum(c['after_risk']<c['before_risk'] for c in changed),
                       'elapsed_seconds':round(time.perf_counter()-started,2)}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',default='c14c945');parser.add_argument('--seeds',nargs='+',type=int,default=[31,47,83]);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run(args.seeds,args.baseline);Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result['summary'],indent=2))
