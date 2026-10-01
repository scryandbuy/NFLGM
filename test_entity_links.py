import copy,time,unittest
import inbox as IB
from league import League
from test_cap_accounting import fixture,player

class EntityLinkTests(unittest.TestCase):
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
