"""Public exchange rates: validation, request bounds and offline fallback."""
import json
import unittest
from unittest import mock
from hoard import exchange


class Exchange(unittest.TestCase):
    def setUp(self):
        self.patch = mock.patch.multiple(exchange, _cache=None, _checked=0, _retry_after=0)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_cache_and_stale_fallback(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.iter_content.return_value = [json.dumps({"base":"EUR", "date":"2026-11-13", "rates":{"USD":1.1,"JPY":160}}).encode()]
        with mock.patch.object(exchange.requests, "get", return_value=response) as get, mock.patch.object(exchange.time, "monotonic", return_value=100):
            first = exchange.latest()
            self.assertFalse(first["stale"])
            self.assertEqual(first["rates"]["EUR"], 1)
            self.assertEqual(exchange.latest(), first)
            self.assertEqual(get.call_count, 1)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        with mock.patch.object(exchange.requests, "get", side_effect=exchange.requests.ConnectionError) as get, mock.patch.object(exchange.time, "monotonic", return_value=5000):
            self.assertTrue(exchange.latest()["stale"])
            self.assertTrue(exchange.latest()["stale"])
            self.assertEqual(get.call_count, 1)

    def test_failed_first_fetch_reports_unavailable_and_backs_off(self):
        with mock.patch.object(exchange.requests, "get", side_effect=exchange.requests.ConnectionError) as get:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "Original prices"):
                    exchange.latest()
            self.assertEqual(get.call_count, 1)

    def test_invalid_rates_are_not_used(self):
        for raw in ({}, {"base":"USD","date":"2026-11-13","rates":{"EUR":1}},
                    {"base":"EUR","date":"2026-11-13","rates":{"USD":float("nan"),"JPY":-1,"GBP":True}}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                exchange.validate(raw)
