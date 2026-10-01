"""Controlled register probe. Overrides are process-local, never saved to a game."""
import argparse
import collections
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import calibrate as CB
import plays as P
import schemes as S
import game as G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=93031)
    ap.add_argument('--seasons', type=int, default=1)
    ap.add_argument('--short', type=float)
    ap.add_argument('--single-script', action='store_true')
    ap.add_argument('--coverage-baseline', action='store_true', help='Restore the prior coverage sign in this process only')
    ap.add_argument('--late-lead-baseline', action='store_true', help='Restore the prior late lead override in this process only')
    ap.add_argument('--franchise', action='store_true')
    ap.add_argument('--baseline-ref', help='Use plays.py from a local Git revision for a controlled comparison')
    ap.add_argument('--limit-games', type=int, help='Stop a fixed-roster diagnostic after this many games')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    import coverage_call as CC
    coverage_source = Path(CC.__file__).read_text(encoding='utf-8')
    game_source = Path(G.__file__).read_text(encoding='utf-8')
    if args.late_lead_baseline:
        game_source = subprocess.check_output(['git', 'show', '2b4d240:game.py'], text=True)
        exec(compile(game_source, 'baseline_game.py', 'exec'), G.__dict__)
    if args.coverage_baseline:
        coverage_source = subprocess.check_output(['git', 'show', '737b17f:coverage_call.py'], text=True)
        exec(compile(coverage_source, 'baseline_coverage_call.py', 'exec'), CC.__dict__)
    source = Path(P.__file__).read_text(encoding='utf-8')
    if args.baseline_ref:
        source = subprocess.check_output(['git', 'show', args.baseline_ref + ':plays.py'], text=True)
        exec(compile(source, 'baseline_plays.py', 'exec'), P.__dict__)
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if args.short is not None:
        P.SHORT_PASS_COMPLETION = args.short
    if args.single_script:
        import decisions as D
        old_rate = S.pass_rate
        def script_rate(down, ydstogo, score_diff, yards_to_endzone, off_pers,
                        gm_pass_bias=0.0, secs_left=None):
            p = old_rate(down, ydstogo, score_diff, yards_to_endzone, off_pers,
                         gm_pass_bias, secs_left)
            if secs_left is None:
                return p
            neutral = S._logit(S.NEUTRAL_SCRIPT)
            sd = int(round(score_diff))
            old_script = next((v for lo, hi, v in S.SCRIPT if lo <= sd <= hi), S.NEUTRAL_SCRIPT)
            target = D.pass_rate(score_diff, secs_left)
            weight = 0 if secs_left > 1800 else .25 if secs_left > 900 else .55 if secs_left > 240 else .85
            logodds = S._logit(p) - (S._logit(old_script)-neutral) + (1-weight)*(S._logit(target)-neutral)
            return float(np.clip(S._sigmoid(logodds), .03, .98))
        S.pass_rate = script_rate
    original = CB.Collector.add
    games = []
    drives = collections.defaultdict(collections.Counter)
    calls = collections.defaultdict(collections.Counter)
    defensive_scores = collections.Counter()
    season_reports = []
    diagnostic_collector = None
    original_game = G.play_game
    def strength(roster, state):
        import offense_roles as OR
        import defense_roles as DR
        import targets as T
        depth = roster.get('depth', {})
        excluded = getattr(state, 'out', ()) if state else ()
        offense = OR.assign(depth, '11', excluded=excluded)
        defense = DR.assign(depth, roster.get('front_family', '4-3'), 'base', excluded=excluded)
        off = [T.position_score(p, role) for role, p in offense]
        deff = [T.position_score(row['player'], row['player']['pos']) for row in defense if row.get('player')]
        qb = next(T.position_score(p, role) for role, p in offense if role == 'QB')
        return dict(overall=float(np.mean(off+deff)), offense=float(np.mean(off)),
                    defense=float(np.mean(deff)), qb=float(qb))
    def game(home, away, *a, **kw):
        before = dict(home=strength(home, kw.get('home_state')), away=strength(away, kw.get('away_state')))
        result = original_game(home, away, *a, **kw)
        result['_audit_strength'] = before
        return result
    G.play_game = game
    class ProbeComplete(Exception):
        pass

    def observe(self, result):
        nonlocal diagnostic_collector
        diagnostic_collector = self
        original(self, result)
        score = {'home': 0, 'away': 0}
        half = None
        for side, dr in result['drives']:
            if half is None and dr.quarter >= 3:
                half = dict(score)
            points = dr.points
            scorer = side if points >= 0 else ('away' if side == 'home' else 'home')
            score[scorer] += abs(points)
            band = 'lead17' if dr.score_diff >= 17 else 'trail17' if dr.score_diff <= -17 else 'close'
            drives[band][dr.result] += 1
            return_score_seen = False
            for play in dr.log:
                if not isinstance(play, dict) or play.get('nullified'):
                    continue
                if play.get('defensive_td') and play.get('return_kind') in ('int', 'fumble'):
                    defensive_scores[play['return_kind']] += 1
                    return_score_seen = True
                if play.get('type') not in ('run', 'scramble', 'complete', 'incomplete', 'drop', 'sack', 'interception'):
                    continue
                quarter = min(4, max(1, 4-int(max(0, play.get('clock', dr.clock)-.01)//900)))
                row = calls[f'{band}_Q{quarter}']
                row['snaps'] += 1
                row['passes'] += bool(play.get('is_pass'))
                clock = play.get('clock', dr.clock)
                spot = play.get('yardline', 50)
                if 0 < clock <= 240 and dr.score_diff > 0 and not (spot >= 80 and clock <= 60):
                    down, distance = play.get('down'), play.get('ydstogo', 0)
                    situation = 'first' if down == 1 else 'third_long' if down == 3 and distance >= 6 else None
                    if situation:
                        lead = '1-8' if dr.score_diff <= 8 else '9-16' if dr.score_diff <= 16 else '17+'
                        row = calls[f'late_lead_{situation}_{lead}']
                        row['snaps'] += 1
                        row['passes'] += bool(play.get('is_pass'))
            if dr.result == 'Defensive touchdown' and not return_score_seen:
                defensive_scores['other'] += 1
        games.append(dict(home=result['home'], away=result['away'], halftime=half,
                          strength=result.get('_audit_strength')))
        if len(games) % 64 == 0:
            print(f'{len(games)} games', flush=True)
        if args.limit_games and len(games) >= args.limit_games:
            raise ProbeComplete

    CB.Collector.add = observe
    if args.franchise:
        # Same CPU calendar as the main study; suppress only user-facing stops.
        deps = Path(__file__).resolve().parents[2] / 'outputs' / 'team-study-deps'
        sys.path.insert(0, str(deps))
        import session as SS
        import season as SN
        import views_league as VL
        total, current = CB.Collector(), CB.Collector()
        original_play, original_awards = SN.SeasonRunner.play, VL.awards
        def play(self, home, away, week, playoffs=False):
            result = original_play(self, home, away, week, playoffs)
            if not playoffs:
                if result is None:
                    raise RuntimeError(f'Unplayed fixture {self.L.year} week {week}: {home} at {away}')
                total.add(result)
                original(current, result)
            return result
        SN.SeasonRunner.play = play
        VL.awards = lambda session, league, abbr: original_awards(session, league, abbr or 'KC')
        session = SS.Session.new('KC', seed=args.seed)
        session.user_team = session.L.user_team = None
        session.blocking = lambda: []
        session._ir_ready_notes = lambda week: None
        session._post_review = lambda status: None
        session._snapshot_season = lambda: None
        session._resign_card = lambda: None
        session.next_label = lambda: dict(title='Audit', sub='AI franchise calendar')
        start = time.time()
        for step in range(args.seasons*85):
            year = session.L.year
            result = session.advance()
            if result.get('done') == 'Blocked':
                failure = dict(complete=False, seed=args.seed, year=year, stop=session.stop,
                               error=result, games=total.ngames, seasons_detail=season_reports,
                               plays_sha256=source_hash,
                               got={k: float(v) for k, v in total.got().items()})
                Path(args.out).write_text(json.dumps(failure, indent=2), encoding='utf-8')
                Path(args.out + '.blocked-save.json').write_text(session.save(), encoding='utf-8')
                raise RuntimeError(str(result))
            if step % 8 == 0:
                print(f'{time.time()-start:.0f}s {year} {session.stop} {total.ngames} games', flush=True)
            if result.get('done') == 'Playoffs':
                season_reports.append(dict(year=year, games=current.ngames,
                                           got={k: float(v) for k,v in current.got().items()}))
                assert current.ngames == 272, current.ngames
                current = CB.Collector()
                Path(args.out + '.progress.json').write_text(json.dumps(season_reports, indent=2), encoding='utf-8')
                if len(season_reports) == args.seasons:
                    break
        else:
            raise RuntimeError('Calendar did not finish requested seasons')
        got = total.got()
    else:
        try:
            got = CB.run(args.seasons, args.seed, verbose=False, coaches='catalog')
        except ProbeComplete:
            got = diagnostic_collector.got()
    report = dict(seed=args.seed, seasons=args.seasons, short=P.SHORT_PASS_COMPLETION,
                  game_sha256=hashlib.sha256(game_source.encode('utf-8')).hexdigest(),
                  late_lead_baseline=args.late_lead_baseline,
                  coverage_baseline=args.coverage_baseline,
                  coverage_sha256=hashlib.sha256(coverage_source.encode('utf-8')).hexdigest(),
                  single_script=args.single_script,
                  baseline_ref=args.baseline_ref,
                  plays_sha256=source_hash,
                  franchise=args.franchise, seasons_detail=season_reports,
                  got={k: float(v) for k, v in got.items()},
                  misses=[k for k, target, tol, _ in CB.TARGETS if abs(got[k]-target)>tol],
                  score_sd=float(np.std([g[k] for g in games for k in ('home', 'away')])),
                  drives=drives, calls=calls, defensive_scores=defensive_scores, games=games)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('games', 'drives')}, indent=2))


if __name__ == '__main__':
    main()
