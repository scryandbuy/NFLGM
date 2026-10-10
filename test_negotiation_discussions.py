import copy
import unittest
from unittest.mock import patch
from test_cap_accounting import fixture, player
from cap_engine import Contract
from league import League, DraftPick
from gm_engine import GM
import negotiation_discussions as ND
import negotiation_engine as NE
import negotiations as NG
import contract_offer as CO
import views_personnel as VP
import trades as TR


class DiscussionTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.user_team = 'GB'; self.L.set_phase('offseason')
        for team in self.L.teams.values(): team.gm = GM()
        self.p = player(self.L, 'negotiator', contract=Contract(1, [10]))
        self.other = player(self.L, 'target', 'MIN', Contract(3, [8, 8, 8]))
        self.t = dict(id=1, pid=self.p.pid, team='GB', kind='extension', state='open',
                      offers=[], ask=22, years=3, patience=3, due=None, counter=None,
                      rival=None, discount=0., mood='open', opened=100, opened_year=2026)
        self.L.negotiations = [self.t]
        self.profile('balanced')
        for abbr in ('GB', 'MIN'):
            self.L.teams[abbr].picks.append(DraftPick(2027, 2, abbr, abbr))

    def profile(self, kind):
        self.p.xp_spent['_negotiation_profile'] = dict(archetype=kind, w=NE.ARCHETYPES[kind].copy(), trust=1., broken=0)

    def reply(self, key):
        result = VP.act_player_discuss(self.L, 'GB', 1, key)
        self.assertTrue(result['ok'], result)

    def start_trade(self, target='target', direction='acquire'):
        r = ND.start_trade(self.L, 'GB', 'MIN', target, direction)
        self.assertTrue(r['ok'], r)

    def trade_reply(self, key):
        r = ND.trade_reply(self.L, 'GB', 'MIN', key)
        self.assertTrue(r['ok'], r)

    def test_player_conversation_never_submits_or_reserves(self):
        before = self.L.teams['GB'].cap_space
        view = VP._thread(self.L, self.t)
        self.assertEqual(view['discussion']['stage'], 'talk')
        self.assertIsNone(view['counter']); self.assertIsNone(view['starting_offer'])
        self.assertFalse(NG.make_offer(self.L, 1, 22, 3)['ok'])
        self.reply('home'); self.reply('price'); self.reply('finish')
        self.assertEqual(self.t['offers'], [])
        self.assertEqual(self.L.teams['GB'].cap_space, before)
        self.assertFalse(getattr(self.L, 'promises', []))
        self.assertFalse(NG.make_offer(self.L, 1, 22, 3)['ok'])
        self.reply('proposal')
        self.assertEqual(ND.starting_offer(self.L, self.t)['promises'], ['no_trade'])

    def test_price_disclosure_replaces_staff_estimate_and_range_refines_it(self):
        with patch('valuation.value_player', return_value=dict(apy=18)):
            self.assertEqual(ND.starting_offer(self.L, self.t)['apy'], 18)
            self.reply('price')
            self.assertEqual(ND.starting_offer(self.L, self.t)['apy'], 21.34)
            del self.t['discussion']; self.profile('max_money')
            self.reply('price')
            self.assertEqual(ND.starting_offer(self.L, self.t)['apy'], 22)

    def test_commitments_and_personalities_survive_reload_without_click_farming(self):
        self.profile('homebody'); self.reply('home'); self.reply('security')
        self.assertFalse(ND.player_reply(self.L, self.t, 'home')['ok'])
        loaded = League.load(self.L.save()); t = NG.find(loaded, 1)
        self.assertEqual(t['discussion'], self.t['discussion'])
        offer = ND.starting_offer(loaded, t)
        self.assertEqual(offer['front_load'], .85); self.assertEqual(offer['promises'], ['no_trade'])
        self.assertEqual(CO.profile_for(loaded.player(self.p.pid))['archetype'], 'homebody')

    def test_existing_pending_and_countered_threads_skip_opening(self):
        for state in ('waiting', 'countered', 'match_requested'):
            self.t.pop('discussion', None); self.t['state'] = state
            self.assertEqual(ND.player_view(self.L, self.t)['stage'], 'proposal')

    def test_regular_season_immediate_signing_follows_conversation(self):
        self.L.set_phase('regular'); self.L.week = 6
        self.L.teams['GB'].roster.remove(self.p)
        self.p.team = None; self.p.contract = None; self.L.free_agents.append(self.p.pid)
        self.t.update(kind='fa_inseason', ask=4, years=1)
        ND.player_view(self.L, self.t)
        quote = NG.sign_today_offer(self.L, self.t)
        args = {k: quote[k] for k in ('apy', 'years', 'bonus', 'front_load', 'promises')}
        self.assertFalse(NG.make_offer(self.L, 1, **args, sign_today=True)['ok'])
        self.reply('home')
        self.reply('finish'); self.reply('proposal')
        quote = NG.sign_today_offer(self.L, self.t)
        args = {k: quote[k] for k in ('apy', 'years', 'bonus', 'front_load', 'promises')}
        r = NG.make_offer(self.L, 1, **args, sign_today=True)
        self.assertTrue(r['ok'], r); self.assertEqual(r['state'], 'accepted')
        self.assertEqual(self.p.team, 'GB'); self.assertEqual(self.L.week, 6)
        self.assertIsNone(self.t['due'])
        self.assertEqual(self.L.promises[0]['kind'], 'no_trade')

    def test_immediate_signing_still_respects_competing_offer(self):
        self.L.set_phase('regular'); self.L.week = 6
        self.L.teams['GB'].roster.remove(self.p)
        self.p.team = None; self.p.contract = None; self.L.free_agents.append(self.p.pid)
        self.t.update(kind='fa_inseason', ask=4, years=1, rival=dict(team='MIN', apy=5, years=1))
        self.reply('finish'); self.reply('proposal')
        quote = NG.sign_today_offer(self.L, self.t)
        r = NG.make_offer(self.L, 1, **{k: quote[k] for k in ('apy', 'years', 'bonus', 'front_load', 'promises')}, sign_today=True)
        self.assertFalse(r['ok']); self.assertIn('Another team', r['why'])
        self.assertEqual(self.t['offers'], []); self.assertIsNone(self.p.team)

    def test_first_counter_allows_revision_second_can_be_final(self):
        self.profile('max_money')
        offer = CO.canonical(self.L, self.p, self.L.teams['GB'], dict(apy=18, years=3, front_load=.5), 'extension')
        NG._answer(self.L, self.t, self.p, offer, 22, quiet=True)
        self.assertFalse(self.t['final_offer'])
        counter = dict(self.t['counter']); counter['apy'] *= .97
        r = NG.make_offer(self.L, 1, counter['apy'], counter['years'], bonus=counter['bonus'], front_load=counter['front_load'], promises=counter['promises'])
        self.assertTrue(r['ok'], r); self.assertEqual(self.t['state'], 'countered')
        self.assertTrue(self.t['final_offer'])
        before = copy.deepcopy(self.t)
        self.assertFalse(NG.make_offer(self.L, 1, self.t['counter']['apy'] * .99, 3)['ok'])
        self.assertEqual(self.t, before)
        self.assertTrue(VP.act_match_counter(self.L, 'GB', 1)['ok'])
        self.assertEqual(self.t['state'], 'accepted')

    def test_promise_has_personal_value_and_duplicates_do_not_stack(self):
        plain = dict(apy=22, years=3, promises=['no_trade'])
        self.profile('homebody'); home = NG._assessment(self.L, self.p, self.t, plain)['ratio']
        duplicate = NG._assessment(self.L, self.p, self.t, dict(plain, promises=['no_trade', 'no_trade']))['ratio']
        self.assertAlmostEqual(home, duplicate)
        self.profile('max_money'); money = NG._assessment(self.L, self.p, self.t, plain)['ratio']
        # Compare the same personality with and without the commitment, since
        # cash preferences also differ between these two players.
        money0 = NG._assessment(self.L, self.p, self.t, dict(plain, promises=[]))['ratio']
        self.profile('homebody'); home0 = NG._assessment(self.L, self.p, self.t, dict(plain, promises=[]))['ratio']
        self.assertGreater(home / home0, money / money0)

    def test_walking_from_final_offer_does_not_reset_the_negotiating_window(self):
        self.t.update(state='countered', final_offer=True, counter=dict(apy=22, years=3))
        self.assertTrue(NG.withdraw(self.L, 1)['ok'])
        r = NG.open_talks(self.L, self.p.pid, 'extension')
        self.assertFalse(r['ok']); self.assertIn('ended these talks', r['why'])

    def test_trade_shortcut_appears_after_availability_and_preserves_no_insights(self):
        self.assertEqual(ND.trade_view(self.L, 'GB', 'MIN')['choices'], [])
        self.start_trade()
        self.assertIn('finish', [x['key'] for x in ND.trade_view(self.L, 'GB', 'MIN')['choices']])
        self.assertFalse(VP.act_propose(self.L, 'GB', 'MIN', [], ['target'])['ok'])
        self.trade_reply('finish'); self.trade_reply('proposal')
        d = ND.trade_state(self.L, 'GB', 'MIN')
        self.assertFalse(d.get('needs_known')); self.assertFalse(d['concession'])
        self.assertEqual(self.other.team, 'MIN')

    def test_gm_concession_is_conditional_targeted_saved_and_not_repeatable(self):
        self.L.teams['MIN'].gm.patience = .9
        self.start_trade(); self.trade_reply('picks')
        self.assertFalse(ND.trade_reply(self.L, 'GB', 'MIN', 'picks')['ok'])
        self.trade_reply('finish'); self.trade_reply('proposal')
        base = TR.persona(self.L.teams['MIN'].gm)['own_bias']
        self.assertEqual(ND.trade_persona(self.L, 'GB', 'MIN', [], ['target'])['own_bias'], base)
        better = ND.trade_persona(self.L, 'GB', 'MIN', ['2027-2-GB'], ['target'])['own_bias']
        self.assertLess(better, base)
        self.assertEqual(ND.trade_persona(self.L, 'GB', 'MIN', ['2027-2-GB'], ['2027-2-MIN'])['own_bias'], base)
        loaded = League.load(self.L.save())
        self.assertEqual(ND.trade_persona(loaded, 'GB', 'MIN', ['2027-2-GB'], ['target'])['own_bias'], better)
        self.start_trade('2027-2-MIN'); self.trade_reply('picks')
        self.assertFalse(ND.trade_state(self.L, 'GB', 'MIN')['concession'])

    def test_different_gm_can_reject_pitch_or_end_call(self):
        gm = self.L.teams['MIN'].gm; gm.patience = .2
        with patch('trade_engine.window', return_value='contending'):
            self.start_trade(); self.trade_reply('picks')
            self.assertFalse(ND.trade_state(self.L, 'GB', 'MIN')['concession'])
        self.trade_reply('pressure')
        self.assertEqual(ND.trade_state(self.L, 'GB', 'MIN')['stage'], 'closed')
        self.assertFalse(ND.start_trade(self.L, 'GB', 'MIN', '2027-2-MIN', 'acquire')['ok'])

    def test_no_trade_commitment_refuses_that_player_not_every_asset(self):
        NG.record_promise(self.L, 'target', 'MIN', 'no_trade')
        self.start_trade()
        self.assertEqual(ND.trade_state(self.L, 'GB', 'MIN')['stage'], 'unavailable')
        self.start_trade('2027-2-MIN')
        self.assertEqual(ND.trade_state(self.L, 'GB', 'MIN')['stage'], 'talk')
        self.assertIsNotNone(ND.trade_refusal(self.L, 'GB', 'MIN', ['target']))
        self.assertIsNone(ND.trade_refusal(self.L, 'GB', 'MIN', ['2027-2-MIN']))
        self.assertFalse(VP.act_ask(self.L, 'GB', 'MIN', ['2027-2-GB'], ['target'])['ok'])

    def test_core_status_does_not_become_blanket_veto(self):
        with patch('trades.seller_willingness', return_value=dict(seller_status='core')):
            self.start_trade()
        self.assertEqual(ND.trade_state(self.L, 'GB', 'MIN')['stage'], 'talk')

    def test_full_assets_ownership_and_calendar_are_rechecked(self):
        self.assertFalse(ND.start_trade(self.L, 'GB', 'MIN', 'negotiator', 'acquire')['ok'])
        self.start_trade('negotiator', 'offer')
        self.L.teams['MIN'].picks.append(DraftPick(2030, 7, 'GB', 'MIN'))
        self.start_trade(dict(kind='pick', id='2030-7-GB'))
        self.assertEqual(ND.trade_state(self.L, 'GB', 'MIN')['topic'], '2030-7-GB')
        self.L.year += 1
        self.assertIsNone(ND.trade_state(self.L, 'GB', 'MIN'))


if __name__ == '__main__': unittest.main()
