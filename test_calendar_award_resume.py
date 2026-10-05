"""Public-calendar regressions for cutdown and persisted award effects."""
import copy
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import session as SS
import waivers as WV
import practice_squad as PSQ


class CalendarAwardResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = SS.Session.new('GB', seed=41).save()

    def fresh(self):
        return SS.Session.load(self.baseline)

    def test_later_cutdown_stops_on_wire_and_reload_clears_same_batch(self):
        original = self.fresh()
        original.L.set_phase('free_agency')
        original.L.week = 22
        # The user must make his own cuts before every year's cutdown.
        for p in list(original.L.teams['GB'].active())[53:]:
            original.L.release(p.pid)
        original.stop = ('offseason', len(original.OFFSEASON) - 1)
        original.advance()
        self.assertEqual(original.stop, ('wire',))
        self.assertEqual(original.L.week, 0)
        self.assertTrue(original.L.post_june1())
        self.assertTrue(all(t.phase == 'season' for t in original.L.teams.values()))
        pending = {e['pid'] for e in WV.pending(original.L)}
        self.assertTrue(pending)
        resumed = SS.Session.load(original.save())
        self.assertEqual(resumed.stop, ('wire',))
        self.assertTrue(resumed.L.post_june1())
        self.assertEqual({a:t.cap_space for a,t in original.L.teams.items()},
                         {a:t.cap_space for a,t in resumed.L.teams.items()})
        self.assertEqual(original.next_label(), resumed.next_label())
        self.assertEqual(original.rng.bit_generator.state, resumed.rng.bit_generator.state)

        for s in (original, resumed):
            s.advance()
            self.assertEqual(s.stop, ('week', 1))
            self.assertEqual(s.L.phase, 'regular')
            self.assertEqual(s.L.week, 1)  # health is synced to the displayed decision week
            self.assertFalse(s.L.post_june1())
            self.assertTrue(all(t.cap_space >= -0.01 for t in s.L.teams.values()))
            self.assertFalse(pending & {e['pid'] for e in WV.pending(s.L)})
            self.assertGreater(sum(len(PSQ.squad(t)) for t in s.L.teams.values()), 0)
        self.assertEqual(original.rng.bit_generator.state, resumed.rng.bit_generator.state)
        self.assertEqual(
            {a: [p.pid for p in t.roster] for a, t in original.L.teams.items()},
            {a: [p.pid for p in t.roster] for a, t in resumed.L.teams.items()})
        self.assertEqual(
            {a: [p.pid for p in PSQ.squad(t)] for a, t in original.L.teams.items()},
            {a: [p.pid for p in PSQ.squad(t)] for a, t in resumed.L.teams.items()})
        final = SS.Session.load(resumed.save())
        self.assertEqual((final.stop, final.L.phase), (('week', 1), 'regular'))

    def award_fixture(self):
        s = self.fresh()
        qbs = [p for p in s.L.players.values() if p.pos == 'QB' and p.team][:4]
        for p in qbs:
            p.dev = 'normal'
        s.L.stats[s.L.year] = {
            p.pid: dict(snaps=500, pass_att=300, pass_cmp=200, pass_yds=2400,
                        pass_td=16, pass_int=8) for p in qbs}
        s.votes = {'mvp': qbs[0], 'all_pro_1': [qbs[0]],
                   'all_pro_2': [qbs[1]], 'coty': 'GB'}
        s.L.awards[s.L.year] = {'mvp': qbs[0].pid, 'all_pro_1': [qbs[0].pid],
                               'all_pro_2': [qbs[1].pid], 'coty': 'GB'}
        s.stop = ('offseason', 1)
        s.L.set_phase('offseason')
        s.rng = np.random.default_rng(0)
        return s, qbs[0].pid

    def test_existing_save_restores_player_and_list_awards_without_revoting(self):
        s, pid = self.award_fixture()
        saved = s.save()
        state = copy.deepcopy(s.rng.bit_generator.state)
        with patch.object(SS.AW, 'vote', side_effect=AssertionError('must not revote')):
            loaded = SS.Session.load(saved)
        self.assertIs(loaded.votes['mvp'], loaded.L.player(pid))
        self.assertIs(loaded.votes['all_pro_1'][0], loaded.L.player(pid))
        self.assertEqual(loaded.votes['coty'], 'GB')
        self.assertEqual(state, loaded.rng.bit_generator.state)
        self.assertEqual(s.L.awards, loaded.L.awards)

    def test_development_step_matches_with_and_without_reload(self):
        original, pid = self.award_fixture()
        resumed = SS.Session.load(original.save())
        # Isolate development inside the real offseason step; regression,
        # retirement and Hall voting have their own tests and RNG draws.
        with patch.object(SS.RG, 'run'), patch.object(SS.RT, 'run'), \
                patch.object(SS.AL, 'hall_vote'), patch('league_notes.season_end'):
            original.step_retire()
            resumed.step_retire()
        self.assertEqual(original.L.player(pid).dev, 'star')
        self.assertEqual(resumed.L.player(pid).dev, 'star')
        self.assertEqual(
            {p.pid: p.dev for p in original.L.players.values()},
            {p.pid: p.dev for p in resumed.L.players.values()})
        self.assertEqual(original.rng.bit_generator.state, resumed.rng.bit_generator.state)
        self.assertEqual(
            [x for x in original.L.transactions if x['kind'] == 'dev_trait'],
            [x for x in resumed.L.transactions if x['kind'] == 'dev_trait'])

    def test_does_not_restore_last_year_awards_into_new_season(self):
        s, pid = self.award_fixture()
        s.L.awards = {s.L.year - 1: {'mvp': pid}}
        self.assertIsNone(SS.Session.load(s.save()).votes)

    def test_missing_legacy_winner_does_not_break_loading(self):
        s, pid = self.award_fixture()
        s.L.awards[s.L.year]['all_pro_1'].append('removed-player')
        s.L.awards[s.L.year]['sb_mvp'] = 'removed-player'
        loaded = SS.Session.load(s.save())
        self.assertEqual([p.pid for p in loaded.votes['all_pro_1']], [pid])
        self.assertIsNone(loaded.votes['sb_mvp'])

    def test_announced_honors_survive_reload_and_are_not_paid_twice(self):
        s = self.fresh()
        p = next(p for p in s.L.teams['GB'].active() if p.pos == 'QB')
        def vote(league, post=None):
            self.assertIsNone(post)
            league.awards[league.year] = {'mvp': p.pid}
            return {'mvp': p, 'coty': 'GB'}
        with patch.object(SS.AW, 'vote', side_effect=vote), patch.object(SS.XP, 'pay_awards'), \
                patch.object(SS.IB, 'post') as letter:
            s._announce_honors()
        self.assertIn(s.L.year, s.L.awards)
        letter.assert_called_once()
        s = SS.Session.load(s.save())
        s.post = SimpleNamespace(champion=None)
        self.assertEqual(s.votes['mvp'].pid, p.pid)
        with patch.object(SS.AW, 'vote', side_effect=AssertionError('regular honors must not be revoted')), \
                patch.object(SS.AW, 'championship_game_mvp', return_value=None), \
                patch.object(SS.MO, 'ensure') as morale, patch.object(SS.RG, 'tick_ages'), \
                patch.object(SS.XP, 'pay_awards'), patch.object(SS.XP, 'close_season'), \
                patch.object(SS.CP, 'season_prestige'), patch.object(SS.STF, 'unit_ranks', return_value={}), \
                patch.object(SS.STF, 'season_end'), patch.object(SS.AL, 'close_season'), \
                patch('views_league.awards', return_value={}), patch('club_notes.season_end'), \
                patch('league_notes.season_end'):
            s.step_awards()
        morale.assert_not_called()

    def test_old_championship_week_save_gets_honors_on_load(self):
        saved = json.loads(self.baseline)
        saved['_stop'] = ['playoffs', 3]
        saved['_post_live'] = dict(games=[], champion=None, finalists={}, exit_round={},
                                   seeds={}, alive={}, conf_champs={'Continental': 'GB', 'United': 'KC'})
        session = SS.Session.load(json.dumps(saved))
        self.assertIn(session.L.year, session.L.awards)
        letters = [m for m in session.L.inbox if m.get('subject') == "The season's honors"]
        self.assertEqual(len(letters), 1)
        again = SS.Session.load(session.save())
        self.assertEqual(again.L.awards, session.L.awards)
        self.assertEqual(len([m for m in again.L.inbox if m.get('subject') == "The season's honors"]), 1)

    def test_old_final_after_rollover_does_not_create_new_season_honors_or_metadata(self):
        for announced in (False, True):
            with self.subTest(announced=announced):
                saved=json.loads(self.baseline);year=saved['year']
                pid=next(pid for pid,p in saved['players'].items() if p['pos']=='QB' and p['team']=='GB')
                saved.update(year=year+1,phase='offseason',_stop=['offseason',2],
                    _offseason_progress=dict(year=year,development_done=True,roll_done=True,coaching_done=True),
                    _post=dict(year=year,champion='GB',finalists={},seeds={},
                               games=[['SB','', 'GB','KC',28,21]]))
                saved['history']={str(year):dict(championship_announced=announced)}
                saved['awards']={str(year):dict(sb_mvp=pid)}
                with patch.object(SS.XP,'pay_awards') as pay,patch.object(SS.IB,'post') as announce:
                    loaded=SS.Session.load(json.dumps(saved))
                    again=SS.Session.load(loaded.save())
                pay.assert_not_called()
                self.assertFalse(any('Championship' in call.args[2]
                                     for call in announce.call_args_list))
                self.assertEqual(again.post.year,year)
                self.assertNotIn(str(year+1),again.L.history)
                self.assertNotIn(year+1,again.L.awards)
                self.assertEqual(again.L.history[str(year)],saved['history'][str(year)])
                self.assertEqual(again.L.awards[year]['sb_mvp'],pid)


if __name__ == '__main__':
    unittest.main()
