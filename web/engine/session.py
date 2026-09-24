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

    # ------------------------------------------------------------ construction
    @classmethod
    def new(cls, team='KC', seed=None):
        rng = np.random.default_rng(seed)
        L = LG.build_league(rng=rng)
        L.user_team = team
        s = cls(L, rng, team)
        try: GW.post_report(L, 1)
        except Exception: pass
        return s

    @classmethod
    def load(cls, text):
        d = json.loads(text)
        L = LG.League.load(text)
        s = cls(L, np.random.default_rng(d.get('_seed_state', None)), d.get('_user_team'))
        s.stop = tuple(d.get('_stop', ['week', 1]))
        return s

    def save(self):
        d = json.loads(self.L.save())
        d['_stop'] = list(self.stop); d['_seed_state'] = int(self.rng.integers(0, 2**31)); d['_user_team'] = self.user_team
        return json.dumps(d)

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
        if k == 'week':
            wk = self.stop[1]; opp = self._opponent(wk)
            return dict(title=f"Play Week {wk}", sub=(f"{'at' if opp and opp[1] else 'vs'} {opp[0]}" if opp else 'Bye Week'))
        if k == 'playoffs':
            return dict(title='Play the Playoffs', sub='Wild Card Through the Super Bowl')
        i = self.stop[1]
        title, _ = self.OFFSEASON[i]
        return dict(title=title, sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)}")

    def blocking(self):
        """Decisions that must be made before the next stop. Empty list = nothing blocks."""
        out = []
        for m in getattr(self.L, 'inbox', []):
            if m.get('status') in ('unread', 'open') and m.get('kind') in ('trade_offer', 'match_request', 'staff') and m.get('needs_decision', True):
                if m.get('kind') == 'trade_offer' or (m.get('payload') or {}).get('poach'):
                    out.append(dict(id=m.get('id'), subject=m.get('subject'), kind=m.get('kind')))
        return out

    def advance(self):
        k = self.stop[0]
        if k == 'week':
            wk = self.stop[1]
            if self.runner is None:
                self.runner = SN.SeasonRunner(self.L, self.rng)
            self.runner.play_week(wk)
            self.stop = ('week', wk + 1) if wk < WEEKS else ('playoffs',)
            return dict(done=f'Week {wk}', next=self.next_label())
        if k == 'playoffs':
            if self.runner is None: self.runner = SN.SeasonRunner(self.L, self.rng)
            self.standings = self.runner.standings()
            self.post, self.order, self.fired = PS.close_season(self.L, self.runner, self.rng)
            MO.postseason(self.L, self.post); CP.top_up(self.L, self.rng); PC.offseason(self.L)
            self.stop = ('offseason', 0)
            return dict(done='Playoffs', champion=self.post.champion, next=self.next_label())
        i = self.stop[1]
        getattr(self, self.OFFSEASON[i][1])()
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
        DR.run(L, self.votes, rng)

    def step_coaching(self):
        STF.carousel(self.L, self.rng, new_head_coaches=[a for a, _bg in self.fired])

    def step_retire(self):
        L, rng = self.L, self.rng
        RT.run(L, rng); AL.hall_vote(L, L.year); RG.run(L, rng)

    def step_roll(self):
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
        DFT.run(self.L, self.rng, year=self.L.year - 1, user_team=self.user_team)

    def step_camp(self):
        L, rng = self.L, self.rng
        PSQ.udfa_camp(L, rng); NG.build(L, rng, draft_year=L.year + 1); SC.scout(L, rng)

    def step_cutdown(self):
        L, rng = self.L, self.rng
        for t in L.teams.values():
            for p in list(PSQ.squad(t)): PSQ.release_from_squad(L, t.abbr, p.pid)
        PSQ.reset_season(L)
        CD.finalize(L, rng)
        WV.notify_user(L, WV.pending(L), 0, digest=True); WV.process(L, rng, 0)
        PSQ.fill_squads(L, rng)
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
