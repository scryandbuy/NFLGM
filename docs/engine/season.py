"""
THE SEASON.

This is the seam. The game engine could play one game between two roster
dicts; the League held 32 real teams and the real 272-game schedule; and the
two had never met. Everything downstream - firing, draft order, free agency,
progression, awards - reads a season's results, so none of it could be built
until a season produced them.

THREE THINGS THIS HAS TO GET RIGHT:

1. HEALTH CARRIES. A TeamState is created once per season and reused every
   week, so condition, jadedness and injuries persist. Building a fresh one
   per game would reset every injury at kickoff and the injury system would
   quietly do nothing across a season.

2. THE FIELD REFLECTS THE ROSTER. Units are rebuilt from the live roster each
   week, so a released or injured man actually disappears and his backup
   actually plays. A roster frozen at load would make every transaction
   cosmetic.

3. STATS LAND TWICE. On the player's own career line and in the league's book,
   by decision - the player so his history travels with him through trades and
   retirement, the league so leaderboards and awards can be computed without
   walking 2,114 players.
"""
import numpy as np

import game as G
import plays as P
import schemes as S
import rosters as R
import standings_and_seeding as SS
import injury_status as IS
import xp as XP
import xp_spend as XS
import trades as TR

WEEKS = 18                      # 17 games, one bye apiece


