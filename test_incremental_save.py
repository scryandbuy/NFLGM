import copy
import json
import unittest

from incremental_save import Snapshot, record_id


def apply(store, snapshot):
    if snapshot['reset']: store.clear()
    for key in snapshot['deletes']: store.pop(key, None)
    store.update(snapshot['puts'])


def assemble(store):
    def read(parts): return json.loads(store[record_id(parts)]['text'])
    data = {}
    for name, kind, keys in json.loads(store['@roots']['text']):
        if kind == 'dict': data[name] = {key:read([name, key]) for key in keys}
        elif kind == 'list': data[name] = [v for i in range(keys) for v in read([name,i])]
        else: data[name] = read([name])
    return data


class IncrementalSaveTests(unittest.TestCase):
    def setUp(self):
        self.data = dict(year=2030, _stop=['week',4], players={
            'one':dict(xp=100, ratings={'awareness':80}, history=['old']),
            'two':dict(xp=200, ratings={'awareness':90})},
            transactions=[dict(i=i) for i in range(130)],
            stats={2029:{'one':dict(yards=121.5)}}, flags={}, nothing=None,
            empty=[], unicode={'Jos\u00e9 \U0001f3c8': ['\u96ea', False]},
            keys={None:0, True:1, 2.5:2})
        self.writer=Snapshot();self.store={}
        self.capture()

    def capture(self):
        snap=json.loads(self.writer.prepare(self.data, str))
        apply(self.store,snap)
        self.assertEqual(assemble(self.store),json.loads(json.dumps(self.data)))
        return snap

    def test_one_changed_player_only_and_no_mutation(self):
        unchanged=self.capture();self.assertFalse(unchanged['reset']);self.assertEqual(unchanged['puts'],{})
        self.data['players']['one']['ratings']['awareness'] += 1
        before=copy.deepcopy(self.data)
        snap=self.capture()
        self.assertEqual(list(snap['puts']),[record_id(['players','one'])])
        self.assertEqual(before,self.data)

    def test_appends_deletes_reordering_and_changed_container_types(self):
        self.data['transactions'].append({'trade':True})
        snap=self.capture();self.assertEqual(list(snap['puts']),[record_id(['transactions',2])])
        del self.data['players']['two'];self.data['players']['three']={'xp':0}
        del self.data['transactions'][15:]
        self.data['flags']=['now','a','list'];self.data.pop('nothing')
        self.capture()
        self.data['players']=dict(reversed(list(self.data['players'].items())))
        self.capture()

    def test_resume_and_calendar_delta_preserve_history(self):
        meta=dict(epoch=self.writer.epoch,revision=self.writer.revision,
                  marker=self.writer.marker,hashes=dict(self.writer.hashes))
        self.writer=Snapshot(meta)
        self.assertEqual(self.capture()['puts'],{})
        self.data['_stop']=['week',5]
        delta=self.capture();self.assertFalse(delta['reset'])
        self.assertEqual(set(delta['puts']),{record_id(['_stop',0])})
        self.data['year']+=1
        self.data['_stop']=['offseason',1]
        self.data['stats'][2030]={'one':{'yards':900}}
        del self.data['players']['two']
        delta=self.capture();self.assertFalse(delta['reset'])
        self.assertIn(record_id(['players','two']),delta['deletes'])
        self.assertNotIn(record_id(['stats','2029']),delta['puts'])
        # Explicit recovery replaces the baseline even across a calendar change.
        self.writer=Snapshot()
        checkpoint=self.capture();self.assertTrue(checkpoint['reset'])
        self.assertEqual(set(checkpoint['puts']),set(self.store))

    def test_failed_encoder_does_not_advance_baseline(self):
        revision=self.writer.revision;hashes=dict(self.writer.hashes)
        self.data['unsupported']=object()
        def fail(value): raise ValueError('encoding failed')
        with self.assertRaises(ValueError):self.writer.prepare(self.data,fail)
        self.assertEqual(self.writer.revision,revision)
        self.assertEqual(self.writer.hashes,hashes)
        del self.data['unsupported'];self.capture()

    def test_fingerprints_do_not_retain_full_snapshot(self):
        for i in range(100):
            self.data['players']['one']['xp']=i
            self.capture()
        self.assertEqual(len(self.writer.hashes),len(self.store))
        self.assertTrue(all(isinstance(v,str) and len(v)==64 for v in self.writer.hashes.values()))


class SessionSnapshotTests(unittest.TestCase):
    def test_contract_action_and_extended_json_round_trip(self):
        import numpy as np
        from session import Session
        from league import League
        from cap_engine import Contract
        from test_cap_accounting import fixture, player
        league=fixture()
        p=player(league,contract=Contract(3,[10]*3,signing_bonus=6))
        s=Session(league,np.random.default_rng(7),'GB')
        league.stats[league.year]={'p':{'yards':np.int64(81),'rate':np.float64(2.5),
                                      'array':np.array([1,2]),'flags':{'a','b'}}}
        s.gameday={'flag':np.bool_(True)}
        store={};before=copy.deepcopy(s.rng.bit_generator.state)
        apply(store,json.loads(s.save_incremental()))
        old_base=list(p.contract.base)
        result=s.frontoffice_act('restructure',pid=p.pid,amount=1)
        self.assertTrue(result['ok'],result)
        self.assertNotEqual(old_base,p.contract.base)
        apply(store,json.loads(s.save_incremental()))
        expected=json.loads(s.save())
        self.assertEqual(assemble(store),expected)
        self.assertEqual(before,s.rng.bit_generator.state)
        # Loading both representations must restore identical contracts/cap.
        a=League.load(json.dumps(assemble(store)))
        b=League.load(json.dumps(expected))
        self.assertEqual(a.player(p.pid).contract.base,b.player(p.pid).contract.base)
        self.assertEqual(a.teams['GB'].cap_space,b.teams['GB'].cap_space)


if __name__=='__main__':unittest.main()
