"""Focused regressions for inbox entity state, references, waivers, and offer sheets."""
import copy
import json
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import inbox as IB
import staff as ST
import market as MK
import waivers as WV
import injury_status as IS
import valuation as VAL
import practice_squad as PSQ
from cap_engine import Contract
from league import League, Team, Player


def league(**kw):
    fields = dict(year=2026, week=1, phase='regular', inbox=[], teams={}, players={}, user_team='GB',
                  transactions=[], log=lambda *a, **k: None)
    fields.update(kw)
    L = N(**fields)
    L.player = lambda pid: L.players.get(pid)
    return L


def sheet(holder='GB', **kw):
    d = dict(kind='offer_sheet', team=holder, suitor='MIN' if holder == 'GB' else 'GB',
             pid='p', subject='Offer sheet: Player', offer=5, years=2)
    d.update(kw)
    return d


class DecisionLifecycleTests(unittest.TestCase):
    def test_answered_poach_closes_and_failed_persuasion_stays_open(self):
        for action in ('block', 'let_go', 'persuade'):
            c = ST.Coach('Coach', 'oc', 70, 50, 'Balanced', 45, team='GB')
            L = league(teams={'GB': N(abbr='GB', staff={'oc': c}), 'MIN': N(abbr='MIN')})
            request = ST.poach_request(L, c, 'MIN')
            rng = N(random=lambda: .999)
            ST.answer_poach(L, request['id'], action, rng=rng)
            self.assertEqual(IB.is_decision(L.inbox[0]), action == 'persuade')
            if action != 'persuade': self.assertEqual(L.inbox[0]['status'], 'done')

    def test_legacy_poach_reconciliation(self):
        L = league(poaches=[dict(id=1, state='blocked')])
        m = IB.post(L, 'staff', 'Request', '', payload={'poach': 1})
        IB.reconcile(L)
        self.assertEqual(m['status'], 'done')
        self.assertEqual(IB.reconcile(L), 0)

    def test_staff_reports_are_information_and_vacancy_resolves_on_hire(self):
        L = league(teams={'GB': N(staff={'oc': None})})
        retire = IB.post(L, 'staff', 'Coach is retiring', '', payload={'role': 'oc'})
        reference = IB.post(L, 'staff', 'References on Coach', '')
        vacancy = IB.post(L, 'staff', 'You need a coordinator', '', payload={'role': 'oc'})
        IB.reconcile(L)
        self.assertFalse(IB.is_decision(retire)); self.assertFalse(IB.is_decision(reference))
        self.assertEqual(retire['status'], 'unread')
        self.assertTrue(IB.is_decision(vacancy))
        L.teams['GB'].staff['oc'] = N(name='New Coach', years=3)
        IB.reconcile(L)
        self.assertEqual(vacancy['status'], 'done')

    def test_expired_staff_notice_resolves_after_release(self):
        L = league(teams={'GB': N(staff={'oc': None})})
        m = IB.post(L, 'staff', "Coach's contract is up", '', payload={'role': 'oc'})
        IB.reconcile(L)
        self.assertEqual(m['status'], 'done')

    def test_final_year_extended_and_exit_batch_answered(self):
        p = N(pid='p', name='Player', pos='WR', ovr=80, age=25, apy=5, team='GB', retired=False, contract=N(years=1))
        L = league(players={'p': p}, exit_meetings={'2026': [dict(pid='p', answer=None)]})
        contract = IB.post(L, 'contract_year', 'Final year', '', payload={'pid': 'p'})
        invite = IB.post(L, 'exit', 'Meetings', '')
        IB.reconcile(L)
        self.assertTrue(IB.is_decision(contract)); self.assertTrue(IB.is_decision(invite))
        p.contract.years = 3; L.exit_meetings['2026'][0]['answer'] = 'heard'
        IB.reconcile(L)
        self.assertEqual((contract['status'], invite['status']), ('done', 'done'))

    def test_bye_week_has_health_listing_but_no_play_decision(self):
        for abbr, week, schedule in [('GB', 8, [(8, 'NYJ', 'MIN', None, None)]),
                                     ('MIN', 19, [(19, 'NYJ', 'GB', None, None)])]:
            L = league(week=week, schedule=schedule)
            p = N(pid='hurt', name='Hurt Player', out_until=week+1,
                  xp_spent={}, ratings={'tough_rating': 70})
            team = N(abbr=abbr, roster=[p], ir=[])
            L.players[p.pid] = p
            desk = IS.InjuryDesk()
            with patch.object(IS, 'designation', return_value='questionable'), patch.object(desk, '_ai_plays') as ai:
                desk.set_week(L, team, week, np.random.default_rng(1))
            self.assertEqual(desk.status['hurt'], 'questionable')
            self.assertFalse(desk.pending)
            self.assertFalse(desk.playing_hurt)
            self.assertFalse(IB.pending(L, 'injury_decision'))
            self.assertEqual(p.out_until, week+1)
            ai.assert_not_called()

    def test_existing_bye_prompt_closes_but_scheduled_prompt_stays(self):
        for schedule, expected in [([], 'done'), ([(8, 'GB', 'MIN', None, None)], 'unread')]:
            L = league(week=8, schedule=schedule)
            m = IB.post(L, 'injury_decision', 'Play or sit?', '', expires_week=8)
            IB.reconcile(L)
            self.assertEqual(m['status'], expected)

    def test_trainer_automatic_decision_closes_original_week(self):
        L = league()
        p = N(pid='hurt', name='Hurt Player', out_until=5, retired=False, contract=None,
              team='GB', fa_class='under_contract', accrued=1, xp_spent={}, ratings={'tough_rating': 70})
        team = N(abbr='GB', roster=[p], ir=[])
        L.players[p.pid] = p; desk = IS.InjuryDesk()
        with patch.object(IS, 'designation', return_value='questionable'), patch.object(IS, 'hurt_words', return_value='Play?'), patch.object(IS, 'will_play', return_value=False):
            desk.set_week(L, team, 1, np.random.default_rng(1))
            desk.resolve_pending(L, team, np.random.default_rng(1))
            desk.set_week(L, team, 2, np.random.default_rng(1))
        IB.reconcile(L)  # next-week listings can precede the league clock roll
        self.assertEqual([m['status'] for m in L.inbox], ['done', 'unread'])
        self.assertEqual(L.inbox[-1]['week'], 2)
        self.assertEqual(len(IB.pending(L, 'injury_decision')), 1)
        L.week = 3; IB.reconcile(L)
        self.assertFalse(IB.pending(L, 'injury_decision'))

    def test_legacy_injury_listing_migrates_target_week_before_reconciling(self):
        L = league(week=2)
        # Old roll_week posted the week-2 desk while L.week still read 1.
        m = IB.post(L, 'injury_decision', 'Play or sit?', '',
                    payload={'pid': 'hurt'}, expires_week=3)
        m['week'] = 1
        L.inbox = json.loads(json.dumps(L.inbox))
        m = L.inbox[0]
        IB.reconcile(L)
        self.assertEqual((m['week'], m['expires_week'], m['status']), (2, 2, 'unread'))
        self.assertTrue(IB.is_decision(m))
        IB.reconcile(L)  # Migration is idempotent.
        self.assertEqual(m['status'], 'unread')
        L.week = 3
        IB.reconcile(L)
        self.assertEqual(m['status'], 'done')

    def test_legacy_current_week_injury_listing_still_expires(self):
        L = league(week=2)
        m = IB.post(L, 'injury_decision', 'Play or sit?', '', expires_week=2)
        m['week'] = 1  # Old week-1 listing, target=expiry-1=1.
        IB.reconcile(L)
        self.assertEqual((m['week'], m['status']), (1, 'done'))

    def test_references_arrive_on_advance_across_year_and_save(self):
        c = ST.Coach('Coach', 'oc', 70, 50, 'Balanced', 45)
        L = league(week=22, staff_pool=[c])
        ST.interview_ask(L, 'GB', c.name, 'references')
        L.interviews = json.loads(json.dumps(L.interviews))
        ST.resolve_references(L)
        self.assertFalse(L.inbox)
        L.year = 2027; L.week = 0
        ST.resolve_references(L, advanced=True)
        self.assertEqual(len(L.inbox), 1)
        self.assertFalse(IB.is_decision(L.inbox[0]))
        ST.resolve_references(L, advanced=True)
        self.assertEqual(len(L.inbox), 1)

    def test_legacy_week23_references_at_offseason_advance(self):
        c = ST.Coach('Coach', 'oc', 70, 50, 'Balanced', 45)
        c.staff_traits = []; c.known = []
        L = league(week=22, staff_pool=[c], interviews={c.name: dict(refs_due=23, log=[])})
        ST.resolve_references(L, advanced=True)
        self.assertEqual(len(L.inbox), 1)
        self.assertIsNone(L.interviews[c.name]['refs_due'])


