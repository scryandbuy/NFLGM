import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
from league import League, Team, Player, DraftPick
from cap_engine import Contract
import gm_engine as GM
import targets as TG
import roster_advisor as RA
import waivers as WV
import inbox as IB


def player(pid, pos='CB', grade=84, team=None, dev='normal'):
    return Player(pid, pid, pos, 24, {k: grade for k in TG.DEPTH_WEIGHTS[pos]},
                  team=team, dev=dev, contract=Contract(2, [1, 1]) if team else None)


def fixture():
    L = League(2026); L.user_team = 'GB'; L.week = 3; L.inbox=[]
    for abbr in ('GB', 'MIN'):
        t = Team(abbr, 'NFC North', 'NFC'); t.league = L; t.gm = GM.GM()
        L.teams[abbr] = t
        counts = dict(QB=2, HB=2, WR=5, TE=3, LT=2, LG=2, C=1, RG=2, RT=2,
                      LEDG=2, REDG=2, DT=4, MIKE=2, WILL=2, SAM=1, CB=5, FS=2, SS=2, K=1, P=1, LS=1)
        for pos, n in counts.items():
            for i in range(n):
                p = player(f'{abbr}-{pos}-{i}', pos, 84 if i == 0 else 78, abbr)
                t.roster.append(p); L.players[p.pid] = p
        t.picks = [DraftPick(2026, r, abbr, abbr, selection=32*r) for r in range(3, 8)]
    L.set_phase('regular')
    return L


def row(pid='target', **kw):
    r = dict(pid=pid, name=pid, pos='CB', ovr=88, dev=None, source='fa', owner=None,
             reason='A need', cost='Estimate', pick=None, release=None,
             context=['fa', None, [], 'CB', 29], score=10, urgent=False)
    r.update(kw)
    return r


class Reports(unittest.TestCase):
    def test_cadence_dedupe_deletion_and_save_load(self):
        L = fixture()
        with patch.object(RA, 'candidates', return_value=[row()]):
            self.assertIsNotNone(RA.weekly(L, 1))
            L.inbox.clear()
            L = League.load(L.save()); L.user_team = 'GB'
            self.assertIsNone(RA.weekly(L, 1))
            self.assertIsNone(RA.weekly(L, 2))
            self.assertIsNone(RA.weekly(L, 4))  # same target cooldown despite inbox deletion
            self.assertIsNotNone(RA.weekly(L, 7))

    def test_urgent_exception_and_three_distinct_positions(self):
        L = fixture()
        with patch.object(RA, 'candidates', return_value=[row()]):
            RA.weekly(L, 1)
        rows = [row(str(i), pos=pos, urgent=True) for i, pos in enumerate(['CB', 'CB', 'LT', 'TE', 'DT'])]
        with patch.object(RA, 'candidates', return_value=rows):
            m = RA.weekly(L, 2)
        self.assertEqual([r['pos'] for r in m['payload']['recommendations']], ['CB', 'LT', 'TE'])

    def test_dismiss_persists_but_new_injury_can_reopen(self):
        L = fixture(); r = row()
        with patch.object(RA, 'candidates', return_value=[r]):
            m = RA.weekly(L, 1)
            self.assertTrue(RA.dismiss(L, m['id'], r['pid'])['ok'])
            self.assertIsNone(RA.weekly(L, 2))
        r = row(context=['fa', None, ['new-injury'], 'CB', 29], urgent=True)
        with patch.object(RA, 'candidates', return_value=[r]):
            self.assertIsNotNone(RA.weekly(L, 3))

    def test_no_forced_filler_and_bounded_history(self):
        L = fixture(); s = RA._state(L)
        s['seen']['ancient'] = dict(tick=RA._tick(L, 1)-64, context=[])
        with patch.object(RA, 'candidates', return_value=[]):
            self.assertIsNone(RA.weekly(L, 1))
        self.assertNotIn('ancient', s['seen']); self.assertFalse(L.inbox)

    def test_waiver_report_replaces_only_duplicate_availability_notice(self):
        L = fixture(); p = player('wire'); L.players[p.pid] = p
        entry = dict(pid=p.pid, from_team='MIN', user_notified=False)
        IB.post(L, 'waiver_notice', 'Available on waivers: wire', 'body', payload={'pid':p.pid})
        IB.post(L, 'waiver_notice', 'Claim awarded: someone else', 'body')
        with patch.object(WV, 'pending', return_value=[entry]), patch.object(RA, 'candidates', return_value=[row('wire', source='waiver', urgent=True)]):
            RA.weekly(L, 1)
        self.assertTrue(entry['user_notified'])
        self.assertEqual([m['kind'] for m in L.inbox], ['waiver_notice', 'roster_report'])

    def test_stale_acquired_injured_and_deadline(self):
        L = fixture(); p = player('target'); L.players[p.pid] = p; L.free_agents.append(p.pid)
        m = dict(year=L.year, status='open', payload={'recommendations':[row()]})
        self.assertTrue(RA.recommendations(L,m)[0]['available'])
        p.team='MIN'; self.assertFalse(RA.recommendations(L,m)[0]['available'])
        m['payload']['recommendations']=[row(source='trade',owner='MIN')]
        L.week=18; self.assertFalse(RA.recommendations(L,m)[0]['available'])
        L.week=3; p.out_until=8; self.assertFalse(RA.recommendations(L,m)[0]['available'])


