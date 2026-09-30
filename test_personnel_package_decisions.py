"""Decision consumers must value actual playing roles, using the same roster plan."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import draft
import draft_plan as DP
import market
import roster_needs as RN
import trades
import targets as TG
from league import Player
from test_draft_planning import fixture, set_grade


def prospect(L, pos, name, overrides=None):
    keys = {k for weights in TG.DEPTH_WEIGHTS.values() for k in weights}
    ratings = dict.fromkeys(keys, 80.0)
    ratings.update(overrides or {})
    p = Player(name, name, pos, 22, ratings, potential=80, potential_range=(80, 80))
    for _ in range(40):
        correction = 80 - p.ovr
        p.ratings = {k: min(99, max(30, v+correction)) for k, v in p.ratings.items()}
        if abs(correction) < .00001: break
    p.xp_spent['_tape'] = 0
    L.players[p.pid] = p
    L.scouting['MIN'][p.pid] = dict(ovr=80, pot_lo=80, pot_hi=80, flags=[], e_phys=0, e_skill=0)
    L.consensus[p.pid] = dict(ovr=80, pot=80, rank=1)
    return p


def offense_fixture(package):
    L, t = fixture(); t.gm.off_personnel = package
    t.gm.board_trust = .25; t.gm.need_inflation = .8; t.gm.job_security = 1
    for p in t.roster: set_grade(p, 90)
    # Three good receivers cover 11; the fourth is a real vacancy in 10.
    for p in t.by_pos('WR')[3:]: set_grade(p, 55)
    for p in t.by_pos('TE')[1:]: set_grade(p, 55)
    if package == '11': set_grade(L.player('WR2'), 55)
    wr, te, qb = (prospect(L, pos, f'new-{pos}') for pos in ('WR', 'TE', 'QB'))
    L.draft_pool = [wr, te, qb]
    return L, t, wr, te, qb


def assets(players):
    return [dict(pid=p.pid, obj=p, kind='player', seen_ovr=80, grp=trades.GRP.get(p.pos,p.pos)) for p in players]


class PersonnelPackageDecisionTests(unittest.TestCase):
    def test_offensive_packages_change_actual_fa_targets_and_trade_order(self):
        for package, expected in [('10','WR'), ('11','WR'), ('12','TE')]:
            with self.subTest(package=package):
                L,t,wr,te,qb = offense_fixture(package)
                pool = [wr,te,qb]
                report=RN.assess(t)
                gains=RN.candidate_gains(t,pool,baseline=report)
                self.assertEqual(max(pool,key=lambda p:gains[p.pid]).pos, expected)
                self.assertLessEqual(gains[qb.pid], .01)
                ranked=trades.package_trade_targets(t,assets(pool),report)
                self.assertEqual(ranked[0]['obj'].pos, expected)
                self.assertNotIn(qb.pid,[r['pid'] for r in ranked])
                with patch.object(market.VAL,'pool_from_league',return_value={}), \
                     patch.object(market.VAL,'value_player',return_value={'apy':10,'years':1}), \
                     patch.object(market,'power',return_value=100), \
                     patch('gm_engine.scheme_fit',return_value=0):
                    bids=market.ai_bids(L,pool,1,np.random.default_rng(7))
                self.assertEqual(L.player(next(iter(bids))).pos, expected)
                self.assertNotIn(qb.pid,bids)
                if wr.pid in bids and te.pid in bids:
                    winner=wr if expected=='WR' else te
                    loser=te if expected=='WR' else wr
                    self.assertGreater(bids[winner.pid][0].apy,bids[loser.pid][0].apy)

    def test_draft_board_uses_same_package_demand(self):
        for package, expected in [('10','WR'),('11','WR'),('12','TE')]:
            L,t,wr,te,qb=offense_fixture(package)
            ranked=draft.board(L,'MIN',40,{},set())
            self.assertEqual(ranked[0][1].pos,expected,package)

    def test_rare_heavy_role_has_less_value_than_base_receiving_role(self):
        L,t,wr,te,qb=offense_fixture('10')
        set_grade(L.player('FB0'),55)
        fb=prospect(L,'FB','new-FB')
        gains=RN.candidate_gains(t,[wr,fb])
        self.assertLess(market.recruit_priority(gains[fb.pid]),market.recruit_priority(gains[wr.pid]))
        plan=DP.assess(L,'MIN')
        self.assertLess(plan['positions']['FB']['starter'],plan['positions']['WR']['starter'])

    def test_multiple_fronts_and_coverage_drive_equal_overall_targets(self):
        for coverage, expected in [(0, 'zone'), (1, 'man')]:
            L,t=fixture();t.gm.def_front='multiple';t.gm.coverage=coverage
            for p in t.roster: set_grade(p,90)
            for p in t.by_pos('CB'): set_grade(p,55)
            man=prospect(L,'CB','man',dict(man_cover_rating=99,press_rating=99,agility_rating=90,
                         zone_cover_rating=40,play_rec_rating=50,awareness_rating=50))
            zone=prospect(L,'CB','zone',dict(man_cover_rating=40,press_rating=40,agility_rating=60,
                          zone_cover_rating=99,play_rec_rating=99,awareness_rating=99))
            qb=prospect(L,'QB','unneeded-QB');pool=[man,zone,qb];L.draft_pool=pool
            self.assertAlmostEqual(man.ovr,zone.ovr,places=3)
            report=RN.assess(t)
            self.assertEqual({r['front'] for r in report['package_assignments']
                              if r['side']=='defense'}, {'3-4','4-3'})
            self.assertEqual(trades.package_trade_targets(t,assets(pool),report)[0]['pid'],expected)
            with patch.object(market.VAL,'pool_from_league',return_value={}), \
                 patch.object(market.VAL,'value_player',return_value={'apy':10,'years':1}), \
                 patch.object(market,'power',return_value=100), \
                 patch('gm_engine.scheme_fit',return_value=0):
                bids=market.ai_bids(L,pool,1,np.random.default_rng(7))
            self.assertEqual(next(iter(bids)),expected)
            self.assertNotIn(qb.pid,bids)
            self.assertEqual(draft.board(L,'MIN',40,{},set())[0][1].pid,expected)

    def test_trade_cache_is_decision_local_and_does_not_mutate_roster(self):
        L,t,wr,te,qb=offense_fixture('12'); snapshot=copy.deepcopy(L.save())
        report=RN.assess(t);cache={}
        with patch.object(RN,'candidate_gains',wraps=RN.candidate_gains) as batch:
            first=trades.package_trade_targets(t,assets([wr,te,qb]),report,cache)
            second=trades.package_trade_targets(t,assets([wr,te,qb]),report,cache)
        self.assertEqual([r['pid'] for r in first],[r['pid'] for r in second])
        self.assertEqual(batch.call_args_list[-1].args[1],[])
        self.assertEqual(L.save(),snapshot)

    def test_prospect_role_gain_respects_scouting_error(self):
        L,t,wr,te,qb=offense_fixture('12');plan=DP.assess(L,'MIN')
        before=DP.prospect_gains(L,'MIN',[te],plan,{te.pid:80})[te.pid]
        L.scouting['MIN'][te.pid].update(ovr=60,e_phys=-20,e_skill=-20)
        after=DP.prospect_gains(L,'MIN',[te],plan,{te.pid:60})[te.pid]
        self.assertLess(after,before)


if __name__=='__main__': unittest.main()
