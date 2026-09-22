"""
DRAFT DAY, one pick at a time.

The draft is a state the interface steps through: sim_pick, sim_to_user,
sim_round, sim_all, make_pick. Nothing happens until a button is pressed.
When an AI club is on the clock it first decides whether to move, then picks
off its own board (draft.board). When the user's club is on the clock the
draft stops and waits, unless auto-pick is on, in which case the AI picks
for the user off the CONSENSUS board and the club's needs.

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
import numpy as np, collections
import draft as DFT
import trade_engine as TE

import json, os
_MARKET = {int(k): v for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                            'pick_values.json')))['market'].items()}
TRADE_GATE = {1: 0.40, 2: 0.30, 3: 0.22, 4: 0.08, 5: 0.05, 6: 0.04, 7: 0.04}
LOOKAHEAD = 12                 # how many slots down a buyer can come from
PREMIUM_UP = 1.08              # buyers overpay to move up; the market curve already carries most of it


class _ConsensusGM:
    """What the AI drafts with for the user: the room's board and the club's
    needs, no private read, no personality."""
    board_trust = 0.0; dev_belief = 0.5; need_inflation = 0.5; job_security = 0.7


class Draft:
    def __init__(self, league, rng, year, user_team=None, auto_pick=False):
        self.L, self.rng, self.year = league, rng, year
        self.user, self.auto = user_team, auto_pick
        self.picks = sorted((pk for t in league.teams.values() for pk in t.picks
                             if pk.year == year and pk.selection and not pk.used_on),
                            key=lambda pk: pk.selection)
        self.i = 0
        self.taken = set()
        self.level = DFT.league_starter_level(league)
        self.scale = DFT.position_scale(league)
        self.results = []
        self.trades = []
        self.dealt = set()          # frozenset({a, b}) pairs that have traded this draft
        self.last_dealt = None
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
        return DFT.board(self.L, abbr, sel, self.level, self.taken, self.scale, gm=gm)

    # ------------------------------------------------------------ the buttons
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
            rows = self.board_for(owner, gm=_ConsensusGM())
        else:
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

    def sim_to_user(self):
        out = []
        while not self.done:
            ev = self.sim_pick()
            if ev[0] == 'user': break
            out.append(ev)
        return out

    def sim_round(self):
        pk = self.current()
        if pk is None: return []
        rnd = pk.round; out = []
        while not self.done and self.current().round == rnd:
            ev = self.sim_pick()
            if ev[0] == 'user': break
            out.append(ev)
        return out

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
    def _value(self, pk):
        """The market chart at the slot, 1000 for pick 1, the scale clubs deal in."""
        return _MARKET.get(int(pk.selection), 1.9)

    def _sweeten(self, extras, gap, slack=1.0):
        """The one or two later picks that close the gap with the least
        overshoot; None if his drawer cannot. A single pick 60 to cover a
        40-point gap was a 36% overpay; 88 and 96 together is a fair one."""
        if gap <= 0: return []
        v = [self._value(x) for x in extras]
        best = None
        for i, x in enumerate(extras):
            if v[i] >= gap * slack and (best is None or v[i] < best[0]): best = (v[i], [x])
        for i, x in enumerate(extras):
            for j in range(i + 1, len(extras)):
                s = v[i] + v[j]
                if s >= gap * slack and (best is None or s < best[0]): best = (s, [x, extras[j]])
        return best[1] if best else None

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
            if p is None: continue
            # he comes up only if his man will be gone before his own turn
            if slot is None or slot > q.selection - 2: continue
            if rng.random() > 0.35 + 0.6 * aggr: continue
            need = self._value(pk) * PREMIUM_UP
            package = [q]; have = self._value(q)
            # sweeten with his later picks this year, latest round first
            extras = sorted((x for x in self.L.teams[buyer].picks if x.year == self.year and x.selection
                             and not x.used_on and x is not q and x.selection > pk.selection),
                            key=lambda x: -x.selection)
            add = self._sweeten(extras, need - have)
            if add is None: continue
            package += add; have += sum(self._value(x) for x in add)
            over = have / need
            if best is None or over < best[0]:
                best = (over, buyer, package, p)
        if best is None:
            return None
        over, buyer, package, target = best
        # the seller takes it when its own board is flat here or the offer is rich
        rows = self.board_for(seller)
        flat = len(rows) >= 4 and (rows[0][0] - rows[3][0]) < 0.12 * rows[0][0]
        patience = float(getattr(self.L.teams[seller].gm, 'patience', 0.5)) if self.L.teams[seller].gm else 0.5
        if not (flat or over >= 1.12 or rng.random() < 0.3 * patience):
            return None
        self.L.trade(buyer, seller, package, [pk])
        self.dealt.add(frozenset((seller, buyer))); self.last_dealt = buyer
        self.trades.append((pk.selection, buyer, seller, [x.selection for x in package]))
        self.L.log('draft_trade', selection=pk.selection, buyer=buyer, seller=seller,
                   sent=[x.selection for x in package], target=target.pid)
        return ('trade', pk.selection, buyer, seller, [x.selection for x in package])

    def gather_offers(self, pk):
        """
        Every AI club's answer for one of the user's picks: what it would send
        to move up to it, off its own board and personality. Ranked by market
        value. [] when nobody wants it.
        """
        offers = []
        later = [q for q in self.picks[self.i:] if q.selection > pk.selection and q.owner not in (self.user, None)]
        seen = set()
        for q in later:
            buyer = q.owner
            if buyer in seen: continue
            seen.add(buyer)
            gm = self.L.teams[buyer].gm
            aggr = float(getattr(gm, 'aggression', 0.5)) if gm else 0.5
            lens = float(getattr(gm, 'pick_lens', 0.5)) if gm else 0.5
            p, slot = self._target_slot(buyer)
            if p is None or slot is None or slot > q.selection - 2: continue
            if q.selection - pk.selection > LOOKAHEAD * (1 + 2 * aggr): continue
            need = self._value(pk) * (1.0 + 0.04 + 0.10 * aggr)
            package = [q]; have = self._value(q)
            extras = sorted((x for x in self.L.teams[buyer].picks if x.year == self.year and x.selection
                             and not x.used_on and x is not q and x.selection > pk.selection),
                            key=lambda x: -x.selection)
            add = self._sweeten(extras, need - have, slack=0.97)
            if add is None: continue
            package += add; have += sum(self._value(x) for x in add)
            offers.append(dict(team=buyer, sends=package, value=round(have, 1), asks=[pk],
                               target_pos=p.pos, gm=getattr(gm, 'name', 'gm')))
        offers.sort(key=lambda o: -o['value'])
        return offers

    def accept_offer(self, offer):
        pk = offer['asks'][0]
        self.L.trade(offer['team'], self.user, offer['sends'], [pk])
        self.dealt.add(frozenset((self.user, offer['team'])))
        self.trades.append((pk.selection, offer['team'], self.user, [x.selection for x in offer['sends']]))
        self.L.log('draft_trade', selection=pk.selection, buyer=offer['team'], seller=self.user,
                   sent=[x.selection for x in offer['sends']], target=None)
        return True

    def trade_for_pick(self, pk):
        """What the trade tab pre-loads: the pick as the target and its owner's
        asking price on the market chart."""
        return dict(target=pk, owner=pk.owner, market=round(self._value(pk), 1))

    # ------------------------------------------------------------ internals
    def _select(self, pk, p):
        from cap_engine import CAP
        cap = CAP.get(self.year + 1, 301.2)
        self.taken.add(p.pid)
        pk.used_on = p.pid
        p.draft_round, p.draft_overall = pk.round, pk.selection
        p.potential = None
        self.L.sign(p.pid, pk.owner, DFT.rookie_contract(pk.selection, cap))
        self.L.log('draft', pid=p.pid, team=pk.owner, round=pk.round, selection=pk.selection,
                   pos=p.pos, consensus_rank=self.L.consensus[p.pid]['rank'])
        self.results.append((pk.selection, pk.owner, p))
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
