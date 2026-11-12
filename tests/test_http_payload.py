"""Regress opaque model JSON versus API object serialization."""
import json
import unittest

from companion_runtime.http_payload import encode_http_body


class HttpPayloadTests(unittest.TestCase):
    def test_model_json_bytes_are_not_quoted_or_serialized_twice(self):
        resource = b'{"FileReferences":{"Moc":"r0001.moc3"}}'
        self.assertEqual(encode_http_body(resource, 'application/json'), resource)
        self.assertEqual(json.loads(encode_http_body(bytearray(resource), 'application/json')), json.loads(resource))

    def test_api_values_remain_json_with_readable_unicode(self):
        encoded = encode_http_body({'message': '你好', 'ready': True}, 'application/json; charset=utf-8')
        self.assertEqual(json.loads(encoded), {'message': '你好', 'ready': True})
        self.assertIn('你好'.encode(), encoded)

    def test_nonfinite_json_and_nontext_binary_payloads_are_rejected(self):
        with self.assertRaises(ValueError):encode_http_body({'time': float('nan')}, 'application/json')
        with self.assertRaises(TypeError):encode_http_body({'not': 'an image'}, 'image/png')


if __name__ == '__main__':unittest.main()
