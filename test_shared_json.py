import io
import json
import math
import struct
import unittest
import weakref
from unittest.mock import patch

import shared_json


class SharedJsonTests(unittest.TestCase):
    def test_exact_values_and_serialized_output(self):
        text = '{"rows":[{"text":"José 🏈","v":-0.0,"flag":true,"none":null},' \
               '{"v":0.0,"large":123456789012345678901234567890,"fraction":1.2345678901234567}],' \
               '"nested":[[1.0,1, false,"escape\\n\\\""]],"empty":{},"list":[]}'
        expected = json.loads(text)
        for actual in (shared_json.loads(text), shared_json.load(io.StringIO(text))):
            self.assertEqual(json.dumps(actual), json.dumps(expected))
            self.assertEqual(math.copysign(1, actual['rows'][0]['v']), -1)
            self.assertEqual(type(actual['rows'][1]['large']), int)

    def test_duplicates_share_only_immutable_values(self):
        line = dict(name='a repeated long player name', rating=82.12345, observations=['Film assessment'])
        data = shared_json.loads(json.dumps([line, line]))
        self.assertIsNot(data[0], data[1])
        self.assertIsNot(data[0]['observations'], data[1]['observations'])
        self.assertIs(data[0]['name'], data[1]['name'])
        self.assertIs(data[0]['rating'], data[1]['rating'])
        self.assertIs(data[0]['observations'][0], data[1]['observations'][0])
        data[0]['rating'] += 1
        data[0]['observations'].append('Visit')
        self.assertEqual(data[1], line)
        other = shared_json.loads(json.dumps([line]))
        self.assertIsNot(data[1]['name'], other[0]['name'])
        self.assertIsNot(data[1]['rating'], other[0]['rating'])

    def test_float_bits_types_nonfinite_and_errors(self):
        text = '[0.0,-0.0,1.0,1,true,NaN,Infinity,-Infinity,5e-324,1.7976931348623157e308]'
        expected, actual = json.loads(text), shared_json.loads(text)
        for a, b in zip(expected, actual):
            self.assertEqual(type(a), type(b))
            if isinstance(a, float): self.assertEqual(struct.pack('!d', a), struct.pack('!d', b))
            else: self.assertEqual(a, b)
        with self.assertRaises(json.JSONDecodeError): shared_json.loads('{bad')

    def test_dictionary_children_are_not_revisited_at_each_ancestor(self):
        original = shared_json._Values.object
        count = []
        def counted(self, record):
            count.append(1)
            return original(self, record)
        with patch.object(shared_json._Values, 'object', counted):
            shared_json.loads('{"outer":{"mid":{"inner":[{"v":42.1}]}}}')
        self.assertEqual(len(count), 4)

    def test_decode_pool_is_released_after_success_and_failure(self):
        refs = []
        class Probe(shared_json._Values):
            __slots__ = ('__weakref__',)
            def __init__(self):
                super().__init__()
                refs.append(weakref.ref(self))
        with patch.object(shared_json, '_Values', Probe):
            result = shared_json.loads('{"value":"saved history"}')
            self.assertEqual(result, {'value':'saved history'})
            with self.assertRaises(json.JSONDecodeError): shared_json.loads('{bad')
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(ref() is None for ref in refs))


if __name__ == '__main__': unittest.main()
