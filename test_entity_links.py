import copy,time,unittest
import inbox as IB
from league import League
from test_cap_accounting import fixture,player

class EntityLinkTests(unittest.TestCase):
    def test_each_namesake_mention_keeps_its_id_after_reload(self):
        L=fixture();a=player(L,'a');b=player(L,'b');a.name=b.name='Mike Smith'
        m=IB.post(L,'league',f'{IB.player_name(a)} traded',
                  f'🏈 {IB.player_name(a)} replaces {IB.player_name(b)}; {IB.player_name(a, "Smith")} starts.')
        self.assertEqual(m['body'],'🏈 Mike Smith replaces Mike Smith; Smith starts.')
        self.assertEqual([r['id'] for r in m['mentions']['body']],['a','b','a'])
        self.assertEqual(m['mentions']['body'][0]['start'],3)
        loaded=League.load(L.save())
        self.assertEqual(loaded.inbox[0]['mentions'],m['mentions'])
        loaded.players['a'].name='Renamed Player'
        self.assertEqual(loaded.inbox[0]['mentions']['body'][0]['id'],'a')
        self.assertNotIn('\x1e',str(L.save()))

    def test_payload_player_route_disambiguates_legacy_names(self):
        L=fixture();a=player(L,'a');b=player(L,'b');a.name=b.name='Mike Smith'
        for link in ('player:b','club:player:b'):
            m=IB.post(L,'club','Mike Smith','Mike Smith signed.',payload={'link':link})
            self.assertEqual([r['id'] for r in m['mentions']['body']],['b'])

    def test_real_batch_producers_keep_two_namesakes(self):
        import club_notes as CN, views_personnel as VP, league_notes as LN
        from cap_engine import Contract
        L=fixture();L.user_team='GB'
        a=player(L,'a',contract=Contract(1,[1]));b=player(L,'b',contract=Contract(1,[1]))
        a.name=b.name='Mike Smith'
        m=IB.post(L,'trade_done','Trade complete',', '.join(VP._words(L,['a','b'])))
        self.assertEqual([r['id'] for r in m['mentions']['body']],['a','b'])
        CN.season_end(L)
        self.assertEqual([r['id'] for r in L.inbox[-1]['mentions']['body']],['a','b'])
        LN.season_end(L,{'mvp':a,'opoy':b})
        self.assertEqual([r['id'] for r in L.inbox[-1]['mentions']['body']],['a','b'])

    def test_injury_backup_same_surname_uses_correct_ids(self):
        import injury_status as IS
        L=fixture();a=player(L,'a');b=player(L,'b');a.name='Mike Smith';b.name='John Smith'
        plain=IS.hurt_words(L,L.teams['GB'],a,'questionable')
        self.assertNotIn('\x1e',plain)
        m=IB.post(L,'injury','Report',IS.hurt_words(L,L.teams['GB'],a,'questionable',mentions=True))
        self.assertEqual([r['id'] for r in m['mentions']['body']],['a','b'])

    def test_ids_survive_reload_and_duplicates_need_context(self):
        L=fixture();a=player(L,'a');b=player(L,'b');a.name=b.name='Mike Smith'
        before=copy.deepcopy(L.save())
        self.assertEqual(IB.entity_references(L,'Mike Smith'),[])
        self.assertEqual(L.save(),before)
        m=IB.post(L,'league','Mike Smith joins Green Bay','Mike Smith signed.',payload={'pid':'b'})
        self.assertEqual({(r['kind'],r['id']) for r in m['entities']},{('player','b'),('team','GB')})
        loaded=League.load(L.save())
        self.assertEqual(loaded.inbox[0]['entities'],m['entities'])
    def test_directory_refresh_and_cached_page_reads(self):
        L=fixture();player(L,'p').name='Jordan Love'
        catalog=IB.entity_catalog(L)
        self.assertIsNone(IB.entity_catalog(L,catalog['key']))
        self.assertIs(IB.entity_catalog(L),catalog)
        player(L,'rookie').name='New Prospect'
        self.assertIsNotNone(IB.entity_catalog(L,catalog['key']))
        self.assertEqual(IB.entity_references(L,'New Prospect arrived.')[0]['id'],'rookie')
    def test_boundaries_and_literal_markup(self):
        L=fixture();player(L,'p').name='A. <Test>'
        self.assertEqual(IB.entity_references(L,'A. <Test> arrived')[0]['id'],'p')
        self.assertEqual(IB.entity_references(L,'NotGreen Baytown'),[])
if __name__=='__main__':unittest.main()
