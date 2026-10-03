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
from inbox import player_name as inbox_player
import copy
from dataclasses import asdict
from collections import defaultdict
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
    import offense_roles as OR
    pers = OR.package_weights(gm)
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
        box_bias=(float(getattr(gm, 'box', 0.5)) - 0.5) * 0.5,
        front_pref=fronts,
        run_scheme_mix=run_mix,
        personnel_mix=pers, off_personnel=base,
        depth_mix=depth_mix,
        pass_bias=float(getattr(gm, 'pass_lean', 0.5) - 0.5) * 0.25,   # x4 in log-odds inside pass_rate
        play_action_rate=float(getattr(gm, 'play_action', 0.5)),
        motion_rate=float(getattr(gm, 'motion', 0.5)),
        tempo=float(getattr(gm, 'tempo', 0.5)),
        fourth_down=float(getattr(gm, 'fourth_down', 0.5)),
        travel_willingness=float(np.clip(gm.aggression, .05, .95)),
        off_script_skill=float(np.clip(gm.patience, .1, .9)))


class StandingsView:
    """Read current results using the same tiebreakers, without simulation state."""

    def __init__(self, league):
        self.L = league

    # ---- standings ------------------------------------------------------
    def completed(self):
        """(home, away, home_pts, away_pts) for every finished game."""
        return [(h, a, hp, ap) for _wk, a, h, ap, hp in self.L.schedule
                if hp is not None and _wk <= 18]                 # playoff games sit in the schedule (weeks 19-22) but never count in the standings

    def season_state(self):
        """The tiebreaker engine, fed from live results instead of history."""
        div = {a: t.division for a, t in self.L.teams.items()}
        conf = {a: t.conf for a, t in self.L.teams.items()}
        td_for = {a: 0 for a in div}
        td_against = {a: 0 for a in div}
        unknown = set()
        saved = getattr(self.L, 'team_game_stats', {}) or {}
        for wk, away, home, ap, hp in self.L.schedule:
            if hp is None or wk > 18: continue
            rows = saved.get(f'{self.L.year}-{wk}-{home}-{away}', {})
            if any('touchdowns' not in rows.get(a, {}) for a in (home, away)):
                unknown.update((home, away))
                continue
            for a, opponent in ((home, away), (away, home)):
                td_for[a] += rows[a]['touchdowns']
                td_against[a] += rows[opponent]['touchdowns']
        net_td = {a: td_for[a] - td_against[a] for a in div if a not in unknown}
        return SS.Season.live(div, conf, self.completed(), self.L.year, net_td)

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


