import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import plays as P
import game as G
import ticker
import skill_runs as SR
from test_run_support_attributes import offense
from test_defensive_rush import unit, call


class SkillRuns(unittest.TestCase):
    def test_play_statbook_fumble_and_ticker_follow_actual_runner(self):
        for action, scheme, distance, motion, pid in (
                ('jet_sweep','outside_zone',10,True,'WR0'),
                ('end_around','stretch',10,False,'WR0'),
                ('fb_handoff','power',1,False,'FB')):
            off=offense(); defense=unit('4-3')
            oc=dict(is_pass=False,scheme=scheme,down=1,ydstogo=distance,motion=motion)
            dc=dict(call('4-3'),front='4-3 over',box=6)
            # Find a naturally selected carry: full resolver remains unmocked.
            for seed in range(2000):
                out=P.resolve_play(off,defense,oc,dc,60,np.random.default_rng(seed))
                if out.get('run_action')==action: break
            else: self.fail(action)
            self.assertEqual(out['carrier'],pid)
            self.assertNotIn(pid,dict(out['rb_reps']))
            book=G.StatBook();book.record(out,off,defense,np.random.default_rng(5))
            self.assertEqual(book.p[pid]['rush_att'],1)
            self.assertEqual(book.p[pid]['rush_yds'],out['yards'])
            self.assertEqual(book.p.get('HB',{}).get('rush_att',0),0)
            with patch('events.fumble_check',return_value=None) as check:
                G._prepare_fumble(SimpleNamespace(yardline=60),out,off,defense,np.random.default_rng(4),P.rate)
            self.assertEqual(check.call_args.args[0]['pid'],pid)
            line=ticker.play_line(SimpleNamespace(player=lambda p:SimpleNamespace(name=p)),
                dict(out,yardline=60,down=1,ydstogo=distance,clock=600),'GB','LA')['text']
            self.assertIn(pid,line)
            if not out.get('touchdown'):
                self.assertIn({'jet_sweep':'jet sweep','end_around':'end-around','fb_handoff':'fullback handoff'}[action],line)

    def test_full_drive_carries_use_selected_personnel_and_book(self):
        for position, action, scheme, distance in [('WR','jet_sweep','outside_zone',10),('FB','fb_handoff','power',1)]:
            off=offense(); defense=unit('4-3'); book=G.StatBook()
            chosen=[]
            def select(field, oc, ytg, rate, rng):
                runners=[p for p in field['wr'] if p.get('pos')==position]
                if oc.get('is_pass') or oc.get('qb_run') or oc.get('sneak') or not runners:
                    return None,None
                chosen.append(runners[0]['pid'])
                return runners[0],action
            def co(down, togo, margin, ytg, rng, **kw):
                return dict(is_pass=False,scheme=scheme,personnel='22',down=down,
                            ydstogo=distance,motion=position=='WR',score_diff=margin)
            with patch.object(SR,'choose',side_effect=select), patch('events.penalty_check',return_value=None), patch('events.fumble_check',return_value=None), patch('schemes.designed_qb_run_chance',return_value=0), patch('playcall.audible',side_effect=lambda oc,*a,**kw:(oc,None)):
                dr=G.run_drive(off,defense,60,700,3,0,np.random.default_rng(31),P.resolve_play,co,
                    lambda *a,**kw:dict(call('4-3'),front='4-3 over',box=6),P.rate,book=book)
            runs=[p for p in dr.log if p.get('run_action')==action]
            self.assertTrue(runs)
            pid=chosen[0]
            self.assertEqual(book.p[pid]['rush_att'],len(runs))
            self.assertAlmostEqual(book.p[pid]['rush_yds'],sum(p['yards'] for p in runs))
            self.assertTrue(all(p['carrier']==pid and pid not in dict(p['rb_reps']) for p in runs))

    def test_restraint_and_missing_personnel(self):
        off=offense();base=dict(is_pass=False,down=1,ydstogo=10,scheme='outside_zone',motion=True)
        for changes in (dict(qb_run=True),dict(sneak=True),dict(is_pass=True),dict(down=4),
                        dict(down=3),dict(protect_ball=True),dict(seconds=60),dict(scheme='inside_zone')):
            for seed in range(100):
                self.assertEqual(SR.choose(off,dict(base,**changes),60,P.rate,np.random.default_rng(seed)),(None,None))
        for changes in (dict(wr=[]),dict(rb=None)):
            for seed in range(100):
                self.assertEqual(SR.choose(dict(off,**changes),base,60,P.rate,np.random.default_rng(seed)),(None,None))
        no_fb=dict(off,offensive_assignments=[(r,p) for r,p in off['offensive_assignments'] if r!='FB'])
        self.assertEqual(SR.choose(no_fb,dict(base,scheme='power',ydstogo=1),60,P.rate,np.random.default_rng(1)),(None,None))
        qb=P.resolve_play(off,unit('4-3'),dict(base,qb_run=True),dict(call('4-3'),front='4-3 over',box=6),60,np.random.default_rng(1))
        self.assertEqual(qb['carrier'],'QB')

    def test_more_receivers_do_not_multiply_call_appetite(self):
        off=offense();wr=next(p for p in off['wr'] if p['pos']=='WR')
        wr.update({key:90 for key in SR.WR_RUN})
        oc=dict(down=1,ydstogo=10,scheme='outside_zone',motion=True)
        counts=[]
        for n in (1,3,4):
            field=dict(off,wr=[dict(wr,pid='WR'+str(i)) for i in range(n)])
            rng=np.random.default_rng(718)
            counts.append(sum(SR.choose(field,oc,60,P.rate,rng)[0] is not None for _ in range(10000)))
        self.assertEqual(counts,[693,693,693])

    def test_serialized_acceleration_and_trucking_attributes_change_fit(self):
        self.assertGreater(P.rate(dict(accel_rating=95),SR.WR_RUN),P.rate(dict(accel_rating=30),SR.WR_RUN))
        self.assertGreater(P.rate(dict(truck_rating=95),SR.FB_RUN),P.rate(dict(truck_rating=30),SR.FB_RUN))
        self.assertNotIn('acceleration_rating',SR.WR_RUN)
        self.assertNotIn('trucking_rating',SR.FB_RUN)

    def test_rare_skill_and_motion_sensitive_selection(self):
        base=dict(is_pass=False,down=1,ydstogo=10,scheme='outside_zone')
        counts={}
        for quality in (45,90):
            off=offense()
            for p in off['wr']:
                p.update({key:quality for key in SR.WR_RUN})
            for motion in (False,True):
                rng=np.random.default_rng(718)
                counts[quality,motion]=sum(SR.choose(off,dict(base,motion=motion),60,P.rate,rng)[0] is not None for _ in range(10000))
        self.assertLess(counts[45,True],counts[90,True])
        self.assertLess(counts[90,False],counts[90,True])
        self.assertGreater(counts[90,True],0)
        self.assertLess(counts[90,True],1000)
        print('Controlled selections per 10,000 eligible runs:',counts)

if __name__=='__main__':unittest.main()
