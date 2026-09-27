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
from views import CLUB_NAME as CLUB_NAME_
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
        self.post_live = None
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
        L.seed_tenures(rng)              # not 32 first-year coaches
        L.set_expectations()             # the owners' preseason ask, relative to the league
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
        rng_ = np.random.default_rng(d.get('_seed_state', None))
        try:
            L.seed_tenures(np.random.default_rng(int(d.get('_seed_state', 1) or 1) + 7))       # a save where every coach shares one tenure
            if any(getattr(t, 'expected_cached', None) is None for t in L.teams.values()): L.set_expectations()
        except Exception as e:
            import sys; print('tenure/expectation seed failed:', e, file=sys.stderr)
        s = cls(L, rng_, d.get('_user_team'))
        s.stop = tuple(d.get('_stop', ['week', 1]))
        s.gameday = d.get('_gameday'); s.gamedays = d.get('_gamedays') or {}; s.played = bool(d.get('_played', False))
        if d.get('_post_live'):
            import season as SN
            if s.runner is None: s.runner = SN.SeasonRunner(s.L, s.rng)
            s.post_live = PS.Postseason.from_dict(s.runner, d['_post_live'])
        lp = d.get('_live_pending')
        if lp and s.played and (s.stop[0] == 'week' or (s.stop[0] == 'playoffs' and lp.get('playoffs'))):
            import season as SN
            if s.runner is None: s.runner = SN.SeasonRunner(s.L, s.rng)
            s.runner.week = lp['week']; s.runner.last_games = []; s.runner.last_played = []
            if lp.get('playoffs') and getattr(s, 'post_live', None) is not None:
                post = s.post_live
                held = getattr(post, 'held', None)
                rnd, conf = (held[0], held[1]) if held else (PS.Postseason.ROUNDS[max(0, min(3, int(s.stop[1]) - 1))] if len(s.stop) > 1 else 'WC', 'NFL')
                def _close(res, _c=conf, _h=lp['home'], _a=lp['away'], _r=rnd): post.record(_r, _c, _h, _a, res); post.held = None
                s.runner.open_live(lp['home'], lp['away'], lp['week'], playoffs=True, on_close=_close)
            else:
                s.runner.open_live(lp['home'], lp['away'], lp['week'])
        s.standings = d.get('_standings'); s.order = d.get('_order'); s.fired = [tuple(x) if isinstance(x, list) else x for x in (d.get('_fired') or [])]
        if d.get('_post'):
            class _Post:            # the shape awards, prestige and the almanac read
                pass
            class _R:
                def __init__(self, seeds): self._s = seeds
                def seeds(self): return self._s
            pp = d['_post']; s.post = _Post(); s.post.champion = pp.get('champion'); s.post.finalists = pp.get('finalists') or {}; s.post.year = pp.get('year')
            s.post.games = [tuple(g) for g in pp.get('games') or []]; s.post.r = _R(pp.get('seeds') or {}); s.post.seeds_at_close = pp.get('seeds') or {}
            s.post.seeds = {c: list(sd) for c, sd in (pp.get('seeds') or {}).items()}
            s.post.exit_round = {}; s.post.conf_champs = dict(s.post.finalists); s.post.alive = {}
            for g in s.post.games:
                rnd, conf, home, away, hs, as_ = g[:6]
                lose = away if (hs or 0) >= (as_ or 0) else home
                s.post.exit_round[lose] = rnd
            if s.post.year is None and s.post.champion and s.stop[0] == 'offseason': s.post.year = int(L.year) - (1 if int(getattr(L, 'week', 0) or 0) == 0 else 0)
        s.draft = None
        try:
            # the current season's exit meetings and review exist only once it has closed; anything filed under the
            # current year before then (an older build wrote meetings on a page view) is removed
            if getattr(L, 'season_closed_year', None) != int(L.year):
                (getattr(L, 'exit_meetings', None) or {}).pop(str(L.year), None)
                ((getattr(L, 'history', None) or {}).get(str(L.year)) or {}).pop('review', None)
        except Exception: pass
        try: s._open_fa_if_due()
        except Exception as e:
            import sys; print('open round on load failed:', e, file=sys.stderr)
        try: s._backfill_history()
        except Exception as e:
            import sys; print('history backfill failed:', e, file=sys.stderr)
        if d.get('_draft_live'):
            import draft_day as DD
            s.draft = DD.Draft(s.L, s.rng, d['_draft_live']['year'], user_team=s.user_team, auto_pick=False)
            s.draft.taken = set(pid for pid in d['_draft_live']['taken'] if pid in s.L.players)
            s.draft.results = [(sel, t, s.L.players[pid]) for sel, t, pid in d['_draft_live']['results'] if pid in s.L.players]
        return s

    def save(self):
        d = json.loads(self.L.save())
        if getattr(self, 'post_live', None) is not None:
            d['_post_live'] = self.post_live.to_dict()
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is not None and not lv['done']:
            # a half-played game cannot be written down; the save marks it pending and a load reopens it at the kick
            d['_live_pending'] = dict(home=lv['home'], away=lv['away'], week=lv['week'], playoffs=bool(lv.get('playoffs')))
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
            d['_post'] = dict(champion=p.champion, year=getattr(p, 'year', None), finalists=dict(p.finalists or {}), games=[list(g) for g in (p.games or [])],
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
        ('Re-sign: Tags and Tenders', 'step_extensions'),
        ('Free Agency: Round 1', 'step_fa_1'),
        ('Free Agency: Round 2', 'step_fa_2'),
        ('Free Agency: Round 3', 'step_fa_3'),
        ('Free Agency: Market Closes', 'step_fa_close'),
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
                lv = getattr(self.runner, 'live', None) if self.runner is not None else None
                if lv is not None and not lv['done']:
                    return dict(title='Game Day', sub=('Halftime: your adjustments' if lv['halftime_open'] else 'Your game is on; finish it to advance'), played=True, live=True)
                return dict(title=(f"Advance to Week {wk + 1}" if wk < WEEKS else 'Advance to the Playoffs'), sub=(f"Week {wk} is in the books"), played=True)
            return dict(title=f"Sim Week {wk}", sub=(f"{'at' if opp and opp[1] else 'vs'} {opp[0]}" if opp else 'Bye Week'), played=False)
        if k == 'playoffs':
            rnd_i = int(self.stop[1]) if len(self.stop) > 1 else 0
            lv = getattr(self.runner, 'live', None) if self.runner is not None else None
            if lv is not None and not lv['done']:
                return dict(title='Game Day', sub=('Halftime: your adjustments' if lv['halftime_open'] else 'Your playoff game is on; finish it to advance'), played=True, live=True)
            if rnd_i >= 4: return dict(title='Close the Season', sub='the champion is crowned', played=True)
            rnd = PS.Postseason.ROUNDS[rnd_i]; name = PS.Postseason.ROUND_NAMES[rnd]
            post = getattr(self, 'post_live', None); user = self.user_team
            if self.played:
                nxt = PS.Postseason.ROUND_NAMES[PS.Postseason.ROUNDS[rnd_i + 1]] if rnd_i + 1 < 4 else 'Offseason'
                return dict(title=f'Advance to the {nxt}', sub=f'The {name} is in the books', played=True)
            if post is not None and hasattr(post, 'alive'):
                alive = {t for a in post.alive.values() for t in a.values()} if rnd != 'SB' else set(post.conf_champs.values())
                if user in alive:
                    ms = [m for m in post.matchups(rnd) if user in (m[1], m[2])]
                    if ms:
                        c, h, a = ms[0]
                        if rnd == 'SB': v = PS.sb_venue(self.L); return dict(title=f"Play Super Bowl {v['numeral']}", sub=f"vs {a if h == user else h} at {v['stadium']}")
                        return dict(title=f'Play the {name}', sub=(f'vs {a}' if h == user else f'at {h}'))
                    return dict(title=f'Sim the {name}', sub='You have the bye')
                return dict(title=f'Sim the {name}', sub="Your season is over")
            try:
                seeds = self.runner.seeds() if self.runner is not None else {}
                inn = any(user in list(sd)[:7] for sd in seeds.values())
            except Exception: inn = False
            return dict(title=('Play the Wild Card' if inn else 'Sim the Wild Card'), sub=('Your playoff run starts' if inn else 'Your season is over'))
        i = self.stop[1]
        if self.draft_live():
            pk = self.draft.current()
            return dict(title='Finish the Draft on Auto', sub=f"or make your pick at {pk.round}.{((pk.selection - 1) % 32) + 1} on Draft Day" if pk else '')
        title, _ = self.OFFSEASON[i]
        name = self.OFFSEASON[i][1]
        if name == 'step_extensions':
            try:
                sh = TG.user_resign_sheet(self.L)
                tag_s = ('tag placed' if sh['tag_used'] else ('no tag' if sh['tag_choice'] == 'none' else 'no tag yet'))
                return dict(title='Lock Tags and Tenders', sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)} · {len(sh['ufa'])} unrestricted, {len(sh['rfa'])} restricted · {tag_s}")
            except Exception: pass
        if name in self.FA_STEPS or name == 'step_fa_close':
            n = len([x for x in self.L.free_agents if self.L.player(x)])
            import negotiations as NG
            mine = sum(1 for t in NG._threads(self.L) if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'))
            return dict(title=('Close the Market' if name == 'step_fa_close' else f"Close Round {self.FA_STEPS[name]}"), sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)} · {n} on the market · {mine} offer{'s' if mine != 1 else ''} out")
        return dict(title=title, sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)}")

    ROSTER_MAX, ROSTER_MIN = 53, 46

    def blocking(self):
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is not None and not lv['done']:
            return [dict(id=None, subject='Your game is still being played: finish it first', kind='live', go='#gameday')]
        """Decisions that must be made before the next stop. Empty list = nothing blocks."""
        out = []
        # THE ROSTER RULE. A club plays with 53 at most and 46 at least; the game will not
        # run a week, or leave camp, until yours is legal. A new franchise starts in camp at
        # 68 and cuts to 53 before week 1, the way every club does.
        if self.stop[0] in ('week', 'cutdown', 'wire') and not getattr(self, 'played', False):
            n = len(self.L.teams[self.user_team].active())
            import inbox as IB
            key_ = f"roster-{self.L.year}-{self.stop[1] if len(self.stop) > 1 else 0}"
            existing = next((m for m in getattr(self.L, 'inbox', []) if (m.get('payload') or {}).get('key') == key_ and m.get('status') in ('unread', 'open')), None)
            if n > self.ROSTER_MAX or n < self.ROSTER_MIN:
                subj = f"Roster at {n}: cut to {self.ROSTER_MAX} before Sunday" if n > self.ROSTER_MAX else f"Roster at {n}: sign to at least {self.ROSTER_MIN}"
                if existing is None:
                    IB.post(self.L, 'roster', subj, (f"You are carrying {n}. The game needs 53 or fewer to start; release or waive to the practice squad before you sim." if n > self.ROSTER_MAX else f"You are at {n}; the game needs at least {self.ROSTER_MIN}. Sign from free agency or call up from the squad."), sender='front office', payload=dict(key=key_, link=('club' if n > self.ROSTER_MAX else 'personnel:fa')))
                    existing = self.L.inbox[-1]
                else:
                    existing['subject'] = subj
                out.append(dict(id=existing.get('id'), subject=subj, kind='roster', go=('#club' if n > self.ROSTER_MAX else '#personnel/fa')))
            elif existing is not None:
                existing['status'] = 'done'
        for m in getattr(self.L, 'inbox', []):
            if m.get('status') in ('unread', 'open') and m.get('kind') in ('trade_offer', 'match_request', 'staff') and m.get('needs_decision', True):
                if m.get('kind') == 'trade_offer' or (m.get('payload') or {}).get('poach'):
                    out.append(dict(id=m.get('id'), subject=m.get('subject'), kind=m.get('kind')))
        return out

    def _league_log_notes(self):
        try:
            import league_notes as LN
            fa_now = self.stop[0] == 'offseason' and self.OFFSEASON[self.stop[1]][1] in (*self.FA_STEPS, 'step_fa_close')
            LN.transactions(self.L, self.L.week or 0, skip_signings=fa_now)
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
                # the other fifteen games are played and stored; YOUR game opens live at the opening kick
                mine = next(((a, h) for (w, a, h, ap, hp) in self.L.schedule if w == wk and self.user_team in (a, h) and hp is None), None)
                self.runner._skip_game = (mine[1], mine[0]) if mine else None
                self.runner.play_games(wk)
                self.runner._skip_game = None
                if mine:
                    self.runner.open_live(mine[1], mine[0], wk)
                    self.played = True
                    return dict(done=f'Week {wk} live', next=self.next_label())
                self._capture_gameday(wk)
                self.played = True
                return dict(done=f'Week {wk} played', next=self.next_label())
            # ADVANCE: the week rolls (XP, morale, agents, the report on next week, the wire,
            # the squads, the trade window) and the calendar moves on
            self._finish_live()
            self.runner.roll_week(wk)
            IB.expire(self.L, wk + 1)
            self.played = False
            self.stop = ('week', wk + 1) if wk < WEEKS else ('playoffs', 0)
            if wk >= WEEKS:
                self._playoff_prep(0)
                post = self.post_live
                if post is not None:
                    field = {t for sd in post.seeds.values() for t in sd}
                    if self.user_team not in field: self._post_review('missed')
                    self._ai_exit_meetings([a for a in self.L.teams if a not in field])
                    self._black_monday([a for a in self.L.teams if a not in field])
            return dict(done=f'Week {wk}', next=self.next_label())
        if k == 'playoffs':
            # THE PLAYOFFS, A ROUND AT A TIME, with the whole week around each game. Entering a round (from week 18's
            # roll or the roll after the last round) is the prep: the bracket is seeded, the round's games go into the
            # schedule, the injury desk lists the hurt with their Play/Sit notes, the opponent report and game plan
            # post, and the inbox gets the round. Advance then plays the round: the other games sim onto the strip and
            # yours opens live on Game Day. Advance again rolls the week (XP, morale, injuries, notes) into the next
            # round's prep. After the Super Bowl the season closes.
            if self.runner is None: self.runner = SN.SeasonRunner(self.L, self.rng)
            rnd_i = int(self.stop[1]) if len(self.stop) > 1 else 0
            lv = getattr(self.runner, 'live', None)
            if lv is not None and not lv['done']:
                return dict(done='Your playoff game is still being played', next=self.next_label())
            if rnd_i >= 4:
                return self._close_playoffs()
            if getattr(self, 'post_live', None) is None or not hasattr(self.post_live, 'seeds'):
                self._playoff_prep(0)
            post = self.post_live
            rnd = PS.Postseason.ROUNDS[rnd_i]; wk_ = 19 + rnd_i
            self.L._post_ref = post
            if self.played and not any(g[0] == rnd for g in post.games):
                self.played = False                       # a save from before the round flow: this round has not been played
                self._playoff_prep(rnd_i)
            if not self.played:
                # PLAY THE ROUND
                user = self.user_team
                self.runner.last_games = []; self.runner.last_played = []
                held = post.play_round(rnd, skip=user, week=wk_)
                self.played = True
                if held is not None:
                    conf, home, away = held
                    post.held = (rnd, conf, home, away)
                    def _close(res, _c=conf, _h=home, _a=away, _r=rnd): post.record(_r, _c, _h, _a, res); post.held = None
                    self.runner.open_live(home, away, wk_, playoffs=True, on_close=_close)
                    self._capture_gameday(wk_)
                    return dict(done=f'{PS.Postseason.ROUND_NAMES[rnd]} live', next=self.next_label())
                self._capture_gameday(wk_)
                self.runner._after_games(wk_, self.runner.last_played)
                return dict(done=PS.Postseason.ROUND_NAMES[rnd], next=self.next_label())
            # ROLL INTO THE NEXT ROUND
            self.runner.roll_week(wk_)
            IB.expire(self.L, wk_ + 1)
            self.played = False
            if self.user_team in (getattr(post, 'exit_round', {}) or {}):
                self._post_review('eliminated')
            losers = [a for a, r in (getattr(post, 'exit_round', {}) or {}).items() if r == rnd]
            self._ai_exit_meetings(losers)
            self._black_monday(losers)
            if rnd == 'WC':
                self._announce_honors()
            if rnd == 'CONF':
                self._senior_bowl()
            if rnd_i + 1 < len(PS.Postseason.ROUNDS):
                self.stop = ('playoffs', rnd_i + 1)
                self._playoff_prep(rnd_i + 1)
                return dict(done=PS.Postseason.ROUND_NAMES[rnd], next=self.next_label())
            self.stop = ('playoffs', 4)
            return self._close_playoffs()
        i = self.stop[1]
        if self.draft_live():
            self.draft.auto = True; self.draft.sim_all(); self._draft_over()
        else:
            getattr(self, self.OFFSEASON[i][1])()
            # TRADES ARE NOT A STEP. The clubs deal with each other whenever the window is open: a light pass at every
            # offseason stop (a quarter of the league picks up the phone each time), the way the season's weeks carry a
            # trickle up to the deadline, so the wire shows trades landing all year rather than in one batch
            try:
                if self.OFFSEASON[i][1] not in ('step_draft', 'step_cutdown'):
                    TRD.run(self.L, self.rng, rounds=1, activity=0.25, exclude=(self.user_team,) if self.user_team else ())
            except Exception as e:
                import sys; print('offseason trade pass failed:', e, file=sys.stderr)
            self._league_log_notes()
            if self.draft_live():
                return dict(done='The Draft is on the clock', next=self.next_label())
        if i + 1 < len(self.OFFSEASON):
            self.stop = ('offseason', i + 1)
            try: self._open_fa_if_due()
            except Exception as e:
                import sys; print('open round failed:', e, file=sys.stderr)
        else:
            self.stop = ('week', 1); self.runner = None
            try: GW.post_report(self.L, 1)
            except Exception: pass
        return dict(done=self.OFFSEASON[i][0], next=self.next_label())

    def _announce_honors(self):
        """The season's honors come out after the Wild Card round, as they do: the vote on the regular season, paid
        in XP the same day, felt in the room, priced into the next ask. The Super Bowl MVP waits for the game."""
        try:
            import morale as MO
            from views import surname
            from views_league import AWARD_NAMES
            self.votes = AW.vote(self.L, None)
            paid = XP.pay_awards(self.L, self.votes)
            names = dict(AWARD_NAMES)
            mine = []; lines = []
            for k, who in self.votes.items():
                if k in ('coty',) or not who: continue
                ws = who if isinstance(who, list) else [who]
                for w in ws:
                    p = self.L.player(getattr(w, 'pid', w)) if not hasattr(w, 'pid') else w
                    if p is None: continue
                    m = MO.ensure(p)
                    if m is not None:
                        m.apply('major_award' if k in ('mvp', 'opoy', 'dpoy', 'oroy', 'droy', 'protector') else 'all_pro' if k == 'all_pro_1' else 'all_pro_2')
                    if p.team == self.user_team: mine.append(f"{surname(p.name)} ({names.get(k, k) if k not in ('all_pro_1', 'all_pro_2') else ('All-Pro first team' if k == 'all_pro_1' else 'All-Pro second team')})")
                if k not in ('all_pro_1', 'all_pro_2'):
                    p = self.L.player(getattr(ws[0], 'pid', ws[0])) if not hasattr(ws[0], 'pid') else ws[0]
                    if p is not None: lines.append(f"{names.get(k, k)}: {p.name} ({p.pos}, {p.team})")
            body = ('Yours: ' + ', '.join(mine) + '. ' if mine else 'None of yours were named. ') + ' · '.join(lines)
            IB.post(self.L, 'league', "The season's honors", body, sender='league', payload=dict(link='league:awards'))
        except Exception as e:
            import sys; print('honors failed:', e, file=sys.stderr)

    def _backfill_history(self):
        """A save whose last season closed before the history existed: rebuild what the game days kept (every week's
        scores) into the season's schedule and standings, and the bracket from the postseason the save carries."""
        import views_league as VL
        from views import club as _club
        yr = int(self.L.year) - 1
        hist = self.L.__dict__.setdefault('history', {})
        if str(yr) in hist and hist[str(yr)].get('standings'): return
        days = {int(k.split('-')[1]): v for k, v in (getattr(self, 'gamedays', None) or {}).items() if k.startswith(f"{yr}-") and v and v.get('scores')}
        if not days: return
        snap = hist.setdefault(str(yr), {})
        rec = {a: [0, 0, 0] for a in self.L.teams}; allg = []
        for wk in sorted(days):
            for g in days[wk]['scores']:
                h, a, hs, as_ = g['home'], g['away'], g['hs'], g['as_']
                if h not in self.L.teams or a not in self.L.teams: continue
                allg.append(dict(week=wk, away=_club(a), home=_club(h), ap=as_, hp=hs, done=True, mine=(self.user_team in (a, h)), winner=(h if hs > as_ else a if as_ > hs else None), away_rec='', home_rec='', note='', box=(self.user_team in (a, h) and f"{yr}-{wk}" in self.gamedays)))
                if wk <= 18:
                    if hs > as_: rec[h][0] += 1; rec[a][1] += 1
                    elif as_ > hs: rec[a][0] += 1; rec[h][1] += 1
                    else: rec[h][2] += 1; rec[a][2] += 1
        missing = [w for w in range(1, 19) if w not in days]
        weeks = sorted(days)
        snap['schedule'] = dict(weeks=weeks, week=max([w for w in weeks if w <= 18], default=18), games=[g for g in allg if g['week'] == max([w for w in weeks if w <= 18], default=18)], all_games=allg, byes=[], note=(f"Week {', '.join(map(str, missing))} was not kept." if missing else None))
        rows = sorted([dict(club=_club(a), record=f"{r[0]}–{r[1]}" + (f"–{r[2]}" if r[2] else ''), pct=round((r[0] + 0.5 * r[2]) / max(1, sum(r)), 3), division=self.L.teams[a].division) for a, r in rec.items()], key=lambda x: -x['pct'])
        snap['standings'] = dict(thin=True, league_rows=rows, divisions=VL._thin_divisions(self.L, rows), picture=None, conferences=[], notes=[f"Rebuilt from the season's scores; week {', '.join(map(str, missing))} was not kept, so some records are a game short." if missing else ''], games_played=len([g for g in allg if g['week'] <= 18]), week=18)
        if not (getattr(self.L, 'standings_history', {}) or {}).get(yr):
            self.L.standings_history[yr] = {a: dict(record=list(r), pct=round((r[0] + 0.5 * r[2]) / max(1, sum(r)), 3), made_playoffs=False) for a, r in rec.items()}
        try:
            if self.post is not None and getattr(self.post, 'champion', None) and getattr(self.post, 'seeds', None):
                b = VL.bracket(self, self.L, self.user_team, year=yr)
                if b and not b.get('missing'): b.pop('rail', None); snap['bracket'] = b
        except Exception: pass

    def _snapshot_season(self):
        """The season's pages, kept as they stood at the close, so the year chooser can show them later: standings,
        the full schedule, the bracket, the season review."""
        import views_league as VL, views_frontoffice as VF
        yr = str(self.L.year); hist = self.L.__dict__.setdefault('history', {}); snap = hist.setdefault(yr, {})
        for page, fn in (('standings', lambda: VL.standings(self, self.L, self.user_team)), ('schedule', lambda: VL.schedule_snapshot(self, self.L, self.user_team)),
                         ('bracket', lambda: VL.bracket(self, self.L, self.user_team)), ('review', lambda: VF.season_review(self, self.L, self.user_team))):
            try:
                d = fn(); d.pop('rail', None); snap[page] = d
            except Exception as e:
                import sys; print('snapshot failed:', page, e, file=sys.stderr)

    def _senior_bowl(self):
        """The week before the Super Bowl: every room's second look at the seniors in Mobile, and the assistants'
        word on who helped himself."""
        try:
            import scouting as SC
            from views import surname
            moves = SC.senior_bowl(self.L, self.rng)
            if not moves: return
            moves.sort(key=lambda x: -x[0])
            up = [f"{surname(p.name)} ({p.pos}, {d:+.1f})" for d, p in moves[:3] if d > 0.4]
            down = [f"{surname(p.name)} ({p.pos}, {d:+.1f})" for d, p in moves[-3:][::-1] if d < -0.4]
            body = f"Your scouts spent the week at the Senior Bowl; {len(moves)} seniors played. " + (f"Helped himself: {', '.join(up)}. " if up else '') + (f"Hurt himself: {', '.join(down)}. " if down else '') + "Their marks on your board have moved; the players who played carry the Senior Bowl tag."
            IB.post(self.L, 'draft', "Senior Bowl week: the scouts' word", body, sender='scouts', payload=dict(link='draft:board'))
        except Exception as e:
            import sys; print('senior bowl failed:', e, file=sys.stderr)

    def _black_monday(self, clubs):
        """The clubs whose season just ended roll their firings now, and a new head coach comes for his staff,
        which can mean a request for one of your coordinators while the playoffs go on."""
        try:
            fired = PS.run_firings(self.L, self.rng, clubs=list(clubs))
            for abbr, bg in fired:
                t = self.L.teams[abbr]
                who = (t.gm.name + ' takes over.') if t.gm else ('The search is on; ' + (f"they are waiting on {self.L.pending_hires[abbr]['first']}." if abbr in (getattr(self.L, 'pending_hires', None) or {}) else 'a name is coming.'))
                IB.post(self.L, 'league', f"{t.abbr} makes a change", f"{CLUB_NAME_.get(abbr, abbr)} moved on from its head coach the morning after its season ended. {who}", sender='league')
            if fired:
                # the market: the names every searching club is calling, by what their units did
                import coaching_pool as CP
                cands = [c for c in CP.coordinators_as_candidates(self.L) if c.team != self.user_team or True]
                def hot(c):
                    rk = list(c.unit_ranks[-2:]); recent = ((2.0 * rk[-1] + rk[-2]) / 3.0 if len(rk) >= 2 else float(rk[-1])) if rk else 16.5
                    return 0.35 * (16.5 - recent) / 15.5 + 0.6 * (c.prestige / 100.0)
                top = sorted(cands, key=hot, reverse=True)[:3]
                if top:
                    lines = [f"{c.name} ({'OC' if c.role == 'oc' else 'DC'}, {c.team}; his unit ranked {', '.join(str(int(r)) + ('st' if r == 1 else 'nd' if r == 2 else 'rd' if r == 3 else 'th') for r in c.unit_ranks[-2:]) or 'unranked'} the last two years)" for c in top]
                    IB.post(self.L, 'league', "The coaching market", f"{len(fired)} club{'s' if len(fired) != 1 else ''} searching. The names every owner is calling: " + '; '.join(lines) + '.', sender='league')
        except Exception as e:
            import sys; print('black monday failed:', e, file=sys.stderr)

    def _ai_exit_meetings(self, clubs):
        import views_frontoffice as VF
        for a in clubs:
            if a == self.user_team: continue
            try: VF.ai_exit_meetings(self.L, a, self.rng)
            except Exception as e:
                import sys; print('AI exit meetings failed:', a, e, file=sys.stderr)

    def _post_review(self, how):
        """The season review lands once, the morning after the club's season ends."""
        key_ = f"review-{self.L.year}"
        if any((m.get('payload') or {}).get('key') == key_ for m in getattr(self.L, 'inbox', [])): return
        try:
            v = self.frontoffice('season_review')
            slot = PS.provisional_slot(self.L, getattr(self, 'post_live', None) or getattr(self, 'post', None), self.user_team)
            slot_line = f" You pick {slot}{'st' if slot % 10 == 1 and slot != 11 else 'nd' if slot % 10 == 2 and slot != 12 else 'rd' if slot % 10 == 3 and slot != 13 else 'th'} in the first round." if slot else ''
            IB.post(self.L, 'review', f"The season, reviewed: {v['record']}, {v['finish'].lower()}", f"{v['owner']['line']} The review is on your desk: the units against the league, who rose and who fell, next year's money and the players whose deals are up.{slot_line}", sender='front office', payload=dict(key=key_, link='front_office:review'))
        except Exception as e:
            import sys; print('season review failed:', e, file=sys.stderr)
        try:
            # THE EXTENSION WINDOW. Your own players are yours to extend from here until the tag period; the note says
            # who is up and what the room is
            t = self.L.teams[self.user_team]
            from views import surname, next_year_cap
            up = sorted([p for p in t.active() if p.contract and p.contract.years <= 1 and p.pos not in ('K', 'P', 'LS')], key=lambda p: -p.ovr)
            two = sorted([p for p in t.active() if p.contract and p.contract.years == 2 and p.ovr >= 82], key=lambda p: -p.ovr)
            limit_next, committed_next, _ro, _dn = next_year_cap(self.L, t)
            if up or two:
                body = (f"Deals up: {', '.join(f'{surname(p.name)} ({p.pos}, {round(p.ovr)})' for p in up[:6])}. " if up else '') + (f"Two years left and worth a look: {', '.join(f'{surname(p.name)} ({p.pos}, {round(p.ovr)})' for p in two[:4])}. " if two else '') + f"About ${limit_next - committed_next:.0f}m of room next year."
                IB.post(self.L, 'contract', "The extension window is open", body, sender='front office', payload=dict(key=f"extwin-{self.L.year}", link='personnel:extensions'))
        except Exception as e:
            import sys; print('extension window note failed:', e, file=sys.stderr)
        try:
            import views_frontoffice as VF
            ms = VF.build_exit_meetings(self, self.L, self.user_team)
            if ms:
                from views import surname
                names = ', '.join(surname(self.L.player(x['pid']).name) for x in ms if self.L.player(x['pid']))
                IB.post(self.L, 'exit', f"Exit meetings: {len(ms)} players want a word", f"{names}.", sender='assistants', payload=dict(key=f"exit-{self.L.year}", link='front_office:exit'))
        except Exception as e:
            import sys; print('exit meetings failed:', e, file=sys.stderr)

    def _playoff_prep(self, rnd_i):
        """The week before a playoff game, for every club: the round's games scheduled, the injury desk's listings and
        Play/Sit notes, the opponent report and the plan, and the round in the inbox."""
        import gameplan_week as GW
        if getattr(self, 'post_live', None) is None or not hasattr(self.post_live, 'seeds'):
            self.standings = self.runner.standings()
            self.L.set_phase('playoffs')
            self.post_live = PS.Postseason(self.runner); self.post_live.start()
        post = self.post_live; rnd = PS.Postseason.ROUNDS[rnd_i]; wk_ = 19 + rnd_i
        self.L._post_ref = post
        self.L.week = wk_; self.runner.week = wk_
        ms = post.schedule_round(rnd)
        try: self.runner.injury_week(wk_); self.runner._listed_week = wk_
        except Exception as e:
            import sys; print('playoff injury listing failed:', e, file=sys.stderr)
        user = self.user_team
        mine = next(((c, h, a) for c, h, a in ms if user in (h, a)), None)
        try: GW.post_report(self.L, wk_)
        except Exception as e:
            import sys; print('playoff report failed:', e, file=sys.stderr)
        subject, body = self._round_letter(post, rnd, ms, user, mine)
        IB.post(self.L, 'league', subject, body, sender='league', payload=dict(link='league:bracket'))

    def _round_letter(self, post, rnd, ms, user, mine):
        """The league's letter for a playoff round: who plays whom, as what seed with what record, and where. The
        Super Bowl letter names the site and walks both finalists' road to it."""
        from views import CLUB_NAME, STADIUM
        L = self.L
        nm = lambda x: CLUB_NAME.get(x, x)
        def rec(x):
            w, l, d = L.teams[x].record
            return f"{w}-{l}" + (f"-{d}" if d else '')
        seed_of = {}
        for c, sd in (getattr(post, 'seeds', {}) or {}).items():
            for i, x in enumerate(sd): seed_of[x] = i + 1
        def tag(x): return f"the {seed_of[x]} seed {nm(x)} ({rec(x)})" if x in seed_of else f"{nm(x)} ({rec(x)})"
        wk_ = 19 + PS.Postseason.ROUNDS.index(rnd)
        name = PS.Postseason.ROUND_NAMES[rnd]
        if rnd == 'SB':
            if not ms: return f"Super Bowl", "The conference championships are not yet decided."
            c, h, a = ms[0]
            site = PS.sb_venue(L)
            def road(x):
                won = [g for g in post.games if g[0] != 'SB' and (g[2] == x or g[3] == x)]
                steps = []
                for (r_, cf, hm, aw, hp, ap) in won:
                    opp = aw if hm == x else hm; mine_, theirs = (hp, ap) if hm == x else (ap, hp)
                    steps.append(f"{nm(opp)} {mine_}-{theirs} in the {PS.Postseason.ROUND_NAMES[r_].replace(' Round', '')}")
                if x in seed_of and seed_of[x] == 1: steps.insert(0, 'the first-round bye')
                return ', then '.join(steps) if steps else 'the conference'
            conf_of = {t: cf for cf, sd in (getattr(post, 'seeds', {}) or {}).items() for t in sd}
            lines = [f"Super Bowl {site['numeral']} is set: {nm(a)} against {nm(h)}, at {site['stadium']} in {site['city']}.",
                     f"{nm(a)}, the {seed_of.get(a, '?')} seed out of the {conf_of.get(a, '')}, finished {rec(a)} and came through {road(a)}.",
                     f"{nm(h)}, the {seed_of.get(h, '?')} seed out of the {conf_of.get(h, '')}, finished {rec(h)} and came through {road(h)}."]
            if user in (h, a): lines.append("You are in it. The game plan is on your desk.")
            else: lines.append("Your season is over; the game is yours to watch from the bracket.")
            return f"Super Bowl {site['numeral']}: {nm(a)} vs {nm(h)} at {site['stadium']}", ' '.join(lines)
        games = [f"{tag(a)} at {tag(h)}, {STADIUM.get(h, nm(h))}" for c, h, a in ms]
        if mine is not None:
            c, h, a = mine
            opener = f"Your {name} game: {'at ' + nm(h) + ', ' + STADIUM.get(h, '') if a == user else 'vs ' + nm(a) + ' at home'}. They finished {rec(h if a == user else a)}."
        else:
            alive = {t for al in post.alive.values() for t in al.values()}
            opener = f"You have the bye this round; the winner of the worst surviving seed's game comes to you." if user in alive else "Your season is over."
        subject = {'WC': f"Wild Card Weekend: {len(ms)} games", 'DIV': f"Divisional Round: {len(ms)} games", 'CONF': "Conference Championships: the two finals"}[rnd]
        return subject, opener + (' The round: ' + '; '.join(games) + '.' if games else '')

    def _close_playoffs(self):
        """After the Super Bowl: the champion, the draft order, the firings, and into the offseason."""
        post = self.post_live
        if post is None or not getattr(post, 'seeds', None):
            self._playoff_prep(0); post = self.post_live
        if self.runner is not None and not hasattr(self.runner, 'last_games'): self.runner.last_games = []; self.runner.last_played = []
        if post.champion is None:
            # the bracket is unfinished (a save from before the rounds, or a final not yet played): play what remains
            for i, rnd in enumerate(PS.Postseason.ROUNDS):
                need = {'WC': 6, 'DIV': 4, 'CONF': 2, 'SB': 1}[rnd]
                if sum(1 for g in post.games if g[0] == rnd) < need:
                    post.schedule_round(rnd)
                    post.play_round(rnd, skip=None, week=19 + i)
        try: self.runner.finish()                 # records into standings_history and each team's history
        except Exception as e:
            import sys; print('season records failed:', e, file=sys.stderr)
        self.post, self.order, self.fired = PS.close_season(self.L, self.runner, self.rng, post=post)
        self.post.year = self.L.year
        self.L.season_closed_year = int(self.L.year)                  # this year's season is over: its review and meetings are its own
        self._post_review('closed')
        self._snapshot_season()
        self._ai_exit_meetings([a for a in self.L.teams if f"{a}-{self.L.year}" not in (getattr(self.L, 'exit_meetings', {}) or {})])
        try: self.post.seeds_at_close = dict(getattr(post, 'seeds', {}) or {})
        except Exception: self.post.seeds_at_close = {}
        MO.postseason(self.L, self.post); CP.top_up(self.L, self.rng); PC.offseason(self.L)
        self.post_live = None
        self.stop = ('offseason', 0)
        # REGRESSION HITS THE DAY AFTER THE SUPER BOWL. Every player takes what age takes; your club's before-and-after
        # is kept, and the analysis lands in the inbox as the offseason opens
        try:
            RG.run(self.L, self.rng, record_for=self.user_team, tick_age=False)
            rec = (getattr(self.L, 'regression', {}) or {}).get(str(self.L.year), {})
            from views import surname
            hit = sorted([(v['lost'], pid) for pid, v in rec.items() if v['lost'] >= 0.5], reverse=True)
            names = ', '.join(f"{surname(self.L.player(pid).name)} ({self.L.player(pid).pos}, −{lost:.0f})" for lost, pid in hit[:6] if self.L.player(pid))
            body = (f"{len(hit)} of your players lost ground with age: {names}. " if hit else "None of your players lost ground with age this year. ") + "The full analysis, every player and every attribute, is on the Regression page."
            IB.post(self.L, 'club', f"Going into {self.L.year + 1}: what age took", body, sender='assistants', payload=dict(link='club:regression'))
        except Exception as e:
            import sys; print('regression report failed:', e, file=sys.stderr)
        return dict(done='Playoffs', champion=self.post.champion, next=self.next_label())

    # ---- the offseason steps, the same code as franchise.play_year in the same order
    def step_awards(self):
        L, rng = self.L, self.rng
        if getattr(self, 'votes', None) and L.awards.get(L.year):
            # the honors came out after the Wild Card; only the Super Bowl MVP is left to add
            try:
                self.votes['sb_mvp'] = AW.super_bowl_mvp(L, self.post, L.year)
                if self.votes['sb_mvp']: L.awards[L.year]['sb_mvp'] = getattr(self.votes['sb_mvp'], 'pid', self.votes['sb_mvp'])
            except Exception: pass
        else:
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
        RT.run(L, rng); AL.hall_vote(L, L.year)
        for p in L.players.values():
            if not p.retired: p.age += 1.0                     # the year's age tick; the decline itself ran the day after the Super Bowl
        try:
            import league_notes as LN; LN.season_end(L, None)          # the Hall class and the retirements, now that they are in
        except Exception as e:
            import sys; print('league_notes retire failed:', e, file=sys.stderr)

    def step_roll(self):
        self.L.user_tag_choice = None          # a new year, a new tag
        L, rng = self.L, self.rng
        L.roll_year(rng)
        (getattr(L, 'exit_meetings', None) or {}).pop(str(L.year), None)          # the new year has no meetings yet
        ((getattr(L, 'history', None) or {}).get(str(L.year)) or {}).pop('review', None)   # and no review
        try:
            import negotiations as NG
            NG.check_promises(L, week=0)       # the new year: extension promises are judged here
        except Exception as e:
            import sys; print('promise check failed:', e, file=sys.stderr)
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

    # ---- FREE AGENCY AS STAGES. Each round is a stop on the calendar: it opens (the AI clubs' bids are lodged, your
    # talks show who else is in) when the calendar lands on it, you make your offers on the Free Agency page, and the
    # Advance resolves it: every player signs, waits, or asks for a match, and your answers land in the inbox. Nothing
    # signs on the spot in the open market. The close prices the leftovers and fills rosters with depth only.
    FA_STEPS = {'step_fa_1': 1, 'step_fa_2': 2, 'step_fa_3': 3}

    def _fa_round(self, k):
        L, rng = self.L, self.rng
        signed, waiting, msgs = MK.resolve_round(L, rng, k, user_team=self.user_team)
        # one note for the round: the AI's notable signings, not one message per deal
        from views import surname
        big = sorted([(t_, p, o) for t_, p, o in signed if p.ovr >= 85 or o.apy >= 15.0], key=lambda x: -x[2].apy)
        if big:
            lines = [f"{p.name} ({p.pos}, {round(p.ovr)}) to {t_} for ${o.apy:.1f}m x {o.years}" for t_, p, o in big[:10]]
            IB.post(L, 'league', f"Free agency, round {k}: the big signings", f"{len(signed)} players signed in the round; {len(waiting)} remain on the market. " + '; '.join(lines) + ('.' if lines else ''), sender='league', payload=dict(link='personnel:free_agency'))
        else:
            IB.post(L, 'league', f"Free agency, round {k}", f"{len(signed)} players signed in the round; {len(waiting)} remain on the market.", sender='league', payload=dict(link='personnel:free_agency'))

    def step_fa_1(self): self._fa_round(1)
    def step_fa_2(self): self._fa_round(2)
    def step_fa_3(self): self._fa_round(3)

    def step_fa_close(self):
        L, rng = self.L, self.rng
        signed = MK.close_market(L, rng, user_team=self.user_team)
        n_left = len([x for x in L.free_agents if L.player(x)])
        big = [f"{p.name} ({p.pos}, {round(p.ovr)}) to {t_} for ${o.apy:.1f}m" for t_, p, o in sorted(signed, key=lambda x: -x[1].ovr)[:8]]
        IB.post(L, 'league', "The market closes", f"{len(signed)} veterans signed one-year deals as the market closed; {n_left} players remain unsigned into camp. " + ('; '.join(big) + '.' if big else ''), sender='league', payload=dict(link='personnel:free_agency'))

    def _resign_card(self):
        """The calendar sits on Re-sign: one card with your expiring players by class, the tag price on each UFA, tender
        or not on each RFA, the ERFAs kept at the minimum. Decide on the Extensions page; the advance locks it."""
        L = self.L; key_ = f"resign-{L.year}"
        if any((m.get('payload') or {}).get('key') == key_ for m in getattr(L, 'inbox', [])): return
        sheet = TG.user_resign_sheet(L)
        from views import surname
        ufa = ', '.join(f"{surname(r['name'])} ({r['pos']}, {r['ovr']}; tag ${r['tag_price']}m)" for r in sheet['ufa'][:8])
        rfa = ', '.join(f"{surname(r['name'])} ({r['pos']}, {r['ovr']}; tender ${r['tender_price']}m)" for r in sheet['rfa'][:8])
        erfa = ', '.join(f"{surname(r['name'])} ({r['pos']})" for r in sheet['erfa'][:8])
        body = (f"Unrestricted: {ufa}. One franchise tag, or none; anyone you do not tag or re-sign goes to the market when you advance. " if sheet['ufa'] else "No unrestricted free agents. ")
        body += (f"Restricted: {rfa}. Tendered at right of first refusal unless you say otherwise; an untendered player goes to the market unrestricted. " if sheet['rfa'] else "")
        body += (f"Exclusive rights, kept at the minimum: {erfa}. " if sheet['erfa'] else "")
        body += f"You can commit about ${sheet['room']}m after the minimums you still owe."
        IB.post(L, 'contract', "Re-sign: your tag and tenders", body, sender='front office', payload=dict(key=key_, link='personnel:extensions'))

    def _open_fa_if_due(self):
        """The calendar sits on a free-agency round: open it (once) so the offers can be made before the advance."""
        if self.stop[0] != 'offseason': return
        name = self.OFFSEASON[self.stop[1]][1]
        if name == 'step_extensions':
            try: self._resign_card()
            except Exception as e:
                import sys; print('resign card failed:', e, file=sys.stderr)
            return
        k = self.FA_STEPS.get(name)
        if k is None: return
        L = self.L
        if getattr(L, 'fa_bids_phase', None) == k and getattr(L, 'fa_bids', None): return
        bids = MK.open_round(L, self.rng, k, user_team=self.user_team)
        n = len([x for x in L.free_agents if L.player(x)])
        contested = sum(1 for pid, offers in bids.items() if len(offers) >= 2)
        IB.post(L, 'contract', f"Free agency, round {k}, is open", f"{n} players on the market; {len(bids)} have offers from other clubs, {contested} from more than one. Open talks on the Free Agency page to see who else is in on a player, and make your offers before you advance. Nobody signs until the round closes.", sender='front office', payload=dict(link='personnel:free_agency'))

    def step_market(self):
        # kept for tools that call the one-shot market
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

    def club_regression(self, year=None):
        import views_club as VC
        return VC.regression(self, self.L, self.user_team, year=year)

    def club_roster(self, abbr=None):
        import views_club as VC
        v = VC.roster(self, self.L, abbr or self.user_team)
        v['club_abbr'] = abbr or self.user_team; v['mine'] = (abbr or self.user_team) == self.user_team
        return v

    def development(self, pid):
        import views_club as VC; return VC.development(self, self.L, self.user_team, pid)

    def progression(self):
        import views_club as VC; return VC.progression(self, self.L, self.user_team)

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
        if name == 'hurt_decision': kw['session'] = self
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
        # a trade made on the Trades tab during the live draft: the draft's own log carries it, and the order already
        # reflects it (the pick objects are shared)
        D = getattr(self, 'draft', None)
        if name == 'propose' and isinstance(r, dict) and r.get('done') and D is not None and not D.done:
            try:
                other = kw.get('other'); moved = []
                for side, items in (('to_me', kw.get('b_sends', [])), ('from_me', kw.get('a_sends', []))):
                    for x in items:
                        if '-' in str(x):
                            yr, rnd, orig = str(x).split('-')[:3]
                            pk = next((q for q in D.picks if q.year == int(yr) and q.round == int(rnd) and q.original == orig), None)
                            if pk is not None and pk.year == D.year: moved.append((pk, side))
                for pk, side in moved:
                    buyer, seller = (self.user_team, other) if side == 'to_me' else (other, self.user_team)
                    D.trades.append((pk.selection, buyer, seller, ['a package from the Trades tab']))
                    self.L.log('draft_trade', selection=pk.selection, buyer=buyer, seller=seller, sent=['trades tab'], target=None)
            except Exception: pass
        return r if isinstance(r, dict) else dict(ok=bool(r))

    # ---- front office
    def frontoffice(self, page, **kw):
        import views_frontoffice as VF
        return getattr(VF, page)(self, self.L, self.user_team, **kw)

    def trade_offer_view(self, msg_id):
        """An AI club's trade offer, laid out for the popup: what they send, what they want, the read, the value gap."""
        import inbox as IB, views_personnel as VP
        from views import club
        m = next((x for x in self.L.inbox if x.get('id') == int(msg_id)), None)
        if m is None or m.get('kind') != 'trade_offer': return dict(ok=False, why='no such offer')
        pl = m.get('payload') or {}; buyer = pl.get('buyer')
        def item(x, owner):
            if isinstance(x, dict) and x.get('pick'):
                return dict(kind='pick', id=f"{x['year']}-{x['round']}-{x['original']}", label=f"{x['year']} round {x['round']} pick" + (f" (from {x['original']})" if x.get('original') and x['original'] != owner else ''), sel=x.get('selection'))
            p = self.L.player(x)
            if p is None: return dict(kind='player', id=str(x), label=str(x))
            return dict(kind='player', id=p.pid, label=p.name, pos=p.pos, ovr=round(p.ovr), age=int(p.age), apy=round(float(getattr(p, 'apy', 0.0) or 0.0), 1), gone=(p.team != owner))
        they = [item(x, buyer) for x in pl.get('sends', [])]; you = [item(x, self.user_team) for x in pl.get('gets', [])]
        gap = None; read = ''
        try:
            ev = VP._evaluate(self.L, self.user_team, buyer, [x['id'] for x in you], [x['id'] for x in they])
            read = (ev.get('my_read', '') + ' ' + ev.get('read', '')).strip()
        except Exception: pass
        return dict(ok=True, id=m['id'], buyer=club(buyer), they=they, you=you, gap=gap, read=read, status=m.get('status'), expires=m.get('expires_week'), open=(m.get('status') in ('unread', 'open')))

    def trade_offer_answer(self, msg_id, action):
        import inbox as IB
        if action == 'accept':
            try: IB.accept(self.L, int(msg_id), self.user_team); return dict(ok=True, line='Trade accepted.')
            except Exception as e: return dict(ok=False, why=str(e)[:120] or 'the offer could not be completed')
        if action == 'decline':
            IB.decline(self.L, int(msg_id)); return dict(ok=True, line='Offer declined.')
        return dict(ok=False, why='unknown action')

    def resign_sheet(self):
        return TG.user_resign_sheet(self.L)

    def resign_act(self, action, pid=None):
        if action == 'tender': r = TG.user_tender(self.L, pid, True)
        elif action == 'no_tender': r = TG.user_tender(self.L, pid, False)
        elif action == 'tag': r = TG.user_tag(self.L, pid)
        elif action == 'untag': r = TG.untag(self.L, pid)
        elif action == 'no_tag': r = TG.user_tag(self.L, 'none')
        else: r = dict(ok=False, why='unknown action')
        return r

    def exit_answer(self, pid, key):
        import views_frontoffice as VF
        r = VF.exit_answer(self, self.L, self.user_team, pid, key)
        if r.get('ok'): self.save_dirty = True
        return r

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
        return dict(id=m['id'], subject=m['subject'], body=m.get('body') or '', tag=views.INBOX_TAG.get(m.get('kind'), (m.get('kind') or '').title()), kind=m.get('kind'), from_=m.get('sender'), pid=pl.get('pid'),
                    **{'from': m.get('sender')}, when=(f"{m.get('year')} · Week {m.get('week')}" if m.get('week') else str(m.get('year') or '')), link=(pl.get('link') or (f"player:{pl['pid']}" if pl.get('pid') else None)), decide=(m.get('status') in ('unread', 'open') and m.get('kind') in views.DECIDE_KINDS))

    def portal_full(self):
        """The Portal view with every inbox message (the Portal itself keeps the recent fourteen)."""
        import views
        v = views.portal(self, self.L, self.user_team)
        v['inbox'] = views._inbox(self.L, limit=None)
        return v

    def _capture_gameday(self, wk):
        import gameday as GD
        self.gameday = GD.capture(self.L, getattr(self.runner, 'last_games', []), self.user_team)
        if self.gameday and (self.gameday.get('game') or self.gameday.get('scores')):
            # your bye week is kept too: the league's scores that week are part of the season's record
            self.gamedays = getattr(self, 'gamedays', None) or {}
            self.gamedays[f"{self.L.year}-{wk}"] = self.gameday

    # ---- the live game
    def live_state(self):
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None: return None
        return dict(open=not lv['done'], at=lv['at'], halftime_open=lv['halftime_open'], score=lv['score'], home=lv['home'], away=lv['away'])

    def live_step(self, mode='play'):
        """Move the live game: 'play', 'drive', 'half', 'finish', or 'resume' from halftime. Returns Game Day."""
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None: return self.gameday_view()
        was_done = lv['done']
        self.runner.live_step(mode)
        if lv['done'] and not was_done:
            self._capture_gameday(lv['week'])
        return self.gameday_view()

    def half_take(self, i, on=True):
        ok = self.runner.half_take(int(i), bool(on)) if self.runner is not None else False
        return self.gameday_view() if ok else dict(ok=False, why='no halftime recommendation to take')

    def _finish_live(self):
        """A save or an advance with a game still open plays it out first."""
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None or lv['done']: return False
        if lv['halftime_open']: self.runner.live_step('resume')
        self.runner.live_step('finish')
        if lv['halftime_open']: self.runner.live_step('resume'); self.runner.live_step('finish')
        self._capture_gameday(lv['week'])
        return True

    def gameday_view(self, week=None, year=None):
        import views
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if week is None and lv is not None and not lv['done']:
            import gameday as GD
            partial = self.runner.live_partial()
            others = [(h, a, r, b) for (h, a, r, b) in getattr(self.runner, 'last_games', [])]
            gd = GD.capture(self.L, others + [(lv['home'], lv['away'], partial, lv['book'])], self.user_team)
            v = views.gameday(self, self.L, self.user_team, gd=gd)
            v['live'] = dict(open=True, at=lv['at'], halftime_open=lv['halftime_open'], score={'home': partial['home'], 'away': partial['away']}, recs=[dict(i=r['i'], side=r['side'], text=r['text'], why=r['why'], taken=r['taken']) for r in (lv.get('half_recs') or [])])
            return v
        if week is not None:
            gd = (getattr(self, 'gamedays', None) or {}).get(f"{year or self.L.year}-{int(week)}")
            if gd is not None: return views.gameday(self, self.L, self.user_team, gd=gd)
        return views.gameday(self, self.L, self.user_team)
