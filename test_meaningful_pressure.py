import unittest
from collections import Counter
from types import SimpleNamespace as N
from pressure_evidence import disrupted, credited_rushers
from halftime import first_half, recommendations
from gameplan_week import pressure_advice, record_game

class MeaningfulPressure(unittest.TestCase):
    def play(self, arrival, **extra):
        return dict(type='complete', is_pass=True, pressured=True, yards=7,
                    pressure_arrivals=[('edge',arrival)], pressure_release=3.,
                    pressure_credit_end=3., **extra)

    def test_legacy_timing_reclassifies_marginal_pressure(self):
        self.assertFalse(disrupted(self.play(2.99)))
        self.assertTrue(disrupted(self.play(2.4)))
        self.assertFalse(disrupted(dict(type='complete',pressured=True)))

    def test_sack_and_forced_throwaway_survive(self):
        self.assertTrue(disrupted(dict(type='sack')))
        self.assertEqual(credited_rushers(dict(throwaway=True),3.,[('edge',2.9)],2.9),{'edge'})
        self.assertFalse(credited_rushers({},3.,[('edge',3.01)],3.))

    def test_halftime_ignores_marginal_arrivals_but_counts_real_threat(self):
        for arrival, expected in [(2.99,0),(2.4,12)]:
            drives=[('home',N(log=[self.play(arrival) for _ in range(12)],points=0,first_downs=3))]
            me,_=first_half(drives,'home')
            self.assertEqual(me['pressures'],expected)
            recs=recommendations(None,'GB','DAL',drives,'home',{'home':0,'away':0},None,None,coherent=False)
            self.assertEqual(any(r.get('review_key')=='protection' for r in recs), bool(expected))

    def test_old_tendency_totals_do_not_contaminate_new_evidence(self):
        L=N(year=2032,tendencies={2032:{'DAL':Counter(pressure_dropbacks=100,pressured_dropbacks=95,plays=100,passes=60,def_snaps=100)}})
        record_game(L,'GB','DAL',dict(drives=[('home',N(log=[self.play(2.99)],result='Punt'))]))
        c=L.tendencies[2032]['DAL']
        self.assertEqual(c['pressure_dropbacks'],1)
        self.assertEqual(c['pressured_dropbacks'],0)
        self.assertEqual(c['plays'],100)

    def test_old_aggregate_alone_cannot_trigger_advice(self):
        self.assertIsNone(pressure_advice(dict(pressure_dropbacks=100,pressured_dropbacks=90),dict(matchups=[dict(gap=20)],recommend=True),None))

if __name__=='__main__': unittest.main()
