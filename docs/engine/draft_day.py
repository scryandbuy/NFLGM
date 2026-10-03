"""
DRAFT DAY, one pick at a time.

The draft is a state the interface steps through: sim_pick, sim_to_user,
sim_round, sim_all, make_pick. Nothing happens until a button is pressed.
When an AI club is on the clock it first decides whether to move, then picks
off its own board (draft.board). When the user's club is on the clock the
draft stops and waits, unless auto-pick is on, in which case the user's
saved board takes priority, followed by the roster-aware draft board.

TRADES ON THE CLOCK, rarely. Real drafts see 15 to 25 pick trades out of
257, most in the first three rounds. A club picking a little later whose
top target will not be there by its own slot may come up for the pick,
paying the market rate plus the premium the research says everyone still
pays (Massey-Thaler's curve has not moved since 2013). The club on the clock
sells when its own board is flat there. A probability gate per round keeps
the count where it belongs, and no two clubs deal twice in one draft.

During the draft the AI never approaches the user; the user GATHERS offers
for a pick (gather_offers) and every club answers off its own board and
personality, or the user goes to the trade tab with any pick pre-loaded
(trade_for_pick). Outside the draft, clubs may come to the user unprompted;
that lives in the trade window, not here.
"""
from functools import wraps
import draft as DFT
import trade_engine as TE

import json, os
_MARKET = {int(k): v for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                            'pick_values.json')))['market'].items()}
TRADE_GATE = {1: 0.40, 2: 0.30, 3: 0.22, 4: 0.08, 5: 0.05, 6: 0.04, 7: 0.04}
LOOKAHEAD = 12                 # how many slots down a buyer can come from
PREMIUM_UP = 1.06              # buyers overpay to move up; the market curve already carries most of it


def _decision_batch(method):
    """Reuse evidence only during one synchronous draft command, never across UI turns."""
    @wraps(method)
    def run(self, *args, **kwargs):
        if getattr(self, '_board_cache', None) is not None:
            return method(self, *args, **kwargs)
        self._board_cache, self._draft_grade_cache = {}, {}
        try:
            return method(self, *args, **kwargs)
        finally:
            self._board_cache = self._draft_grade_cache = None
    return run