def _deps():
    """The scheme-layer callers the drive loop takes."""
    # The drive loop hands the callers the offence, the defence and rate_fn
    # so the identity layer and the coverage call can read the rosters. These
    # lambdas swallowed none of that and the season runner crashed on the
    # first snap - the register's own callers forward it, which is why the
    # register ran and the franchise calendar did not.
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(
        d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(
        oc, d, di, r, yards_to_endzone=ytg, **kw)
    return co, cd


def make_coach(gm):
    """
    The coach ratings the drive loop reads. GM and head coach are the same
    actor by decision, so these come off the GM rather than a second person.
    The adjustment engine's hooks are wired here; play styles and scheme
    identity are still tabled.
    """
    if gm is None:
        return dict(adjust_skill=.5, adjust_willingness=.5, man_rate=.35,
                    blitz_rate=.133, travel_willingness=.5, off_script_skill=.5)
    # WHAT HE RUNS, from the identity on the GM object. These are the leans
    # the play caller and the coverage call read; the situation still
    # decides the call and the lean moves the odds.
    fronts = {'4-3': ['4-3 over', '4-3 under', 'wide 9'], '3-4': ['3-4 one', '3-4 two', 'tite', 'mint'],
              'multiple': ['4-3 over', '3-4 one', 'tite', 'bear']}.get(getattr(gm, 'def_front', '4-3'), ['4-3 over', '4-3 under'])
    blocking = getattr(gm, 'off_blocking', 'zone')
    run_mix = {'zone': {'zone': .80, 'gap': .20}, 'gap': {'zone': .25, 'gap': .75}}.get(blocking, {'zone': .55, 'gap': .45})
    base = getattr(gm, 'off_personnel', '11')
    pers = {'11': .595, '12': .195, '21': .070, '13': .030, '10': .075, '22': .025, '00': .010}
    if base in pers:
        pers[base] += 0.20                    # his base grouping, a fifth more often
        pers = {k: v / sum(pers.values()) for k, v in pers.items()}
    deep = float(getattr(gm, 'deep', 0.5))
    depth_mix = (0.62 - 0.12 * (deep - 0.5), 0.24, 0.14 + 0.12 * (deep - 0.5))
    return dict(
        adjust_skill=float(np.clip(0.35 + 0.5 * gm.board_trust, .1, .95)),
        adjust_willingness=float(np.clip(gm.aggression, .1, .95)),
        man_rate=float(np.clip(getattr(gm, 'coverage', 0.25), 0.0, 1.0)),
        shell_lean=float(getattr(gm, 'shell', 0.5)),
        zone_aggression=float(getattr(gm, 'zone_aggression', 0.5)),
        bracket_willingness=float(np.clip(0.3 + 0.5 * getattr(gm, 'aggression', 0.5), 0.1, 0.9)),
        blitz_lean=float(getattr(gm, 'blitz', 0.35)),
        blitz_rate=0.133,
        front_pref=fronts,
        run_scheme_mix=run_mix,
        personnel_mix=pers,
        depth_mix=depth_mix,
        pass_bias=float(getattr(gm, 'pass_lean', 0.5) - 0.5) * 0.25,   # x4 in log-odds inside pass_rate
        play_action_rate=float(getattr(gm, 'play_action', 0.5)),
        motion_rate=float(getattr(gm, 'motion', 0.5)),
        tempo=float(getattr(gm, 'tempo', 0.5)),
        fourth_down=float(getattr(gm, 'fourth_down', 0.5)),
        travel_willingness=float(np.clip(gm.aggression, .05, .95)),
        off_script_skill=float(np.clip(gm.patience, .1, .9)))


class SeasonRunner:
    """
    Runs one regular season on a live League.

    Owns the per-team TeamState for the whole year, which is the reason this
    is a class and not a function: health has to survive between weeks.
    """

    def __init__(self, league, rng=None):
        self.L = league
        self.rng = rng or np.random.default_rng()
        self.co, self.cd = _deps()
        self.states = {}
        self.books = {}
        # one injury desk a club, for the season: designations, the IR list
        # and how many returns it has left
        self.desks = {a: IS.InjuryDesk() for a in league.teams}
        self.week = 0
        for abbr, t in league.teams.items():
            coach = make_coach(t.gm)
            self.states[abbr] = G.TeamState(self._units(abbr), coach=coach,
                                            scheme=t.scheme)
            self.states[abbr].abbr = abbr
            self._staff_terms(abbr)
        self.week = 0

    # ---- the field ------------------------------------------------------
    def injury_week(self, week):
        """
        Wednesday. Every club re-lists its hurt, puts the long-term cases on
        IR, brings back whoever has served his four games, and decides who is
        playing through something.
        """
        for abbr, team in self.L.teams.items():
            desk = self.desks[abbr]
            desk.activate_from_ir(self.L, team, week)
            desk.set_week(self.L, team, week, self.rng)

    def _units(self, abbr):
        """
        Rebuild the roster dicts the engine wants from the LIVE roster, so a
        release or an injury shows up on the field immediately instead of
        being frozen at load.
        """
        t = self.L.teams[abbr]
        desk = self.desks.get(abbr)
        import position_change as PC, morale as MO
        rows = [dict(MO.effective_ratings_from(PC.effective_ratings(p), p), pid=p.pid, pos=p.pos)
                for p in t.active()
                if (desk.available(p, self.week) if desk
                    else p.out_until is None)]
        # game-day elevations from the practice squad dress this week
        rows += [dict(p.ratings, pid=p.pid, pos=p.pos) for p in getattr(t, '_elevated', [])]
        return R.build_roster_rows(rows, t.scheme, pins=getattr(t, 'depth_pins', None))

    def refresh(self, abbr):
        self.states[abbr].roster = self._units(abbr)
        r = self.states[abbr].roster
        # the special teams coordinator rides on the kicker's dict into the game
        if r and isinstance(r.get('k'), dict):
            import staff as ST
            r['k']['st_noise'] = ST.kick_noise_mult(self.L.teams[abbr]) if getattr(self.L.teams[abbr], 'staff', None) else 1.0
        return r

    # ---- one game -------------------------------------------------------
    def play(self, home, away, week, playoffs=False):
        hr, ar = self.refresh(home), self.refresh(away)
        if hr is None or ar is None:          # a roster too thin to field
            return None
        # A man playing hurt does not start the game fresh. Condition drives
        # injury risk on a violently nonlinear curve, so this is also what
        # makes him likelier to break down again - the cost of playing him is
        # real and it is a choice, not a penalty.
        for side in (home, away):
            desk = self.desks.get(side)
            st = self.states.get(side)
            if desk is None or st is None:
                continue
            for pid in desk.playing_hurt:
                hit, _mult = desk.condition_hit(pid)
                if hit:
                    st.cond.cond[pid] = max(35.0, st.cond.get(pid) - hit)
        # THE WEEK'S PLAN. Each coordinator reads the assistants' report on
        # the other side and takes what he takes; the user's saved changes
        # apply to his club. The state's plan resets when the game ends.
        import gameplan_week as GW
        user = getattr(self.L, 'user_team', None)
        for me, opp in ((home, away), (away, home)):
            st = self.states.get(me)
            if st is None or st.plan is None: continue
            try:
                if me == user: GW.user_plan(self.L, st, week)
                else: GW.ai_plan(self.L, st, me, opp, week, self.rng)
            except Exception:
                pass
        book = G.StatBook()
        self._book = book
        res = G.play_game(hr, ar, self.rng, P.resolve_play, self.co, self.cd,
                          P.rate, home_state=self.states[home],
                          away_state=self.states[away], week=week, book=book,
                          playoffs=playoffs)

        # ---- record ------------------------------------------------------
        GW.record_game(self.L, home, away, res)
        H, A = self.L.teams[home], self.L.teams[away]
        if playoffs:
            pass                      # postseason does not touch the record
        elif res['home'] > res['away']:
            H.record[0] += 1; A.record[1] += 1
        elif res['away'] > res['home']:
            A.record[0] += 1; H.record[1] += 1
        else:
            H.record[2] += 1; A.record[2] += 1

        key = f'{self.L.year}-{week}-{home}-{away}'
        # this week's lines, league-wide, for the honors note
        wb = self.L.__dict__.setdefault('week_book', {})
        for pid, line in book.p.items():
            wb[pid] = dict(line)
        for pid, line in book.p.items():
            self.L.record_stats(self.L.year, pid, line,
                                postseason=playoffs, game=key)
            # XP EARNED, game by game: the events plus every weekly line he
            # crossed. The ledger existed and nothing paid into it. Postseason
            # games pay like any other; the season and milestone lines are
            # settled at the end of the year (xp.close_season).
            p = self.L.player(pid)
            if p is not None:
                p.xp += XP.credit(p, XP.game_xp(p, line, self.L.year), 'game')
        # SNAPS AND GAMES. TeamState counts every snap and nothing kept them, so a
        # lineman or a backup finished a season with no record of playing at
        # all - and playing time is the strongest predictor of whether a
        # career continues. Read from last_snaps: play_game calls end_game on
        # both states before returning, which CLEARS state.snaps. Exactly the
        # bug that was silently losing every injury in the league.
        # them, so a lineman or a backup finished a season with no record of
        # having played at all - and playing time is the single strongest
        # predictor of whether a career continues.
        for side in (home, away):
            st = self.states[side]
            import position_change as PC
            for pid, n in (st.last_snaps or st.snaps).items():
                _pp = self.L.player(pid)
                if _pp is not None: PC.played(_pp, n)
                self.L.record_stats(self.L.year, pid, {'snaps': n, 'games': 1},
                                    postseason=playoffs)
                # a snap is worth something on its own: it is why a backup
                # who gets on the field develops and one who does not, does not
                p = self.L.player(pid)
                if p is not None:
                    p.xp += XP.credit(p, XP.event_xp({'snaps': n}) * XP.modifier(p), 'snaps')

        # Injuries come off the RESULT, not off TeamState. play_game calls
        # end_game() on both states before returning, which clears
        # state.injuries - so reading them there always found an empty list
        # and every injury in the league silently vanished.
        for inj in res['injuries']:
            p = self.L.player(inj['player'])
            if p is None: continue
            weeks = int(inj['weeks_out'])
            p.out_until = week + weeks
            p.injury_history.append(dict(year=self.L.year, week=week,
                                         weeks_out=weeks, kind=inj['kind'],
                                         season_ending=inj['season_ending']))
            self.L.log('injury', pid=p.pid, team=p.team, weeks=weeks,
                       injury=inj['kind'])
        return res

    # ---- one week -------------------------------------------------------
    def play_week(self, week):
        """Play every scheduled game in this week and write the scores back, then roll the week."""
        played = self.play_games(week)
        self.roll_week(week, played)
        return played

    def _staff_terms(self, abbr):
        """The staff's Sunday terms onto the state: penalty and fumble factors, and the Sharp on
        Sunday edge as a step in the in-game adjustment skill on that side."""
        import staff as ST
        t = self.L.teams[abbr]; st = self.states[abbr]
        st.staff_fx = ST.game_terms(t)
        if not hasattr(st, 'coach_base'): st.coach_base = dict(st.coach)     # the head coach's own numbers, before any staff edge
        st.coach = dict(st.coach_base)
        if st.staff_fx.get('sharp_off') or st.staff_fx.get('sharp_def'):
            st.coach['adjust_skill'] = min(1.0, float(st.coach_base.get('adjust_skill', 0.5)) + 0.15)

    def play_games(self, week):
        self.L.week_book = {}                                        # this Sunday's lines only
        for abbr in self.states: self._staff_terms(abbr)          # a staff change since last Sunday counts
        """The games only. Sunday: every scheduled game this week, the scores written back,
        expired injuries cleared. The week itself has not rolled; that is roll_week."""
        self.week = week
        self.injury_week(week)
        played = []
        self.last_games = []                      # (home, away, res, book) for Game Day
        for i, (wk, away, home, ap, hp) in enumerate(self.L.schedule):
            if wk != week or hp is not None:
                continue
            res = self.play(home, away, week)
            if res is None:
                continue
            self.last_games.append((home, away, res, self._book))
            self.L.schedule[i] = (wk, away, home, res['away'], res['home'])
            played.append((home, away, res['home'], res['away']))

        # anyone whose injury has expired is available again
        for p in self.L.players.values():
            if p.out_until is not None and p.out_until <= week:
                p.out_until = None
        self.week = week
        self.L.week = week
        self.last_played = played
        try:
            import club_notes as CN
            CN.after_games(self.L, week, played)
        except Exception:
            pass
        return played

    def roll_week(self, week, played=None):
        """The week after Sunday: XP spent, morale, agents, promises, next week's report,
        the wire, the squads, the trade window. Called by Advance once the games are in."""
        if played is None: played = getattr(self, 'last_played', []) or []
        self.week = week
        self.L.week = week
        # THE WEEKLY ADVANCE: every AI club spends what its men earned, and
        # the user's auto-spend men go with them. The user's other players
        # keep their XP until he spends it from the player tab.
        XS.spend_week(self.L, week, self.rng,
                      user_team=getattr(self.L, 'user_team', None))
        import inbox as IB, practice_squad as PSQ, waivers as WV, morale as MO
        # MORALE moves with the week: results, usage against what each man
        # believes he is owed, the room, benchings
        results = {}
        for home, away, hs, as_ in played:
            results[home] = ('W' if hs > as_ else 'L' if hs < as_ else 'T', hs - as_)
            results[away] = ('W' if as_ > hs else 'L' if as_ < hs else 'T', as_ - hs)
        snaps = {}
        for abbr, st in self.states.items():
            for pid, n in (getattr(st, 'last_snaps', None) or st.snaps or {}).items(): snaps[pid] = n
        # a start: he took at least 60% of his club's snaps on the day (the busiest man on his side sets the day's count)
        for abbr_, st_ in self.states.items():
            sn_ = getattr(st_, 'last_snaps', None) or st_.snaps or {}
            if not sn_: continue
            t_ = self.L.teams[abbr_]; off_ = {p.pid: p for p in t_.active()}
            side_max = {}
            for pid_, n_ in sn_.items():
                p_ = off_.get(pid_)
                if p_ is None: continue
                side_ = 'off' if p_.pos in ('QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT') else 'def'
                side_max[side_] = max(side_max.get(side_, 0), n_)
            for pid_, n_ in sn_.items():
                p_ = off_.get(pid_)
                if p_ is None or p_.pos in ('K', 'P', 'LS'): continue
                side_ = 'off' if p_.pos in ('QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT') else 'def'
                if side_max.get(side_, 0) and n_ >= 0.6 * side_max[side_]: p_.xp_spent['_starts'] = int(p_.xp_spent.get('_starts', 0) or 0) + 1
        MO.weekly(self.L, week, results, snaps)
        try:
            import club_notes as CN
            CN.returns(self.L, week + 1)
        except Exception:
            pass
        MO.check_resolutions(self.L, week)
        MO.unresolved_weekly(self.L)
        import negotiations as NG
        NG.resolve(self.L, week=week)          # agents get back to you
        for t in self.L.teams.values():          # coordinators reach XP through the player's club
            for p in t.roster: p._team_ref = t
        NG.check_promises(self.L, week)        # promises not kept are broken
        # the assistants' report on next week's opponent, into the inbox now
        if week < 18:
            import gameplan_week as GW
            try: GW.post_report(self.L, week + 1)
            except Exception: pass
        IB.expire(self.L, week)
        # THE WIRE: award last week's claims first (the user had the week to
        # claim from the inbox), then notify the user of this week's waivers
        WV.process(self.L, self.rng, week)
        WV.notify_user(self.L, WV.pending(self.L), week)
        try:
            import club_notes as CN
            CN.weekly(self.L, week)
        except Exception as e:
            import sys; print('club_notes weekly failed:', e, file=sys.stderr)
        # the squads: elevations for clubs short of healthy men, the odd poach
        PSQ.weekly(self.L, self.rng, week, user_team=getattr(self.L, 'user_team', None))
        # THE TRADE WINDOW. A trickle through the early weeks, the phones
        # busy in the two weeks before the deadline, nothing after it. The
        # user's club is never traded with on its own account.
        if week <= TR.TRADE_DEADLINE_WEEK:
            user = getattr(self.L, 'user_team', None)
            made = TR.run(self.L, self.rng, rounds=1,
                          activity=TR.IN_SEASON_ACTIVITY.get(week, 0.0),
                          exclude=(user,) if user else ())
            for a, b, sends, got, res in made:
                self.L.log('trade_window', buyer=a, seller=b, got=got.pid,
                           sent=[x['pid'] if x['kind'] != 'pick' else 'pick' for x in sends])
        return played

    def run(self, weeks=WEEKS, verbose=False):
        self.L.set_phase('regular')
        for wk in range(1, weeks + 1):
            got = self.play_week(wk)
            if verbose:
                print(f'  week {wk:2d}: {len(got)} games')
        self.finish()
        return self.standings()

    # ---- standings ------------------------------------------------------
    def completed(self):
        """(home, away, home_pts, away_pts) for every finished game."""
        return [(h, a, hp, ap) for _wk, a, h, ap, hp in self.L.schedule
                if hp is not None]

    def season_state(self):
        """The tiebreaker engine, fed from live results instead of history."""
        div = {a: t.division for a, t in self.L.teams.items()}
        conf = {a: t.conf for a, t in self.L.teams.items()}
        return SS.Season.live(div, conf, self.completed(), self.L.year)

    def standings(self):
        S_ = self.season_state()
        ranks = SS.division_ranks(S_)
        out = {}
        for abbr, t in self.L.teams.items():
            w, l, tie = t.record
            out[abbr] = dict(w=w, l=l, t=tie, pct=round(S_.wpct(abbr), 3),
                             div=t.division, div_rank=ranks.get(abbr),
                             pf=S_.pf[abbr], pa=S_.pa[abbr])
        return out

    def seeds(self):
        S_ = self.season_state()
        return {c: SS.seed_conference(S_, c) for c in sorted(set(
            t.conf for t in self.L.teams.values()))}

    def finish(self):
        """Close the year out: records into history, health rolled forward."""
        S_ = self.season_state()
        seeds = self.seeds()
        made = {t for conf in seeds.values() for t in conf}
        self.L.standings_history[self.L.year] = {
            a: dict(record=list(t.record), pct=round(S_.wpct(a), 3),
                    made_playoffs=a in made)
            for a, t in self.L.teams.items()}
        for abbr, t in self.L.teams.items():
            t.history.append(dict(year=self.L.year, win_pct=t.win_pct,
                                  made_playoffs=abbr in made,
                                  record=list(t.record)))


def run_season(league, rng=None, weeks=WEEKS, verbose=False):
    r = SeasonRunner(league, rng)
    import gameplan_week as GW
    try: GW.post_report(league, 1)          # week one's report before the season opens
    except Exception: pass
    r.run(weeks, verbose)
    return r


if __name__ == '__main__':
    import league as LG, time
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    t0 = time.time()
    r = run_season(L, rng, verbose=True)
    print('\nran in %.0fs' % (time.time() - t0))
    st = r.standings()
    for conf, seeds in r.seeds().items():
        print(f'\n{conf} seeds:')
        for i, t in enumerate(seeds, 1):
            s = st[t]
            rec = f'{s["w"]}-{s["l"]}' + (f'-{s["t"]}' if s["t"] else '')
            print(f'  {i}. {t:<4} {rec:<7} {s["div"]:<10}'
                  f' pf {s["pf"]:4d} pa {s["pa"]:4d}')
    print('\npassing leaders:', L.leaders(L.year, 'pass_yds', 3))
    print('rushing leaders:', L.leaders(L.year, 'rush_yds', 3))
    print('injuries logged:',
          sum(1 for x in L.transactions if x['kind'] == 'injury'))
