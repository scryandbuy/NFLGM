"""Package quality matters to competing sellers, independently of asset totals."""
import unittest
from test_trade_integrity import roster,league,player
import trades as TR

class SellerLineupTests(unittest.TestCase):
    def case(self,window='race'):
        a,b=roster('GB'),roster('ARI'); L=league(a,b); L.user_team='GB';L.phase='regular';L.week=9
        b.ctx=lambda:dict(win_pct=.375,avg_age=28,phase='regular',games_played=8,
                         division_gap=2.,wildcard_gap=1. if window=='race' else 3.)
        target=next(p for p in b.roster if p.pos=='TE');target.ovr=95
        return L,a,b,target

    def test_competing_seller_cannot_swap_star_for_redundant_depth(self):
        L,a,b,target=self.case()
        sends=[next(p.pid for p in a.roster if p.pos==pos) for pos in ('HB','WR')]
        r=TR.package_football(L,a,b,sends,[target.pid])
        self.assertFalse(r['approved']);self.assertEqual(r['reason'],'competitive_roster_loss')

    def test_genuine_seller_can_take_future_value(self):
        L,a,b,target=self.case('seller')
        r=TR.package_football(L,a,b,[],[target.pid])
        self.assertTrue(r['approved']);self.assertLess(r['gains']['ARI'],-TR.UPGRADE_GAP)

    def test_competing_seller_can_receive_equivalent_starter(self):
        L,a,b,target=self.case();replacement=next(p for p in a.roster if p.pos=='TE');replacement.ovr=95
        self.assertTrue(TR.package_football(L,a,b,[replacement.pid],[target.pid])['approved'])

    def test_user_can_choose_to_trade_own_star(self):
        L,a,b,target=self.case();L.user_team='ARI'
        self.assertTrue(TR.package_football(L,a,b,[],[target.pid])['approved'])

if __name__=='__main__':unittest.main()
