"""Targeted, read-only production-game audit of the recurring game-log watch items.

No RNG draws or simulation outcomes are changed. Fresh catalog teams, four
independent seeds; this is not a reproduction of a developed 2027 saved roster.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import game
import plays as PL
import defensive_rush as DR
import game_recap as recap
import league as LG
import season as SN
from calibrate import Collector


def run(seeds):
    collector = Collector()
    games, rows, players, kicks = [], [], [], []
    original_kick = game.attempt_field_goal
    context = {}
    original_run = PL._run_play
    original_pass = PL._pass_play
    original_protection = PL.resolve_protection
    protection_trace = {}

    def record_protection(blockers, rushers, rng, qb=None, chip=None, assignments=None, protection='five'):
        result = original_protection(blockers,rushers,rng,qb,chip,assignments,protection)
        assignment = {a['player'].get('pid'):a for a in assignments or []}
        winner = next((p for p in rushers if p.get('pid')==result['beaten_by']),{})
        protection_trace.clear()
        protection_trace.update(winner=result['beaten_by'],winner_pos=winner.get('pos'),
            alignment=(assignment.get(result['beaten_by']) or {}).get('alignment'),
            unblocked=result['beaten'] is None,
            rushers=[dict(pid=p.get('pid'),pos=p.get('pos'),alignment=(assignment.get(p.get('pid')) or {}).get('alignment')) for p in rushers])
        return result

    def record_pass(off,deff,off_call,def_call,ytg,rng):
        protection_trace.clear()
        result=original_pass(off,deff,off_call,def_call,ytg,rng)
        result['_audit_rush']=dict(protection_trace)
        return result

    def record_run(off, deff, off_call, def_call, ytg, rng):
        # These deterministic matchup calculations duplicate the resolver's
        # inputs only; no extra random draws or player mutations occur.
        roles = DR.assignments(deff, def_call)
        front = [a for a in roles if a['alignment'] in DR.EDGES + DR.INTERIOR]
        ids = {DR.player_key(a['player']) for a in front}
        rest = sorted((a for a in roles if DR.player_key(a['player']) not in ids),
                      key=lambda a:(not a['alignment'].startswith('offball_'), a['alignment'], DR.player_key(a['player'])))
        defenders = [a['player'] for a in front + rest]
        matches = DR.protection_pairs(off['ol'][:5], front)
        scheme = off_call.get('scheme', 'inside_zone')
        key = 'finesse' if PL.S.RUN_SCHEMES[scheme]['family']=='zone' else 'power'
        wins = [PL.edge(PL.rate(b,PL.RUN_BLOCK['blocker'][key]),PL.rate(a['player'],PL.RUN_BLOCK['defender']['shed']))
                for b,a in zip(matches,front) if b is not None]
        push = float(np.mean(wins)) if wins else 0
        fill = float(np.mean([PL.rate(d,PL.RUN_BLOCK['defender']['fill']) for d in defenders[:7]]))
        result = original_run(off,deff,off_call,def_call,ytg,rng)
        result['_audit_run'] = dict(push=push,fill=fill,mean_ybc=PL.RUN_BASE+3.5*push-2*(fill-PL.AVG),
                                   box=def_call['box'],scheme=scheme,noise=PL.RUN_NOISE)
        return result

    def record_kick(yardline_100, kicker, rng, rate_fn, snapper=None):
        # Mirror the probability calculation, without drawing from RNG.
        distance = yardline_100 + 17
        probability = game.fg_probability(distance, kicker, rate_fn) * (game.ENV.kick_mult if distance >= 35 else 1 - .3 * (1 - game.ENV.kick_mult))
        noise = float(kicker.get('st_noise', 1)) if isinstance(kicker, dict) else 1
        if noise != 1:
            probability = float(np.clip(.5 + (probability - .5) / noise, .02, .99))
        probability = float(np.clip(probability + .02 * game.snap_quality(snapper, rate_fn), .005, .995))
        result = original_kick(yardline_100, kicker, rng, rate_fn, snapper)
        kicks.append(dict(context, distance=distance, probability=probability, made=bool(result['made']),
                          kicker=kicker.get('pid'), kick_mult=game.ENV.kick_mult))
        return result

    game.attempt_field_goal = record_kick
    PL._run_play = record_run
    PL._pass_play = record_pass
    PL.resolve_protection = record_protection
    try:
        for seed in seeds:
            league = LG.build_league(rng=np.random.default_rng(seed))
            runner = SN.SeasonRunner(league, np.random.default_rng(seed + 1000))
            teams = sorted(league.teams)
            np.random.default_rng(seed).shuffle(teams)
            for home, away in zip(teams[::2], teams[1::2]):
                context.update(seed=seed, home=home, away=away)
                result = runner.play(home, away, 1)
                collector.add(result)
                reps, wins = Counter(), Counter()
                team_counts = {}
                for side, team, opponent in [('home', home, away), ('away', away, home)]:
                    team_rows = recap.plays(result, side)
                    team_counts[team] = recap.stats(team_rows)
                    for p in team_rows:
                        for pid, won in p.get('pr_reps') or []:
                            reps[pid] += 1
                            wins[pid] += bool(won)
                        rows.append(dict(seed=seed, offense=team, defense=opponent,
                            **{k:p.get(k) for k in ('type','yards','down','ydstogo','clock','score_diff','box','box_count','personnel','pressured','blitz','screen','runner','sacker','converted','touchdown','ybc','yac','front','_audit_run','_audit_rush')},
                            conversion=recap.converted(p)))
                book = runner._book.p
                mismatches = sum((line.get('pr_reps',0),line.get('pr_wins',0)) != (reps[pid],wins[pid]) for pid,line in book.items())
                games.append(dict(context, home_score=result['home'], away_score=result['away'],
                                  rush_accounting_mismatches=mismatches, teams=team_counts))
                for team in (home, away):
                    state = runner.states[team]
                    counts = state.last_snap_counts.get('defense', {})
                    for player in league.teams[team].active():
                        if player.pos not in ('LEDG','REDG','DT','MIKE','WILL','SAM'): continue
                        line = book.get(player.pid,{})
                        depth = state.roster.get('depth',{}).get(player.pos,[])
                        rank = next((i+1 for i,p in enumerate(depth) if p.get('pid')==player.pid),None)
                        players.append(dict(seed=seed, team=team, name=player.name, pid=player.pid,
                            pos=player.pos, ovr=round(player.ovr,2), rank=rank,
                            snaps=counts.get('players',{}).get(player.pid,0), total_snaps=counts.get('total',0),
                            **{k:line.get(k,0) for k in ('pr_reps','pr_wins','pressures','sacks')}))
                print(f'seed {seed}: {home} {result["home"]}-{result["away"]} {away}',flush=True)
    finally:
        game.attempt_field_goal = original_kick
        PL._run_play = original_run
        PL._pass_play = original_pass
        PL.resolve_protection = original_protection

    def run_summary(items):
        runs = [p for p in items if p['type']=='run']
        return dict(carries=len(runs), yards=sum(p['yards'] or 0 for p in runs),
                    raw_losses=sum(p['yards']<0 for p in runs),
                    displayed_losses=sum(round(p['yards'])<0 for p in runs),
                    at_least_5=sum(p['yards']>=5 for p in runs))
    thirds = {}
    for p in rows:
        if p['down'] != 3: continue
        distance = p['ydstogo'] or 10
        band = '1-2' if distance<=2 else '3-4' if distance<=4 else '5-7' if distance<=7 else '8+'
        for key in (band,band+('/run' if p['type']=='run' else '/dropback')):
            cell=thirds.setdefault(key,dict(attempts=0,converted=0))
            cell['attempts']+=1; cell['converted']+=int(p['conversion'])
    fg = {}
    for p in kicks:
        d=p['distance']; band='<40' if d<40 else '40-49' if d<50 else '50-54' if d<55 else '55-59' if d<60 else '60+'
        cell=fg.setdefault(band,dict(attempts=0,made=0,expected=0))
        cell['attempts']+=1;cell['made']+=p['made'];cell['expected']+=p['probability']
    pressure={}
    for p in players:
        role='edge' if p['pos'] in ('LEDG','REDG') else 'interior' if p['pos']=='DT' else 'offball'
        for key in (role,role+('/elite' if p['ovr']>=88 else '/other')):
            cell=pressure.setdefault(key,dict(player_games=0,snaps=0,pr_reps=0,pr_wins=0,pressures=0,sacks=0))
            cell['player_games']+=1
            for stat in ('snaps','pr_reps','pr_wins','pressures','sacks'):cell[stat]+=p[stat]
    return dict(seeds=seeds, games=games, register=collector.got(), runs=run_summary(rows),
                runs_by_offense={t:run_summary([p for p in rows if p['offense']==t]) for t in sorted({p['offense'] for p in rows})},
                runs_by_seed={s:run_summary([p for p in rows if p['seed']==s]) for s in seeds},
                third_down=thirds, field_goals=fg, pressure=pressure,
                players=players,kicks=kicks,plays=rows,
                limitations='Fresh 2026 rosters, week-one games; no development, accumulated fatigue, or reproduction of the user 2027 roster. Observational outcomes do not prove causal tuning requirements.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--seeds',nargs='+',type=int,default=[100101,100102,100103,100104])
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    Path(args.out).write_text(json.dumps(run(args.seeds),indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
