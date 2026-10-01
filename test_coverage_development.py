"""Coverage development uses attributed evidence, not team results or quiet box scores."""
import copy
import unittest
from types import SimpleNamespace as N
import dev_evaluation as DE
import dev_roll as DR
from test_dev_role_integration import add
from test_cap_accounting import fixture


def line(cmp=40, air=400, targets=80, snaps=650, bucket='man_short'):
    d=dict(def_plays=800,cov_snaps=snaps,cov_outside_snaps=snaps)
    for k,v in dict(targets=targets,completions=cmp,air_yards=air,td=0,explosive=0,pd=0,ints=0).items():
        d['cov_'+bucket+'_'+k]=v
    return d


def calibrated(lines):
    rows={str(i):DE.assessment(N(pos='CB'),d) for i,d in enumerate(lines)}
    DE.calibrate_coverage(rows)
    return list(rows.values())


class CoverageDevelopmentTests(unittest.TestCase):
    def test_better_outcomes_and_sufficient_evidence(self):
        rows=calibrated([line(cmp=x,air=x*10) for x in (20,30,40,50,60,70)])
        self.assertTrue(all(r['credible'] for r in rows))
        self.assertGreater(rows[0]['score'],rows[-1]['score'])

    def test_no_peers_cannot_demote(self):
        self.assertFalse(calibrated([line()])[0]['credible'])

    def test_low_targets_and_partial_season_cannot_demote(self):
        for weak in (line(10,80,targets=15),line(snaps=200)):
            rows=calibrated([weak]+[line() for _ in range(5)])
            self.assertFalse(rows[0]['credible'])

    def test_role_and_depth_are_not_mixed(self):
        rows=calibrated([line() for _ in range(5)]+[line(bucket='zone_deep')])
        self.assertFalse(rows[-1]['credible'])
        slot=line();slot['cov_outside_snaps']=0;slot['cov_slot_snaps']=650
        rows=calibrated([line() for _ in range(5)]+[slot])
        self.assertFalse(rows[-1]['credible'])

    def test_volume_is_not_quality_and_team_epa_is_ignored(self):
        a=line(); b={k:v*2 for k,v in a.items()}; b['def_epa']=-9999
        rows=calibrated([a,b]+[line() for _ in range(5)])
        self.assertAlmostEqual(rows[0]['score'],rows[1]['score'])

    def test_equal_bucket_quality_with_different_depth_mix(self):
        lines=[]
        for short,deep in ((60,20),(20,60),(40,40),(50,30),(30,50),(45,35)):
            d=line(cmp=short*.7,air=short*2,targets=short)
            deep_line=line(cmp=deep*.4,air=deep*10,targets=deep,bucket='zone_deep')
            d.update({k:v for k,v in deep_line.items() if k.startswith('cov_zone_')})
            lines.append(d)
        rows=calibrated(lines)
        self.assertTrue(all(r['credible'] for r in rows))
        for r in rows:self.assertAlmostEqual(r['score'],0.)

    def test_two_seasons_then_save_reload_idempotence(self):
        from league import League
        l=fixture()
        for i in range(6):add(l,str(i),'CB',line(cmp=25+i*10,air=200+i*100),ovr=70+i*4,dev='superstar')
        bad=l.player('5');rng=N(random=lambda:.999999)
        DR.run(l,{},rng);self.assertEqual(bad.dev,'superstar')
        self.assertEqual(bad.xp_spent['_dev_review'][-1]['poor_seasons'],1)
        old=l.year;l.year+=1;l.stats[l.year]=copy.deepcopy(l.stats[old])
        DR.run(l,{},rng);self.assertEqual(bad.dev,'star')
        loaded=League.load(l.save());DR.run(loaded,{},rng)
        self.assertEqual(loaded.player('5').dev,'star')
        self.assertEqual(len(loaded.player('5').xp_spent['_dev_review']),2)

    def test_legacy_evidence_never_starts_coverage_downgrade(self):
        row=DE.assessment(N(pos='CB'),dict(def_plays=1000,pass_def=0,int_def=0))
        self.assertFalse(row['credible'])
        self.assertNotIn('coverage_cells',row)

if __name__=='__main__':unittest.main()
