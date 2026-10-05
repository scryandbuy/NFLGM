"""Concept preferences follow receiving jobs without rewriting play geometry."""
import copy
import unittest
import targets as T


def pair(pid, pos='WR', **ratings):
    return dict(receiver=dict(pid=pid,pos=pos,**ratings),separation=.42,
                defender={'pid':'def'+pid},route_air=12)


class ConceptRoles(unittest.TestCase):
    def test_vertical_and_underneath_specialists_get_different_jobs(self):
        rows=[pair('deep',route_run_deep_rating=95,speed_rating=95,
                   route_run_short_rating=55),
              pair('short',route_run_deep_rating=55,speed_rating=70,
                   route_run_short_rating=95,catch_rating=95)]
        T.assign_concept_roles(rows,'go','deep')
        self.assertEqual(rows[0]['concept_order'],0)
        T.assign_concept_roles(rows,'slant_flat','short')
        self.assertEqual(rows[1]['concept_order'],0)

    def test_dagger_dig_is_primary_and_back_stays_outlet(self):
        rows=[pair('dig',route_run_med_rating=95),
              pair('seam','TE',route_run_deep_rating=95),
              pair('back','HB',route_run_deep_rating=99,route_run_med_rating=99)]
        T.assign_concept_roles(rows,'dagger')
        self.assertEqual([r['concept_role'] for r in rows],['dig','seam','check'])
        self.assertEqual(rows[0]['concept_order'],0)

    def test_receiving_back_can_be_screen_primary(self):
        rows=[pair('wr',catch_rating=60,accel_rating=60,agility_rating=60,speed_rating=60),
              pair('back','HB',catch_rating=95,accel_rating=95,agility_rating=95,speed_rating=95)]
        T.assign_concept_roles(rows,'screen','short')
        self.assertEqual(rows[1]['concept_order'],0)

    def test_late_chip_does_not_become_primary_over_ready_receiver(self):
        rows=[pair('chip','TE',route_run_deep_rating=99),pair('ready')]
        rows[0]['late']=True
        T.assign_concept_roles(rows,'go','deep')
        self.assertEqual(rows[1]['concept_order'],0)

    def test_existing_fourth_down_routes_and_matchups_unchanged(self):
        rows=[pair('wr'),pair('te','TE'),pair('back','HB')]
        rows[2]['route_air']=2.6
        original=copy.deepcopy(rows)
        T.assign_concept_roles(rows,'four_verts','deep')
        for before,after in zip(original,rows):
            for key,val in before.items(): self.assertEqual(after[key],val)
        self.assertEqual(len({r['concept_order'] for r in rows}),3)
        self.assertTrue(all(.85<=r['concept_read_weight']<=1.15 for r in rows))

    def test_unknown_concept_neutral_and_empty_safe(self):
        rows=[pair('wr')]
        T.assign_concept_roles(rows,'go')
        T.assign_concept_roles(rows,'unknown')
        self.assertNotIn('concept_read_weight',rows[0])
        self.assertEqual(T.assign_concept_roles([],'go'),[])


if __name__=='__main__': unittest.main()
