"""Real role scores connected to annual reviews, awards, and saved leagues."""
import unittest
from types import SimpleNamespace as N
import awards as AW
import dev_evaluation as DE
import dev_roll as DR
import targets as TG
from league import League, Player
from test_cap_accounting import fixture


def add(l,pid,pos,line,ovr=75,dev='normal'):
    p=Player(pid,pid,pos,28,{k:ovr for k in TG.DEPTH_WEIGHTS[pos]},team='GB',dev=dev)
    l.players[pid]=p;l.teams['GB'].roster.append(p)
    l.stats.setdefault(l.year,{})[pid]=line
    return p


class DevelopmentRoleIntegrationTests(unittest.TestCase):
    def test_specialist_honors_follow_performance_not_insertion_order(self):
        l=fixture()
        for pos in ('K','P'):
            if pos=='K':
                weak=dict(fg_att=35,fg_made=24,xp_att=40,xp_made=36)
                strong=dict(fg_att=35,fg_made=33,xp_att=40,xp_made=40)
                tiny=dict(fg_att=3,fg_made=3,xp_att=6,xp_made=6)
            else:
                weak=dict(punts=60,punt_net_yds=2100,punt_in20=10,punt_tb=10)
                strong=dict(punts=60,punt_net_yds=2700,punt_in20=25,punt_tb=4)
                tiny=dict(punts=3,punt_net_yds=160,punt_in20=3,punt_tb=0)
            add(l,pos+'weak',pos,weak)
            add(l,pos+'strong',pos,strong)
            add(l,pos+'tiny',pos,tiny)
        for reverse in (False,True):
            if reverse:l.stats[l.year]=dict(reversed(list(l.stats[l.year].items())))
            first,second=AW.Ballot(l).all_pro()
            self.assertEqual({p.pid for p in first},{'Kstrong','Pstrong'})
            self.assertEqual({p.pid for p in second},{'Kweak','Pweak'})
        # Awards still give a real specialist the existing upgrade opportunity.
        DR.run(l,{'all_pro_1':first,'all_pro_2':second},N(random=lambda:0.))
        self.assertEqual(l.player('Kstrong').dev,'star')
        self.assertEqual(l.player('Pstrong').dev,'star')
        loaded=League.load(l.save())
        self.assertEqual(loaded.player('Kstrong').dev,'star')

    def test_lineman_full_season_is_not_penalized_twice_for_playing_more(self):
        l=fixture()
        better=dict(snaps=1200,pb_snaps=600,pb_wins=570,rb_snaps=600,rb_wins=540,
                    sacks_allowed=2,pressures_allowed=10)
        worse=dict(snaps=300,pb_snaps=150,pb_wins=120,rb_snaps=150,rb_wins=105,
                   sacks_allowed=2,pressures_allowed=10)
        a=add(l,'full','LT',better);b=add(l,'backup','RT',worse)
        add(l,'other1','LT',dict(better,pb_wins=500,rb_wins=450))
        add(l,'other2','RT',dict(better,pb_wins=520,rb_wins=470))
        self.assertGreater(DE.assessment(a,better)['score'],DE.assessment(b,worse)['score'])
        DR.run(l,{},N(random=lambda:.5))
        self.assertGreater(a.xp_spent['_dev_review'][-1]['production'],
                           b.xp_spent['_dev_review'][-1]['production'])

    def test_quiet_corner_is_not_demoted_without_individual_coverage_evidence(self):
        l=fixture()
        for i in range(4):
            add(l,str(i),'CB',dict(snaps=900,def_plays=900,pass_def=i*5,int_def=i,
                                 tackles=40,def_epa=100*i),ovr=90-i*5,dev='superstar')
        for _ in range(3):
            DR.run(l,{},N(random=lambda:.9999))
            self.assertEqual(l.player('0').dev,'superstar')
            self.assertEqual(l.player('0').xp_spent['_dev_review'][-1]['chance_down'],0)
            old=l.year;l.year+=1;l.stats[l.year]=dict(l.stats[old])
        # Shared team EPA must not be read as a corner's personal coverage result.
        p=l.player('0');line=l.stats[l.year]['0']
        self.assertEqual(DE.assessment(p,line)['score'],DE.assessment(p,dict(line,def_epa=-999))['score'])


if __name__=='__main__':unittest.main()
