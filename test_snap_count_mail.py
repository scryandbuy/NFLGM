"""Per-game participation mail: exact unit denominators, persistence, and no sim effects."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game
import game_recap as GR
from season import SeasonRunner
from session import Session
from test_offense_personnel import roster, State


class SnapCountUnitTests(unittest.TestCase):
    def test_selected_players_counted_once_and_no_extra_random_draws(self):
        a, b = State(), State()
        ra, rb = np.random.default_rng(31), np.random.default_rng(31)
        one = game.field_units(roster(), a, ra, True, '12')
        two = game._field_units(roster(), b, rb, True, '12')
        self.assertEqual(one, two)
        self.assertEqual(a.recorded, b.recorded)
        self.assertEqual(ra.bit_generator.state, rb.bit_generator.state)
        self.assertEqual(a.snap_counts['offense']['total'], 1)
        self.assertEqual(a.snap_counts['offense']['players'], dict.fromkeys(one[1], 1))

    def test_zero_snaps_elevation_cross_unit_and_immutable_mail(self):
        ps = [NS(pid=str(i), name=f'Player {i}', pos=pos) for i, pos in enumerate(['QB','WR','LEDG','CB','K','HB'])]
        team = NS(active=lambda:ps[:5], _elevated=[ps[5]])
        league = NS(year=2027, week=19, user_team='GB', teams={'GB':team},
                    notes_sent={}, inbox=[], player=lambda pid:next(p for p in ps if p.pid==pid))
        counts = dict(offense=dict(total=82,players={'0':82,'1':51,'5':6}),
                      defense=dict(total=75,players={'2':70,'1':1}))
        states = {'GB':NS(last_snap_counts=counts)}
        msg = GR.post_snap_counts(league,'MIN','GB',19,states,True)
        data=msg['payload']['snap_counts']
        self.assertEqual(data['offense']['total'],82)
        self.assertEqual(data['defense']['total'],75)
        self.assertIn(dict(pid='3',name='Player 3',pos='CB',snaps=0),data['defense']['rows'])
        self.assertIn('Player 5: 6/82 Snaps',msg['body'])
        self.assertNotIn('Player 4',msg['body'])
        self.assertEqual(next(r['snaps'] for r in data['defense']['rows'] if r['pid']=='1'),1)
        frozen=copy.deepcopy(data); counts['offense']['players']['0']=0; ps[0].name='Changed'
        self.assertEqual(data,frozen)
        league.inbox=[]; league.notes_sent=json.loads(json.dumps(league.notes_sent))
        self.assertIsNone(GR.post_snap_counts(league,'MIN','GB',19,states,True))
        self.assertIsNone(GR.post_snap_counts(league,'MIN','CHI',19,states,True))


class SnapCountSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.saved=Session.new('GB',seed=27).save()

    def check_report(self,s,home,away):
        reports=[m for m in s.L.inbox if m.get('payload',{}).get('snap_counts')]
        self.assertEqual(len(reports),1)
        data=reports[0]['payload']['snap_counts']
        for unit in ('offense','defense'):
            row=data[unit]
            self.assertGreater(row['total'],0)
            self.assertEqual(sum(p['snaps'] for p in row['rows']),11*row['total'])
            self.assertTrue(all(0<=p['snaps']<=row['total'] for p in row['rows']))
        states=s.runner.states
        self.assertEqual(states[home].last_snap_counts['offense']['total'],states[away].last_snap_counts['defense']['total'])
        self.assertEqual(states[away].last_snap_counts['offense']['total'],states[home].last_snap_counts['defense']['total'])
        self.assertEqual(s.inbox_message(reports[0]['id'])['snap_counts'],data)
        for st in (states[home],states[away]):
            combined={}
            for unit in st.last_snap_counts.values():
                for pid,n in unit['players'].items(): combined[pid]=combined.get(pid,0)+n
            self.assertEqual(combined,st.last_snaps)
            self.assertEqual(st.snap_counts,{})
        return data

    def test_simulated_playoff_and_save_reload(self):
        s=Session.load(self.saved); s.runner=SeasonRunner(s.L,s.rng)
        s.runner.play('MIN','GB',19,playoffs=True)
        data=self.check_report(s,'MIN','GB')
        saved=s.save()
        loaded=Session.load(saved)
        self.assertEqual(next(m['payload']['snap_counts'] for m in loaded.L.inbox if m['payload'].get('snap_counts')),data)
        self.assertIsNone(GR.post_snap_counts(loaded.L,'MIN','GB',19,loaded.runner.states,True))

    def test_live_halftime_reload_and_finish_matches_uninterrupted(self):
        s=Session.load(self.saved); s.L.set_phase('regular'); s.L.week=1; s.stop=('week',1); s.played=True
        s.runner=SeasonRunner(s.L,s.rng); s.runner.open_live('GB','MIN',1)
        s.runner.live_step('half')
        self.assertEqual(s.runner.live['at'],'halftime')
        self.assertFalse(any(m.get('payload',{}).get('snap_counts') for m in s.L.inbox))
        saved=s.save()
        halftime=copy.deepcopy(s.runner.states['GB'].snap_counts)
        # Run independently: weather and kickoff buffers are module globals.
        for _ in range(10):
            lv=s.runner.live
            if lv['done']: break
            s.runner.live_step('resume' if lv['halftime_open'] else 'finish')
        self.assertTrue(s.runner.live['done'])
        loaded=Session.load(saved)
        self.assertEqual(halftime,loaded.runner.states['GB'].snap_counts)
        for _ in range(10):
            lv=loaded.runner.live
            if lv['done']: break
            loaded.runner.live_step('resume' if lv['halftime_open'] else 'finish')
        self.assertEqual(self.check_report(s,'GB','MIN'),self.check_report(loaded,'GB','MIN'))
        self.assertEqual(s.rng.bit_generator.state,loaded.rng.bit_generator.state)

    def test_overtime_adds_to_regulation_counts_and_next_game_starts_empty(self):
        import plays
        s=Session.load(self.saved); r=SeasonRunner(s.L,s.rng); s.runner=r
        h,a=r.states['GB'],r.states['MIN']
        for st in (h,a):
            game.field_units(st.roster,st,s.rng,True,'11')
            game.field_units(st.roster,st,s.rng,False,'base')
        before=copy.deepcopy(h.snap_counts)
        _,drives,_=game.play_overtime(h.roster,a.roster,dict(home=24,away=24),s.rng,
            plays.resolve_play,r.co,r.cd,plays.rate,h,a,week=1)
        self.assertTrue(drives)
        self.assertGreater(sum(row['total'] for row in h.snap_counts.values()),2)
        for unit, row in before.items():
            self.assertGreaterEqual(h.snap_counts[unit]['total'],row['total'])
        h.end_game(s.rng); a.end_game(s.rng)
        GR.post_snap_counts(s.L,'GB','MIN',1,r.states)
        self.check_report(s,'GB','MIN')
        previous=copy.deepcopy(h.last_snap_counts)
        game.field_units(h.roster,h,s.rng,True,'11')
        self.assertEqual(h.snap_counts['offense']['total'],1)
        self.assertEqual(h.last_snap_counts,previous)


if __name__=='__main__': unittest.main()