class WaiverLifecycleTests(unittest.TestCase):
    def scenario(self, fits, room=True):
        p = N(pid='wire', name='Wire Player', pos='QB', team=None, retired=False, contract=None)
        active = [] if room else [N(pid=f'active-{i}') for i in range(53)]
        L = league(players={p.pid: p}, teams={'GB': N(active=lambda: active), 'MIN': N()},
                   waivers=[dict(pid=p.pid, from_team='DAL', claims=['GB'], user_notified=True)])
        IB.post(L, 'waiver_notice', 'Available', '', payload={'pid': p.pid})
        IB.post(L, 'waiver_digest', 'Wire', '')
        def award(L, e, a): L.player(e['pid']).team = a
        with patch.object(WV, 'priority', return_value=['GB', 'MIN']), patch.object(VAL, 'pool_from_league', return_value=[]), patch.object(VAL, 'value_player', return_value={'apy': 1}), patch.object(WV, 'claim_fits', side_effect=lambda L,e,a: fits if a == 'GB' else True), patch.object(WV, 'wants', return_value=True), patch.object(WV, 'make_room', side_effect=lambda L,a,p,e: room if a == 'GB' else True), patch.object(WV, 'award', side_effect=award), patch.object(PSQ, 'shunned', return_value=False):
            WV.process(L, np.random.default_rng(1), 1)
        return L

    def test_cap_failure_has_one_truthful_unread_outcome(self):
        L = self.scenario(False)
        self.assertEqual([m['status'] for m in L.inbox], ['closed', 'closed', 'unread'])
        self.assertIn('Claim failed', L.inbox[-1]['subject'])
        self.assertEqual(L.player('wire').team, 'MIN')
        self.assertFalse(L.waivers)

    def test_roster_failure_does_not_claim_player_stays_on_wire(self):
        L = self.scenario(True, False)
        self.assertEqual(len(L.inbox), 3)
        self.assertNotIn('stays on the wire', L.inbox[-1]['body'])
        self.assertIn('Claim failed', L.inbox[-1]['subject'])
        self.assertEqual(L.player('wire').team, 'MIN')


