from inbox import player_name as inbox_player
from player_background import home_state
from stable import stable_seed
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
import player_age as PA
from views import CLUB_NAME as CLUB_NAME_
import league as LG, season as SN, postseason as PS, awards as AW, coaching_pool as CP, position_change as PC
import morale as MO, staff as STF, almanac as AL, xp as XP, dev_roll as DR, retirement as RT, regression as RG
import schedule as SCH, contracts as CT, waivers as WV, extensions as EXT, tags as TG, market as MK, trades as TRD
import draft_class as DC, scouting as SC, spring as SP, draft as DFT, practice_squad as PSQ, cutdown as CD, newgens as NG
import gameplan_week as GW, inbox as IB, negotiations as NG_
import inbox_events as IE
from franchise import prune_pool

WEEKS = 18


class Session:
    def __init__(self, league, rng, user_team):
        self.L = league; self.rng = rng; self.user_team = user_team
        self.L.user_team = user_team
        # Legacy saves may contain unresolved ranges. Clone the stream so this
        # one-time migration preserves the next live simulation draw.
        import copy
        migration_rng = copy.deepcopy(rng)
        for p in sorted(league.players.values(), key=lambda p: p.pid):
            XP.resolve_potential(p, migration_rng)
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
        for t in L.teams.values(): t.phase = 'season'
        PA.sync_session(s)
        return s

    @classmethod
    def load(cls, text):
        from competition_names import migrate_save
        d = migrate_save(json.loads(text))
        L = LG.League.load(d)
        rng_ = np.random.default_rng(d.get('_seed_state', None))
        if d.get('_rng_state') is not None:
            rng_.bit_generator.state = d['_rng_state']
        try:
            L.seed_tenures(np.random.default_rng(int(d.get('_seed_state', 1) or 1) + 7))       # a save where every coach shares one tenure
            if any(getattr(t, 'expected_cached', None) is None for t in L.teams.values()): L.set_expectations()
        except Exception as e:
            import sys; print('tenure/expectation seed failed:', e, file=sys.stderr)
        s = cls(L, rng_, d.get('_user_team'))
        s.votes = s._recorded_votes()
        if d.get('_week_book') is not None: L.week_book = d['_week_book']
        s.stop = tuple(d.get('_stop', ['week', 1]))
        if (s.stop[0] in ('cutdown', 'wire') or
                (s.stop[0] == 'offseason' and s.OFFSEASON[s.stop[1]][1] == 'step_cutdown')):
            for t in L.teams.values(): t.phase = 'season'
            # Older builds posted this before cutdown/waivers had finished.
            # Replace it with a fresh roster-aware report upon entering Week 1.
            L.inbox = [m for m in getattr(L, 'inbox', [])
                       if not (m.get('kind') == 'game_plan' and m.get('year') == L.year
                               and (m.get('payload') or {}).get('link') == 'gameplan:1')]
            reports = getattr(L, 'game_plan_reports', None) or {}
            reports.pop(1, None)
            reports.pop('1', None)
        s.gameday = d.get('_gameday'); s.gamedays = d.get('_gamedays') or {}; s.played = bool(d.get('_played', False))
        if d.get('_runner_state'):
            s.runner = SN.SeasonRunner(s.L, s.rng)
            s.runner.load_state(d['_runner_state'])
        if d.get('_post_live'):
            if s.runner is None: s.runner = SN.SeasonRunner(s.L, s.rng)
            s.post_live = PS.Postseason.from_dict(s.runner, d['_post_live'])
        import practice_integration as PI
        PI.migrate(self=s, saved=d)
        if s.post_live is not None: s.L._post_ref = s.post_live
        lp = d.get('_live_pending')
        if lp and s.played and (s.stop[0] == 'week' or (s.stop[0] == 'playoffs' and lp.get('playoffs'))):
            if s.runner is None: s.runner = SN.SeasonRunner(s.L, s.rng)
            s.runner.week = lp['week']
            if lp.get('playoffs') and getattr(s, 'post_live', None) is not None:
                post = s.post_live
                held = getattr(post, 'held', None)
                rnd, conf = (held[0], held[1]) if held else (PS.Postseason.ROUNDS[max(0, min(3, int(s.stop[1]) - 1))] if len(s.stop) > 1 else 'WC', 'NFL')
                def _close(res, _c=conf, _h=lp['home'], _a=lp['away'], _r=rnd): post.record(_r, _c, _h, _a, res); post.held = None
                s.runner.open_live(lp['home'], lp['away'], lp['week'], playoffs=True, on_close=_close,
                                   replay_start=lp.get('start'))
            else:
                s.runner.open_live(lp['home'], lp['away'], lp['week'], replay_start=lp.get('start'))
            if lp.get('start'):
                s.runner.replay_live(lp.get('actions') or [], d['_rng_state'])
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
            # a closed postseason in the offseason belongs to the season that just ended: the year itself until the
            # New Year step has run (awards, carousel, retirements), and the year before after it. The old rule read
            # the league's week, which the offseason keeps at 22, and stamped last season's bracket with the new year;
            # that made the new year look closed and its review and meetings appear before it was played
            roll_i = next((i for i, (_n, fn) in enumerate(cls.OFFSEASON) if fn == 'step_roll'), 3)
            if s.post.champion and s.stop[0] == 'offseason':
                right = int(L.year) if int(s.stop[1]) <= roll_i else int(L.year) - 1
                if s.post.year is None or int(s.post.year) != right: s.post.year = right
                if getattr(L, 'season_closed_year', None) != right: L.season_closed_year = right
            elif s.post.champion and s.stop[0] == 'week' and s.post.year is not None and int(s.post.year) >= int(L.year):
                s.post.year = int(L.year) - 1; L.season_closed_year = int(L.year) - 1
        s.draft = None
        try:
            # THE PHASE FOLLOWS THE STOP. A session standing at a week (or in the playoffs) is in season, whatever phase
            # the league last wrote: a save that reached Week 1 with the phase still reading free_agency made every
            # draft-cycle page (the Spring, Draft Results, the visits) believe it was the offseason and show last year
            if s.stop[0] in ('week', 'playoffs') and L.phase in ('offseason', 'free_agency'):
                L.set_phase('regular')
        except Exception: pass
        try:
            import personality as _PT
            _PT.reconcile_all(L)                              # traits that contradict each other in words, from before the reconcile step existed
        except Exception: pass
        try:
            # THE DRAFT CYCLE'S USER STATE NAMES PROSPECTS. Visits, their timing and the board that name players who are
            # no longer in the class (drafted, signed, or from a class already gone) are dropped; an older build kept
            # them, so last spring's thirty stayed 'spoken for' against the new class
            import views_draft as _VD
            pool = {p.pid for p in _VD._pool(L)}
            if getattr(L, 'user_visits', None):
                L.user_visits = [pid for pid in L.user_visits if pid in pool]
                L.user_visit_week = {k: v for k, v in (getattr(L, 'user_visit_week', None) or {}).items() if k in pool}
            ub = getattr(L, 'user_board', None) or {}
            if ub:
                for key in ('rank', 'ranks', 'order', 'dnd'):
                    v = ub.get(key)
                    if isinstance(v, list): ub[key] = [pid for pid in v if pid in pool]
                    elif isinstance(v, dict): ub[key] = {k: x for k, x in v.items() if k in pool}
        except Exception: pass
        try:
            # a last_draft with no results but a draft on the record is rebuilt from the record, so its page has rows
            ld = getattr(L, 'last_draft', None)
            if ld and not ld.get('results'):
                yr = int(ld.get('year', -1)) + 1
                rows = sorted(((int(x.get('selection') or 0), x.get('team'), x.get('pid')) for x in L.transactions if x.get('kind') == 'draft' and int(x.get('year', -9)) == yr and x.get('selection')), key=lambda r: r[0])
                if rows: ld['results'] = rows
        except Exception: pass
        try:
            # Older builds could file these pages before the club's season ended. An eliminated club's meetings
            # and review are valid during the playoffs, even while the league season is still open.
            import views_frontoffice as VF
            if not VF._club_done(s, L, s.user_team):
                (getattr(L, 'exit_meetings', None) or {}).pop(str(L.year), None)
                ((getattr(L, 'history', None) or {}).get(str(L.year)) or {}).pop('review', None)
        except Exception: pass
        # Drain legacy CPU-only offer sheets without consuming the live RNG.
        import copy
        MK.resolve_offer_sheets(L, copy.deepcopy(s.rng))
        IB.reconcile(L)
        IE.remember(L)
        try: s._open_fa_if_due()
        except Exception as e:
            import sys; print('open round on load failed:', e, file=sys.stderr)
        try:
            # a class built before arms were treated as tools: a quarterback prospect's arm is lifted to the tool
            # scale once (an 80-overall rookie about 87, a 70 about 82), and the scouting reads follow
            import scouting as SC
            # arms are drawn as tools, loosely tied to overall the way the college file is (mean 86, sd 3.8,
            # correlation about 0.5): a 65 can carry a 99, an 81 an 88 or a little less
            for p in list(getattr(L, 'draft_pool', None) or []) + list(getattr(L, 'next_class', None) or []):
                if p.pos not in ('QB', 'K', 'P') or p.xp_spent.get('_arm_fixed') == 2: continue
                key = 'throw_power_rating' if p.pos == 'QB' else 'kick_power_rating'
                r_ = np.random.default_rng(stable_seed((p.pid, key)))
                mean = (84.0 if p.pos == 'QB' else 86.0) + 0.35 * (float(p.ovr) - 72.0)
                p.ratings[key] = float(np.clip(r_.normal(mean, 3.5), 67.0, 99.0))
                for abbr_, views in (getattr(L, 'scouting', None) or {}).items():
                    v = views.get(p.pid)
                    if v is not None:
                        try: SC._refresh(v, p)
                        except Exception: pass
                p.xp_spent['_arm_fixed'] = 2
        except Exception as e:
            import sys; print('arm fix failed:', e, file=sys.stderr)
        NG.upgrade_saved_te_class(L)
        try: s._backfill_history()
        except Exception as e:
            import sys; print('history backfill failed:', e, file=sys.stderr)
        if d.get('_draft_live'):
            import draft_day as DD
            live = d['_draft_live']
            s.draft = DD.Draft(s.L, s.rng, live['year'], user_team=s.user_team, auto_pick=live.get('auto', False),
                               level=live.get('level'), scale=live.get('scale'))
            s.draft.taken = set(pid for pid in live['taken'] if pid in s.L.players)
            s.draft.results = [(sel, t, s.L.players[pid]) for sel, t, pid in live['results'] if pid in s.L.players]
            s.draft.trades = [tuple(x) for x in live.get('trades', [])]
            s.draft.dealt = {frozenset(x) for x in live.get('dealt', [])}
            s.draft.last_dealt = live.get('last_dealt')
            s.draft.trade_targets = {int(sel): dict(intent) for sel, intent in live.get('trade_targets', {}).items()
                                     if intent.get('pid') in s.L.players and intent.get('buyer') in s.L.teams}
        # Saves made before honors moved to the week before the final have
        # already crossed that calendar boundary. Publish the ballot on load.
        if (s.stop[0] == 'playoffs' and len(s.stop) > 1 and int(s.stop[1]) >= 3
                and s.post_live is not None and len(getattr(s.post_live, 'conf_champs', {}) or {}) == 2):
            s._announce_honors()
        if s.stop[0] == 'week' and not s.played:
            GW.refresh_open_report(L, int(s.stop[1]))
        PA.sync_session(s)
        if s.stop[0] == 'offseason':
            s._offseason_condition_reset()
        return s

    def _offseason_condition_reset(self):
        """Summer restores freshness for every club; injury healing stays separate."""
        for st in self.runner.states.values():
            st.cond.cond.clear()
            st.cond.snaps.clear()
            st.jaded.clear()

    def _recorded_votes(self):
        """Rehydrate this season's ballot without voting again or consuming RNG.

        League.awards already persists the results. Development expects Player
        objects, while the saved ledger contains IDs (except COTY, a team).
        """
        awards = getattr(self.L, 'awards', {}) or {}
        recorded = awards.get(self.L.year, awards.get(str(self.L.year)))
        if recorded is None:
            return None
        votes = {}
        for key, winner in recorded.items():
            if key == 'coty':
                votes[key] = winner
            elif isinstance(winner, list):
                votes[key] = [p for pid in winner if (p := self.L.player(pid)) is not None]
            else:
                votes[key] = self.L.player(winner) if winner is not None else None
        return votes

    def save(self):
        # Build the snapshot once; the final encoder handles the league's
        # numpy values and sets without an intermediate JSON round trip.
        d = self.L.to_dict()
        if getattr(self.L, 'week_book', None) is not None:
            d['_week_book'] = self.L.week_book
        if self.runner is not None:
            d['_runner_state'] = self.runner.save_state()
        if getattr(self, 'post_live', None) is not None:
            d['_post_live'] = self.post_live.to_dict()
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is not None and not lv['done']:
            # A generator is not serializable. Replay the same decisions from its opening state on load.
            d['_live_pending'] = dict(home=lv['home'], away=lv['away'], week=lv['week'],
                                      playoffs=bool(lv.get('playoffs')), start=lv['start'],
                                      actions=lv['actions'])
        d['_stop'] = list(self.stop)
        d['_rng_state'] = self.rng.bit_generator.state
        # Keep a seed for older builds without advancing the live generator merely to save the game.
        d['_seed_state'] = stable_seed(json.dumps(d['_rng_state'], sort_keys=True))
        d['_user_team'] = self.user_team
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
        d['_draft_live'] = (dict(year=self.draft.year, taken=sorted(self.draft.taken),
                                 results=[(sel, t, p.pid) for sel, t, p in self.draft.results],
                                 trades=[list(x) for x in self.draft.trades],
                                 dealt=[sorted(x) for x in self.draft.dealt],
                                 last_dealt=self.draft.last_dealt, auto=self.draft.auto,
                                 level=self.draft.level, scale=self.draft.scale, trade_targets=self.draft.trade_targets)
                            if self.draft_live() else None)
        return json.dumps(d, default=LG._session_json_default)

    def live_journal(self):
        """Small autosave between full saves while the user's game is open."""
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None or lv['done']: return None
        return dict(home=lv['home'], away=lv['away'], week=lv['week'],
                    actions=lv['actions'], rng_state=self.rng.bit_generator.state)

    def apply_live_journal(self, journal):
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if not journal or lv is None or lv['done']:
            return False
        if (lv['home'], lv['away'], lv['week']) != (journal.get('home'), journal.get('away'), journal.get('week')):
            return False
        actions = journal.get('actions') or []
        base = lv['actions']
        if len(actions) < len(base): return False
        if json.dumps(actions[:len(base)], sort_keys=True) != json.dumps(base, sort_keys=True):
            raise ValueError('Live game journal does not match the saved game')
        if len(actions) > len(base):
            self.runner.replay_live(actions[len(base):], journal['rng_state'])
            lv['actions'] = list(actions)
        return True

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
            # the count under the day, red while over the limit and yellow once at or under it
            return dict(title='Cut-Down Day', sub=f"{n}/{self.ROSTER_MAX}", tone=('danger' if n > self.ROSTER_MAX else 'warn'), played=False)
        if k == 'wire':
            import waivers as WV
            n = sum(1 for e in WV.pending(self.L) if e.get('ahead', None) is None and e.get('from_team') != self.user_team and self.L.player(e['pid']) is not None and self.L.player(e['pid']).team is None)
            return dict(title='Post-Cutdown Waivers', sub=f"{n} reach your priority · advance to Week 1 when ready", played=False)
        if k == 'week':
            wk = self.stop[1]; opp = self._opponent(wk)
            if getattr(self, 'played', False):
                lv = getattr(self.runner, 'live', None) if self.runner is not None else None
                if lv is not None and not lv['done']:
                    return dict(title='Game Day', sub=(('Overtime: your adjustments' if lv.get('adjustment_period') == 'overtime' else 'Halftime: your adjustments') if lv['halftime_open'] else 'Your game is on; finish it to advance'), played=True, live=True)
                return dict(title=(f"Advance to Week {wk + 1}" if wk < WEEKS else 'Advance to the Playoffs'), sub=(f"Week {wk} is in the books"), played=True)
            if self._practice_pending():
                return dict(title='Run Practice', sub=f'Week {wk} preparation', played=False)
            return dict(title=f"Sim Week {wk}", sub=(f"{'at' if opp and opp[1] else 'vs'} {opp[0]}" if opp else 'Bye Week'), played=False)
        if k == 'playoffs':
            rnd_i = int(self.stop[1]) if len(self.stop) > 1 else 0
            lv = getattr(self.runner, 'live', None) if self.runner is not None else None
            if lv is not None and not lv['done']:
                return dict(title='Game Day', sub=(('Overtime: your adjustments' if lv.get('adjustment_period') == 'overtime' else 'Halftime: your adjustments') if lv['halftime_open'] else 'Your playoff game is on; finish it to advance'), played=True, live=True)
            if rnd_i >= 4: return dict(title='Close the Season', sub='the champion is crowned', played=True)
            rnd = PS.Postseason.ROUNDS[rnd_i]; name = PS.Postseason.ROUND_NAMES[rnd]
            SHORT = {'WC': 'Wild Card', 'DIV': 'Divisional Round', 'CONF': 'Conference Finals', 'SB': 'Championship Game'}   # the button has one line; 'Conference Championship' broke the header
            name = SHORT.get(rnd, name)
            post = getattr(self, 'post_live', None); user = self.user_team
            if self.played:
                nxt = SHORT[PS.Postseason.ROUNDS[rnd_i + 1]] if rnd_i + 1 < 4 else 'Offseason'
                return dict(title=f'Advance to the {nxt}', sub=f'The {name} is in the books', played=True)
            if self._practice_pending():
                return dict(title='Run Practice', sub=f'{name} preparation', played=False)
            if post is not None and hasattr(post, 'alive'):
                alive = {t for a in post.alive.values() for t in a.values()} if rnd != 'SB' else set(post.conf_champs.values())
                if user in alive:
                    ms = [m for m in post.matchups(rnd) if user in (m[1], m[2])]
                    if ms:
                        c, h, a = ms[0]
                        if rnd == 'SB': v = PS.sb_venue(self.L); return dict(title=f"Play Championship Game {v['numeral']}", sub=f"vs {a if h == user else h} at {v['stadium']}")
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
                return dict(title='Franchise Tag and Re-Sign', sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)} · {len(sh['ufa'])} unrestricted, {len(sh['rfa'])} restricted · {tag_s}")
            except Exception: pass
        if name in self.FA_STEPS or name == 'step_fa_close':
            n = len([x for x in self.L.free_agents if self.L.player(x)])
            import negotiations as NG
            mine = sum(1 for t in NG._threads(self.L) if t['kind'] == 'fa_offseason' and t['state'] in ('waiting', 'countered', 'match_requested'))
            return dict(title=('Close the Market' if name == 'step_fa_close' else f"Close Round {self.FA_STEPS[name]}"), sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)} · {n} on the market · {mine} offer{'s' if mine != 1 else ''} out")
        return dict(title=title, sub=f"Offseason Step {i + 1} of {len(self.OFFSEASON)}")

    ROSTER_MAX, ROSTER_MIN = 53, 46

    def blocking(self):
        import inbox as IB
        IB.reconcile(self.L)
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is not None and not lv['done']:
            return [dict(id=None, subject='Your game is still being played: finish it first', kind='live', go='#gameday')]
        """Decisions that must be made before the next stop. Empty list = nothing blocks."""
        out = []
        if self.stop[0] == 'offseason' and self.OFFSEASON[self.stop[1]][1] == 'step_extensions':
            pending = TG.pending_tender_cost(self.L)
            room = TG.power(self.L, self.L.teams[self.user_team], TG.CAP.get(self.L.year, 301.2))
            if pending > 0 and pending > room + .0005:
                out.append(dict(id=None, kind='cap', go='#personnel/retain',
                                subject='Your pending tenders no longer fit: clear cap space or withdraw a tender.'))
        # THE ROSTER RULE. A club plays with 53 at most and 46 at least; the game will not
        # run a week, or leave camp, until yours is legal. A new franchise starts in camp at
        # 68 and cuts to 53 before week 1, the way every club does.
        offseason_cutdown = (self.stop[0] == 'offseason'
                             and self.OFFSEASON[self.stop[1]][1] == 'step_cutdown')
        if offseason_cutdown or self.stop[0] in ('week', 'playoffs', 'cutdown', 'wire'):
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
                    existing['body'] = (f'You are carrying {n}. Cut to {self.ROSTER_MAX} before Sunday.' if n > self.ROSTER_MAX else f'You are at {n}; sign to at least {self.ROSTER_MIN} before Sunday.')
                    existing['payload']['link'] = 'club' if n > self.ROSTER_MAX else 'personnel:fa'
                out.append(dict(id=existing.get('id'), subject=subj, kind='roster', go=('#club' if n > self.ROSTER_MAX else '#personnel/fa')))
            elif existing is not None:
                existing['status'] = 'done'
        team = self.L.teams.get(self.user_team)
        if team is not None and getattr(team, 'cap', None) is not None:
            team.sync_cap()
            # Cutdown must fit all contracts before its full-roster ledger
            # takes effect; earlier offseason stops retain top-51 accounting.
            cap_phase = 'season' if offseason_cutdown or self.stop[0] in ('cutdown', 'wire') else team.phase
            over = team.cap.charges(cap_phase) - team.cap.limit
            if over > .0005:
                out.append(dict(id=None, kind='cap', go='#frontoffice/cap',
                                subject=f'You are ${over:.2f}m over the cap: restructure or release players before advancing'))
        for m in getattr(self.L, 'inbox', []):
            if IB.is_decision(m):
                if m.get('kind') == 'trade_offer' or (m.get('payload') or {}).get('poach') or (m.get('kind') == 'offer_sheet' and m.get('team') == self.user_team):
                    out.append(dict(id=m.get('id'), subject=m.get('subject'), kind=m.get('kind')))
        return out

    def _league_log_notes(self):
        try:
            import league_notes as LN
            fa_now = self.stop[0] == 'offseason' and self.OFFSEASON[self.stop[1]][1] in (*self.FA_STEPS, 'step_fa_close')
            LN.transactions(self.L, self.L.week or 0, skip_signings=fa_now)
        except Exception: pass

    def advance(self):
        PA.sync_session(self)
        # References follow a successful calendar action, not football week numbers.
        blocks = [b for b in self.blocking() if b['kind'] in ('offer_sheet', 'cap', 'roster')]
        if blocks:
            return dict(done='Blocked', next=self.next_label(), why=blocks[0]['subject'])
        from game_availability import FieldabilityError
        try:
            result = self._advance()
        except FieldabilityError as exc:
            # Keep completed scores and the calendar position for a safe retry.
            if self.runner is not None: self.runner._skip_game = None
            return dict(done='Blocked', next=self.next_label(), why=str(exc))
        if result.get('done') != 'Blocked':
            STF.resolve_references(self.L, advanced=True)
            IB.reconcile(self.L)
        PA.sync_session(self)
        return result

    def _advance(self):
        if self._skip_empty_offseason_waivers():
            self._open_fa_if_due()
            return dict(done='No offseason waivers to resolve', next=self.next_label())
        k = self.stop[0]
        if k == 'cutdown':
            # camp breaks: every club cuts to 53 (yours must already be there), the wire runs, the squads fill
            if any(b['kind'] == 'roster' for b in self.blocking()):
                return dict(done='Blocked', next=self.next_label(), why=self.blocking()[0]['subject'])
            self.step_cutdown()
            self.stop = ('wire',); self.played = False
            return dict(done='Cutdown', next=self.next_label())
        if k == 'wire':
            if self.step_clear_wire() is False:
                if getattr(self, '_cpu_roster_block', None):
                    return dict(done='Blocked', next=self.next_label(), why=self._cpu_roster_block)
                return dict(done='Cap compliance cuts are on waivers', next=self.next_label())
            self.stop = ('week', 1); self.played = False
            try: GW.post_report(self.L, 1)
            except Exception as e:
                import sys; print('Week 1 report failed:', e, file=sys.stderr)
            return dict(done='Post-Cutdown Waivers', next=self.next_label())
        if k == 'week':
            wk = self.stop[1]
            if self.runner is None:
                self.runner = SN.SeasonRunner(self.L, self.rng)
            if not getattr(self, 'played', False):
                if self._practice_pending():
                    self.practice_act('run')
                    return dict(done='Practice complete', next=self.next_label())
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
            self._ir_ready_notes(wk + 1)
            self.played = False
            self.stop = ('week', wk + 1) if wk < WEEKS else ('playoffs', 0)
            if wk >= WEEKS:
                self._playoff_prep(0)
                post = self.post_live
                if post is not None:
                    field = {t for sd in post.seeds.values() for t in sd}
                    if self.user_team not in field: self._post_review('missed')
                    self._ai_exit_meetings([a for a in self.L.teams if a not in field])
            return dict(done=f'Week {wk}', next=self.next_label())
        if k == 'playoffs':
            # THE PLAYOFFS, A ROUND AT A TIME, with the whole week around each game. Entering a round (from week 18's
            # roll or the roll after the last round) is the prep: the bracket is seeded, the round's games go into the
            # schedule, the injury desk lists the hurt with their Play/Sit notes, the opponent report and game plan
            # post, and the inbox gets the round. Advance then plays the round: the other games sim onto the strip and
            # yours opens live on Game Day. Advance again rolls the week (XP, morale, injuries, notes) into the next
            # round's prep. After the Championship Game the season closes.
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
            if rnd == 'SB' and len(getattr(post, 'conf_champs', {}) or {}) == 2:
                self._announce_honors()
            self.L._post_ref = post
            if self.played and not any(g[0] == rnd for g in post.games):
                self.played = False                       # a save from before the round flow: this round has not been played
                self._playoff_prep(rnd_i)
            if not self.played:
                if self._practice_pending():
                    self.practice_act('run')
                    return dict(done='Practice complete', next=self.next_label())
                self.runner.prepare_practice(wk_)
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
            self._ir_ready_notes(wk_ + 1)
            self.played = False
            if self.user_team in (getattr(post, 'exit_round', {}) or {}):
                self._post_review('eliminated')
            losers = [a for a, r in (getattr(post, 'exit_round', {}) or {}).items() if r == rnd]
            self._ai_exit_meetings(losers)
            if rnd == 'CONF':
                self._announce_honors()
                self._senior_bowl()
            if rnd_i + 1 < len(PS.Postseason.ROUNDS):
                self.stop = ('playoffs', rnd_i + 1)
                self._playoff_prep(rnd_i + 1)
                return dict(done=PS.Postseason.ROUND_NAMES[rnd], next=self.next_label())
            self.stop = ('playoffs', 4)
            return self._close_playoffs()
        i = self.stop[1]
        if self.OFFSEASON[i][1] == 'step_cutdown':
            roster_blocks = [b for b in self.blocking() if b['kind'] == 'roster']
            if roster_blocks:
                return dict(done='Blocked', next=self.next_label(), why=roster_blocks[0]['subject'])
        if self.draft_live():
            self.draft.auto = True; self.draft.sim_all()
            if not self.draft.done:
                self.draft.auto = False
                return dict(done='Your draft board has no eligible player', next=self.next_label())
            self._draft_over()
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
            # Every year's cutdown gets the same claim window as initial camp.
            # Clearing that wire fills squads and enters the regular phase.
            self.stop = ('wire',); self.runner = None; self.played = False
        return dict(done=self.OFFSEASON[i][0], next=self.next_label())

    def _announce_honors(self):
        """Announce regular-season honors after the conference finals and before the Championship Game."""
        if self.L.year in self.L.awards:
            return
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
                    if p.team == self.user_team: mine.append([inbox_player(p), names.get(k, k) if k not in ('all_pro_1', 'all_pro_2') else ('All-Pro first team' if k == 'all_pro_1' else 'All-Pro second team')])
                if k not in ('all_pro_1', 'all_pro_2'):
                    p = self.L.player(getattr(ws[0], 'pid', ws[0])) if not hasattr(ws[0], 'pid') else ws[0]
                    if p is not None: lines.append([names.get(k, k), inbox_player(p), p.pos, p.team])
            body = f'{len(mine)} honors for your team.' if mine else 'None of your players were named.'
            sections = ([IB.mail_section('Your team', mine, ['Player', 'Honor'])] if mine else []) + [IB.mail_section('League awards', lines, ['Award', 'Player', 'Position', 'Team'])]
            IB.post(self.L, 'league', "The season's honors", body, sender='league', payload=dict(link='league:awards', mail_sections=sections))
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
                         ('stats', lambda: VL.stats(self, self.L, self.user_team)), ('bracket', lambda: VL.bracket(self, self.L, self.user_team)), ('review', lambda: VF.season_review(self, self.L, self.user_team))):
            try:
                d = fn(); d.pop('rail', None); snap[page] = d
            except Exception as e:
                import sys; print('snapshot failed:', page, e, file=sys.stderr)

    def _senior_bowl(self):
        """The week before the Championship Game: every room's second look at the seniors in Mobile, and the assistants'
        word on who helped himself."""
        try:
            import scouting as SC
            from views import surname
            moves = SC.senior_bowl(self.L, self.rng)
            if not moves: return
            moves.sort(key=lambda x: -x[0])
            up = [f"{inbox_player(p, surname(p.name))} ({p.pos}, {d:+.1f})" for d, p in moves[:3] if d > 0.4]
            down = [f"{inbox_player(p, surname(p.name))} ({p.pos}, {d:+.1f})" for d, p in moves[-3:][::-1] if d < -0.4]
            body = f"Your scouts watched {len(moves)} seniors. Their marks on your board have moved; participants carry the Senior Bowl tag."
            sections = ([IB.mail_section('Helped himself', up)] if up else []) + ([IB.mail_section('Hurt himself', down)] if down else [])
            IB.post(self.L, 'draft', "Senior Bowl week: the scouts' word", body, sender='scouts', payload=dict(link='draft:board', mail_sections=sections))
        except Exception as e:
            import sys; print('senior bowl failed:', e, file=sys.stderr)

    def _black_monday(self, clubs):
        """The clubs roll their firings, and a new head coach comes for his staff, which can mean a request for one of
        your coordinators. Runs once, at Step 2 of the offseason."""
        fired = []
        try:
            fired = PS.run_firings(self.L, self.rng, clubs=list(clubs))
            for abbr, bg in fired:
                t = self.L.teams[abbr]
                who = (t.gm.name + ' takes over.') if t.gm else ('The search is on; ' + (f"they are waiting on {self.L.pending_hires[abbr]['first']}." if abbr in (getattr(self.L, 'pending_hires', None) or {}) else 'a name is coming.'))
                IE.post(self.L, f'coach-hire-{self.L.year}-{abbr}-{t.gm.name}' if t.gm else f'coach-search-{self.L.year}-{abbr}', 'league', f"{t.abbr} makes a change", f"{CLUB_NAME_.get(abbr, abbr)} moved on from its head coach. {who}", sender='league')
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
                    IB.post(self.L, 'league', "The coaching market", f"{len(fired)} club{'s' if len(fired) != 1 else ''} making coaching changes.", sender='league', payload=dict(mail_sections=[IB.mail_section('Notable coaching candidates', lines)]))
        except Exception as e:
            import sys; print('black monday failed:', e, file=sys.stderr)
        return fired

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
        if not IE.seen(self.L, key_):
            try:
                v = self.frontoffice('season_review')
                slot = PS.provisional_slot(self.L, getattr(self, 'post_live', None) or getattr(self, 'post', None), self.user_team)
                slot_line = f" You pick {slot}{'st' if slot % 10 == 1 and slot != 11 else 'nd' if slot % 10 == 2 and slot != 12 else 'rd' if slot % 10 == 3 and slot != 13 else 'th'} in the first round." if slot else ''
                IE.post(self.L, key_, 'review', f"The season, reviewed: {v['record']}, {v['finish'].lower()}", f"{v['owner']['line']} The review is on your desk: the units against the league, who rose and who fell, next year's money and the players whose deals are up.{slot_line}", sender='front office', payload=dict(key=key_, link='front_office:review'))
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
                sections = [IB.mail_section(label, [[inbox_player(p), p.pos, str(round(p.ovr))] for p in players], ['Player', 'Position', 'OVR'])
                            for label, players in [('Expiring contracts', up), ('Two years left: worth a look', two)] if players]
                body = f"About ${limit_next - committed_next:.0f}m of room next year."
                if not IE.seen(self.L, f"extwin-{self.L.year}"):
                    IE.post(self.L, f"extwin-{self.L.year}", 'contract', "The extension window is open", body, sender='front office', payload=dict(key=f"extwin-{self.L.year}", link='personnel:extensions', mail_sections=sections))
        except Exception as e:
            import sys; print('extension window note failed:', e, file=sys.stderr)
        try:
            import views_frontoffice as VF
            ms = [m for m in VF.build_exit_meetings(self, self.L, self.user_team) if not m.get("answer")]
            if ms:
                from views import surname
                rows = [[inbox_player(self.L.player(x['pid'])), x.get('quote') or x.get('kind', '').replace('_', ' ').title()] for x in ms if self.L.player(x['pid'])]
                if not IE.seen(self.L, f"exit-{self.L.year}"):
                    IE.post(self.L, f"exit-{self.L.year}", 'exit', f"Exit meetings: {len(ms)} players want a word", 'Players waiting to discuss their future.', sender='assistants', payload=dict(key=f"exit-{self.L.year}", link='front_office:exit', mail_sections=[IB.mail_section('Meetings', rows, ['Player', 'Reason'])]))
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
        Championship Game letter names the site and walks both finalists' road to it."""
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
            if not ms: return f"Championship Game", "The conference championships are not yet decided."
            c, h, a = ms[0]
            site = PS.sb_venue(L)
            def road(x):
                won = [g for g in post.games if g[0] != 'SB' and (g[2] == x or g[3] == x)]
                steps = []
                for (r_, cf, hm, aw, hp, ap) in won:
                    opp = aw if hm == x else hm; mine_, theirs = (hp, ap) if hm == x else (ap, hp)
                    steps.append(f"{nm(opp)} {mine_}-{theirs} in the {PS.Postseason.ROUND_NAMES[r_].replace(' Round', '')}")
                if x in seed_of and seed_of[x] == 1: steps.insert(0, 'the first-round bye')
                return '\n'.join(steps) if steps else 'the conference'
            conf_of = {t: cf for cf, sd in (getattr(post, 'seeds', {}) or {}).items() for t in sd}
            lines = [f"Championship Game {site['numeral']} is set: {nm(a)} against {nm(h)}, at {site['stadium']} in {site['city']}.",
                     f"{nm(a)}, the {seed_of.get(a, '?')} seed out of the {conf_of.get(a, '')}, finished {rec(a)}. Road to the final:\n{road(a)}",
                     f"{nm(h)}, the {seed_of.get(h, '?')} seed out of the {conf_of.get(h, '')}, finished {rec(h)}. Road to the final:\n{road(h)}"]
            if user in (h, a): lines.append("You are in it. The game plan is on your desk.")
            return f"Championship Game {site['numeral']}: {nm(a)} vs {nm(h)} at {site['stadium']}", '\n\n'.join(lines)
        games = [f"{tag(a)} at {tag(h)}, {STADIUM.get(h, nm(h))}" for c, h, a in ms]
        if mine is not None:
            c, h, a = mine
            opener = f"Your {name} game: {'at ' + nm(h) + ', ' + STADIUM.get(h, '') if a == user else 'vs ' + nm(a) + ' at home'}. They finished {rec(h if a == user else a)}."
        else:
            alive = {t for al in post.alive.values() for t in al.values()}
            opener = f"You have the bye this round; the winner of the worst surviving seed's game comes to you." if user in alive else "Your season is over."
        subject = {'WC': f"Wild Card Weekend: {len(ms)} games", 'DIV': f"Divisional Round: {len(ms)} games", 'CONF': "Conference Championships: the two finals"}[rnd]
        return subject, opener + ('\n\nThe round\n' + '\n'.join(games) if games else '')

    def _close_playoffs(self):
        """After the Championship Game: the champion, the draft order, the firings, and into the offseason."""
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
        self.post, self.order, _ = PS.close_season(self.L, self.runner, self.rng, post=post, fire=False)   # firings and hires wait for Step 2
        self.fired = []
        self.post.year = self.L.year
        self.L.season_closed_year = int(self.L.year)                  # this year's season is over: its review and meetings are its own
        self._post_review('closed')
        self._snapshot_season()
        from cap_accounting import settle_week
        settle_week(self.L,18)
        # THE DAY AFTER THE CHAMPIONSHIP GAME: practice squad contracts expire (every squad player is a free agent; his club
        # can sign him back on the market like anyone else), and the offseason heals. A player's weeks left run off
        # against the thirty weeks to camp; only a long-term injury carries into next season
        try:
            import practice_squad as PSQ_, inbox as IB_
            mine = [p for p in list(PSQ_.squad(self.L.teams[self.user_team]))] if self.user_team else []
            for t in self.L.teams.values():
                for p in list(PSQ_.squad(t)): PSQ_.release_from_squad(self.L, t.abbr, p.pid)
            if mine:
                IB_.post(self.L, 'club', f"Your practice squad's {len(mine)} players are free agents", f"Practice squad deals expire when the season ends. {', '.join(f'{inbox_player(p)} ({p.pos})' for p in mine[:8])}{'…' if len(mine) > 8 else ''} are on the market; sign any of them back from Free Agency to the roster or, after camp, to the squad.", sender='assistants', payload=dict(link='fa'))
            OFFSEASON_WEEKS = 30
            for p in self.L.players.values():
                if p.out_until is None: continue
                left = 8 if int(p.out_until) >= 99 else max(0, int(p.out_until) - 22)     # season-ending IR: the rest of it heals over the summer
                p.out_until = None if left <= OFFSEASON_WEEKS else int(left - OFFSEASON_WEEKS)
            PSQ_.reset_season(self.L)
        except Exception as e:
            import sys; print('season-end release and healing failed:', e, file=sys.stderr)
        self._ai_exit_meetings([a for a in self.L.teams if f"{a}-{self.L.year}" not in (getattr(self.L, 'exit_meetings', {}) or {})])
        try: self.post.seeds_at_close = dict(getattr(post, 'seeds', {}) or {})
        except Exception: self.post.seeds_at_close = {}
        MO.postseason(self.L, self.post); CP.top_up(self.L, self.rng); PC.offseason(self.L)
        self.post_live = None
        self._offseason_condition_reset()
        self.stop = ('offseason', 0)
        return dict(done='Playoffs', champion=self.post.champion, next=self.next_label())

    # ---- the offseason steps, the same code as franchise.play_year in the same order
    def step_awards(self):
        """Close the season's awards, adding the Championship Game MVP to the announced regular-season ballot."""
        L, rng = self.L, self.rng
        PA.offseason(L, 0)
        honors_announced = L.year in L.awards
        self.votes = self._recorded_votes() if honors_announced else AW.vote(L)
        try:
            self.votes['sb_mvp'] = AW.championship_game_mvp(L, self.post, L.year)
            if self.votes['sb_mvp']: L.awards[L.year]['sb_mvp'] = getattr(self.votes['sb_mvp'], 'pid', self.votes['sb_mvp'])
        except Exception: pass
        try:
            import morale as MO
            XP.pay_awards(L, self.votes)
            for k, who in self.votes.items():
                if k in ('coty',) or not who: continue
                if honors_announced and k != 'sb_mvp': continue
                for w in (who if isinstance(who, list) else [who]):
                    p = L.player(getattr(w, 'pid', w)) if not hasattr(w, 'pid') else w
                    m = MO.ensure(p) if p is not None else None
                    if m is not None: m.apply('major_award' if k in ('mvp', 'opoy', 'dpoy', 'oroy', 'droy', 'protector', 'sb_mvp') else 'all_pro' if k == 'all_pro_1' else 'all_pro_2')
        except Exception as e:
            import sys; print('award pay failed:', e, file=sys.stderr)
        CP.season_prestige(L, self.post, coty_team=self.votes.get('coty'))
        STF.season_end(L, STF.unit_ranks(L, L.year))
        AL.close_season(L, L.year, self.post, self.votes)
        import views_league as VL
        award_view = VL.awards(self, L, self.user_team)
        award_view.pop('rail', None)
        L.__dict__.setdefault('history', {}).setdefault(str(L.year), {})['awards'] = award_view
        XP.close_season(L, self.votes)
        try:
            import club_notes as CN; CN.season_end(L)
        except Exception: pass
        try:
            import league_notes as LN; LN.season_end(L, self.votes)
        except Exception as e:
            import sys; print('league_notes season_end failed:', e, file=sys.stderr)

    def step_coaching(self):
        """STEP 2: the coaching carousel, all of it here. Every club rolls its head coach now (none rolled during the
        playoffs or at the close), the searching clubs hire, and the coordinators and position coaches move."""
        self.fired = self._black_monday(list(self.L.teams))
        STF.carousel(self.L, self.rng, new_head_coaches=[a for a, _bg in (self.fired or [])])
        import league_notes as LN
        LN.coaching_summary(self.L)

    def step_retire(self):
        """STEP 3: retirements and development, all of it here. Age takes what it takes, development traits roll,
        players retire, the Hall votes, and the year ticks."""
        L, rng = self.L, self.rng
        PA.offseason(L, 2)
        # Judge the season's performance against ratings before physical aging,
        # matching the batch franchise path.
        DR.run(L, getattr(self, 'votes', None) or {}, rng)
        # regression: every player takes what age takes; your club's before-and-after is kept for the Regression page
        try:
            RG.run(self.L, self.rng, record_for=self.user_team, tick_age=False)
            rec = (getattr(self.L, 'regression', {}) or {}).get(str(self.L.year), {})
            from views import surname
            hit = sorted([(v['lost'], pid) for pid, v in rec.items() if v['lost'] >= 0.5], reverse=True)
            rows = [[inbox_player(self.L.player(pid)), self.L.player(pid).pos, f'−{lost:.1f}'] for lost, pid in hit if self.L.player(pid)]
            body = (f"{len(hit)} of your players lost ground with age. " if hit else "None of your players lost ground with age this year. ") + "The full attribute analysis is on the Regression page."
            IB.post(self.L, 'club', f"Going into {self.L.year + 1}: what age took", body, sender='assistants', payload=dict(link='club:regression', mail_sections=[IB.mail_section('Regression', rows, ['Player', 'Position', 'OVR lost'])] if rows else []))
        except Exception as e:
            import sys; print('regression report failed:', e, file=sys.stderr)
        RT.run(L, rng); AL.hall_vote(L, L.year)
        try:
            import league_notes as LN; LN.season_end(L, None)          # the Hall class and the retirements, now that they are in
        except Exception as e:
            import sys; print('league_notes retire failed:', e, file=sys.stderr)

    def step_roll(self):
        self.L.user_tag_choice = None          # a new year, a new tag
        self.L.user_tenders = []
        self.L.user_no_tender = []
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
        WV.process(L, rng, 0)

    def step_extensions(self):
        L, rng = self.L, self.rng
        MO.check_resolutions(L, week=None); MO.clear_free_agents(L); prune_pool(L, rng)
        MO.offseason_requests(L, rng); MO.offseason_reset(L); MO.offseason_contracts(L, rng)
        EXT.ai_rookie_options(L); EXT.ai_round(L, rng); EXT.notify_user(L)
        TG.run(L, rng); CT.enforce(L, rng)

    # ---- FREE AGENCY AS STAGES. Each round is a stop on the calendar: it opens (the AI clubs' bids are lodged, your
    # talks show who else is in) when the calendar lands on it, you make your offers on the Free Agency page, and the
    # Advance resolves it: every player signs, waits, or asks for a match, and your answers land in the inbox. Nothing
    # signs on the spot in the open market. The close prices the leftovers;
    # minimum-salary depth is filled after the draft and undrafted signings.
    FA_STEPS = {'step_fa_1': 1, 'step_fa_2': 2, 'step_fa_3': 3}

    def _fa_round(self, k):
        L, rng = self.L, self.rng
        signed, waiting, msgs = MK.resolve_round(L, rng, k, user_team=self.user_team)
        # one note for the round: the AI's notable signings, not one message per deal
        from views import surname
        big = sorted([(t_, p, o) for t_, p, o in signed if p.ovr >= 85 or o.apy >= 15.0], key=lambda x: -x[2].apy)
        if big:
            rows = [[inbox_player(p), p.pos, str(round(p.ovr)), t_, str(o.years), f'${o.apy:.1f}m'] for t_, p, o in big[:10]]
            IB.post(L, 'league', f"Free agency, round {k}: the big signings", f"{len(signed)} players signed in the round; {len(waiting)} remain on the market.", sender='league', payload=dict(link='personnel:free_agency', mail_sections=[IB.mail_section('Notable signings', rows, ['Player', 'Position', 'OVR', 'Team', 'Years', 'Annual salary'])]))
        else:
            IB.post(L, 'league', f"Free agency, round {k}", f"{len(signed)} players signed in the round; {len(waiting)} remain on the market.", sender='league', payload=dict(link='personnel:free_agency'))

    def step_fa_1(self): self._fa_round(1)
    def step_fa_2(self): self._fa_round(2)
    def step_fa_3(self): self._fa_round(3)

    def step_fa_close(self):
        L, rng = self.L, self.rng
        signed = MK.close_market(L, rng, user_team=self.user_team)
        n_left = len([x for x in L.free_agents if L.player(x)])
        rows = [[inbox_player(p), p.pos, str(round(p.ovr)), t_, f'${o.apy:.1f}m'] for t_, p, o in sorted(signed, key=lambda x: -x[1].ovr)[:8]]
        IB.post(L, 'league', "The market closes", f"{len(signed)} veterans signed one-year deals as the market closed; {n_left} players remain unsigned into camp.", sender='league', payload=dict(link='personnel:free_agency', mail_sections=[IB.mail_section('Notable signings', rows, ['Player', 'Position', 'OVR', 'Team', 'Annual salary'])] if rows else []))

    def _resign_card(self):
        """The calendar sits on Re-sign: one card with your expiring players by class, the tag price on each UFA, tender
        or not on each RFA, the ERFAs kept at the minimum. Decide on the Extensions page; the advance locks it."""
        L = self.L; key_ = f"resign-{L.year}"
        if IE.seen(L, key_): return
        sheet = TG.user_resign_sheet(L)
        from views import surname
        sections = []
        for kind, title, price in [('ufa', 'Unrestricted free agents', 'tag_price'), ('rfa', 'Restricted free agents', 'tender_price'), ('erfa', 'Exclusive rights: kept at the minimum', None)]:
            rows = [[inbox_player(L.player(r['pid']), r['name']), r['pos'], str(r.get('ovr', '—'))] + ([f"${r[price]}m"] if price else []) for r in sheet[kind]]
            if rows: sections.append(IB.mail_section(title, rows, ['Player', 'Position', 'OVR'] + (['Tag price' if kind == 'ufa' else 'Tender price'] if price else [])))
        sections.append(IB.mail_section('Before advancing', [
            'One franchise tag, or none. Untagged unrestricted players without new deals enter the market.',
            'Tender restricted players in Retain Players to keep matching rights. Untendered players enter the market unrestricted.']))
        IE.post(L, key_, 'contract', "Re-sign: your tag and tenders", f"You can commit about ${sheet['room']}m after the minimums you still owe.", sender='front office', payload=dict(key=key_, link='personnel:retain', mail_sections=sections))

    def _open_fa_if_due(self):
        """The calendar sits on a free-agency round: open it (once) so the offers can be made before the advance."""
        if self.stop[0] != 'offseason': return
        self._skip_empty_offseason_waivers()
        PA.sync_session(self)
        name = self.OFFSEASON[self.stop[1]][1]
        if name == 'step_cutdown':
            for t in self.L.teams.values(): t.phase = 'season'
            return
        if name == 'step_waivers_1':
            WV.notify_user(self.L, WV.pending(self.L), 0, digest=True)
            return
        if name == 'step_extensions':
            try: self._resign_card()
            except Exception as e:
                import sys; print('resign card failed:', e, file=sys.stderr)
            return
        k = self.FA_STEPS.get(name)
        if k is None: return
        L = self.L
        if getattr(L, 'fa_bids_phase', None) == k: return
        bids = MK.open_round(L, self.rng, k, user_team=self.user_team)
        n = len([x for x in L.free_agents if L.player(x)])
        contested = sum(1 for pid, offers in bids.items() if len(offers) >= 2)
        IE.post(L, f'fa-open-{L.year}-{k}', 'contract', f"Free agency, round {k}, is open", f"{n} players on the market; {len(bids)} have offers from other clubs, {contested} from more than one. Open talks on the Free Agency page to see who else is in on a player, and make your offers before you advance. Nobody signs until the round closes.", sender='front office', payload=dict(link='personnel:free_agency'))

    def _skip_empty_offseason_waivers(self):
        """Keep saved calendar indices stable, but omit an empty claim window."""
        if (self.stop[0] == 'offseason'
                and self.OFFSEASON[self.stop[1]][1] == 'step_waivers_1'
                and not WV.pending(self.L)):
            self.stop = ('offseason', self.stop[1] + 1)
            return True
        return False

    def step_market(self):
        # kept for tools that call the one-shot market
        L, rng = self.L, self.rng
        L.set_phase('free_agency')
        MK.run(L, rng, user_team=self.user_team)

    def step_trades(self):
        TRD.run(self.L, self.rng, rounds=2, exclude=(self.user_team,) if self.user_team else ())

    def step_spring(self):
        L, rng = self.L, self.rng
        if SP.completed(L): return
        if getattr(L, 'next_class', None):
            L.draft_pool = L.next_class; L.next_class = []
        else:
            DC.build(L, rng, draft_year=L.year); SC.scout(L, rng)
        SP.run_spring(L, rng)

    def step_draft(self):
        """The draft with you at the buttons. Sims to your first pick and stops; Draft Day
        takes it from there, and an Advance from the Portal finishes it on auto."""
        import draft_day as DD
        # Older saves can still sit on Draft after its final UI pick. Do not
        # reopen an empty draft and overwrite its results/scouting snapshot.
        last = getattr(self.L, 'last_draft', None) or {}
        year = self.L.year - 1
        if (last.get('year') == year and not any(
                pk.year == year and pk.selection and not pk.used_on
                for t in self.L.teams.values() for pk in t.picks)):
            return
        self.draft = DD.Draft(self.L, self.rng, self.L.year - 1, user_team=self.user_team, auto_pick=False)
        # nothing is picked until you say so: the draft opens on pick one and the tools at the top move it
        if self.draft.done:
            self._draft_over()

    def _draft_over(self):
        D = self.draft
        if D is None: return
        if not D.done: D._finish()
        user_views = (getattr(self.L, 'scouting', None) or {}).get(self.user_team, {})
        consensus = getattr(self.L, 'consensus', None) or {}
        snapshot = {p.pid: dict(cons_rank=(consensus.get(p.pid) or {}).get('rank'),
                                cons_ovr=(consensus.get(p.pid) or {}).get('ovr'),
                                user_ovr=(user_views.get(p.pid) or {}).get('ovr'))
                    for _, _, p in D.results}
        self.L.last_draft = dict(year=D.year, results=[(s, t, p.pid) for s, t, p in D.results],
                                 trades=len(D.trades), trade_log=[list(x) for x in D.trades], scouting=snapshot)
        # the draft cycle's user state ends with the draft: the thirty visits and their timing, and the board
        # (ranks and do-not-draft) all name players who are now on rosters; left in place they carried into the
        # next class as visits already 'spoken for' and board entries for drafted players
        self.L.user_visits = []; self.L.user_visit_week = {}; self.L.user_board = {}
        # THE GEMS AND THE BUSTS, SURFACED. The day after the draft the rookies are on rosters at their true grades,
        # and the league notices the ones it missed and the ones it overrated
        try:
            import inbox as IB
            for s_, t_, p in D.results:
                role = p.xp_spent.get('_tape_role')
                if not role: continue
                rnd = (s_ - 1) // 32 + 1
                if t_ != self.user_team and role == 'gem' and rnd >= 3:
                    IB.news(self.L, f"{t_} may have found one: {inbox_player(p)} at pick {s_}", f"{inbox_player(p)} ({p.pos}, {home_state(p)}) went {s_}th, in round {rnd}, and the first look at him in a pro building says the league had him badly wrong. He grades {round(p.ovr)}, a starter's number. {t_} got a round-{rnd} pick that plays like a top-forty one.")
                elif t_ != self.user_team and role == 'bust' and rnd <= 2:
                    IB.news(self.L, f"Questions at {t_} about {inbox_player(p)}, the {s_}th pick", f"{inbox_player(p)} ({p.pos}, {home_state(p)}) was taken {s_}th, in round {rnd}, and the first look at him in a pro building has the room wondering what it saw on tape. He grades {round(p.ovr)}. The league had him at {round(float((self.L.consensus.get(p.pid) or {}).get('ovr', 0) or 0))}; the tape was wrong.")
                if t_ == self.user_team:
                    if role == 'gem': IB.post(self.L, 'club', f"Your scouts on {inbox_player(p)}: better than anyone thought", f"The first sessions with {inbox_player(p)} ({p.pos}) say the whole league missed him. He grades {round(p.ovr)} today, not the {round(float((self.L.consensus.get(p.pid) or {}).get('ovr', 0) or 0))} the consensus carried. You have a starter on a round-{rnd} contract.", sender='assistants', payload=dict(link=f'player:{p.pid}'))
                    elif role == 'bust': IB.post(self.L, 'club', f"Your scouts on {inbox_player(p)}: the tape was wrong", f"The first sessions with {inbox_player(p)} ({p.pos}) are not what the tape promised. He grades {round(p.ovr)} today, not the {round(float((self.L.consensus.get(p.pid) or {}).get('ovr', 0) or 0))} the consensus carried. The whole league had him there; the room did not see it either.", sender='assistants', payload=dict(link=f'player:{p.pid}'))
        except Exception as e:
            import sys; print('gem/bust notes failed:', e, file=sys.stderr)
        self.draft = None
        if self.stop[0] == 'offseason' and self.OFFSEASON[self.stop[1]][1] == 'step_draft':
            self.stop = ('offseason', self.stop[1] + 1)
            PA.sync_session(self)

    def draft_live(self):
        return self.draft is not None and not self.draft.done

    def step_camp(self):
        L, rng = self.L, self.rng
        PSQ.udfa_camp(L, rng)
        MK.fill_out_rosters(L, [p for p in MK._pool(L) if p.team is None], rng)
        NG.build(L, rng, draft_year=L.year + 1); SC.scout(L, rng)

    def step_cutdown(self):
        L, rng = self.L, self.rng
        # The previous postseason's week must not leak into the new wire,
        # injury/claim dates or the first regular-season decision window.
        L.week = 0
        for t in L.teams.values():
            for p in list(PSQ.squad(t)): PSQ.release_from_squad(L, t.abbr, p.pid)
        PSQ.reset_season(L)
        # Budget all 53 contracts before the final wire. League.phase stays
        # offseason so these releases retain the game's post-June 1 split.
        for t in L.teams.values(): t.phase = 'season'
        CD.finalize(L, rng)
        # the cuts are on the wire; the GM reads it and claims before it clears (the next step)
        WV.notify_user(L, WV.pending(L), 0, digest=True)

    def step_clear_wire(self):
        """Cut-down waivers clear: claims awarded by priority, the squads fill, the undrafted pile is settled, the season opens."""
        L, rng = self.L, self.rng
        self._cpu_roster_block = None
        for t in L.teams.values(): t.phase = 'season'
        # Legacy saves may have cut down using only top-51 charges. Repair
        # their cap now, preserving a claim opportunity for any new cuts.
        before = {e['pid'] for e in WV.pending(L)}
        CD.finalize(L, rng)
        if any(e['pid'] not in before for e in WV.pending(L)):
            WV.notify_user(L, WV.pending(L), 0, digest=True)
            return False
        WV.process(L, rng, 0)
        before = {e['pid'] for e in WV.pending(L)}
        CD.finalize(L, rng)
        if any(e['pid'] not in before for e in WV.pending(L)):
            WV.notify_user(L, WV.pending(L), 0, digest=True)
            return False
        problems = CD.violations(L)
        if problems:
            self._cpu_roster_block = 'CPU roster repair needed before Week 1: ' + '; '.join(
                f"{p['team']} ({p['size']} players, ${p['cap']:.2f}m cap space"
                + (', missing ' + ', '.join(p['missing']) if p['missing'] else '') + ')'
                for p in problems)
            return False
        PSQ.fill_squads(L, rng)
        from franchise import clear_undrafted
        clear_undrafted(L, rng)
        L.set_phase('regular')

    # ------------------------------------------------------------ helpers
    def _ir_ready_notes(self, week):
        """The week a player on IR becomes eligible to come back (four weeks served, healthy, placed with a return),
        one note to the GM; once per stint. Without it the only way to know was to open the IR list and count."""
        t = self.L.teams[self.user_team]
        for p in list(getattr(t, 'ir', None) or []):
            if not p.xp_spent.get('_ir_return', False): continue
            if p.xp_spent.get('_ir_ready_note') == int(p.xp_spent.get('_ir_week', 0) or 0): continue
            served = int(week or 0) - int(p.xp_spent.get('_ir_week', 0) or 0)
            healthy = p.out_until is None or int(p.out_until) <= int(week or 0)
            if served < t.IR_MIN_WEEKS or not healthy: continue
            p.xp_spent['_ir_ready_note'] = int(p.xp_spent.get('_ir_week', 0) or 0)
            left = int(t.IR_RETURNS) - int(getattr(t, 'ir_returns_used', 0) or 0)
            room = 53 - len(t.active())
            body = (f"{inbox_player(p)} ({p.pos}, {round(p.ovr)} overall) has served his {t.IR_MIN_WEEKS} weeks on injured reserve and is healthy. "
                    f"He can be activated to the 53 from the roster page. The club has {left} IR return{'s' if left != 1 else ''} left this season"
                    + ("." if room > 0 else "; the 53 is full, so a spot has to open first."))
            IB.post(self.L, 'ir_ready', f"{inbox_player(p)} is ready to come off IR", body, sender='trainers', payload=dict(pid=p.pid))

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

    def club_salaries(self, abbr=None):
        import views_club as VC
        return VC.salaries(self, self.L, abbr or self.user_team)

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

    def club_depth(self, package='Base', abbr=None, front=None, offense=None):
        import views_club as VC
        v = VC.depth(self, self.L, abbr or self.user_team, package, front, offense)
        v['club_abbr'] = abbr or self.user_team; v['mine'] = (abbr or self.user_team) == self.user_team
        return v

    def development_notices(self):
        """Read pending ceiling milestones without changing players or simulation RNG."""
        import xp as XP
        from views import club
        team = self.L.teams.get(self.user_team)
        pending = []
        for p in (team.roster if team else []):
            if p.team != self.user_team or p.retired or not XP.at_ceiling(p): continue
            unlocks = int(p.xp_spent.get('_unlocks', 0))
            if p.xp_spent.get('_ceiling_notice_ack', -1) >= unlocks: continue
            pending.append(dict(pid=p.pid, name=p.name, unlocks=unlocks, can_unlock=(p.potential < 99)))
        return dict(players=pending, club=club(self.user_team) if pending else None)

    def dismiss_ceiling_notice(self, pid, unlocks):
        """Remember the acknowledged ceiling level in the existing saved XP ledger."""
        p = self.L.player(pid)
        if p is None or p.team != self.user_team:
            return dict(ok=False, why='This player is no longer on your team.')
        if int(unlocks) != int(p.xp_spent.get('_unlocks', 0)):
            return dict(ok=False, why='His ceiling has changed since this notification.')
        p.xp_spent['_ceiling_notice_ack'] = int(unlocks)
        return dict(ok=True)

    def club_act(self, name, **kw):
        """Roster and depth actions from the page; the page re-reads the view after."""
        import views_club as VC
        fn = getattr(VC, 'act_' + name, None)
        if fn is None: return dict(ok=False, why='unknown action')
        if name == 'elevate':
            kw['playoffs'] = self.stop[0] == 'playoffs'
            kw['week'] = (19 + int(self.stop[1]) if kw['playoffs'] else
                          self.stop[1] if self.stop[0] == 'week' else 1)
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
                        ident = x.get('id') if isinstance(x, dict) else x
                        if isinstance(x, dict) and x.get('kind') != 'pick': continue
                        pk = next((q for q in D.picks if f"{q.year}-{q.round}-{q.original}" == str(ident)), None)
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

    def rail_state(self):
        """A short state for file names and the like."""
        k = self.stop[0]; tail = '-'.join(str(x) for x in self.stop[1:])
        return dict(year=int(self.L.year), stop=(f"{k}{'-' + tail if tail else ''}"), build=None)

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
        return dict(ok=True, id=m['id'], buyer=club(buyer), me=club(self.user_team), they=they, you=you, gap=gap, read=read, status=m.get('status'), expires=m.get('expires_week'), open=(m.get('status') in ('unread', 'open')), counter=pl.get('counter'))

    def trade_offer_answer(self, msg_id, action):
        import inbox as IB
        if action == 'accept':
            try: IB.accept(self.L, int(msg_id), self.user_team); return dict(ok=True, line='Trade accepted.')
            except Exception as e: return dict(ok=False, why=str(e)[:120] or 'the offer could not be completed')
        if action == 'decline':
            m = next((m for m in self.L.inbox if m.get('id') == int(msg_id)), None)
            if not m or m.get('kind') != 'trade_offer' or m.get('status') not in ('unread', 'open'):
                return dict(ok=False, why='No open offer with that id.')
            IB.decline(self.L, int(msg_id)); return dict(ok=True, line='Offer declined.')
        if action == 'counter':
            try:
                draft = IB.counter(self.L, int(msg_id), self.user_team)
                return dict(ok=True, line='Counter opened. The original offer is closed.', counter=draft)
            except ValueError as e: return dict(ok=False, why=str(e))
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
        if r.get('ok'): self.save_dirty = True
        return r

    def exit_answer(self, pid, key):
        import views_frontoffice as VF
        r = VF.exit_answer(self, self.L, self.user_team, pid, key)
        if r.get('ok'): self.save_dirty = True
        return r

    def frontoffice_act(self, action, **kw):
        import views_frontoffice as VF
        identity_action = action in ('apply_identity', 'set_identity', 'apply_archetype')
        live = getattr(self.runner, 'live', None) if self.runner else None
        if identity_action and live and not live.get('done', False):
            return dict(ok=False, why='Change team identity after the current game finishes.')
        fn = getattr(VF, 'act_' + action, None)
        if fn is None: return dict(ok=False, why='unknown action')
        r = fn(self.L, self.user_team, **kw)
        if identity_action and isinstance(r, dict) and r.get('ok') and self.runner:
            self.runner.refresh(self.user_team)
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
        wk = VG._week(self, self.L)
        if wk is None or self._opponent(wk) is None: return dict(ok=False, why='no game to plan for')
        live = getattr(self.runner, 'live', None) if self.runner is not None else None
        if self.played or (live and not live.get('done', False)):
            return dict(ok=False, why='The game has started; use halftime adjustments.')
        if VG.status(self, self.L, self.user_team)['locked'] and name not in ('reopen', 'save_failed'):
            return dict(ok=False, why='Your game plan is saved. Re-open Game Plan to make changes.')
        r = fn(self, self.L, self.user_team, **kw)
        r = r if isinstance(r, dict) else dict(ok=bool(r))
        r['plan_state'] = VG.status(self, self.L, self.user_team)
        return r

    def plan_take_all(self):
        import views_gameplan as VG
        if VG.status(self, self.L, self.user_team)['locked']:
            return dict(ok=False, why='Your game plan is saved. Re-open Game Plan to make changes.')
        wk = VG._week(self, self.L)
        if wk is None: return dict(ok=False, why='no game this week')
        import gameplan_week as GW
        opp = self._opponent(wk)
        if opp is None: return dict(ok=False, why='bye week')
        rep = GW.opponent_report(self.L, self.user_team, opp[0], wk); n = 0
        for i in range(len(rep['suggestions'])):
            if rep['suggestions'][i]['text'] in VG._skipped(self.L, wk): continue
            r = self.plan_act('take', i=i)
            if not r.get('ok'): return r
            n += 1
        return dict(ok=True, n=n, line=f"Took {n} suggestion{'s' if n != 1 else ''}.",
                    plan_state=VG.status(self, self.L, self.user_team))

    def inbox_mark_all(self):
        import inbox as IB
        IB.reconcile(self.L)
        n = 0
        for m in getattr(self.L, 'inbox', []):
            if m.get('status') == 'unread': m['status'] = 'open'; n += 1
        return dict(ok=True, n=n)

    def inbox_read(self, mid):
        import inbox as IB
        IB.reconcile(self.L)
        for m in getattr(self.L, 'inbox', []):
            if m['id'] == int(mid) and m.get('status') == 'unread': m['status'] = 'open'
        return dict(ok=True)

    def inbox_later(self, mid):
        """Hide a reminder from Overview without resolving its inbox decision."""
        import inbox as IB
        IB.reconcile(self.L)
        msg = next((m for m in getattr(self.L, 'inbox', []) if m['id'] == int(mid)), None)
        if msg is None:
            return dict(ok=False, why='Message not found.')
        msg['overview_dismissed'] = True
        if msg.get('status') == 'unread':
            msg['status'] = 'open'
        return dict(ok=True)

    def inbox_delete(self, mid):
        import inbox as IB
        IB.reconcile(self.L)
        import views
        import inbox_events as IE
        IE.remember(self.L)
        msg = next((m for m in getattr(self.L, 'inbox', []) if m['id'] == int(mid)), None)
        if msg and IB.is_decision(msg):
            return dict(ok=False, why='Resolve this decision before deleting it.')
        box = getattr(self.L, 'inbox', [])
        self.L.inbox = [m for m in box if m['id'] != int(mid)]
        return dict(ok=True)

    def inbox_clear_read(self):
        import inbox as IB
        IB.reconcile(self.L)
        import views
        import inbox_events as IE
        IE.remember(self.L)
        box = getattr(self.L, 'inbox', [])
        keep = [m for m in box if m.get('status') == 'unread' or IB.is_decision(m)]
        n = len(box) - len(keep); self.L.inbox = keep
        return dict(ok=True, n=n)

    def inbox_message(self, mid):
        import inbox as IB
        IB.reconcile(self.L)
        import views
        m = next((m for m in getattr(self.L, 'inbox', []) if m['id'] == int(mid)), None)
        if m is None: return dict(error='no such message')
        pl = m.get('payload') or {}
        import roster_advisor as RA
        return dict(id=m['id'], mentions=m.get('mentions', {}), entities=m.get('entities') or IB.entity_references(self.L, m['subject']+'\n'+(m.get('body') or ''), pl), status=m.get('status'), subject=m['subject'], body=m.get('body') or '', body_rows=IB.body_rows(self.L, m), tag=views.INBOX_TAG.get(m.get('kind'), (m.get('kind') or '').title()), kind=m.get('kind'), from_=m.get('sender'), pid=pl.get('pid'), recap=pl.get('recap'), snap_counts=pl.get('snap_counts'),
                    mail_sections=pl.get('mail_sections'), mail_intro=pl.get('mail_intro'),
                    recommendations=RA.recommendations(self.L, m) if m.get('kind') == 'roster_report' else [],
                    **{'from': m.get('sender')}, when=IB.date_label(m), link=(pl.get('link') or (f"player:{pl['pid']}" if pl.get('pid') else None)), decide=IB.is_decision(m))

    def inbox_roster_dismiss(self, mid, pid):
        import roster_advisor as RA
        return RA.dismiss(self.L, mid, pid)

    def inbox_hurt_action(self, mid, play=True):
        IB.reconcile(self.L)
        m = next((m for m in self.L.inbox if m['id'] == int(mid)), None)
        if not m or m.get('kind') != 'injury_decision' or not IB.is_decision(m):
            return dict(ok=False, why='This injury decision is no longer open.')
        pid = (m.get('payload') or {}).get('pid')
        desk = getattr(self.runner, 'desks', {}).get(self.user_team) if self.runner else None
        if desk is None or pid not in desk.pending:
            m['status'] = 'done'
            return dict(ok=False, why='The trainers have already resolved this decision.')
        return self.club_act('hurt_decision', pid=pid, play=play)

    def inbox_offer_sheet(self, mid, action):
        IB.reconcile(self.L)
        result = MK.answer_offer_sheet(self.L, int(mid), action, rng=self.rng)
        IB.reconcile(self.L)
        return result

    def _practice_pending(self):
        import practice_integration as PI
        return PI.pending(self)

    def practice_view(self):
        import practice_integration as PI
        return PI.view(self)

    def practice_act(self, action, plan_json=None, enabled=None):
        import practice_integration as PI
        return PI.action(self, action, plan_json, enabled)

    def inbox_view(self):
        """Only the header and full inbox needed by the mailbox screen."""
        import views
        return dict(rail=views.rail(self, self.L, self.user_team),
                    inbox=views._inbox(self.L, limit=None))

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
        if self.L.phase not in ('regular', 'playoffs', 'preseason'): return None
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None: return None
        return dict(open=not lv['done'], at=lv['at'], halftime_open=lv['halftime_open'], adjustment_period=lv.get('adjustment_period'), score=lv['score'], home=lv['home'], away=lv['away'])

    def live_step(self, mode='play'):
        """Move the live game: 'play', 'drive', 'half', 'finish', or 'resume' from halftime. Returns Game Day."""
        if self.L.phase not in ('regular', 'playoffs', 'preseason'):
            return self.gameday_view()
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None: return self.gameday_view()
        was_done = lv['done']
        self.runner.live_step(mode)
        if lv['done'] and not was_done:
            self._capture_gameday(lv['week'])
        return self.gameday_view()

    def half_take(self, i, on=True):
        if self.L.phase not in ('regular', 'playoffs', 'preseason'):
            return dict(ok=False, why='No game is being played.')
        ok = self.runner.half_take(int(i), bool(on)) if self.runner is not None else False
        return self.gameday_view() if ok else dict(ok=False, why='no break recommendation to take')

    def _finish_live(self):
        """A save or an advance with a game still open plays it out first."""
        if self.L.phase not in ('regular', 'playoffs', 'preseason'): return False
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if lv is None or lv['done']: return False
        while not lv['done']:
            self.runner.live_step('resume' if lv['halftime_open'] else 'finish')
        self._capture_gameday(lv['week'])
        return True

    def gameday_view(self, week=None, year=None):
        import views
        if week is None and self.L.phase not in ('regular', 'playoffs', 'preseason'):
            return views.gameday(self, self.L, self.user_team)
        lv = getattr(self.runner, 'live', None) if self.runner is not None else None
        if week is None and lv is not None and not lv['done']:
            import gameday as GD
            partial = self.runner.live_partial()
            others = [(h, a, r, b) for (h, a, r, b) in getattr(self.runner, 'last_games', [])]
            gd = GD.capture(self.L, others + [(lv['home'], lv['away'], partial, lv['book'])], self.user_team)
            v = views.gameday(self, self.L, self.user_team, gd=gd)
            v['live'] = dict(open=True, at=lv['at'], halftime_open=lv['halftime_open'], adjustment_period=lv.get('adjustment_period'), score={'home': partial['home'], 'away': partial['away']}, recs=[dict(i=r['i'], side=r['side'], text=r['text'], why=r['why'], taken=r['taken']) for r in (lv.get('ot_recs' if lv.get('adjustment_period') == 'overtime' else 'half_recs') or [])])
            v['live']['playoffs'] = bool(lv.get('playoffs'))
            v['live']['possession'] = (lv[lv['pos']] if lv['at'] in ('kick', 'snap')
                                      and not lv['halftime_open']
                                      and getattr(lv.get('current'), 'result', None) is None else None)
            return v
        if week is not None:
            gd = (getattr(self, 'gamedays', None) or {}).get(f"{year or self.L.year}-{int(week)}")
            if gd is not None: return views.gameday(self, self.L, self.user_team, gd=gd)
        return views.gameday(self, self.L, self.user_team)
