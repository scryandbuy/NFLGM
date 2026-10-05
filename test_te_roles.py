import unittest
from types import SimpleNamespace as NS
import numpy as np
import targets as T
from league import Player
import offense_roles as O
import xp_spend as S
import field_fit as F

class TightEndRoles(unittest.TestCase):
    def player(self, pid='te', receiving=90, blocking=60):
        r={k:float(receiving) for k in T.TE_LEGACY_WEIGHTS}
        for k in T._TE_BLOCK:r[k]=float(blocking)
        return Player(pid,pid,'TE',24,r,potential=95,team='GB')
    def test_headline_and_role_grades(self):
        p=self.player()
        self.assertAlmostEqual(p.ovr,87)
        self.assertAlmostEqual(T.te_role_score(p.ratings,'balanced'),83.7)
        self.assertAlmostEqual(T.te_role_score(p.ratings,'blocking'),75)
        self.assertAlmostEqual(O.role_grade(p,'TE','12',0),87)
        self.assertAlmostEqual(O.role_grade(p,'TE','12',1),75)
    def test_run_block_visible_and_affects_fb_and_te_overall(self):
        import views_club as VC
        for pos in ('FB', 'TE'):
            p = Player('blocker', 'Blocker', pos, 24,
                       {key: 70. for key in T.DEPTH_WEIGHTS[pos]}, potential=99, team='GB')
            rows = [row for column in VC.attr_cols(p) for row in column['rows']]
            run_block = [row for row in rows if row['key'] == 'run_block_rating']
            self.assertEqual(len(run_block), 1)
            self.assertEqual(run_block[0]['label'], 'Run Block')
            before = p.ovr
            p.ratings['run_block_rating'] += 10
            expected = 10 * T.DEPTH_WEIGHTS[pos]['run_block_rating'] / sum(T.DEPTH_WEIGHTS[pos].values())
            self.assertAlmostEqual(p.ovr - before, expected)
            self.assertGreater(p.ovr, before)

    def test_migration_once_preserves_room_and_range(self):
        p=self.player();d=p.to_dict();d.pop('te_rating_version');d['potential']=88;d['potential_range']=[86,92]
        q=Player.from_dict(d)
        self.assertAlmostEqual(q.potential,91.3)
        self.assertAlmostEqual(q.potential_range[0],89.3)
        self.assertEqual(q.ratings,p.ratings)
        self.assertEqual(q.xp,p.xp)
        r=Player.from_dict(q.to_dict());self.assertEqual(q.potential,r.potential)
    def test_non_te_unchanged(self):
        p=self.player();p.pos='WR';d=p.to_dict();d.pop('te_rating_version')
        self.assertEqual(Player.from_dict(d).potential,p.potential)

    def test_new_player_no_migration(self):
        p=self.player();self.assertEqual(Player.from_dict(p.to_dict()).potential,95)
    def test_legacy_tags_do_not_double_count(self):
        p=self.player()
        for tag in ('heavy_te','spread_te'):
            self.assertAlmostEqual(T.position_score(p.ratings,'TE',tag),p.ovr)
            self.assertEqual(F.touched('TE',[tag]),{})
    def test_pinned_lead_and_reserve_roles(self):
        p=self.player();q=self.player('other',85,90)
        team=NS(roster=[p,q],gm=NS(off_personnel='12'),depth_pins={'TE':[p.pid,q.pid]})
        self.assertEqual(O.te_development_role(p,team),'receiving')
        self.assertEqual(O.te_development_role(q,team),'blocking')
    def test_role_directs_upgrade_mix(self):
        p=self.player(receiving=75,blocking=75);q=self.player('other',75,75)
        gm=NS(off_personnel='12',dev_belief=.5)
        team=NS(roster=[p,q],gm=gm,depth_pins={})
        def count(player):
            rng=np.random.default_rng(9)
            return sum(S.choose_attr(player,gm,rng,team) in T._TE_BLOCK for _ in range(2000))
        self.assertGreater(count(q),count(p)*2)
    def test_ceiling_clamp(self):
        d=self.player().to_dict();d.pop('te_rating_version');d['potential']=98
        self.assertEqual(Player.from_dict(d).potential,99)

if __name__=='__main__':unittest.main()
