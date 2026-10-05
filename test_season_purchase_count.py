import unittest
from types import SimpleNamespace as NS
import json
import xp as XP

class SeasonalPurchases(unittest.TestCase):
    def test_year_rollover_and_reload_keep_career_separate(self):
        p=NS(xp_spent={'catch_rating':40, '_bought_season':40, '_purchases':[
            {'kind':'buy','year':2028}, {'kind':'buy','year':2029},
            {'kind':'buy','year':2029}, {'kind':'unlock','year':2029},
            {'kind':'buy','year':None}]})
        self.assertEqual(XP.points_bought_in_year(p,2029),2)
        self.assertEqual(XP.points_bought_in_year(p,2030),0)
        self.assertEqual(XP.points_bought(p),40)
        loaded=NS(xp_spent=json.loads(json.dumps(p.xp_spent)))
        self.assertEqual(XP.points_bought_in_year(loaded,2029),2)
        XP._record_purchase(loaded,'buy',500,year=2030,attr='catch_rating')
        self.assertEqual(XP.points_bought_in_year(loaded,2030),1)
        self.assertEqual(XP.points_bought_in_year(loaded,2029),2)

    def test_undated_old_total_is_not_presented_as_this_year(self):
        self.assertEqual(XP.points_bought_in_year(NS(xp_spent={'_bought_season':50}),2029),0)
