"""Senior Bowl reporting across playoffs, save/load, and the spring year roll."""
import copy
import unittest
from unittest.mock import patch

import scouting as SC
import session
import spring as SP
import views_draft as VD


class SeniorBowlReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = session.Session.new('GB', seed=91).save()

    def fresh(self):
        s = session.Session.load(self.initial)
        s.L.phase = 'playoffs'
        return s

    def report(self, s):
        with patch.object(VD, 'rail', return_value={}):
            return VD.spring(s, s.L, 'GB')

    def test_early_results_survive_save_roll_and_spring_without_replay(self):
        s = self.fresh()
        L = s.L
        seniors = [p for p in L.next_class if p.age >= 22.5 and p.pos not in ('K', 'P', 'LS')]
        self.assertGreaterEqual(len(seniors), 2)
        up, down = seniors[:2]
        real_consensus = SC.consensus

        def moved(league):
            result = real_consensus(league)
            result[up.pid].update(prev_rank=50, rank=20)
            result[down.pid].update(prev_rank=20, rank=50)
            return result

        with patch.object(SC, 'consensus', side_effect=moved):
            s._senior_bowl()
        news = copy.deepcopy(L.spring_news)
        self.assertTrue(all(x['year'] == L.year + 1 for x in news))
        view = self.report(s)
        invited = {p.pid for p in L.next_class if p.xp_spent.get('_senior_bowl') == L.year}
        self.assertEqual({r['pid'] for r in view['senior_bowl']}, invited)
        self.assertIn(up.pid, [r['pid'] for r in view['risers']])
        self.assertIn(down.pid, [r['pid'] for r in view['fallers']])
        self.assertFalse(VD._spring_done(L))
        self.assertIn('after the conference championships', view['note'])
        self.assertEqual(view['events'][0]['event'], 'Senior Bowl')
        resumed = session.Session.load(s.save())
        self.assertEqual({r['pid'] for r in self.report(resumed)['senior_bowl']}, invited)
        self.assertEqual(resumed.L.spring_news, news)
        rng_before = copy.deepcopy(resumed.rng.bit_generator.state)
        resumed._senior_bowl()
        self.assertEqual(resumed.L.spring_news, news)
        self.assertEqual(resumed.rng.bit_generator.state, rng_before)
        resumed.L.year += 1
        resumed.L.phase = 'offseason'
        resumed.L.season_closed_year = resumed.L.year - 1
        resumed.L.draft_pool, resumed.L.next_class = resumed.L.next_class, []
        self.assertEqual({r['pid'] for r in self.report(resumed)['senior_bowl']}, invited)
        with patch.object(SP, 'senior_bowl', side_effect=AssertionError('must not replay')):
            SP.run_spring(resumed.L, resumed.rng)
        self.assertEqual([x for x in resumed.L.spring_news if x.get('event') == 'Senior Bowl'], news)
        self.assertTrue(VD._spring_done(resumed.L))
        self.assertIsNone(self.report(resumed)['note'])
        saved = session.Session.load(resumed.save())
        self.assertEqual(saved.L.spring_news, resumed.L.spring_news)

    def test_zero_moves_is_a_valid_report_not_a_missing_event(self):
        s = self.fresh()
        real_consensus = SC.consensus

        def unchanged(league):
            result = real_consensus(league)
            for c in result.values():
                c['prev_rank'] = c['rank']
            return result

        with patch.object(SC, 'consensus', side_effect=unchanged):
            SC.senior_bowl(s.L, s.rng)
        v = self.report(s)
        self.assertTrue(v['done'])
        self.assertEqual(v['risers'], [])
        self.assertEqual(v['fallers'], [])
        self.assertEqual(v['events'][0]['n'], 0)
        self.assertEqual(len(v['senior_bowl']), 110)
        self.assertTrue(all(r['move'] is None for r in v['senior_bowl']))
        self.assertFalse(VD._spring_done(s.L))

    def test_full_movement_list_and_attendance_are_independent(self):
        s = self.fresh()
        players = s.L.next_class[:30]
        for p in players:
            p.xp_spent.pop('_senior_bowl', None)
        players[0].xp_spent['_senior_bowl'] = s.L.year
        players[1].xp_spent['_senior_bowl'] = s.L.year - 2
        s.L.spring_news = [dict(kind='stock', year=s.L.year + 1, event='Senior Bowl',
                               pid=p.pid, name=p.name, pos=p.pos, frm=100, to=50)
                           for p in players]
        v = self.report(s)
        self.assertEqual(len(v['risers']), 30)
        self.assertEqual([r['pid'] for r in v['senior_bowl']], [players[0].pid])
        self.assertEqual(v['senior_bowl'][0]['move']['delta'], 50)

    def test_spring_discards_previous_class_and_marks_zero_movement_complete(self):
        s = self.fresh()
        L = s.L
        L.year += 1
        L.phase = 'offseason'
        L.draft_pool, L.next_class = L.next_class, []
        L.spring_news = [dict(year=L.year - 1, event='Senior Bowl', kind='event')]
        with patch.object(SP, 'combine', return_value=(0, [])), \
             patch.object(SP, 'senior_bowl', return_value=(0, [])) as fallback, \
             patch.object(SP, 'pro_days', return_value=(0, [])), \
             patch.object(SP, 'visits', return_value=(0, [])):
            SP.run_spring(L, s.rng)
        fallback.assert_called_once()
        self.assertEqual(L.spring_news, [dict(kind='stage', year=L.year, event='pre_visits'),
                                        dict(kind='complete', year=L.year, event='spring')])
        self.assertTrue(VD._spring_done(L))


if __name__ == '__main__':
    unittest.main()
