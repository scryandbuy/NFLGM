"""
SESSION. What the browser talks to.

  s = Session.new(team='KC', seed=2026)  /  Session.load(json_text)
  s.next_label()          what the Advance button says
  s.advance()             one stop on the calendar: a week, the playoffs, one offseason step
  s.portal()              the Portal's data
  s.save()                json text

THE CALENDAR AS STOPS. franchise.play_year runs a whole year in one call;
the Advance button cannot, because the user acts between stops (a claim on
Tuesday, the draft, free agency). So the year is the same code as play_year
cut at every point where the user gets a turn. The labels are what the
button reads. Anything the user must do before a stop is a blocking
decision the Portal shows on the button.
"""
import json, numpy as np
import league as LG, season as SN, postseason as PS, awards as AW, coaching_pool as CP, position_change as PC
import morale as MO, staff as STF, almanac as AL, xp as XP, dev_roll as DR, retirement as RT, regression as RG
import schedule as SCH, contracts as CT, waivers as WV, extensions as EXT, tags as TG, market as MK, trades as TRD
import draft_class as DC, scouting as SC, spring as SP, draft as DFT, practice_squad as PSQ, cutdown as CD, newgens as NG
import gameplan_week as GW, inbox as IB, negotiations as NG_
from franchise import prune_pool

WEEKS = 18