class Draft:
    def __init__(self, league, rng, year, user_team=None, auto_pick=False, level=None, scale=None):
        self.L, self.rng, self.year = league, rng, year
        self.user, self.auto = user_team, auto_pick
        self.picks = sorted((pk for t in league.teams.values() for pk in t.picks
                             if pk.year == year and pk.selection and not pk.used_on),
                            key=lambda pk: pk.selection)
        self.i = 0
        self.taken = set()
        self.level = dict(level) if level is not None else DFT.league_starter_level(league)
        self.scale = {pos: tuple(values) for pos, values in scale.items()} if scale is not None else DFT.position_scale(league)
        self.results = []
        self.trades = []
        self.dealt = set()          # frozenset({a, b}) pairs that have traded this draft
        self.last_dealt = None
        self.trade_targets = {}  # selection -> buyer/player: bind the pick to the negotiated target
        if not getattr(league, 'scouting', None):
            import scouting as SC
            SC.scout(league, rng)

    # ------------------------------------------------------------ state
    @property
    def done(self):
        return self.i >= len(self.picks)

    def current(self):
        return None if self.done else self.picks[self.i]

    def on_user(self):
        pk = self.current()
        return pk is not None and pk.owner == self.user

    def available(self):
        return [p for p in self.L.draft_pool if p.pid not in self.taken]

    def board_for(self, abbr, gm=None):
        pk = self.current()
        sel = pk.selection if pk else 1
        cache = getattr(self, '_board_cache', None)
        key = (abbr, sel, id(gm))
        if cache is not None and key in cache:
            return list(cache[key])
        rows = DFT.board(self.L, abbr, sel, self.level, self.taken, self.scale, gm=gm,
                         _grade_cache=getattr(self, '_draft_grade_cache', None))
        if cache is not None: cache[key] = tuple(rows)
        return rows

    def user_pick(self):
        """Honor explicit board priorities, then draft for roster needs like the CPU."""
        ub = getattr(self.L, 'user_board', None) or {}
        dnd = set(ub.get('dnd') or [])
        available = {p.pid: p for p in self.available() if p.pid not in dnd}
        for pid in ub.get('order') or []:
            if pid in available:
                return available[pid]
        if not available:
            return None
        return next((p for _, p in self.board_for(self.user) if p.pid in available), None)

    # ------------------------------------------------------------ the buttons
    @_decision_batch
    def sim_pick(self):
        """One selection. Returns ('user',) when it is the user's turn and
        auto-pick is off, else ('pick', selection, team, player) or
        ('trade', ...) followed by the pick."""
        if self.done:
            return ('done',)
        pk = self.current()
        if pk.owner == self.user and not self.auto:
            return ('user', pk)
        events = []
        if pk.owner != self.user:
            tr = self._maybe_trade(pk)
            if tr: events.append(tr)
        owner = pk.owner
        if owner == self.user:
            p = self.user_pick()
            if p is None: return ('user', pk)
        else:
            intent = self.trade_targets.get(pk.selection)
            p = self.L.players.get(intent['pid']) if intent and intent['buyer'] == owner else None
            if p is None or p.pid in self.taken or p not in self.L.draft_pool:
                rows = self.board_for(owner)
                p = rows[0][1]
        self._select(pk, p)
        events.append(('pick', pk.selection, owner, p))
        return events[0] if len(events) == 1 else ('trade_then_pick', *events)

    def make_pick(self, pid):
        """The user's selection."""
        pk = self.current()
        if pk is None or pk.owner != self.user:
            raise ValueError('not the user\'s pick')
        p = self.L.players[pid]
        if p.pid in self.taken or p not in self.L.draft_pool:
            raise ValueError('not available')
        self._select(pk, p)
        return ('pick', pk.selection, self.user, p)

    @_decision_batch
    def sim_to_user(self):
        out = []
        while not self.done:
            ev = self.sim_pick()
            if ev[0] == 'user': break
            out.append(ev)
        return out

    @_decision_batch
    def sim_round(self):
        pk = self.current()
        if pk is None: return []
        rnd = pk.round; out = []
        while not self.done and self.current().round == rnd:
            ev = self.sim_pick()
            if ev[0] == 'user': break
            out.append(ev)
        return out

    @_decision_batch
    def sim_all(self):
        out = []
        while not self.done:
            ev = self.sim_pick()
            if ev[0] == 'user': break
            out.append(ev)
        if self.done:
            self._finish()
        return out

    # ------------------------------------------------------------ trades
    # Everything here prices on the trade engine's ledger: picks at the
    # market chart in dollars, players at their two-sided trade value with
    # the seller's dead money (post-June 1, since the draft is in the
    # offseason) and the buyer's inherited cost. A pick on the clock is just
    # another asset, so a club can come up for it with a pick, a player, or
    # both, and the same cap block that kills a cap-killing deal in October
    # kills it here.
    def _pool(self):
        if not hasattr(self, '_val_pool'):
            import valuation as VAL
            self._val_pool = VAL.pool_from_league(self.L)
        return self._val_pool

    def _pick_asset(self, pk):
        import trades as TR
        asset = TR.pick_asset(self.L, pk)
        # Draft.year is the season whose picks are on the clock, even after
        # the league calendar has rolled into the following year.
        asset['years_out'] = max(0, pk.year - self.year)
        return asset

    def _bank(self, abbr, exclude_pick=None, rng=None):
        """What this club can put into a package: its remaining picks this
        year and the picks after, and its surplus players."""
        import trades as TR
        team = self.L.teams[abbr]
        picks = [self._pick_asset(x) for x in team.picks if not x.used_on and x is not exclude_pick
                 and self.year <= x.year <= self.year + 2
                 and (x.year > self.year or (x.selection or 0) > (self.current().selection if self.current() else 0))]
        surplus, _ = TR.surplus_and_needs(self.L, team, self._pool(), rng if rng is not None else self.rng)
        return picks + list(surplus)

    def _offer_for(self, buyer, seller, pk, premium, slack=1.0, rng=None, target_player=None):
        """
        Build the cheapest package from the buyer's bank that the SELLER's own
        pricing accepts for pk, at the buyer's premium over the pick's market
        price. Returns (offer, result) or (None, None).
        """
        import trades as TR
        L = self.L; ta, tb = L.teams[buyer], L.teams[seller]
        ga, gb = TR.persona(ta.gm), TR.persona(tb.gm)
        ctx_a, ctx_b = ta.ctx(), tb.ctx()
        target = self._pick_asset(pk)
        # This buyer has a player he expects to lose before its own pick.
        # The trade engine prices that concrete opportunity for the buyer;
        # the seller still prices the pick at its ordinary chart value.
        target['draft_target_premium'] = 1.20
        market = TE.market_price(target)
        want = market * premium
        market_floor, market_ceiling = .85 * market, 1.35 * market
        bank = sorted(self._bank(buyer, exclude_pick=None, rng=rng), key=lambda x: TE.team_price(x, ctx_a, ta.cap_space, ga, owns=True))
        best = None
        target_checks = {}
        football_cache, financial_cache = {}, {}
        # Search singles, pairs and triples lazily. Prices are additive, so
        # reject packages outside either club's window before evaluation.
        import itertools
        buyer_prices = {id(x): TE.team_price(x, ctx_a, ta.cap_space, ga, owns=True) for x in bank}
        seller_prices = {id(x): TE.team_price(x, ctx_b, tb.cap_space, gb, owns=False) for x in bank}
        buyer_limit = TE.team_price(target, ctx_a, ta.cap_space, ga, owns=False) - 0.5
        seller_floor = TE.team_price(target, ctx_b, tb.cap_space, gb, owns=True) + 0.5
        # draft-day deals are mostly THIS year's picks (about three in four
        # real ones); a future pick or a player is the sweetener, so they
        # carry a small handicap in the search, not in the price
        def handicap(pkg): return 1.0 + 0.12 * sum(1 for x in pkg if x['kind'] != 'pick' or x.get('years_out', 0) > 0)
        for pkg in itertools.chain(((x,) for x in bank), itertools.combinations(bank, 2),
                                    itertools.combinations(bank, 3)):
            neutral = sum(TE.market_price(x) for x in pkg)
            if not market_floor - 1e-9 <= neutral <= market_ceiling + 1e-9:
                continue
            # NEXT YEAR'S PICK BUYS THE SAME ROUND OR BETTER, this year. A
            # future first goes for a first, a future second for a first or
            # a second. Price alone let a club with nothing left this year
            # send a 2028 first for pick 54, which no room does.
            if any(x['kind'] == 'pick' and x.get('years_out', 0) > 0 and pk.round > x['obj'].round
                   for x in pkg):
                continue
            t = sum(seller_prices[id(x)] for x in pkg)
            if t < max(want * slack, seller_floor): continue
            paid = sum(buyer_prices[id(x)] for x in pkg)
            if paid >= buyer_limit: continue
            paid *= handicap(pkg)
            if best is not None and paid >= best[0]: continue
            offer = dict(a_sends=list(pkg), a_gets=[target])
            r = TE.evaluate(offer, ctx_a, ctx_b, ta.cap_space, tb.cap_space, ga, gb)
            if not r.get('accepted'): continue
            if target_player is not None:
                collateral = tuple(sorted(x['pid'] for x in pkg if x['kind'] == 'player'))
                if collateral not in target_checks:
                    target_checks[collateral] = self._trade_target_valid(buyer, offer, pk, target_player)
                if not target_checks[collateral]: continue
            if not self._package_valid(buyer, seller, offer, pk, target_player,
                                       football_cache, financial_cache):
                continue
            if best is None or paid < best[0]:
                best = (paid, offer, r)
        if best is None:
            return None, None
        return best[1], best[2]

    def _package_valid(self, buyer, seller, offer, pk, target_player=None,
                       football_cache=None, financial_cache=None):
        """Shared roster and funding guards, including the rookie bought here."""
        import trades as TR
        import roster_needs as RN
        ta, tb = self.L.teams[buyer], self.L.teams[seller]
        sent = [x['obj'] if x['kind'] == 'pick' else x['pid'] for x in offer['a_sends']]
        neutral = sum(TE.market_price(x) for x in offer['a_sends'])
        market = TE.market_price(self._pick_asset(pk))
        if not .85 * market - 1e-9 <= neutral <= 1.35 * market + 1e-9:
            return False
        if any(isinstance(x, str) for x in sent):
            import draft_plan as DP
            # The buyer prices the rookie it has scouted, not the hidden
            # player object it will receive after making the pick.
            observed = DP.observed_prospect(self.L, buyer, target_player) if target_player is not None else None
            football = TR.package_football(self.L, ta, tb, sent, [pk],
                                           prospect=observed, cache=football_cache)
            if not football['approved']: return False
            seller_reserve = football.get('reserves', {}).get(seller, 0.)
            if seller_reserve:
                result = TE.evaluate(offer, ta.ctx(), tb.ctx(), ta.cap_space, tb.cap_space,
                                     TR.persona(ta.gm), TR.persona(tb.gm))
                if result.get('blocked') or result['b_gain'] + 1e-9 < seller_reserve:
                    return False
            if buyer != getattr(self.L, 'user_team', None):
                # CPU player collateral requires a concrete prospect and an
                # improvement after giving up every player in the package.
                if target_player is None: return False
                net = football['gains'][buyer]
                gross = RN.move_gain(ta, observed)
                ceiling = 1.35 * market * min(1., TR._upgrade_budget(net) / TR._upgrade_budget(gross))
                if net <= .5 or neutral > ceiling + 1e-9: return False
        # Financial planning includes the acquired pick's actual rookie deal,
        # plus every future pick and contract on both sides of the exchange.
        return TR._financial_trade(self.L, ta, tb, sent, [pk], financial_cache)

    def _trade_target_valid(self, buyer, offer, pk, target_player):
        """The target must remain the buyer's first choice after paying the roster collateral."""
        if target_player.pid in self.taken or target_player not in self.L.draft_pool:
            return False
        import draft_plan
        roster = draft_plan.projected_players(self.L.teams[buyer])
        outgoing = {x['pid'] for x in offer['a_sends'] if x['kind'] == 'player'}
        if not outgoing.issubset({p.pid for p in roster}):
            return False
        projected = [p for p in roster if p.pid not in outgoing]
        rows = DFT.board(self.L, buyer, pk.selection, self.level, self.taken,
                         self.scale, players=projected,
                         _grade_cache=getattr(self, '_draft_grade_cache', None))
        return bool(rows and rows[0][1].pid == target_player.pid)

    def _execute(self, buyer, seller, offer, pk, target_player=None):
        if pk is not self.current() or pk.used_on or pk.owner != seller:
            return None
        if target_player is not None and not self._trade_target_valid(buyer, offer, pk, target_player):
            return None
        if not self._package_valid(buyer, seller, offer, pk, target_player):
            return None
        sends = [x['obj'] if x['kind'] == 'pick' else x['pid'] for x in offer['a_sends']]
        try: self.L.trade(buyer, seller, sends, [pk])
        except ValueError: return None
        if getattr(self, '_board_cache', None) is not None: self._board_cache.clear()
        if target_player is not None:
            self.trade_targets[pk.selection] = dict(buyer=buyer, pid=target_player.pid)
        self.dealt.add(frozenset((seller, buyer))); self.last_dealt = buyer
        desc = [self._label(x) for x in offer['a_sends']]
        self.trades.append((pk.selection, buyer, seller, desc))
        self.L.log('draft_trade', selection=pk.selection, buyer=buyer, seller=seller, sent=desc,
                   target=target_player.pid if target_player else None)
        return ('trade', pk.selection, buyer, seller, desc)

    def _label(self, x):
        if x['kind'] == 'pick':
            pk = x['obj']
            return f"pick {pk.selection}" if pk.selection and pk.year == self.year else f"{pk.year + 1} R{pk.round}"
        p = self.L.players[x['pid']]
        return f"{p.name} ({p.pos} {x.get('seen_ovr', p.ovr):.0f})"

    def _target_slot(self, abbr):
        """Where this club's top available man is expected to go by the room."""
        rows = self.board_for(abbr)
        if not rows: return None, None
        p = rows[0][1]
        return p, self.L.consensus[p.pid].get('slot', 999)

    def _maybe_trade(self, pk):
        """A club below comes up for this pick, if the gate opens and it wants to."""
        rng = self.rng
        if rng.random() > TRADE_GATE.get(pk.round, 0.02):
            return None
        seller = pk.owner
        if seller == self.last_dealt:
            return None
        later = [q for q in self.picks[self.i + 1:self.i + 1 + LOOKAHEAD] if q.owner not in (seller, self.user)]
        best = None
        for q in later:
            buyer = q.owner
            if frozenset((seller, buyer)) in self.dealt: continue
            gm = self.L.teams[buyer].gm
            aggr = float(getattr(gm, 'aggression', 0.5)) if gm else 0.5
            p, slot = self._target_slot(buyer)
            if p is None or slot is None or slot > q.selection - 2: continue
            if rng.random() > 0.35 + 0.6 * aggr: continue
            offer, r = self._offer_for(buyer, seller, pk, PREMIUM_UP + 0.08 * aggr, target_player=p)
            if offer is None or not r.get('accepted'): continue
            over = r['b_gain']
            if best is None or over > best[0]:
                best = (over, buyer, offer, p)
        if best is None:
            return None
        over, buyer, offer, target = best
        # the seller takes it when its board is flat here, the gain is real,
        # or it is patient enough to bank the assets
        rows = self.board_for(seller)
        flat = len(rows) >= 4 and (rows[0][0] - rows[3][0]) < 0.12 * rows[0][0]
        patience = float(getattr(self.L.teams[seller].gm, 'patience', 0.5)) if self.L.teams[seller].gm else 0.5
        if not (flat or over > 1.0 or rng.random() < 0.3 * patience):
            return None
        return self._execute(buyer, seller, offer, pk, target)

    @_decision_batch
    def gather_offers(self, pk):
        """
        Every AI club's answer for one of the user's picks: the package it
        would send to move up to it, picks and players, off its own board,
        bank and personality. Ranked by what the offer is worth to the user.
        """
        import trades as TR
        import copy
        preview_rng = copy.deepcopy(self.rng)
        offers = []
        tu = self.L.teams[self.user]; gu = TE.GM_ARCHETYPES['balanced']; ctx_u = tu.ctx()
        later = [q for q in self.picks[self.i:] if q.selection > pk.selection and q.owner not in (self.user, None)]
        seen = set()
        for q in later:
            buyer = q.owner
            if buyer in seen: continue
            seen.add(buyer)
            gm = self.L.teams[buyer].gm
            aggr = float(getattr(gm, 'aggression', 0.5)) if gm else 0.5
            p, slot = self._target_slot(buyer)
            if p is None or slot is None or slot > q.selection - 2: continue
            if q.selection - pk.selection > LOOKAHEAD * (1 + 2 * aggr): continue
            offer, r = self._offer_for(buyer, self.user, pk, 1.04 + 0.10 * aggr, slack=0.97, rng=preview_rng, target_player=p)
            if offer is None or not r.get('accepted'): continue
            worth = sum(TE.team_price(x, ctx_u, tu.cap_space, gu, owns=False) for x in offer['a_sends'])
            offers.append(dict(team=buyer, sends=offer['a_sends'], asks=[pk], value=round(worth, 1),
                               target_pos=p.pos, target_pid=p.pid, gm=getattr(gm, 'name', 'gm'),
                               summary=[self._label(x) for x in offer['a_sends']]))
        offers.sort(key=lambda o: -o['value'])
        return offers

    @_decision_batch
    def accept_offer(self, offer):
        pk = offer['asks'][0]
        if pk is not self.current() or pk.used_on:
            return None
        import trades as TR
        buyer, seller = self.L.teams[offer['team']], self.L.teams[self.user]
        target = self._pick_asset(pk)
        target['draft_target_premium'] = 1.20
        package = dict(a_sends=offer['sends'], a_gets=[target])
        target_player = self.L.players.get(offer.get('target_pid'))
        if target_player is None:
            return None
        r = TE.evaluate(package, buyer.ctx(), seller.ctx(), buyer.cap_space, seller.cap_space,
                        TR.persona(buyer.gm), TR.persona(seller.gm))
        if not r.get('accepted'):
            return None
        ev = self._execute(offer['team'], self.user, package, pk, target_player)
        return ev

    def trade_for_pick(self, pk):
        """What the trade tab pre-loads: the pick as the target and its owner's
        asking price in dollars."""
        return dict(target=pk, owner=pk.owner, market=round(TE.market_price(self._pick_asset(pk)), 1))

    # ------------------------------------------------------------ internals
    def _select(self, pk, p):
        if getattr(self, '_board_cache', None) is not None: self._board_cache.clear()
        from valuation import _league_cap
        cap = _league_cap(self.L, self.year + 1)
        self.taken.add(p.pid)
        pk.used_on = p.pid
        p.draft_round, p.draft_overall = pk.round, pk.selection
        self.L.sign(p.pid, pk.owner, DFT.rookie_contract(pk.selection, cap, signed=self.L.year))
        self.L.log('draft', pid=p.pid, team=pk.owner, round=pk.round, selection=pk.selection,
                   pos=p.pos, consensus_rank=self.L.consensus[p.pid]['rank'], ovr_then=round(float(p.ovr), 1))
        self.results.append((pk.selection, pk.owner, p))
        self.trade_targets.pop(pk.selection, None)
        self.i += 1
        if self.done:
            self._finish()

    def _finish(self):
        for p in self.L.draft_pool:
            if p.pid not in self.taken:
                p.draft_round, p.draft_overall = None, None
                if p.pid not in self.L.free_agents:
                    self.L.free_agents.append(p.pid)
        self.L.draft_pool = []