class OfferSheetTests(unittest.TestCase):
    def fixture(self, holder='GB'):
        L = League(2026); L.user_team = 'GB'; L.week = 0
        for a in ('GB', 'MIN'):
            t = Team(a, 'United North', 'United'); t.league = L; L.teams[a] = t
        L.set_phase('free_agency')
        p = Player('p', 'Player', 'QB', 25, {}, team=holder, contract=Contract(1, [3]), accrued=3)
        p.fa_class = 'tendered'; p.tender_team = holder
        L.players[p.pid] = p; L.teams[holder].roster.append(p); L.teams[holder].sync_cap()
        L.free_agents = [p.pid]
        return L, p

    def test_user_sheet_not_automatically_answered(self):
        L, p = self.fixture()
        m = MK.inbox_add(L, sheet())
        MK.resolve_offer_sheets(L, np.random.default_rng(1)); IB.reconcile(L)
        self.assertEqual(m['status'], 'unread'); self.assertTrue(IB.is_decision(m))
        self.assertEqual(p.team, 'GB')
        self.assertIs(MK.inbox_add(L, sheet()), m)
        self.assertEqual(len(L.inbox), 1)

    def test_match_and_decline_use_real_signing_without_pick_compensation(self):
        for action, destination in [('match','GB'), ('decline','MIN')]:
            L, p = self.fixture(); m = MK.inbox_add(L, sheet())
            picks = {a: list(t.picks) for a,t in L.teams.items()}
            with patch.object(MK, 'signing_terms', return_value=dict(base=[4,4], signing_bonus=2)):
                result = MK.answer_offer_sheet(L, m['id'], action)
            self.assertTrue(result['ok'], result)
            self.assertEqual(p.team, destination); self.assertEqual(p.contract.years, 2)
            self.assertEqual(m['status'], 'done'); self.assertTrue(m['resolved'])
            self.assertFalse(IB.is_decision(m)); self.assertIsNone(p.tender_team)
            self.assertEqual({a: t.picks for a,t in L.teams.items()}, picks)
            self.assertFalse(MK.answer_offer_sheet(L, m['id'], action)['ok'])

    def test_failed_match_preserves_original_contract_and_open_request(self):
        L, p = self.fixture(); m = MK.inbox_add(L, sheet()); old = p.contract
        with patch.object(MK, 'signing_terms', return_value=dict(base=[400,400], signing_bonus=0)):
            result = MK.answer_offer_sheet(L, m['id'], 'match')
        self.assertFalse(result['ok']); self.assertIs(p.contract, old)
        self.assertEqual(p.team, 'GB'); self.assertTrue(IB.is_decision(m))

    def test_failed_suitor_keeps_tender_and_closes_request(self):
        L, p = self.fixture(); m = MK.inbox_add(L, sheet()); old = p.contract
        with patch.object(MK, 'signing_terms', return_value=dict(base=[400,400], signing_bonus=0)):
            result = MK.answer_offer_sheet(L, m['id'], 'decline')
        self.assertEqual(result['outcome'], 'void'); self.assertIs(p.contract, old)
        self.assertEqual(p.team, 'GB'); self.assertFalse(IB.is_decision(m))

    def test_cpu_request_resolves_without_user_inbox(self):
        L, p = self.fixture('MIN')
        with patch.object(MK, 'power', return_value=100), patch.object(VAL, 'value_player', return_value={'apy':5}), patch.object(MK, 'signing_terms', return_value=dict(base=[4,4], signing_bonus=2)):
            result = MK.inbox_add(L, sheet('MIN'), np.random.default_rng(1))
        self.assertEqual(getattr(L, 'inbox', []), []); self.assertTrue(result['resolved'])
        self.assertEqual(p.team, 'MIN'); self.assertEqual(p.contract.years, 2)

    def test_legacy_cpu_missing_player_closes(self):
        L = league()
        m = IB.post(L, 'offer_sheet', 'Old CPU request', '', payload=sheet('MIN'))
        m.update(sheet('MIN'))
        MK.resolve_offer_sheets(L, np.random.default_rng(1))
        self.assertEqual(m['status'], 'done'); self.assertTrue(m['resolved'])

    def test_stale_user_sheet_cannot_replace_newer_contract(self):
        L, p = self.fixture(); m = MK.inbox_add(L, sheet())
        p.fa_class = 'signed'; old = p.contract
        result = MK.answer_offer_sheet(L, m['id'], 'match')
        self.assertEqual(result['outcome'], 'void'); self.assertIs(p.contract, old)


if __name__ == '__main__': unittest.main()
