"""Combined rollover/carousel, save migration, and outgoing-season evidence."""
import copy
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np
import offseason_calendar as OC
import player_age as PA
import session as SS
import postseason as PS
import staff as ST


class CalendarMapping(unittest.TestCase):
    def test_every_legacy_stop_maps_without_replaying_completed_work(self):
        for old in range(15):
            year = 2028 if old <= 3 else 2029
            saved = dict(year=year, _stop=['offseason', old])
            stop, progress = OC.saved_progress(saved)
            self.assertEqual(stop, ('offseason', 1 if old <= 3 else 2 if old == 4 else old - 2))
            self.assertEqual(progress['year'], 2028)
            self.assertEqual(progress['development_done'], old >= 3)
            self.assertEqual(progress['coaching_done'], old >= 2)
            self.assertEqual(progress['roll_done'], old >= 4)
            updated = dict(saved, _stop=stop, _offseason_calendar_version=OC.VERSION,
                           _offseason_progress=progress)
            self.assertEqual(OC.saved_progress(updated), (stop, progress))

    def test_visible_order_and_birthday_dates(self):
        names = [fn for _, fn in SS.Session.OFFSEASON]
        self.assertEqual(names[:4], ['step_awards', 'step_development_roll', 'step_coaching', 'step_extensions'])
        self.assertNotIn('step_roll', names)
        self.assertNotIn('step_staff_contracts', names)
        dates = [PA.stop_date(2028 if i < 2 else 2029, ('offseason', i), calendar_version=OC.VERSION)
                 for i in range(len(names))]
        self.assertEqual(dates, sorted(set(dates)))
        self.assertEqual(str(dates[1]), '2029-02-25')
        self.assertEqual(str(dates[2]), '2029-03-11')
        self.assertEqual(str(dates[3]), '2029-03-12')
        self.assertEqual(str(dates[-1]), '2029-08-25')

    def test_old_new_year_save_only_rolls_and_retry_is_safe(self):
        s = SS.Session.__new__(SS.Session)
        s.L = NS(year=2028, teams={})
        s.stop, s.offseason_progress = OC.saved_progress(dict(year=2028, _stop=['offseason', 3]))
        def roll(): s.L.year += 1
        with patch.object(s, 'step_awards') as awards, patch.object(s, 'step_retire') as retire, \
                patch.object(s, 'step_roll', side_effect=roll) as rollover, patch.object(PA, 'offseason'):
            s.step_development_roll()
            s.step_development_roll()
        awards.assert_not_called(); retire.assert_not_called(); rollover.assert_called_once()
        self.assertEqual(s.L.year, 2029)

    def test_firings_receive_completed_season_history_and_worst_record_first(self):
        teams = {a: NS(gm=NS(), record=[0,0,0], win_pct=.5, roster_strength=lambda: 75,
                       starter=lambda pos: None, hist=lambda: {'win_pct': .5}, tenure=1)
                 for a in ('Winner', 'Loser')}
        L = NS(year=2029, teams=teams, user_team=None)
        context = dict(records={'Winner':[14,3,0], 'Loser':[3,14,0]},
                       histories={'Winner':{'win_pct':.82},'Loser':{'win_pct':.18}})
        observed=[]
        with patch.object(PS.FM, 'fire_chance_offseason', side_effect=lambda hist,*_: observed.append(hist) or 0):
            PS.run_firings(L, np.random.default_rng(4), season_year=2028, context=context)
        self.assertEqual(observed, [{'win_pct':.18},{'win_pct':.82}])
        self.assertEqual(L._firings_rolled, {'2028':['Loser','Winner']})

    def test_interrupted_rollover_retries_without_advancing_year_or_contracts_twice(self):
        s=SS.Session.__new__(SS.Session)
        s.L=NS(year=2028,teams={},players={},game_date='2029-02-25',phase='offseason',week=22)
        s.stop=('offseason',1);s.offseason_progress={'year':2028};s.standings={};s.rng=None
        def roll(rng):
            s.L.year+=1
            PA.offseason(s.L,4)
        with patch.object(s,'step_awards') as awards,patch.object(s,'step_retire') as retire,patch.object(s,'_offseason_trade_pass') as trades, \
                patch.object(s.L,'roll_year',side_effect=roll,create=True) as years, \
                patch.object(s.L,'advance_contracts',create=True) as contracts, \
                patch('negotiations.check_promises'),patch.object(SS.SCH,'division_ranks'), \
                patch.object(SS.SCH,'new_season',side_effect=[RuntimeError('schedule interrupted'),None]) as schedule, \
                patch.object(SS.CT,'run',side_effect=[RuntimeError('cleanup interrupted'),None]),patch.object(SS.CT,'enforce'):
            for failure in ('schedule interrupted','cleanup interrupted'):
                with self.assertRaisesRegex(RuntimeError,failure): s.step_development_roll()
                s.offseason_progress=json.loads(json.dumps(s.offseason_progress))
                PA.sync_session(s)
                self.assertEqual(s.L.game_date,'2029-03-11')
            s.step_development_roll();s.step_development_roll()
        years.assert_called_once();contracts.assert_called_once();awards.assert_called_once();retire.assert_called_once()
        trades.assert_called_once()
        self.assertEqual(schedule.call_count,2)
        self.assertEqual(s.L.year,2029)


class CalendarResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = SS.Session.new('GB', seed=47).save()

    def fresh(self):
        s = SS.Session.load(self.baseline)
        s.L.set_phase('offseason');s.L.waivers=[]
        return s

    def test_actual_rollover_and_carousel_then_user_renewals_and_reload(self):
        s = self.fresh(); year=s.L.year
        s.stop=('offseason',1); s.offseason_progress={'year':year}
        s.standings={a:dict(w=10,l=7,t=0,pct=10/17,div=t.division,div_rank=1,pf=350,pa=320)
                     for a,t in s.L.teams.items()}
        divisions={}
        for a,t in sorted(s.L.teams.items()):
            divisions[t.division]=divisions.get(t.division,0)+1
            s.standings[a]['div_rank']=divisions[t.division]
        for t in s.L.teams.values(): t.record=[10,7,0]
        c=s.L.teams['GB'].staff['scout'];c.years=0
        c.hc_candidate=False;c.disgruntled=0
        s.L.teams['GB'].cap.cap += 200  # isolate calendar from the user's cap choices
        p=next(p for p in s.L.teams['GB'].roster if p.contract and p.contract.years >= 3)
        old_contract=p.contract.years;old_accrued=p.accrued
        old_staff_years={r:c.years for r,c in s.L.teams['GB'].staff.items() if c}
        # Annual evidence/development have separate tests; run actual cap,
        # schedule, player-contract and all 32 teams' coaching transitions here.
        with patch.object(s,'step_awards') as awards, patch.object(s,'step_retire') as retire, patch.object(SS.TRD,'run') as trades:
            result=s.advance()
        self.assertNotEqual(result['done'],'Blocked')
        awards.assert_called_once();retire.assert_called_once()
        self.assertEqual(trades.call_count,3)  # retirement, rollover, carousel-opening market passes
        self.assertEqual(s.L.year,year+1)
        self.assertEqual(s.stop,('offseason',2))
        self.assertEqual((p.contract.years,p.accrued),(old_contract-1,old_accrued+1))
        self.assertEqual(s.L.game_date,f'{year+1}-03-11')
        self.assertTrue(all(t.record==[0,0,0] for t in s.L.teams.values()))
        self.assertEqual(s.offseason_progress['coaching_context']['records']['GB'],[10,7,0])
        self.assertTrue(s.offseason_progress['coaching_done'])
        self.assertTrue(s.frontoffice('staff')['renewal_step'])
        self.assertEqual(s.next_label()['title'],'Coaching Carousel')
        self.assertEqual(s.advance()['done'],'Blocked')
        self.assertEqual(s.L.teams['GB'].staff['scout'].years,0)
        s.L.teams['GB'].gm.salary = 1  # leave owner-budget room for the test renewal
        self.assertTrue(s.frontoffice_act('staff_extend',role='scout',years=3,salary=ST.ask(c))['ok'])
        # Settle any other expirations without silently renewing/releasing them.
        for role in ST.unresolved_expirations(s.L,'GB'): ST.choose_expiry(s.L,'GB',role)
        rng=copy.deepcopy(s.rng.bit_generator.state)
        loaded=SS.Session.load(s.save())
        self.assertEqual(loaded.offseason_progress,s.offseason_progress)
        with patch.object(loaded,'_black_monday',side_effect=AssertionError('carousel repeated')), \
                patch.object(SS.TRD,'run'),patch.object(loaded,'step_extensions') as extensions:
            loaded._open_fa_if_due()
            loaded._open_fa_if_due()
            loaded.advance()
        extensions.assert_not_called()
        self.assertEqual(loaded.stop,('offseason',3))
        self.assertEqual(loaded.L.year,year+1)
        self.assertEqual(loaded.L.player(p.pid).accrued,old_accrued+1)
        self.assertEqual(loaded.L.teams['GB'].staff['scout'].years,3)

    def test_all_legacy_saves_load_twice_without_simulating(self):
        base=json.loads(self.baseline)
        for old in range(15):
            with self.subTest(old=old):
                d=copy.deepcopy(base)
                d.pop('_offseason_calendar_version',None);d.pop('_offseason_progress',None)
                d.update(_stop=['offseason',old],phase='offseason',week=22)
                if old>=4: d['year']+=1
                first=SS.Session.load(json.dumps(d));again=SS.Session.load(first.save())
                self.assertEqual(first.stop,again.stop)
                self.assertEqual(first.L.year,again.L.year)
                self.assertEqual(first.L.game_date,again.L.game_date)
                self.assertEqual(first.rng.bit_generator.state,again.rng.bit_generator.state)
                self.assertEqual(first.offseason_progress,again.offseason_progress)
                self.assertEqual(first.L.players[next(iter(first.L.players))].accrued,
                                 again.L.players[next(iter(again.L.players))].accrued)

    def test_cpu_staff_decisions_keep_record_effect_after_reset(self):
        before=self.fresh();after=self.fresh()
        records={}
        for i,a in enumerate(before.L.teams):
            records[a]=[i%15,17-i%15,0]
            before.L.teams[a].record=records[a]
            after.L.teams[a].record=[0,0,0]
            for L in (before.L,after.L):
                for c in L.teams[a].staff.values():
                    if c: c.years=0
        ST.carousel(before.L,before.rng)
        ST.carousel(after.L,after.rng,season_records=records)
        self.assertEqual(ST.to_dict(before.L),ST.to_dict(after.L))
        self.assertEqual(before.rng.bit_generator.state,after.rng.bit_generator.state)

    def test_old_postseason_year_stays_closed_on_both_sides_of_rollover(self):
        base=json.loads(self.baseline);closed=base['year']
        for old in (3,4):
            d=copy.deepcopy(base)
            d.pop('_offseason_calendar_version',None);d.pop('_offseason_progress',None)
            d.update(_stop=['offseason',old],phase='offseason',week=22,year=closed+(old==4),
                     _post=dict(champion='GB',year=closed+1,finalists={},games=[],seeds={}))
            with patch.object(SS.AW,'announce_championship'):
                s=SS.Session.load(json.dumps(d));again=SS.Session.load(s.save())
            self.assertEqual(s.post.year,closed)
            self.assertEqual(again.post.year,closed)
            self.assertEqual(again.L.season_closed_year,closed)


if __name__=='__main__': unittest.main()