class Assessment(unittest.TestCase):
    def run_candidates(self, L):
        # Isolate market dollar estimates; exercise real roster/cap/role checks.
        with patch.object(RA, '_terms', return_value=(Contract(1,[1]), 'Estimated $1m')):
            return RA.candidates(L, 4)

    def test_empty_role_recommends_fa_without_mutating_roster_or_rng(self):
        L = fixture(); t=L.teams['GB']; t.roster=[p for p in t.roster if p.pos!='K']
        p=player('available-k','K',85); L.players[p.pid]=p; L.free_agents.append(p.pid)
        before=[p.pid for p in t.roster]; rng=np.random.default_rng(41); state=copy.deepcopy(rng.bit_generator.state)
        rows=self.run_candidates(L)
        self.assertIn(p.pid,[r['pid'] for r in rows]); self.assertEqual(before,[p.pid for p in t.roster])
        self.assertEqual(state,rng.bit_generator.state)

    def test_own_squad_alternative_suppresses_external_signing(self):
        L=fixture(); t=L.teams['GB']; t.roster=[p for p in t.roster if p.pos!='K']
        p=player('external','K',85); L.players[p.pid]=p; L.free_agents.append(p.pid)
        q=player('internal','K',85,'GB'); t.practice_squad=[q]; L.players[q.pid]=q
        self.assertNotIn(p.pid,[r['pid'] for r in self.run_candidates(L)])

    def test_injured_targets_and_unaffordable_deals_excluded(self):
        L=fixture(); t=L.teams['GB']; t.roster=[p for p in t.roster if p.pos!='K']
        p=player('external','K',85); p.out_until=7; L.players[p.pid]=p; L.free_agents.append(p.pid)
        self.assertNotIn(p.pid,[r['pid'] for r in self.run_candidates(L)])
        p.out_until=None  # huge ask tests affordability regardless of cap model defaults
        with patch.object(RA, '_terms', return_value=(Contract(1,[1000]), 'Expensive')):
            self.assertNotIn(p.pid,[r['pid'] for r in RA.candidates(L,4)])

    def test_seller_starter_is_never_trade_recommendation(self):
        L=fixture(); p=L.player('MIN-QB-0')
        self.assertIsNone(RA._trade_offer(L,L.teams['GB'],p,[],4))
        self.assertIsNone(RA._trade_offer(L,L.teams['GB'],L.player('MIN-QB-1'),[],18))

    def test_short_injury_does_not_trigger_expensive_rental(self):
        L=fixture(); L.player('GB-K-0').out_until=5
        p=player('external','K',85); L.players[p.pid]=p; L.free_agents.append(p.pid)
        with patch.object(RA, '_terms', return_value=(Contract(1,[8]), 'Expensive')):
            self.assertNotIn(p.pid,[r['pid'] for r in RA.candidates(L,4)])

    def test_practice_squad_route_and_public_dev_not_hidden_potential(self):
        L=fixture(); t=L.teams['GB']; t.roster=[p for p in t.roster if p.pos!='K']
        p=player('ps-k','K',85,'MIN',dev='superstar'); p.potential=86
        L.players[p.pid]=p; L.teams['MIN'].practice_squad=[p]
        first=next(r for r in self.run_candidates(L) if r['pid']==p.pid)
        p.potential=99
        second=next(r for r in self.run_candidates(L) if r['pid']==p.pid)
        self.assertEqual(first,second); self.assertEqual(first['source'],'ps'); self.assertEqual(first['dev'],'Epic')
        L.negotiations=[dict(pid=p.pid,team='GB',state='waiting')]
        self.assertNotIn(p.pid,[r['pid'] for r in self.run_candidates(L)])

    def test_waiver_route_and_existing_claim_suppression(self):
        L=fixture(); t=L.teams['GB']; t.roster=[p for p in t.roster if p.pos!='K']
        p=player('waived-k','K',85); L.players[p.pid]=p; L.free_agents.append(p.pid)
        WV.waive(L,p,'MIN',3)
        r=next(r for r in self.run_candidates(L) if r['pid']==p.pid)
        self.assertEqual(r['source'],'waiver'); self.assertTrue(r['urgent'])
        L.waivers[0]['claims'].append('GB')
        self.assertNotIn(p.pid,[r['pid'] for r in self.run_candidates(L)])

    def test_trade_offer_requires_both_sides_to_accept(self):
        import trade_engine as TE
        L=fixture(); t=L.teams['MIN']
        # Spare fifth DT is not a starter or required depth.
        p=player('spare-dt','DT',76,'MIN'); L.players[p.pid]=p; t.roster.append(p)
        with patch('trades.player_asset',return_value={'kind':'player'}), patch.object(TE,'evaluate',return_value={'accepted':False}):
            self.assertIsNone(RA._trade_offer(L,L.teams['GB'],p,[],4))
        with patch('trades.player_asset',return_value={'kind':'player'}), patch.object(TE,'evaluate',return_value={'accepted':True}):
            offer=RA._trade_offer(L,L.teams['GB'],p,[],4)
            self.assertIsNotNone(offer); self.assertIn('-7-',offer['id'])

    def test_advisor_price_matches_real_signing_preview_including_bonus(self):
        import market as MK, valuation as VAL, staff as ST
        L=fixture(); t=L.teams['GB']; t.cap.paid_week=10
        p=player('priced')
        with patch.object(VAL,'value_player',return_value={'apy':10}), patch.object(ST,'recruit_pull',return_value=(0,1)):
            c, _=RA._terms(L,t,p,'fa',[])
        terms=MK.signing_terms(L,p,t,10,1,RA.CAP.get(L.year,301.2))
        self.assertAlmostEqual(c.cap_hit(0),terms['cap_hits'][0],places=3)
        self.assertGreater(c.cap_hit(0),10*8/18)  # bonus is not salary-prorated

    def test_negotiated_ps_signing_keeps_existing_three_game_lock(self):
        import market as MK, practice_squad as PS
        L=fixture(); p=player('ps-sign','CB',80,'MIN')
        L.players[p.pid]=p; L.teams['MIN'].practice_squad=[p]
        MK.sign(L,p,MK.Offer('GB',p.pid,1.2,1),RA.CAP.get(L.year,301.2))
        self.assertEqual(p.team,'GB'); self.assertNotIn(p,L.teams['MIN'].practice_squad)
        self.assertTrue(PS.locked(p,L.week+2)); self.assertFalse(PS.locked(p,L.week+3))
        self.assertEqual([x['kind'] for x in L.transactions if x.get('pid')==p.pid],['ps_release','ps_poach'])


if __name__ == '__main__':
    unittest.main()
