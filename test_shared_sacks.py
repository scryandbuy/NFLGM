"""Joint finishes share one sack, survive storage, and disappear on escapes."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G
import plays as P
import rush_matchup as R
import league as LG
import ticker, gameday, almanac


class SharedSacks(unittest.TestCase):
    def test_near_arrival_shares_but_late_pressure_is_not_an_assist(self):
        self.assertEqual(R.sack_credits('a',[('a',1.5),('b',1.58),('c',1.59)]), [('a',.5),('b',.5)])
        self.assertEqual(R.sack_credits('a',[('a',1.5),('b',1.7)]), [('a',1.)])
        self.assertEqual(R.sack_credits('a',[]), [('a',1.)])
        self.assertEqual(R.sack_credits('a',[('a',1.5),('a',1.51)]), [('a',1.)])
        self.assertEqual(R.sack_credits('b',[('a',1.5),('b',1.5)]), [('b',.5),('a',.5)])

    def line(self, **kw):
        return dict(type='sack',yards=-5,by='a',beaten='lt',
                    sack_credits=[('a',.5),('b',.5)],rush_pressures=['a','b'],**kw)

    def book(self,out):
        book=G.StatBook()
        book.record(out,dict(qb=dict(pid='qb')),dict(dl=[dict(pid='a')],lb=[dict(pid='b')]),np.random.default_rng(1))
        return book

    def test_book_conserves_sack_and_primary_block_failure(self):
        book=self.book(self.line())
        self.assertEqual(book.p['qb']['sacked'],1)
        self.assertEqual(book.p['a']['sacks'],.5);self.assertEqual(book.p['b']['sacks'],.5)
        self.assertEqual(sum(p['sacks'] for p in book.p.values()),1.)
        self.assertEqual(book.p['lt']['sacks_allowed'],1)
        self.assertEqual(book.p['a']['pressures'],1);self.assertEqual(book.p['b']['pressures'],1)
        self.assertEqual(book.p['a']['tackles'],1);self.assertEqual(book.p['b']['tackles'],1)
        solo=self.book(dict(type='sack',yards=-3,by='a'))
        self.assertEqual(solo.p['a']['sacks'],1.)

    def test_duplicate_and_malformed_credit_never_creates_or_loses_sacks(self):
        out=self.line();out['sack_credits']=[('a',.5),('a',.5),('b',.5),('c',.5)]
        book=self.book(out)
        self.assertEqual(sum(p['sacks'] for p in book.p.values()),1.)
        self.assertEqual(book.p['a']['sacks'],.5);self.assertEqual(book.p['b']['sacks'],.5)
        self.assertNotIn('c',book.p)
        self.assertEqual(self.book(self.line(nullified=True)).p,{})

    def test_live_resolver_emits_shared_credit_and_both_pressures(self):
        from test_fourth_down_routes import FourthDownRoutes
        FourthDownRoutes.setUpClass();fixture=FourthDownRoutes()
        original=P.resolve_protection
        def close(*args,**kw):
            out=original(*args,**kw)
            ids=[p['pid'] for p in args[1]]
            out.update(time=1.5,beaten_by=ids[0],rush_arrivals=[(pid,1.5+.07*i) for i,pid in enumerate(ids)])
            return out
        with patch.object(P,'resolve_protection',side_effect=close):
            sacks=[p for seed in range(20) if (p:=fixture.play(seed,down=2))['type']=='sack']
        self.assertTrue(sacks)
        for out in sacks:
            self.assertEqual(len(out['sack_credits']),2)
            self.assertEqual(out['by'],out['sack_credits'][0][0])
            self.assertEqual(sum(c for _,c in out['sack_credits']),1.)
            self.assertTrue({p for p,c in out['sack_credits']} <= set(out['rush_pressures']))

    def test_escape_removes_all_sack_shares_but_preserves_pressure(self):
        import events
        from test_game_clock_decisions import ClockDecisions
        f=ClockDecisions();f.setUp()
        out=self.line()
        with patch.object(events,'scramble_chance',return_value=1.), \
             patch.object(events,'resolve_scramble',return_value=dict(type='scramble',yards=36,touchdown=True)):
            dr,book,_=f.drive([out])
        self.assertEqual(sum(p['sacks'] for p in book.p.values()),0.)
        self.assertEqual(book.p['qb']['sacked'],0)
        self.assertEqual(book.p['a']['pressures'],1);self.assertEqual(book.p['b']['pressures'],1)
        scramble=next(p for p in dr.log if p.get('type')=='scramble')
        self.assertNotIn('sack_credits',scramble)

    def test_fractional_book_career_and_game_history_survive_reload(self):
        league=LG.League(2029);book=self.book(self.line())
        for pid in ('a','b'):
            league.players[pid]=LG.Player(pid,'Player '+pid,'REDG',25,{},team='GB')
            league.record_stats(2029,pid,book.p[pid],game='2029-1-GB-DAL')
        restored=LG.League.load(league.save())
        for pid in ('a','b'):
            for row in (restored.stats[2029][pid],restored.game_stats['2029-1-GB-DAL'][pid],restored.players[pid].career[2029]):
                self.assertEqual(row['sacks'],.5)
        self.assertEqual(sum(r['sacks'] for r in restored.stats[2029].values()),1.)

    def test_ticker_compact_gameday_and_hall_of_fame_keep_both_halves(self):
        league=NS(player=lambda pid:NS(name={'a':'First Rusher','b':'Second Defender','qb':'The Quarterback','lt':'Left Tackle'}[pid]))
        out=self.line();out['passer']='qb'
        text=ticker.play_line(league,out,'GB','DAL')['text']
        self.assertIn('share a sack',text);self.assertIn('Rusher',text);self.assertIn('Defender',text)
        saved=gameday.write_play(league,out,'qb','GB','DAL')
        self.assertEqual(saved['sack_credits'],[('a',.5),('b',.5)])
        self.assertEqual(saved['sacker'],'a')
        why=almanac._why(None,NS(career={2029:dict(sacks=100.5)}),dict(honours=0,titles=0,seasons=10))
        self.assertIn('100.5 sacks',why)


if __name__=='__main__':unittest.main()
