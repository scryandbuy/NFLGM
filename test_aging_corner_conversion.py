import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import numpy as np
from league import League, Team, Player
from gm_engine import GM
from cap_engine import Contract
import targets as TG
import position_change as PC
import roster_needs as RN


class AgingCornerConversion(unittest.TestCase):
    def setup_roster(self):
        L = League(2031)
        L.phase = 'offseason'
        t = Team('DAL', 'NFC East', 'NFC', gm=GM(), scheme=None)
        L.teams = {'DAL': t}; L.user_team = 'GB'
        def add(pid, pos, age, rating):
            ratings = {k: rating for weights in TG.DEPTH_WEIGHTS.values() for k in weights}
            p = Player(pid, pid, pos, age, ratings, team='DAL', contract=Contract(2, [1., 1.]))
            L.players[pid] = p; t.roster.append(p)
            return p
        p = add('veteran', 'CB', 31, 82)
        p.contract = Contract(2, [12., 13.], signing_bonus=4.)
        p.ratings.update(speed_rating=78, man_cover_rating=70, zone_cover_rating=89,
                         play_rec_rating=90, awareness_rating=90, tackle_rating=84, pursuit_rating=86)
        for i in range(4): add('corner'+str(i), 'CB', 25, 80)
        add('free', 'FS', 30, 69); add('strong', 'SS', 30, 75)
        return L, t, p

    def test_corner_acquisition_unlocks_plan_but_does_not_move_player_yet(self):
        L, t, p = self.setup_roster()
        arrival = t.roster.pop(4)
        self.assertEqual(PC.aging_corner_options(L, t), [])
        before = RN.planning_assess(L, t)
        gain = RN.move_gain(t, arrival, baseline=before)
        plain = RN.move_gain(t, arrival)
        self.assertGreater(gain, plain + 5)
        after = RN.planning_assess(L, t, t.roster + [arrival])
        self.assertTrue(after['corner_moves'])
        self.assertEqual(p.pos, 'CB')
        self.assertEqual(PC.review_aging_corners(L), [])
        # Start a fresh review year, then acquire the actual replacement.
        p.xp_spent.pop('_cb_safety_review', None)
        t.roster.append(arrival)
        self.assertEqual(PC.review_aging_corners(L), [(p.pid, 'FS')])

    def test_safety_acquisition_can_cancel_conversion(self):
        L, t, p = self.setup_roster()
        before = RN.planning_assess(L, t)
        self.assertTrue(before['corner_moves'])
        safeties = []
        for n, pos in enumerate(('FS', 'SS')):
            q = copy.deepcopy(L.players['free']); q.pid = 'new'+str(n); q.pos = pos
            q.ratings = {k: 92 for k in q.ratings}; safeties.append(q)
        after = RN.planning_assess(L, t, t.roster + safeties)
        self.assertFalse(after['corner_moves'])
        self.assertEqual(p.pos, 'CB')
        t.roster.extend(safeties)
        self.assertEqual(PC.review_aging_corners(L), [])

    def test_trade_departures_are_included_and_picks_are_not_replacements(self):
        L, t, p = self.setup_roster()
        before = RN.planning_assess(L, t)
        self.assertTrue(before['corner_moves'])
        after = RN.planning_assess(L, t, [q for q in t.roster if q.pid != 'corner0'])
        self.assertFalse(after['corner_moves'])
        self.assertGreater(RN.departure_loss(t, L.players['corner0'], baseline=before), 5)

    def test_regular_season_and_user_planning_do_not_project_moves(self):
        L, t, p = self.setup_roster(); L.phase = 'regular'
        self.assertNotIn('_corner_context', RN.planning_assess(L, t))
        L.phase = 'offseason'; L.user_team = t.abbr
        self.assertNotIn('_corner_context', RN.planning_assess(L, t))

    def test_draft_uses_scouted_replacement_without_hidden_ceiling(self):
        import draft_plan as DP
        L, t, p = self.setup_roster()
        rookie = t.roster.pop(4); rookie.pid = 'rookie'; rookie.team = None
        rookie.age = 22; rookie.contract = None
        L.scouting = {'DAL': {rookie.pid: dict(ovr=80., e_phys=0., e_skill=0.)}}
        plan = DP.assess(L, 'DAL')
        gain = DP.prospect_gains(L, 'DAL', [rookie], plan, {rookie.pid: 80.})[rookie.pid]
        self.assertGreater(gain, 8.)
        rookie.potential = 99
        self.assertEqual(gain, DP.prospect_gains(L, 'DAL', [rookie], plan, {rookie.pid: 80.})[rookie.pid])
        self.assertEqual(p.pos, 'CB')

    def test_acquisition_financial_gate_still_binds(self):
        import market as MK
        L, t, p = self.setup_roster(); L.set_phase('free_agency')
        arrival = t.roster.pop(4); arrival.team = None; arrival.contract = None
        t.sync_cap(); t.cap.dead = t.cap.cap
        quote = dict(apy=5., years=2)
        import financial_plan as FP
        with patch.object(MK.VAL, 'value_player', return_value=quote), patch.object(FP, 'evaluate', wraps=FP.evaluate) as gate:
            bids = MK.ai_bids(L, [arrival], 1, np.random.default_rng(2))
        self.assertFalse(bids)
        self.assertTrue(gate.called)
        self.assertEqual(p.pos, 'CB')

    def test_camp_finalizes_after_actual_acquisitions(self):
        from session import Session
        L, t, p = self.setup_roster(); arrival = t.roster.pop(4)
        session = NS(L=L, rng=np.random.default_rng(3), user_team='GB')
        def acquire(*args, **kwargs):
            self.assertEqual(p.pos, 'CB'); t.roster.append(arrival)
        with patch('veteran_market.review', side_effect=acquire), patch('practice_squad.udfa_camp'), \
                patch('market.fill_out_rosters'), patch('market._pool', return_value=[]), \
                patch('newgens.build'), patch('scouting.scout'):
            Session.step_camp(session)
        self.assertEqual(p.pos, 'FS')

    def test_keep_valuable_corner_when_replacement_would_weaken_secondary(self):
        L, t, p = self.setup_roster()
        p.ratings = {k: 94 for k in p.ratings}
        for q in t.roster:
            if q.pos == 'CB' and q is not p: q.ratings = {k: 65 for k in q.ratings}
        self.assertEqual(PC.aging_corner_options(L, t), [])

    def test_unrelated_acquisitions_do_not_collect_conversion_bonus_twice(self):
        L, t, p = self.setup_roster()
        before = RN.planning_assess(L, t)
        arrival = copy.deepcopy(p); arrival.pid = 'new-wr'; arrival.pos = 'WR'; arrival.age = 22
        gain = RN.move_gain(t, arrival, baseline=before)
        after = RN.planning_assess(L, t, t.roster + [arrival])
        self.assertAlmostEqual(gain, after['score'] - before['score'])

    def test_useful_conversion_keeps_roster_contract_and_attributes(self):
        L, t, p = self.setup_roster()
        ratings = copy.deepcopy(p.ratings); roster = list(t.roster); contract = p.contract
        options = PC.aging_corner_options(L, t)
        self.assertTrue(options)
        self.assertGreater(options[0]['settled_gain'], options[0]['immediate_gain'])
        self.assertEqual(p.pos, 'CB')
        self.assertEqual(PC.review_aging_corners(L), [(p.pid, 'FS')])
        self.assertEqual(p.ratings, ratings); self.assertIs(p.contract, contract)
        self.assertEqual(t.roster, roster)
        self.assertEqual(sum(q.pos == 'CB' for q in t.roster), 4)
        self.assertEqual(L.transactions[-1]['displaced'], ['free'])
        self.assertEqual(PC.review_aging_corners(L), [])

    def test_thin_or_injured_corner_depth_stays_put(self):
        L, t, p = self.setup_roster()
        t.roster[-3].out_until = 4
        self.assertEqual(PC.aging_corner_options(L, t), [])
        t.roster[-3].out_until = None; t.roster.remove(L.players['corner3'])
        self.assertEqual(PC.review_aging_corners(L), [])
        self.assertEqual(p.pos, 'CB')

    def test_bad_tackler_and_no_range_cannot_hide_at_safety(self):
        for attr, value in (('tackle_rating', 50), ('speed_rating', 60), ('play_rec_rating', 50)):
            L, t, p = self.setup_roster(); p.ratings[attr] = value
            self.assertEqual(PC.aging_corner_options(L, t), [])

    def test_age_invites_review_without_forcing_it(self):
        L, t, p = self.setup_roster(); p.age = 27
        self.assertEqual(PC.aging_corner_options(L, t), [])
        p.age = 31
        self.assertTrue(PC.aging_corner_options(L, t))
        for q in t.roster:
            if q.pos in ('FS', 'SS'): q.ratings = {k: 95 for k in q.ratings}
        self.assertEqual(PC.aging_corner_options(L, t), [])

    def test_young_safety_is_not_displaced_for_marginal_upgrade(self):
        L, t, p = self.setup_roster()
        for q in t.roster:
            if q.pos in ('FS', 'SS'):
                q.age = 24; q.ratings = {k: 83 for k in q.ratings}
        self.assertEqual(PC.aging_corner_options(L, t), [])
        # A substantial upgrade still receives consideration.
        for q in t.roster:
            if q.pos in ('FS', 'SS'): q.ratings = {k: 65 for k in q.ratings}
        self.assertTrue(PC.aging_corner_options(L, t))

    def test_user_and_recent_transition_are_preserved(self):
        L, t, p = self.setup_roster(); L.user_team = 'DAL'
        self.assertEqual(PC.review_aging_corners(L), [])
        L.user_team = 'GB'; p.transition = dict(penalty=3, games_left=7, games_total=10)
        self.assertEqual(PC.aging_corner_options(L, t), [])

    def test_coach_preferences_can_disagree_on_close_case(self):
        found = False
        for grade in np.arange(77, 81, .25):
            L, t, p = self.setup_roster()
            for q in t.roster:
                if q.pos in ('FS', 'SS'): q.ratings = {k: float(grade) for k in q.ratings}
            t.gm.scheme_rigidity = 0; t.gm.patience = 1
            flexible = bool(PC.aging_corner_options(L, t))
            t.gm.scheme_rigidity = 1; t.gm.patience = 0
            conservative = bool(PC.aging_corner_options(L, t))
            if flexible and not conservative: found = True; break
        self.assertTrue(found)

    def test_no_hidden_potential_or_name_exception(self):
        L, t, p = self.setup_roster()
        before = [(x['to'], x['immediate_gain']) for x in PC.aging_corner_options(L, t)]
        p.name = 'Different Name'; p.potential = 99; p.longevity = .1
        after = [(x['to'], x['immediate_gain']) for x in PC.aging_corner_options(L, t)]
        self.assertEqual(before, after)

    def test_review_marker_survives_save_load(self):
        L, t, p = self.setup_roster(); PC.review_aging_corners(L)
        restored = League.load(L.save())
        self.assertEqual(restored.player(p.pid).xp_spent['_cb_safety_review'], 2031)
        self.assertEqual(PC.review_aging_corners(restored), [])


if __name__ == '__main__': unittest.main()
