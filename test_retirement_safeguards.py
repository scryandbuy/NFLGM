import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import retirement as R
import league as LG


def player(pid='p', age=30, ovr=85):
    return N(pid=pid, name=pid, pos='HB', age=age, development_age=age,
             ovr=ovr, longevity=1., retired=False, team='T', contract=None, xp_spent={})


class RetirementTests(unittest.TestCase):
    def test_smooth_age_boundaries(self):
        for age in (29.5, 30, 30.5, 31, 36, 39, 40):
            self.assertLess(abs(R.chance(player(age=age-.0001), ovr=85)-R.chance(player(age=age+.0001), ovr=85)), .0001)

    def test_early_star_protection_and_aging(self):
        self.assertLess(R.chance(player(), ovr=85), .01)
        self.assertGreater(R.chance(player(age=35), ovr=85), R.chance(player(), ovr=85))
        self.assertGreater(R.chance(player(), ovr=72), R.chance(player(), ovr=85))
        self.assertGreater(R.chance(player(), ovr=85), 0)

    def test_quality_baseline_independent_of_class(self):
        self.assertEqual(R.chance(player(), ovr=85, league_avg_ovr=60), R.chance(player(), ovr=85, league_avg_ovr=85))

    def test_all_locations_cleanup_and_once(self):
        a,b,c,d = [player(k) for k in ('active','ir','ps','prospect')]
        t=N(roster=[a,b], ir=[b], practice_squad=[c], _elevated=[c], sync_cap=lambda:None)
        l=N(year=2028, players={p.pid:p for p in (a,b,c,d)}, teams={'T':t}, free_agents=[], next_class=[d], stats={}, log=lambda *a,**k:None)
        rng=N(random=lambda:0.)
        with patch('cap_accounting.settle_week'):
            self.assertEqual(len(R.run(l,rng)),3)
        self.assertFalse(d.retired)
        self.assertEqual(t.roster+t.ir+t.practice_squad+t._elevated,[])
        self.assertEqual(R.run(l,N(random=lambda: self.fail('reroll'))),[])

    def test_survivor_not_rerolled_after_partial_retry(self):
        p=player(); l=N(year=2028, players={'p':p},teams={},free_agents=['p'],stats={},log=lambda *a,**k:None)
        R.run(l,N(random=lambda:1.))
        l.retirement_applied_years=[]
        R.run(l,N(random=lambda:self.fail('survivor rerolled')))
        self.assertFalse(p.retired)

    def test_year_guard_roundtrip(self):
        l=LG.League(2028); l.retirement_applied_years=[2027,2028]
        self.assertEqual(LG.League.load(l.save()).retirement_applied_years,[2027,2028])

if __name__ == '__main__': unittest.main()