class Session:
    def __init__(self, league, rng, user_team):
        self.L = league; self.rng = rng; self.user_team = user_team
        self.L.user_team = user_team
        self.runner = None
        self.post = None; self.order = None; self.fired = []; self.votes = None
        self.standings = None
        # where we are: ('week', n) | ('playoffs',) | ('offseason', i)
        self.stop = getattr(league, '_stop', None) or ('week', 1)
        self.gameday = None
        self.gamedays = {}
        self.played = False
        self.draft = None

    # ------------------------------------------------------------ construction
    @classmethod
    def new(cls, team='KC', seed=None):
        rng = np.random.default_rng(seed)
        L = LG.build_league(rng=rng)
        L.user_team = team
        # the first class sits on the scouting board all season, the way every class after it does
        DC.build(L, rng, draft_year=L.year + 1)
        L.next_class = list(L.draft_pool); L.draft_pool = []
        SC.scout(L, rng)
        s = cls(L, rng, team)
        s.stop = ('cutdown',)
        try: GW.post_report(L, 1)
        except Exception: pass
        return s

    @classmethod
    def load(cls, text):
        d = json.loads(text)
        L = LG.League.load(text)
        s = cls(L, np.random.default_rng(d.get('_seed_state', None)), d.get('_user_team'))
        s.stop = tuple(d.get('_stop', ['week', 1]))
        s.gameday = d.get('_gameday'); s.gamedays = d.get('_gamedays') or {}; s.played = bool(d.get('_played', False))
        s.standings = d.get('_standings'); s.order = d.get('_order'); s.fired = [tuple(x) if isinstance(x, list) else x for x in (d.get('_fired') or [])]
        if d.get('_post'):
            class _Post:            # the shape awards, prestige and the almanac read
                pass
            class _R:
                def __init__(self, seeds): self._s = seeds
                def seeds(self): return self._s
            pp = d['_post']; s.post = _Post(); s.post.champion = pp.get('champion'); s.post.finalists = pp.get('finalists') or {}
            s.post.games = [tuple(g) for g in pp.get('games') or []]; s.post.r = _R(pp.get('seeds') or {}); s.post.seeds_at_close = pp.get('seeds') or {}
        s.draft = None
        if d.get('_draft_live'):
            import draft_day as DD
            s.draft = DD.Draft(s.L, s.rng, d['_draft_live']['year'], user_team=s.user_team, auto_pick=False)
            s.draft.taken = set(pid for pid in d['_draft_live']['taken'] if pid in s.L.players)
            s.draft.results = [(sel, t, s.L.players[pid]) for sel, t, pid in d['_draft_live']['results'] if pid in s.L.players]
        return s

    def save(self):
        d = json.loads(self.L.save())
        d['_stop'] = list(self.stop); d['_seed_state'] = int(self.rng.integers(0, 2**31)); d['_user_team'] = self.user_team
        d['_gameday'] = self.gameday
        d['_gamedays'] = getattr(self, 'gamedays', None) or {}
        d['_played'] = bool(getattr(self, 'played', False))
        # the offseason reads what the playoffs left: standings for the new schedule, the fired
        # coaches for the carousel, and the postseason (champion, finalists, games, seeds) for
        # awards, prestige and the almanac. Without these a save between the playoffs and the
        # New Year could not be resumed.
        d['_standings'] = self.standings
        d['_fired'] = [list(x) if isinstance(x, (list, tuple)) else x for x in (self.fired or [])]
        d['_order'] = self.order
        d['_post'] = None
        if self.post is not None:
            p = self.post
            d['_post'] = dict(champion=p.champion, finalists=dict(p.finalists or {}), games=[list(g) for g in (p.games or [])],
                              seeds=(getattr(p, 'seeds_at_close', None) if getattr(p, 'seeds_at_close', None) is not None else (p.r.seeds() if getattr(p, 'r', None) is not None else {})))
        d['_draft_live'] = dict(year=self.draft.year, taken=sorted(self.draft.taken), results=[(sel, t, p.pid) for sel, t, p in self.draft.results]) if self.draft_live() else None
        return json.dumps(d, default=lambda o: o.item() if hasattr(o, 'item') else str(o))

    # ------------------------------------------------------------ the calendar
    OFFSEASON = [
        ('Season Awards', 'step_awards'),
        ('Coaching Carousel', 'step_coaching'),
        ('Retirements and Development', 'step_retire'),
        ('New Year: Cap and Contracts', 'step_roll'),
        ('Offseason Waivers', 'step_waivers_1'),
        ('Extensions and Tags', 'step_extensions'),
        ('Free Agency', 'step_market'),
        ('Offseason Trades', 'step_trades'),
        ('The Spring: Combine and Pro Days', 'step_spring'),
        ('The Draft', 'step_draft'),
        ('Camp and Next Year\'s Class', 'step_camp'),
        ('Cut-Down to 53', 'step_cutdown'),
    ]

    def next_label(self):
        k = self.stop[0]
        if k == 'cutdown':
            n = len(self.L.teams[self.user_team].active())
            return dict(title='Cut-Down Day', sub=(f"Cut to 53 first · you are at {n}" if n > self.ROSTER_MAX else 'The league goes to 53; the cuts hit the wire'), played=False)
        if k == 'wire':
            import waivers as WV
            n = sum(1 for e in WV.pending(self.L) if e.get('ahead', None) is None and e.get('from_team') != self.user_team and self.L.player(e['pid']) is not None and self.L.player(e['pid']).team is None)
            return dict(title='Sim to Reg. Season', sub=f"{n} on the wire reach your priority · claim any first", played=False)
        if k == 'week':
            wk = self.stop[1]; opp = self._opponent(wk)
            if getattr(self, 'played', False):
                return dict(title=(f"Advance to Week {wk + 1}" if wk < WEEKS else 'Advance to the Playoffs'), sub=(f"Week {wk} is in the books"), played=True)
            return dict(title=f"Sim Week {wk}", sub=(f"{'at' if opp and opp[1] else 'vs'} {opp[0]}" if opp else 'Bye Week'), played=False)
        if k == 'playoffs':
            return dict(title='Play the Playoffs', sub='Wild Card Through the Super Bowl')
        i = self.stop[1]
        if self.draft_live():
            pk = self.draft.current()
            return dict(title='Finish the Draft on Auto', sub=f"or make your pick at {pk.round}.{((pk.selection - 1) % 32) + 1} on Draft Day" if pk else '')
        title, _ = self.OFFSEASON[i]
        return dict(title=title, sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)}")

    ROSTER_MAX, ROSTER_MIN = 53, 46

    def blocking(self):
        """Decisions that must be made before the next stop. Empty list = nothing blocks."""
        out = []
        # THE ROSTER RULE. A club plays with 53 at most and 46 at least; the game will not
        # run a week, or leave camp, until yours is legal. A new franchise starts in camp at
        # 68 and cuts to 53 before week 1, the way every club does.
        if self.stop[0] in ('week', 'cutdown', 'wire') and not getattr(self, 'played', False):
            n = len(self.L.teams[self.user_team].active())
            if n > self.ROSTER_MAX: out.append(dict(id=None, subject=f"Roster at {n}: cut to {self.ROSTER_MAX} before Sunday", kind='roster', go='#club'))
            elif n < self.ROSTER_MIN: out.append(dict(id=None, subject=f"Roster at {n}: sign to at least {self.ROSTER_MIN}", kind='roster', go='#personnel/fa'))
        for m in getattr(self.L, 'inbox', []):
            if m.get('status') in ('unread', 'open') and m.get('kind') in ('trade_offer', 'match_request', 'staff') and m.get('needs_decision', True):
                if m.get('kind') == 'trade_offer' or (m.get('payload') or {}).get('poach'):
                    out.append(dict(id=m.get('id'), subject=m.get('subject'), kind=m.get('kind')))
        return out

    def _league_log_notes(self):
        try:
            import league_notes as LN; LN.transactions(self.L, self.L.week or 0)
            import staff as STF_; STF_.resolve_references(self.L)
        except Exception: pass

    def advance(self):
        k = self.stop[0]
        if k == 'cutdown':
            # camp breaks: every club cuts to 53 (yours must already be there), the wire runs, the squads fill
            if any(b['kind'] == 'roster' for b in self.blocking()):
                return dict(done='Blocked', next=self.next_label(), why=self.blocking()[0]['subject'])
            self.step_cutdown()
            self.stop = ('wire',); self.played = False
            return dict(done='Cutdown', next=self.next_label())
        if k == 'wire':
            self.step_clear_wire()
            self.stop = ('week', 1); self.played = False
            return dict(done='Camp', next=self.next_label())
        if k == 'week':
            wk = self.stop[1]
            if self.runner is None:
                self.runner = SN.SeasonRunner(self.L, self.rng)
            if not getattr(self, 'played', False):
                # SUNDAY: the games are played and Game Day shows them. The week does not roll
                # until Advance, so the GM can read the box score, work the wire and the
                # inbox, and still be in this week.
                self.runner.play_games(wk)
                import gameday as GD
                self.gameday = GD.capture(self.L, getattr(self.runner, 'last_games', []), self.user_team)
                if self.gameday and self.gameday.get('game'):
                    self.gamedays = getattr(self, 'gamedays', None) or {}
                    self.gamedays[f"{self.L.year}-{wk}"] = self.gameday
                self.played = True
                return dict(done=f'Week {wk} played', next=self.next_label())
            # ADVANCE: the week rolls (XP, morale, agents, the report on next week, the wire,
            # the squads, the trade window) and the calendar moves on
            self.runner.roll_week(wk)
            IB.expire(self.L, wk + 1)
            self.played = False
            self.stop = ('week', wk + 1) if wk < WEEKS else ('playoffs',)
            return dict(done=f'Week {wk}', next=self.next_label())
        if k == 'playoffs':
            if self.runner is None: self.runner = SN.SeasonRunner(self.L, self.rng)
            self.standings = self.runner.standings()
            self.post, self.order, self.fired = PS.close_season(self.L, self.runner, self.rng)
            try: self.post.seeds_at_close = self.runner.seeds()      # kept for the save: the runner's standings reset at the New Year
            except Exception: self.post.seeds_at_close = {}
            MO.postseason(self.L, self.post); CP.top_up(self.L, self.rng); PC.offseason(self.L)
            self.stop = ('offseason', 0)
            return dict(done='Playoffs', champion=self.post.champion, next=self.next_label())
        i = self.stop[1]
        if self.draft_live():
            self.draft.auto = True; self.draft.sim_all(); self._draft_over()
        else:
            getattr(self, self.OFFSEASON[i][1])()
            self._league_log_notes()
            if self.draft_live():
                return dict(done='The Draft is on the clock', next=self.next_label())
        if i + 1 < len(self.OFFSEASON):
            self.stop = ('offseason', i + 1)
        else:
            self.stop = ('week', 1); self.runner = None
            try: GW.post_report(self.L, 1)
            except Exception: pass
        return dict(done=self.OFFSEASON[i][0], next=self.next_label())

    # ---- the offseason steps, the same code as franchise.play_year in the same order
    def step_awards(self):
        L, rng = self.L, self.rng
        self.votes = AW.vote(L, self.post)
        CP.season_prestige(L, self.post, coty_team=self.votes.get('coty'))
        STF.season_end(L, STF.unit_ranks(L, L.year))
        AL.close_season(L, L.year, self.post, self.votes)
        XP.close_season(L, self.votes)
        try:
            import club_notes as CN; CN.season_end(L)
        except Exception: pass
        try:
            import league_notes as LN; LN.season_end(L, self.votes)
        except Exception as e:
            import sys; print('league_notes season_end failed:', e, file=sys.stderr)
        DR.run(L, self.votes, rng)

    def step_coaching(self):
        STF.carousel(self.L, self.rng, new_head_coaches=[a for a, _bg in self.fired])

    def step_retire(self):
        L, rng = self.L, self.rng
        RT.run(L, rng); AL.hall_vote(L, L.year); RG.run(L, rng)
        try:
            import league_notes as LN; LN.season_end(L, None)          # the Hall class and the retirements, now that they are in
        except Exception as e:
            import sys; print('league_notes retire failed:', e, file=sys.stderr)

    def step_roll(self):
        self.L.user_tag_choice = None          # a new year, a new tag
        L, rng = self.L, self.rng
        L.roll_year(rng)
        ranks = SCH.division_ranks(L, self.standings); SCH.new_season(L, ranks, rng)
        for t in L.teams.values(): t.record = [0, 0, 0]
        L.advance_contracts()
        CT.run(L, rng); CT.enforce(L, rng)

    def step_waivers_1(self):
        L, rng = self.L, self.rng
        WV.notify_user(L, WV.pending(L), 0, digest=True); WV.process(L, rng, 0)

    def step_extensions(self):
        L, rng = self.L, self.rng
        MO.check_resolutions(L, week=None); MO.clear_free_agents(L); prune_pool(L, rng)
        MO.offseason_requests(L, rng); MO.offseason_reset(L); MO.offseason_contracts(L, rng)
        EXT.ai_round(L, rng); EXT.notify_user(L)
        TG.run(L, rng); CT.enforce(L, rng)

    def step_market(self):
        L, rng = self.L, self.rng
        L.set_phase('free_agency')
        MK.run(L, rng, user_team=self.user_team)

    def step_trades(self):
        TRD.run(self.L, self.rng, rounds=2, exclude=(self.user_team,) if self.user_team else ())

    def step_spring(self):
        L, rng = self.L, self.rng
        if getattr(L, 'next_class', None):
            L.draft_pool = L.next_class; L.next_class = []
        else:
            DC.build(L, rng, draft_year=L.year); SC.scout(L, rng)
        SP.run_spring(L, rng)

    def step_draft(self):
        """The draft with you at the buttons. Sims to your first pick and stops; Draft Day
        takes it from there, and an Advance from the Portal finishes it on auto."""
        import draft_day as DD
        self.draft = DD.Draft(self.L, self.rng, self.L.year - 1, user_team=self.user_team, auto_pick=False)
        self.draft.sim_to_user()
        if self.draft.done:
            self._draft_over()

    def _draft_over(self):
        D = self.draft
        if D is None: return
        if not D.done: D._finish()
        self.L.last_draft = dict(year=D.year, results=[(s, t, p.pid) for s, t, p in D.results], trades=len(D.trades))
        self.draft = None

    def draft_live(self):
        return self.draft is not None and not self.draft.done

    def step_camp(self):
        L, rng = self.L, self.rng
        PSQ.udfa_camp(L, rng); NG.build(L, rng, draft_year=L.year + 1); SC.scout(L, rng)

    def step_cutdown(self):
        L, rng = self.L, self.rng
        for t in L.teams.values():
            for p in list(PSQ.squad(t)): PSQ.release_from_squad(L, t.abbr, p.pid)
        PSQ.reset_season(L)
        CD.finalize(L, rng)
        # the cuts are on the wire; the GM reads it and claims before it clears (the next step)
        WV.notify_user(L, WV.pending(L), 0, digest=True)

    def step_clear_wire(self):
        """Cut-down waivers clear: claims awarded by priority, the squads fill, the undrafted pile is settled, the season opens."""
        L, rng = self.L, self.rng
        WV.process(L, rng, 0)
        PSQ.fill_squads(L, rng)
        from franchise import clear_undrafted
        clear_undrafted(L, rng)
        L.set_phase('regular')

    # ------------------------------------------------------------ helpers
    def _opponent(self, week):
        for (wk, away, home, ap, hp) in getattr(self.L, 'schedule', []) or []:
            if wk == week and self.user_team in (home, away):
                is_away = away == self.user_team
                return (home if is_away else away, is_away)
        return None

    # ------------------------------------------------------------ views
    def portal(self):
        import views
        return views.portal(self, self.L, self.user_team)

    def club_roster(self, abbr=None):
        import views_club as VC
        v = VC.roster(self, self.L, abbr or self.user_team)
        v['club_abbr'] = abbr or self.user_team; v['mine'] = (abbr or self.user_team) == self.user_team
        return v

    def club_list(self):
        from views import club
        return [dict(club(a), mine=(a == self.user_team)) for a in sorted(self.L.teams)]

    def team_page(self, abbr):
        import views_league as VL; return VL.team_page(self, self.L, self.user_team, abbr)

    def club_card(self, pid):
        import views_club as VC
        pool = list(getattr(self.L, 'draft_pool', None) or []) + list(getattr(self.L, 'next_class', None) or [])
        if any(q.pid == pid for q in pool):
            import views_draft as VD; return VD.prospect_card(self, self.L, self.user_team, pid)
        return VC.card(self, self.L, pid)

    def club_depth(self, package='Nickel', abbr=None):
        import views_club as VC
        v = VC.depth(self, self.L, abbr or self.user_team, package)
        v['club_abbr'] = abbr or self.user_team; v['mine'] = (abbr or self.user_team) == self.user_team
        return v

    def club_act(self, name, **kw):
        """Roster and depth actions from the page; the page re-reads the view after."""
        import views_club as VC
        fn = getattr(VC, 'act_' + name, None)
        if fn is None: return dict(ok=False, why='unknown action')
        if name == 'elevate': kw['week'] = self.stop[1] if self.stop[0] == 'week' else 1
        return fn(self.L, self.user_team, **kw)

    # ---- personnel
    def personnel(self, page, **kw):
        import views_personnel as VP
        return getattr(VP, page)(self, self.L, self.user_team, **kw)

    def personnel_act(self, name, **kw):
        import views_personnel as VP
        fn = getattr(VP, 'act_' + name, None)
        if fn is None: return dict(ok=False, why='unknown action')
        r = fn(self.L, self.user_team, **kw)
        return r if isinstance(r, dict) else dict(ok=bool(r))

    # ---- front office
    def frontoffice(self, page, **kw):
        import views_frontoffice as VF
        return getattr(VF, page)(self, self.L, self.user_team, **kw)

    def frontoffice_act(self, action, **kw):
        import views_frontoffice as VF
        fn = getattr(VF, 'act_' + action, None)
        if fn is None: return dict(ok=False, why='unknown action')
        r = fn(self.L, self.user_team, **kw)
        return r if isinstance(r, dict) else dict(ok=bool(r))

    # ---- draft
    def draft_view(self, page, **kw):
        import views_draft as VD
        return getattr(VD, page)(self, self.L, self.user_team, **kw)

    def draft_act(self, name, **kw):
        import views_draft as VD
        fn = getattr(VD, 'act_' + name, None)
        if fn is None: return dict(ok=False, why='unknown action')
        r = fn(self, self.L, self.user_team, **kw)
        return r if isinstance(r, dict) else dict(ok=bool(r))

    # ---- league
    def league_view(self, page, **kw):
        import views_league as VL
        return getattr(VL, page)(self, self.L, self.user_team, **kw)

    # ---- game plan
    def plan_view(self, page, **kw):
        import views_gameplan as VG
        return getattr(VG, page)(self, self.L, self.user_team, **kw)

    def plan_act(self, name, **kw):
        import views_gameplan as VG
        fn = getattr(VG, 'act_' + name, None)
        if fn is None: return dict(ok=False, why='unknown action')
        r = fn(self, self.L, self.user_team, **kw)
        return r if isinstance(r, dict) else dict(ok=bool(r))

    def plan_take_all(self):
        import views_gameplan as VG
        wk = self.stop[1] if self.stop[0] == 'week' else None
        if wk is None: return dict(ok=False, why='no game this week')
        import gameplan_week as GW
        opp = self._opponent(wk)
        if opp is None: return dict(ok=False, why='bye week')
        rep = GW.opponent_report(self.L, self.user_team, opp[0], wk); n = 0
        for i in range(len(rep['suggestions'])):
            r = VG.act_take(self, self.L, self.user_team, i); n += int(bool(r.get('ok')))
        return dict(ok=True, n=n, line=f"Took {n} suggestion{'s' if n != 1 else ''}.")

    def inbox_mark_all(self):
        n = 0
        for m in getattr(self.L, 'inbox', []):
            if m.get('status') == 'unread': m['status'] = 'read'; n += 1
        return dict(ok=True, n=n)

    def inbox_read(self, mid):
        for m in getattr(self.L, 'inbox', []):
            if m['id'] == int(mid) and m.get('status') == 'unread': m['status'] = 'read'
        return dict(ok=True)

    def inbox_delete(self, mid):
        box = getattr(self.L, 'inbox', [])
        self.L.inbox = [m for m in box if m['id'] != int(mid)]
        return dict(ok=True)

    def inbox_clear_read(self):
        import views
        box = getattr(self.L, 'inbox', [])
        keep = [m for m in box if m.get('status') == 'unread' or (m.get('status') in ('unread', 'open') and m.get('kind') in views.DECIDE_KINDS)]
        n = len(box) - len(keep); self.L.inbox = keep
        return dict(ok=True, n=n)

    def inbox_message(self, mid):
        import views
        m = next((m for m in getattr(self.L, 'inbox', []) if m['id'] == int(mid)), None)
        if m is None: return dict(error='no such message')
        pl = m.get('payload') or {}
        return dict(id=m['id'], subject=m['subject'], body=m.get('body') or '', tag=views.INBOX_TAG.get(m.get('kind'), (m.get('kind') or '').title()), kind=m.get('kind'), from_=m.get('sender'),
                    **{'from': m.get('sender')}, when=(f"{m.get('year')} · Week {m.get('week')}" if m.get('week') else str(m.get('year') or '')), link=pl.get('link'), decide=(m.get('status') in ('unread', 'open') and m.get('kind') in views.DECIDE_KINDS))

    def portal_full(self):
        """The Portal view with every inbox message (the Portal itself keeps the recent fourteen)."""
        import views
        v = views.portal(self, self.L, self.user_team)
        v['inbox'] = views._inbox(self.L, limit=None)
        return v

    def gameday_view(self, week=None, year=None):
        import views
        if week is not None:
            gd = (getattr(self, 'gamedays', None) or {}).get(f"{year or self.L.year}-{int(week)}")
            if gd is not None: return views.gameday(self, self.L, self.user_team, gd=gd)
        return views.gameday(self, self.L, self.user_team)