class SeasonRunner(StandingsView):
    """
    Runs one regular season on a live League.

    Owns the per-team TeamState for the whole year, which is the reason this
    is a class and not a function: health has to survive between weeks.
    """

    def __init__(self, league, rng=None):
        self.L = league
        self.last_games = []; self.last_played = []                 # the strip and the notes read these; a runner built on a load starts empty
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
            self.states[abbr].defer_recovery = True
            self._staff_terms(abbr)
        self.week = 0

    @staticmethod
    def _state_data(st, include_roster=False):
        """Plain data needed to carry a team's health and replay a live game."""
        d = dict(defer_recovery=getattr(st, "defer_recovery", False),
                 cond=dict(st.cond.cond), cond_snaps=dict(st.cond.snaps),
                 cond_policy=st.cond.policy, jaded=dict(st.jaded),
                 snaps=dict(st.snaps), last_snaps=dict(getattr(st, 'last_snaps', {}) or {}),
                 snap_counts=copy.deepcopy(getattr(st, 'snap_counts', {})),
                 last_snap_counts=copy.deepcopy(getattr(st, 'last_snap_counts', {})),
                 plan=asdict(st.plan), base_plan=asdict(st.base_plan),
                 script=dict(st.script.__dict__), coach=copy.deepcopy(st.coach),
                 scheme=copy.deepcopy(st.scheme),
                 memories={unit: dict(series=mem.series, window=mem.window,
                          by_series={str(k): dict(v) for k, v in mem.by_series.items()})
                           for unit, mem in st.memories.items()},
                 last_adjustment=copy.deepcopy(st.last_adjustment),
                 injuries=copy.deepcopy(st.injuries), out=sorted(st.out),
                 cov_memory=dict(st.cov_memory),
                 staff_fx=copy.deepcopy(getattr(st, 'staff_fx', {})),
                 coach_base=copy.deepcopy(getattr(st, 'coach_base', {})),
                 seq=copy.deepcopy(getattr(st, 'seq', {})),
                 road_noise=getattr(st, 'road_noise', 1.0),
                 road_stamina=getattr(st, 'road_stamina', 1.0))
        if include_roster:
            d['roster'] = copy.deepcopy(st.roster)
        return d

    @staticmethod
    def _restore_state(st, d):
        import gameplan as GP, adjust as AD
        identity_skill = float((getattr(st, 'coach_base', None) or st.coach)
                               .get('adjust_skill', .5))
        st.defer_recovery = d.get('defer_recovery', True)
        if 'roster' in d: st.roster = d['roster']
        st.cond.cond = dict(d.get('cond') or {})
        st.cond.snaps = dict(d.get('cond_snaps') or {})
        st.cond.policy = d.get('cond_policy', st.cond.policy)
        st.jaded = dict(d.get('jaded') or {})
        st.snaps = dict(d.get('snaps') or {})
        st.last_snaps = dict(d.get('last_snaps') or {})
        st.snap_counts = copy.deepcopy(d.get('snap_counts') or {})
        st.last_snap_counts = copy.deepcopy(d.get('last_snap_counts') or {})
        if d.get('plan'): st.plan = GP.Gameplan(**d['plan'])
        if d.get('base_plan'): st.base_plan = GP.Gameplan(**d['base_plan'])
        if d.get('script'): st.script.__dict__.update(d['script'])
        if 'coach' in d: st.coach = copy.deepcopy(d['coach'])
        if 'scheme' in d: st.scheme = d['scheme']
        # Old `mem` mixed both teams' offensive possessions. It cannot be
        # assigned a trustworthy perspective; start fresh rather than guess.
        st.memories = {}
        for unit in ('offense', 'defense'):
            md = (d.get('memories') or {}).get(unit) or {}
            mem = AD.GameMemory(window=md.get('window', 4))
            mem.series = md.get('series', 0)
            mem.by_series = defaultdict(lambda: defaultdict(list),
                    {int(k): defaultdict(list, v) for k, v in (md.get('by_series') or {}).items()})
            st.memories[unit] = mem
        st.last_adjustment = (copy.deepcopy(d.get('last_adjustment'))
                              if d.get('memories') else None)
        st.injuries = list(d.get('injuries') or [])
        st.out = set(d.get('out') or [])
        st.cov_memory = dict(d.get('cov_memory') or {})
        st.staff_fx = d.get('staff_fx') or {}
        st.coach_base = d.get('coach_base') or {}
        if 'memories' not in d:
            # A replay can start here without _staff_terms. Old coach skill
            # included either coordinator's shared bonus; use the unboosted
            # saved base (or the freshly constructed identity) immediately.
            baseline = float(st.coach_base.get('adjust_skill', identity_skill))
            st.coach['adjust_skill'] = baseline
            for unit in ('off', 'def'):
                st.coach['adjust_skill_' + unit] = min(1.0, baseline +
                        (.15 if st.staff_fx.get('sharp_' + unit) else 0.0))
        st.seq = d.get('seq') or {'run_hot': 0.0}
        st.road_noise = d.get('road_noise', 1.0)
        st.road_stamina = d.get('road_stamina', 1.0)

    def save_state(self):
        return dict(week=self.week, listed_week=getattr(self, '_listed_week', None),
                    after_done=getattr(self, '_after_done', None),
                    states={a: self._state_data(st) for a, st in self.states.items()},
                    desks={a: copy.deepcopy(d.__dict__) for a, d in self.desks.items()},
                    last_played=list(self.last_played),
                    last_games=[(h, a, r['home'], r['away'], bool(r.get('overtime')))
                                for h, a, r, _b in self.last_games])

    def load_state(self, data):
        self.week = data.get('week', self.week)
        self._listed_week = data.get('listed_week')
        self._after_done = data.get('after_done')
        for a, sd in (data.get('states') or {}).items():
            if a in self.states: self._restore_state(self.states[a], sd)
        for a, dd in (data.get('desks') or {}).items():
            if a in self.desks: self.desks[a].__dict__.update(dd)
        self.last_played = [tuple(row) for row in (data.get('last_played') or [])]
        self.last_games = []
        for h, a, hs, away_score, ot in (data.get('last_games') or []):
            self.last_games.append((h, a, dict(home=hs, away=away_score, overtime=ot), G.StatBook()))

    # ---- the field ------------------------------------------------------
    def injury_week(self, week):
        """
        Wednesday. Every club re-lists its hurt, puts the long-term cases on
        IR, brings back whoever has served his four games, and decides who is
        playing through something.
        """
        IS.clear_recovered(self.L, week, self.desks)
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
        # Elevated men dress under the same health and effective-rating rules.
        import game_availability as GA
        rows = [dict(MO.effective_ratings_from(PC.effective_ratings(p), p),
                     pid=p.pid, pos=p.pos, weight=getattr(p, 'weight', None), traits=dict(p.traits or {}))
                for p in GA.dressed(t, desk, self.week)]
        # a man playing hurt plays with the injury's hit on his ratings this Sunday
        if desk is not None and desk.playing_hurt:
            import injury_status as IS
            for r in rows:
                d = desk.playing_hurt.get(r['pid'])
                if d:
                    p_ = self.L.player(r['pid']); hits, _risk = IS.hurt_profile(p_, d)
                    for a, v in hits.items(): r[a] = max(1.0, float(r.get(a, 60.0)) + v)
        units = R.build_roster_rows(rows, t.scheme, pins=getattr(t, 'depth_pins', None),
                                    front=getattr(t.gm, 'def_front', '4-3'),
                                    box=getattr(t.gm, 'box', 0.5))
        # FIT ON THE FIELD: the depth chart is ordered on the card, then every player dresses with his
        # scheme fit on his game-day ratings (field_fit), centered at the league mean for his spot
        self._apply_field_fit(rows, t)
        return units

    def _fit_centers(self):
        """League mean game-day move on each attribute at each position this week, from every active
        player through his own club's tags (field_fit.centers)."""
        key = (int(self.L.year), int(self.week))
        cache = getattr(self, '_fit_center_cache', None)
        if cache and cache[0] == key:
            return cache[1]
        import field_fit as FF
        by_pos = {}
        for t in self.L.teams.values():
            tags = getattr(t, 'scheme', None); rig = float(getattr(t.gm, 'scheme_rigidity', 0.5)) if getattr(t, 'gm', None) else 0.5
            for p in t.active():
                by_pos.setdefault(p.pos, []).append(FF.deltas(p.ratings, p.pos, tags, rig))
        c = FF.centers(by_pos)
        self._fit_center_cache = (key, c)
        return c

    def _apply_field_fit(self, rows, t):
        import field_fit as FF
        tags = getattr(t, 'scheme', None)
        if not tags:
            return
        rig = float(getattr(t.gm, 'scheme_rigidity', 0.5)) if getattr(t, 'gm', None) else 0.5
        centers = self._fit_centers()
        for r in rows:
            pos = r.get('pos')
            r.update(FF.shifted(r, pos, FF.deltas(r, pos, tags, rig), centers))

    def refresh_identity(self, abbr):
        """Replace cached coaching identity between games without resetting health."""
        live = getattr(self, 'live', None)
        if live and not live.get('done', False): return False
        import gameplan as GP, gameplan_week as GW, json
        t = self.L.teams[abbr]; st = self.states[abbr]
        coach = make_coach(t.gm)
        # Save JSON turns tuples into lists; that alone is not an identity change.
        if (json.dumps(getattr(st, 'coach_base', None), sort_keys=True) == json.dumps(coach, sort_keys=True)
                and st.scheme == t.scheme):
            return False
        st.coach_base = copy.deepcopy(coach)
        st.coach = copy.deepcopy(coach)
        st.scheme = copy.deepcopy(t.scheme)
        st.base_plan = GP.base_plan(coach)
        st.plan = st.base_plan.copy()
        st.script.off_script_skill = coach.get('off_script_skill', .5)
        self._fit_center_cache = None
        if abbr == getattr(self.L, 'user_team', None):
            wp = getattr(self.L, 'user_week_plan', None) or {}
            if wp.get('year') == self.L.year and wp.get('week', -1) >= self.week:
                GW.user_plan(self.L, st, wp['week'])
        self._staff_terms(abbr)
        return True

    def refresh(self, abbr):
        import practice_integration as PI
        PI.restore_transfers(self, abbr)
        self.refresh_identity(abbr)
        self.states[abbr].roster = self._units(abbr)
        r = self.states[abbr].roster
        # the special teams coordinator rides on the kicker's dict into the game
        if r and isinstance(r.get('k'), dict):
            import staff as ST
            r['k']['st_noise'] = ST.kick_noise_mult(self.L.teams[abbr]) if getattr(self.L.teams[abbr], 'staff', None) else 1.0
        return r

    # ---- one game -------------------------------------------------------
    def _venue(self, week, playoffs):
        """The building a game is played in when it is not the home club's: the Championship Game's neutral site."""
        if not playoffs or week < 22: return None
        try:
            import postseason as PS
            return PS.sb_venue(self.L)['abbr']
        except Exception: return None

    def prepare_practice(self, week, clubs=None):
        import player_age as PA
        PA.game_week(self.L, week)
        import practice_integration as PI
        return PI.prepare(self, week, clubs)

    def require_available(self, abbr, week, playoffs=False):
        import game_availability as GA
        GA.ensure(self.L, self.L.teams[abbr], self.desks.get(abbr), week, playoffs)
        roster = self.refresh(abbr)
        if roster is None:
            raise GA.FieldabilityError(f'Week {week}: {abbr} has no valid game roster')
        return roster

    def play(self, home, away, week, playoffs=False):
        self.prepare_practice(week, (home, away))
        hr = self.require_available(home, week, playoffs)
        ar = self.require_available(away, week, playoffs)
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
            st.plan = st.base_plan.copy()
            try:
                if me == user: GW.user_plan(self.L, st, week)
                else: GW.ai_plan(self.L, st, me, opp, week, self.rng)
            except Exception:
                pass
        import game_recap as GR
        review = GR.capture(self.L, self.states[user], week) if user in (home, away) else None
        book = G.StatBook()
        self._book = book
        res = G.play_game(hr, ar, self.rng, P.resolve_play, self.co, self.cd,
                          P.rate, home_state=self.states[home],
                          away_state=self.states[away], week=week, book=book,
                          playoffs=playoffs, venue=self._venue(week, playoffs))
        if review is not None: res['coaching_review'] = dict(pregame=review, halftime=[])
        self._record(home, away, week, res, book, playoffs)
        if playoffs:
            self.last_games.append((home, away, res, book))
            self.last_played = list(getattr(self, 'last_played', []) or []) + [(home, away, res['home'], res['away'])]
        return res

    # ------------------------------------------------------------ the live game
    def open_live(self, home, away, week, playoffs=False, on_close=None, replay_start=None):
        """The user's game, opened at the opening kick and played on demand. The same preparation as play()
        (hurt players, the week's plans), then the stepped engine held open until Finish."""
        import player_age as PA
        PA.game_week(self.L, week)
        if replay_start is not None:
            self.rng.bit_generator.state = copy.deepcopy(replay_start['rng'])
            for side in (home, away):
                # Replayed states mutate during play; keep the kickoff snapshot frozen
                # so another save/reload (including the OT break) can replay it again.
                self._restore_state(self.states[side], copy.deepcopy(replay_start['states'][side]))
            hr, ar = self.states[home].roster, self.states[away].roster
            start = copy.deepcopy(replay_start)
        else:
            self.prepare_practice(week, (home, away))
            hr = self.require_available(home, week, playoffs)
            ar = self.require_available(away, week, playoffs)
            for side in (home, away):
                desk = self.desks.get(side); st = self.states.get(side)
                if desk is None or st is None: continue
                for pid in desk.playing_hurt:
                    hit, _mult = desk.condition_hit(pid)
                    if hit: st.cond.cond[pid] = max(35.0, st.cond.get(pid) - hit)
            import gameplan_week as GW
            user = getattr(self.L, 'user_team', None)
            for me, opp in ((home, away), (away, home)):
                st = self.states.get(me)
                if st is None or st.plan is None: continue
                st.plan = st.base_plan.copy()
                try:
                    if me == user: GW.user_plan(self.L, st, week)
                    else: GW.ai_plan(self.L, st, me, opp, week, self.rng)
                except Exception: pass
            start = dict(adjustment_version=2, rng=copy.deepcopy(self.rng.bit_generator.state),
                         states={side: self._state_data(self.states[side], include_roster=True)
                                  for side in (home, away)})
            import game_recap as GR
            if user in (home, away): start['pregame_review'] = GR.capture(self.L, self.states[user], week)
        book = G.StatBook(); self._book = book
        gen = G.game_steps(hr, ar, self.rng, P.resolve_play, self.co, self.cd, P.rate, home_state=self.states[home], away_state=self.states[away], week=week, book=book, playoffs=playoffs, venue=self._venue(week, playoffs))
        self.live = dict(gen=gen, home=home, away=away, week=week, book=book, drives=[], current=None, pos='away', score={'home': 0, 'away': 0}, at='kick', done=False, res=None, halftime_open=False, adjustment_period=None, playoffs=playoffs, on_close=on_close, start=start, actions=[])
        return self.live

    def replay_live(self, actions, saved_rng):
        """Rebuild the paused generator by repeating its deterministic user actions."""
        self._replaying_live = True
        try:
            for action in actions:
                if action[0] == 'step':
                    if len(action) >= 4: self.rng.bit_generator.state = action[2]
                    self.live_step(action[1])
                    if len(action) >= 4 and self.rng.bit_generator.state != action[3]:
                        raise ValueError('Saved live game diverged during replay')
                elif action[0] == 'half_take': self.half_take(action[1], action[2])
                else: raise ValueError('Unknown live game action in save')
            if self.live['done']:
                raise ValueError('Saved live game ended during replay')
            # Other GM actions may have consumed RNG between live steps. Keep the
            # saved stream position while preserving the already-replayed game.
            self.rng.bit_generator.state = saved_rng
            self.live['actions'] = list(actions)
        finally:
            self._replaying_live = False

    def live_step(self, mode='play'):
        """Advance the live game: 'play' one snap, 'drive' to the end of the possession, 'half' to halftime or the
        end, 'finish' to the next break/end. Both halftime and overtime require 'resume'."""
        lv = getattr(self, 'live', None)
        if lv is None or lv['done']: return lv
        if lv['halftime_open'] and mode != 'resume': return lv
        requested_mode = mode
        rng_before = (copy.deepcopy(self.rng.bit_generator.state)
                      if not getattr(self, '_replaying_live', False) else None)
        if mode == 'resume': lv['halftime_open'] = False; mode = 'play'
        gen = lv['gen']
        try:
            while True:
                ev = next(gen)
                kind = ev[0]
                if kind == 'snap':
                    lv['current'] = ev[1]; lv['at'] = 'snap'
                    if mode == 'play': break
                elif kind == 'drive':
                    _k, pos, dr, score = ev; lv['drives'].append((pos, dr)); lv['current'] = None; lv['score'] = dict(score); lv['at'] = 'drive'; lv['pos'] = 'away' if pos == 'home' else 'home'
                    if mode == 'drive': break          # in play mode the end of a drive rides with its last play; the next click is the next snap
                elif kind == 'halftime':
                    lv['score'] = dict(ev[1]); lv['halftime_open'] = True; lv['at'] = 'halftime'; lv['adjustment_period'] = 'halftime'; lv['pos'] = 'home'
                    self._halftime_read(lv); break
                elif kind == 'overtime':
                    lv['score'] = dict(ev[1]); lv['at'] = 'overtime'; lv['halftime_open'] = True
                    lv['adjustment_period'] = 'overtime'
                    self._halftime_read(lv); break
        except StopIteration as done:
            lv['res'] = done.value; lv['done'] = True; lv['current'] = None; lv['score'] = {'home': lv['res']['home'], 'away': lv['res']['away']}; lv['at'] = 'final'
            self._close_live()
        if not getattr(self, '_replaying_live', False):
            lv['actions'].append(('step', requested_mode, rng_before,
                                  copy.deepcopy(self.rng.bit_generator.state)))
        return lv

    def _halftime_read(self, lv):
        """Read the completed half or regulation for the active adjustment window."""
        import halftime as HT
        user = getattr(self.L, 'user_team', None)
        me_side = 'home' if lv['home'] == user else 'away'
        opp = lv['away'] if me_side == 'home' else lv['home']
        st = self.states.get(user)
        period = lv.get('adjustment_period') or 'halftime'
        rec_key = 'ot_recs' if period == 'overtime' else 'half_recs'
        if st is None or st.plan is None: lv[rec_key] = []; return
        lv['adjustment_base'] = st.plan.copy()
        if period == 'halftime':
            lv['half_plan_before'] = dict(protection=getattr(st.plan, 'protection', None))
        try: recs = HT.recommendations(self.L, user, opp, lv['drives'], me_side, lv['score'], st.plan, st.base_plan, period=period, legacy=lv['start'].get('adjustment_version', 1) < 2)
        except Exception as e:
            import sys; print('halftime read failed:', e, file=sys.stderr); recs = []
        for i, r in enumerate(recs): r['i'] = i; r['taken'] = False
        lv[rec_key] = recs

    def half_take(self, i, on=True):
        """Accept/withdraw a choice at the current break; preserve the plan entering that break."""
        import gameplan_week as GW
        lv = getattr(self, 'live', None)
        if lv is None or not lv['halftime_open']: return False
        recs = lv.get('ot_recs' if lv.get('adjustment_period') == 'overtime' else 'half_recs') or []
        if i < 0 or i >= len(recs): return False
        r = recs[i]; user = getattr(self.L, 'user_team', None); st = self.states.get(user)
        if r['taken'] == bool(on) or st is None: return True
        if lv['start'].get('adjustment_version', 1) < 2:
            # Preserve the action semantics of saves created before reversible break choices.
            ch = r['changes'] if on else {k: (tuple(-x for x in v) if isinstance(v, (tuple, list)) else (-v if isinstance(v, (int, float)) else st.base_plan.__dict__.get(k, v))) for k, v in r['changes'].items()}
            GW.apply_changes(st.plan, st.base_plan, ch); r['taken'] = bool(on)
        else:
            r['taken'] = bool(on)
            st.plan = lv['adjustment_base'].copy()
            for accepted in recs:
                if accepted['taken']: GW.apply_changes(st.plan, st.base_plan, accepted['changes'])
        lv['half_taken'] = [x['text'] for x in recs if x['taken']]
        if not getattr(self, '_replaying_live', False): lv['actions'].append(('half_take', i, bool(on)))
        return True

    def _close_live(self):
        """The live game is over: recorded exactly as a simmed game, and the week's after-game steps run."""
        lv = self.live; res = lv['res']; home, away, week = lv['home'], lv['away'], lv['week']
        res['coaching_review'] = dict(pregame=copy.deepcopy(lv['start'].get('pregame_review')),
            halftime=[copy.deepcopy(r) for r in lv.get('half_recs', []) if r.get('taken')],
            halftime_declined=[copy.deepcopy(r) for r in lv.get('half_recs', []) if not r.get('taken')],
            halftime_existing=copy.deepcopy(lv.get('half_plan_before', {})),
            overtime=[copy.deepcopy(r) for r in lv.get('ot_recs', []) if r.get('taken')])
        if lv.get('playoffs'):
            # a playoff game: the stats book, but no standings; the bracket takes the result
            self._record(home, away, week, res, lv['book'], True)
            self.last_games.append((home, away, res, lv['book']))
            if lv.get('on_close') is not None: lv['on_close'](res)
            return
        self._record(home, away, week, res, lv['book'], False)
        self.last_games.append((home, away, res, lv['book']))
        for i, (wk, a_, h_, ap, hp) in enumerate(self.L.schedule):
            if wk == week and h_ == home and a_ == away: self.L.schedule[i] = (wk, a_, h_, res['away'], res['home'])
        self.last_played = list(getattr(self, 'last_played', []) or []) + [(home, away, res['home'], res['away'])]
        self._after_games(week, self.last_played)

    def live_partial(self):
        """The live game as a result-shaped record for Game Day: the drives so far and the one in progress."""
        lv = getattr(self, 'live', None)
        if lv is None: return None
        drives = list(lv['drives'])
        score = dict(lv['score'])
        if lv['current'] is not None:
            drives = drives + [(lv['pos'], lv['current'])]
            # the points of a drive that has scored show with the scoring play, before the drive's own event lands
            pts = int(getattr(lv['current'], 'points', 0) or 0)
            if pts > 0: score[lv['pos']] += pts
            elif pts < 0: score['away' if lv['pos'] == 'home' else 'home'] += abs(pts)
        return dict(home=score['home'], away=score['away'], drives=drives, overtime=(lv['at'] == 'overtime' or (lv['res'] or {}).get('overtime')), env=(lv['res'] or {}).get('env'), live=not lv['done'], at=lv['at'], halftime_open=lv['halftime_open'], half_recs=lv.get('ot_recs' if lv.get('adjustment_period') == 'overtime' else 'half_recs') or [], adjustment_period=lv.get('adjustment_period'))

    def _record(self, home, away, week, res, book, playoffs=False):
        import gameplan_week as GW
        GW.record_game(self.L, home, away, res)
        GW.record_team_performance(self.L, home, away, week, res)
        import practice_integration as PI
        PI.record_health(self, (home, away))
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

            # Every player on the active roster gets a small game-day credit,
            # including reserves and injured players who still hold a roster
            # spot. IR is excluded by active(); elevations join the roster.
            depth = (st.roster or {}).get('depth', {})
            team = self.L.teams[side]
            rostered = {p.pid: p for p in team.active()}
            rostered.update((p.pid, p) for p in (getattr(team, '_elevated', None) or []))
            for p in rostered.values():
                p.xp += XP.credit(p, XP.GAME_DAY_XP * XP.modifier(p), 'roster')

            # Kicks and punts are logged as plays but do not go through the
            # ordinary offensive/defensive snap picker. Credit the first
            # dressed long snapper from those real attempts and outcomes.
            long_snappers = depth.get('LS', [])
            if long_snappers:
                p = self.L.player(long_snappers[0]['pid'])
                if p is not None:
                    line = XP.long_snap_line(res['drives'], 'home' if side == home else 'away')
                    if line['snaps']:
                        self.L.record_stats(self.L.year, p.pid, dict(line, games=1),
                                            postseason=playoffs, game=key)
                        p.xp += XP.credit(p, XP.long_snap_xp(line) * XP.modifier(p), 'long_snap')

        # Injuries come off the RESULT, not off TeamState. play_game calls
        # end_game() on both states before returning, which clears
        # state.injuries - so reading them there always found an empty list
        # and every injury in the league silently vanished.
        for inj in res['injuries']:
            p = self.L.player(inj['player'])
            if p is None: continue
            weeks = int(inj['weeks_out'])
            p.out_until = week + weeks
            p.xp_spent['_inj_kind'] = inj.get('kind'); p.xp_spent['_inj_week'] = week
            k_ = f"_inj_count_{inj.get('kind')}"; p.xp_spent[k_] = int(p.xp_spent.get(k_, 0) or 0) + 1
            p.injury_history.append(dict(year=self.L.year, week=week,
                                         weeks_out=weeks, kind=inj['kind'],
                                         season_ending=inj['season_ending']))
            self.L.log('injury', pid=p.pid, team=p.team, weeks=weeks,
                       injury=inj['kind'])
        import game_recap as GR
        GR.post(self.L, home, away, week, res, playoffs)
        GR.post_snap_counts(self.L, home, away, week, self.states, playoffs)
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
        st.staff_fx['short_kick_bias'] = ST.short_kick_bias(t)
        if not getattr(st, 'coach_base', None):
            # Older saves can contain an empty base and an already-boosted
            # coach. Rebuild from the GM where available, not that staff total.
            st.coach_base = (make_coach(t.gm) if getattr(t, 'gm', None) is not None
                             else dict(st.coach))
        st.coach = dict(st.coach_base)
        baseline = float(st.coach_base.get('adjust_skill', 0.5))
        for unit in ('off', 'def'):
            st.coach['adjust_skill_' + unit] = min(1.0, baseline +
                    (0.15 if st.staff_fx.get('sharp_' + unit) else 0.0))

    def play_games(self, week):
        self.prepare_practice(week)
        completed = any(wk == week and hp is not None for wk, _a, _h, _ap, hp in self.L.schedule)
        if not completed:
            self.L.week_book = {}                                    # this Sunday's lines only
        previous = {(h, a): (res, book) for h, a, res, book in self.last_games} if self.week == week else {}
        for abbr_, desk_ in self.desks.items():
            desk_.resolve_pending(self.L, self.L.teams[abbr_], self.rng); self.refresh(abbr_)
        for abbr in self.states: self._staff_terms(abbr)          # a staff change since last Sunday counts
        """The games only. Sunday: every scheduled game this week, the scores written back,
        expired injuries cleared. The week itself has not rolled; that is roll_week."""
        self.week = week
        if getattr(self, '_listed_week', None) != week:
            self.injury_week(week)                      # a week that was never listed (the first, or a loaded save) lists now
            self._listed_week = week
        played = []
        self.last_games = []                      # (home, away, res, book) for Game Day
        skip = getattr(self, '_skip_game', None)
        for i, (wk, away, home, ap, hp) in enumerate(self.L.schedule):
            if wk != week: continue
            if hp is not None:
                played.append((home, away, hp, ap))
                res, book = previous.get((home, away),
                                         (dict(home=hp, away=ap, overtime=False), G.StatBook()))
                self.last_games.append((home, away, res, book))
                continue
            if skip and (home, away) == skip: continue          # the user's game is played live, after these
            res = self.play(home, away, week)
            if res is None:
                from game_availability import FieldabilityError
                raise FieldabilityError(f'Week {week}: {away} at {home} returned no result')
            self.last_games.append((home, away, res, self._book))
            self.L.schedule[i] = (wk, away, home, res['away'], res['home'])
            played.append((home, away, res['home'], res['away']))

        self.week = week
        self.L.week = week
        self.last_played = played
        if not skip: self._after_games(week, played)
        return played

    def _after_games(self, week, played):
        """Once every game of the week is in (the user's live game included): expired injuries clear, playing-hurt
        flares roll, and the week's club and league notes post. Runs once a week."""
        # Direct/live callers may finish one game before the rest of the slate.
        # Never settle the whole week early; roll_week rejects unfinished games.
        if any(w == week and (ap is None or hp is None)
               for w, a, h, ap, hp in self.L.schedule): return played
        if getattr(self, '_after_done', None) == week: return
        self._after_done = week
        from cap_accounting import settle_week
        settle_week(self.L,week)
        # anyone whose injury has expired is available again
        for p in self.L.players.values():
            if p.out_until is not None and p.out_until <= week:
                p.out_until = None
        # men who played hurt: did it flare?
        for abbr_, desk_ in self.desks.items():
            for p_, wks in desk_.flare(self.L, self.L.teams[abbr_], week, self.rng):
                if abbr_ == getattr(self.L, 'user_team', None):
                    import inbox as IB
                    IB.post(self.L, 'injury', f"{inbox_player(p_)} aggravated the {str(p_.xp_spent.get('_inj_kind') or 'injury').lower()}", f"{inbox_player(p_)} ({p_.pos}) played through it and it went again; he is out {wks} more week{'s' if wks != 1 else ''}.", sender='trainers')
        try:
            import club_notes as CN, league_notes as LN
            CN.after_games(self.L, week, played)
            LN.standings(self.L, week)
            LN.big_result(self.L, week, played)
        except Exception as e:
            import sys; print('notes after games failed:', e, file=sys.stderr)
        return played

    def roll_week(self, week, played=None):
        """The week after Sunday: XP spent, morale, agents, promises, next week's report,
        the wire, the squads, the trade window. Called by Advance once the games are in."""
        from game_availability import require_scores
        require_scores(self.L, week)
        if played is None: played = getattr(self, 'last_played', []) or []
        self.week = week
        self.L.week = week
        # CPU clubs spend accumulated XP every third week. User auto-spend
        # still runs weekly; other user players keep XP for manual spending.
        XS.spend_week(self.L, week, self.rng,
                      user_team=getattr(self.L, 'user_team', None))
        import inbox as IB, practice_squad as PSQ, waivers as WV, morale as MO
        # MORALE moves with the week: results, usage against what each player
        # believes he is owed, the room, benchings
        results = {}
        for home, away, hs, as_ in played:
            results[home] = ('W' if hs > as_ else 'L' if hs < as_ else 'T', hs - as_)
            results[away] = ('W' if as_ > hs else 'L' if as_ < hs else 'T', as_ - hs)
        # Advancing the calendar supplies the rest before next week's decisions.
        # All clubs recover here; practice and game preparation never add rest.
        import practice_integration as PI
        PI.recover_week(self, int(week) + 1)
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
        # Recovery belongs to the next decision week, before its roster
        # assessments, assistant report and injury listings are prepared.
        IS.clear_recovered(self.L, week + 1, self.desks)
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
        import staff as STF_
        STF_.midseason_review(self.L, self.rng, week)
        # the assistants' report on next week's opponent, into the inbox now
        if week < 18:
            import gameplan_week as GW
            try: GW.post_report(self.L, week + 1)
            except Exception: pass
        IB.expire(self.L, week)
        # THE WIRE: award last week's claims first (the user had the week to
        # claim from the inbox), then notify the user of this week's waivers
        WV.process(self.L, self.rng, week)
        # WEDNESDAY: next week's injury report is listed now, so the Questionable and Doubtful decisions sit in
        # the inbox all week and are answered before Sunday, not thirty seconds before the kick
        if week < 18:
            self.injury_week(week + 1); self._listed_week = week + 1
        try:
            import club_notes as CN, league_notes as LN
            CN.weekly(self.L, week)
            LN.transactions(self.L, week)
            import staff as STF_; STF_.resolve_references(self.L, advanced=True)
        except Exception as e:
            import sys; print('club_notes weekly failed:', e, file=sys.stderr)
        # the squads: elevations for clubs short of healthy players, the odd poach
        # This prepares the NEXT game; week 18 rolls before the calendar
        # changes phase, but its elevations already belong to the playoffs.
        PSQ.weekly(self.L, self.rng, week, user_team=getattr(self.L, 'user_team', None),
                   playoffs=week >= 18)
        try:
            import extensions as EXT
            EXT.in_season_round(self.L, self.rng, week)          # a few clubs extend their expiring starters each week
        except Exception as e:
            import sys; print('in-season extensions failed:', e, file=sys.stderr)
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
        import roster_advisor as RA
        RA.weekly(self.L, week)
        WV.notify_user(self.L, WV.pending(self.L), week)
        return played

    def run(self, weeks=WEEKS, verbose=False):
        self.L.set_phase('regular')
        for wk in range(1, weeks + 1):
            got = self.play_week(wk)
            if verbose:
                print(f'  week {wk:2d}: {len(got)} games')
        self.finish()
        return self.standings()

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
