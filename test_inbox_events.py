import ast, copy, json, unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from player_background import home_state
import inbox as IB, inbox_events as IE, club_notes as CN, league_notes as LN, negotiations as NG, waivers as WV

src=ast.parse(Path('session.py').read_text(encoding='utf-8'))
cls=next(n for n in src.body if isinstance(n,ast.ClassDef) and n.name=='Session')
names={'_draft_over','_open_fa_if_due','_skip_empty_offseason_waivers','_black_monday','blocking','_resign_card','inbox_delete','inbox_clear_read','inbox_read','inbox_message','inbox_hurt_action','inbox_offer_sheet','advance','step_waivers_1'}
ns={'IB':IB,'IE':IE,'MK':N(),'PS':N(),'CLUB_NAME_':{},'TG':N(),'WV':WV,'home_state':home_state,'inbox_player':IB.player_name}
exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='S',bases=[],keywords=[],body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names],decorator_list=[])],type_ignores=[])),'session.py','exec'),ns)
S=ns['S']
S.OFFSEASON=ast.literal_eval(next(n.value for n in cls.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OFFSEASON' for t in n.targets)))
def league(**kw):
 d=dict(year=2026,week=1,inbox=[],teams={},players={},transactions=[],user_team='GB',notes_sent={},league_notes_sent={},log=lambda *a,**k:None)
 d.update(kw); L=N(**d); L.player=lambda pid:L.players.get(pid); return L

def session(L):
 s=S();s.L=L;s.user_team='GB';s.rng=None;s.runner=None;s.stop=('offseason',0);s.ROSTER_MIN=46;s.ROSTER_MAX=53;return s

class EventTests(unittest.TestCase):
 def test_event_survives_delete_and_json_roundtrip(self):
  L=league();IE.post(L,'review-2026','review','Review','Body');L.inbox=[]
  L.notes_sent=json.loads(json.dumps(L.notes_sent));self.assertIsNone(IE.post(L,'review-2026','review','Review','Body'));self.assertEqual(L.inbox,[])
 def test_event_ledger_survives_league_serialization(self):
  from league import League
  L=League(2026);IE.post(L,'review-2026','review','Review','Body');L.inbox=[]
  restored=League.load(L.save())
  self.assertTrue(IE.seen(restored,'review-2026'));self.assertIsNone(IE.post(restored,'review-2026','review','Review','Body'))
 def test_legacy_key_adopted_before_clear(self):
  L=league();IB.post(L,'contract','Resign','Body',payload={'key':'resign-2026'});s=session(L);s.inbox_read(L.inbox[0]['id']);s.inbox_clear_read()
  self.assertTrue(IE.seen(L,'resign-2026'));self.assertFalse(L.inbox)
 def test_new_year_and_distinct_event_still_deliver(self):
  L=league();IE.post(L,'review-2026','review','Review','Body');IE.post(L,'review-2027','review','Review','Body');self.assertEqual(len(L.inbox),2)
 def test_roster_keys_are_not_remembered(self):
  L=league();IB.post(L,'roster','Roster','Body',payload={'key':'roster-2026-1'});IE.remember(L);self.assertNotIn('roster-2026-1',IE.ledger(L))
 def test_fa_empty_opened_phase_does_not_reopen(self):
  L=league(fa_bids_phase=1,fa_bids={},free_agents=[]);s=session(L);s.OFFSEASON=[('FA','fa1')];s.FA_STEPS={'fa1':1}
  with patch.dict(ns,MK=N(open_round=lambda *a,**k:self.fail('reopened'))):s._open_fa_if_due()
  self.assertEqual(L.inbox,[])
 def test_fa_opens_once_even_without_bids(self):
  L=league(fa_bids_phase=None,fa_bids={},free_agents=[]);s=session(L);s.OFFSEASON=[('FA','fa1')];s.FA_STEPS={'fa1':1}
  def op(*args,**kwargs):L.fa_bids_phase=1;return {}
  with patch.dict(ns,MK=N(open_round=op)):s._open_fa_if_due();s._open_fa_if_due()
  self.assertEqual(len(L.inbox),1)
 def test_resign_clear_does_not_repost(self):
  L=league();s=session(L)
  with patch.dict(ns,TG=N(user_resign_sheet=lambda L:dict(ufa=[],rfa=[],erfa=[],room=10))):
   s._resign_card();s.inbox_read(L.inbox[0]['id']);s.inbox_clear_read();s._resign_card()
  self.assertFalse(L.inbox)
 def test_draft_user_has_one_mail_cpu_has_one(self):
  L=league(consensus={});s=session(L)
  p=N(pid='p',name='Rookie',pos='WR',college='School',ovr=85,xp_spent={'_tape_role':'gem'})
  s.draft=N(done=True,year=2026,results=[(97,'GB',p),(98,'MIN',p)],trades=[]);s._draft_over()
  self.assertEqual([m['kind'] for m in L.inbox],['club','league']);self.assertNotIn('day-three',L.inbox[1]['body'])
 def test_coaching_direct_log_consolidated(self):
  import coaching_pool as CP
  L=league(teams={'MIN':N(abbr='MIN',gm=N(name='Coach'))},transactions=[dict(year=2026,kind='gm_change',team='MIN',hired='Coach')]);s=session(L)
  with patch.dict(ns,PS=N(run_firings=lambda *a,**k:[('MIN','offense')])),patch.object(CP,'coordinators_as_candidates',return_value=[]):s._black_monday(['MIN'])
  LN.transactions(L,1);self.assertEqual(len(L.inbox),1)
 def test_roster_text_updates(self):
  roster=list(range(68));L=league(teams={'GB':N(active=lambda:roster)});s=session(L);s.stop=('cutdown',)
  s.blocking();roster[:]=list(range(55));s.blocking();self.assertEqual(len(L.inbox),1);self.assertIn('55',L.inbox[0]['body']);self.assertNotIn('68',L.inbox[0]['body'])
 def test_ir_not_recovery(self):
  p=N(pid='p',name='Hurt',pos='QB',team='GB',out_until=8,retired=False)
  t=N(abbr='GB',roster=[p],ir=[p],depth={});L=league(teams={'GB':t},players={'p':p},notes_sent={'_out':{'p':1}})
  CN.returns(L,2);self.assertFalse(L.inbox);p.out_until=None;CN.returns(L,8);self.assertFalse(L.inbox)
 def test_actual_recovery_once(self):
  p=N(pid='p',name='Recovered',pos='QB',team='GB',out_until=None,retired=False)
  L=league(teams={'GB':N(abbr='GB',roster=[p],ir=[],depth={})},players={'p':p},notes_sent={'_out':{'p':1}})
  CN.returns(L,2);CN.returns(L,2);self.assertEqual(len(L.inbox),1)
 def test_repeat_promise_keeps_original_terms(self):
  p=N(contract=None);L=league(players={'p':p});NG.record_promise(L,'p','GB','extension_by',year=2027,source='exit');NG.record_promise(L,'p','GB','extension_by',year=2028)
  self.assertEqual(len(L.promises),1);self.assertEqual(L.promises[0]['year'],2027)
 def test_legacy_promises_apply_one_outcome(self):
  effects=[];p=N(pid='p',name='Player',team='GB',contract=None,morale=N(apply=effects.append),xp_spent={'_captain':True});L=league(players={'p':p},teams={'GB':N()})
  NG.record_promise(L,'p','GB','captaincy');L.promises.append(copy.deepcopy(L.promises[0]));NG.check_promises(L,8)
  self.assertEqual(len(L.inbox),1);self.assertEqual(effects,['promise_kept']);self.assertEqual(L.promises[1]['status'],'superseded')
 def test_distinct_promise_types_preserved(self):
  L=league(players={'p':N(contract=None)});NG.record_promise(L,'p','GB','captaincy');NG.record_promise(L,'p','GB','no_trade');self.assertEqual(len(L.promises),2)
 def test_tie_is_not_win(self):
  L=league(teams={a:N(abbr=a,division='United North',record=[1,1,1]) for a in ('GB','MIN','CHI')});LN.big_result(L,3,[('MIN','CHI',20,20)])
  self.assertIn('tied 20–20',L.inbox[0]['body']);self.assertNotIn('beat',L.inbox[0]['body'])
 def test_weak_division_winner_not_eliminated(self):
  teams={}
  for d,rs in zip(('East','North','South','West'),([12,11,10,9],[12,11,10,9],[12,7,6,5],[8,7,6,1])):
   for i,w in enumerate(rs):a=f'{d}{i}';teams[a]=N(abbr=a,division='United '+d,record=[w,17-w,0])
  L=league(week=18,teams=teams,user_team='West0');LN.standings(L,18)
  mine=[m for m in L.inbox if m['kind']=='result'];self.assertEqual(len(mine),1);self.assertIn('clinch',mine[0]['subject']);self.assertNotIn('eliminated',mine[0]['body'])
 def test_equal_ceiling_does_not_promise_playoffs(self):
  teams={f'T{i}':N(abbr=f'T{i}',division=f'United D{i//4}',record=[9,7,0]) for i in range(16)}
  L=league(week=17,teams=teams,user_team='T0');LN.standings(L,17);self.assertFalse(any('clinch' in m['subject'] for m in L.inbox))
 def test_final_messages_match_actual_seeding(self):
  import standings_and_seeding as SS
  teams={f'T{i}':N(abbr=f'T{i}',division=f'United D{i//4}',record=[0,0,0]) for i in range(16)}
  games=[]
  for i in range(16):
   for j in range(i+1,16):games.append((f'T{i}',f'T{j}',20,17 if (i+j)%3 else 20))
  for _ in range(2):
   for i in range(0,16,2):games.append((f'T{i}',f'T{i+1}',10,20))
  state=SS.Season.live({a:t.division for a,t in teams.items()},{a:'United' for a in teams},games,2026)
  for a,t in teams.items():t.record=state.rec[a]
  L=league(week=18,teams=teams,user_team='T0',schedule=[(18,a,h,ap,hp) for h,a,hp,ap in games]);LN.standings(L,18)
  actual=set(SS.seed_conference(state,'United'));notified={a for a in teams if f'po-2026-{a}' in L.league_notes_sent}
  self.assertEqual(actual,notified);self.assertFalse(any(f'out-2026-{a}' in L.league_notes_sent for a in actual))
 def test_awards_consolidated_and_complete(self):
  p=N(pid='p',name='Winner',pos='FB',team='GB');L=league(players={'p':p})
  LN.season_end(L,{'all_pro_1':[p],'all_pro_2':[p],'sb_mvp':p});self.assertEqual(len(L.inbox),2);self.assertIn('Second team',L.inbox[1]['body']);self.assertIn('your team',L.inbox[1]['body']);self.assertIn('Championship Game MVP',L.inbox[0]['body'])

class SessionIntegrationTests(unittest.TestCase):
 def test_answered_poach_unblocks_and_can_delete(self):
  import staff as ST
  c=N(name='Coach',role='oc',team='GB',traits={})
  L=league(teams={'GB':N(abbr='GB',staff={'oc':c}),'MIN':N(abbr='MIN')});s=session(L)
  r=ST.poach_request(L,c,'MIN');self.assertEqual(len(s.blocking()),1)
  ST.answer_poach(L,r['id'],'block');self.assertEqual(s.blocking(),[])
  self.assertTrue(s.inbox_delete(L.inbox[0]['id'])['ok'])
 def test_offer_sheet_blocks_backend_advance_until_answered(self):
  import market as MK
  from test_inbox_entity_lifecycle import OfferSheetTests, sheet
  L,p=OfferSheetTests().fixture();s=session(L);s.next_label=lambda:'Next';m=MK.inbox_add(L,sheet())
  s._advance=lambda:self.fail('advanced past pending offer sheet')
  self.assertEqual(s.advance()['done'],'Blocked')
  with patch.dict(ns,MK=MK):
   # Verify Session dispatch; the entity lifecycle suite exercises contract changes.
   with patch.object(MK,'answer_offer_sheet',side_effect=lambda L,mid,action,rng:dict(ok=True,mid=mid,action=action)):
    result=s.inbox_offer_sheet(m['id'],'match')
  self.assertEqual(result['action'],'match');self.assertEqual(result['mid'],m['id'])
 def test_stale_injury_message_cannot_answer_current_pending(self):
  L=league(week=2);s=session(L);s.runner=N(desks={'GB':N(pending={'p':'questionable'})})
  m=IB.post(L,'injury_decision','Old','',payload={'pid':'p'},expires_week=2);m['week']=1
  s.club_act=lambda *a,**k:self.fail('dispatched stale injury')
  self.assertFalse(s.inbox_hurt_action(m['id'])['ok'])
 def test_current_injury_message_dispatches(self):
  L=league(week=2);s=session(L);s.runner=N(desks={'GB':N(pending={'p':'questionable'})})
  m=IB.post(L,'injury_decision','Current','',payload={'pid':'p'},expires_week=2)
  s.club_act=lambda action,**kw:dict(ok=True,action=action,**kw)
  self.assertEqual(s.inbox_hurt_action(m['id'],play=False),dict(ok=True,action='hurt_decision',pid='p',play=False))
 def test_offseason_waiver_arrival_notifies_before_processing(self):
  import waivers as WV
  L=league(waivers=[dict(pid='p')]);s=session(L);s.stop=('offseason',4);s.FA_STEPS={}
  with patch.dict(ns,WV=WV),patch.object(WV,'notify_user') as notify,patch.object(WV,'process') as process:
   s._open_fa_if_due();notify.assert_called_once();process.assert_not_called()
   s.step_waivers_1();process.assert_called_once();self.assertEqual(notify.call_count,1)
 def test_references_only_follow_successful_advance(self):
  import staff as ST
  L=league();s=session(L);s._advance=lambda:dict(done='Blocked')
  with patch.dict(ns,STF=ST),patch.object(ST,'resolve_references') as resolve:
   s.advance();resolve.assert_not_called()
   s._advance=lambda:dict(done='Camp');s.advance();resolve.assert_called_once_with(L,advanced=True)

if __name__=='__main__':unittest.main()

