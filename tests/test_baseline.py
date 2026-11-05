"""Owned synthetic API fixtures: never presented as actual component health."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('baseline', Path(__file__).resolve().parents[1] / 'scripts/baseline.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
NOW = 1800000000


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.target = {'labels': {'job': 'baseline', 'instance': 'localhost:9090'},
                       'health': 'up', 'lastScrape': self.stamp(NOW - 1)}
        self.targets = {'status': 'success', 'data': {'activeTargets': [self.target]}}
        self.query = {'status': 'success', 'data': {'resultType': 'vector', 'result': [
            {'metric': copy.deepcopy(self.target['labels']), 'value': [NOW, str(NOW - 1)]}]}}

    @staticmethod
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()

    def get(self, path):
        if path == '/-/ready':
            return b'Prometheus Server is Ready.\n'
        return json.dumps(self.targets if path == '/api/v1/targets' else self.query).encode()

    def status(self):
        return baseline.assess(self.get, NOW)['status']

    def test_healthy_requires_all_checks(self):
        self.assertEqual(self.status(), 'healthy')

    def test_connection_failure(self):
        def unavailable(path):
            raise TimeoutError()
        self.assertEqual(baseline.assess(unavailable, NOW)['status'], 'unavailable')

    def test_partial_scrape_failure(self):
        self.target['health'] = 'down'
        self.assertEqual(self.status(), 'partial')

    def test_stale_scrape(self):
        self.target['lastScrape'] = self.stamp(NOW - 46)
        self.assertEqual(self.status(), 'stale')

    def test_stale_sample_despite_fresh_target(self):
        self.query['data']['result'][0]['value'][1] = str(NOW - 46)
        self.assertEqual(self.status(), 'stale')

    def test_missing_targets_and_samples_are_unknown(self):
        self.targets['data']['activeTargets'] = []
        self.assertEqual(self.status(), 'unknown')
        self.targets['data']['activeTargets'] = [self.target]
        self.query['data']['result'] = []
        self.assertEqual(self.status(), 'unknown')

    def test_extra_or_foreign_target_is_unknown(self):
        self.targets['data']['activeTargets'].append(copy.deepcopy(self.target))
        self.assertEqual(self.status(), 'unknown')
        self.targets['data']['activeTargets'].pop()
        self.target['labels']['job'] = 'customer'
        self.assertEqual(self.status(), 'unknown')

    def test_malformed_api_is_unknown(self):
        self.targets = {}
        self.assertEqual(self.status(), 'unknown')

    def test_nonfinite_or_future_sample_is_unknown(self):
        for value in ['NaN', 'Inf', str(NOW + 6)]:
            with self.subTest(value=value):
                self.query['data']['result'][0]['value'][1] = value
                self.assertEqual(self.status(), 'unknown')

    def test_warning_is_unknown(self):
        self.query['warnings'] = ['partial query']
        self.assertEqual(self.status(), 'unknown')

    def test_bad_clock_is_unknown(self):
        self.target['lastScrape'] = self.stamp(NOW + 6)
        self.assertEqual(self.status(), 'unknown')

    def test_query_failure_is_unknown(self):
        self.query['status'] = 'error'
        self.assertEqual(self.status(), 'unknown')

    def test_query_source_must_match(self):
        self.query['data']['result'][0]['metric']['job'] = 'other'
        self.assertEqual(self.status(), 'unknown')

    def test_readiness_body_is_verified(self):
        self.assertEqual(baseline.assess(lambda _: b'ok', NOW)['status'], 'unavailable')

    def test_entire_slow_http_exchange_is_bounded(self):
        with patch.object(baseline, 'HTTP_TIMEOUT', 0.05), patch.object(baseline, 'build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.side_effect = lambda _: time.sleep(1)
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                baseline.fetch('/-/ready')
            self.assertLess(time.monotonic() - started, 0.5)

    def test_redirects_rejected(self):
        with self.assertRaises(ValueError):
            baseline.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org')

    def test_lifecycle_bounded_and_local(self):
        with patch.object(baseline.subprocess, 'run') as run:
            baseline.compose('down', '--timeout', '10')
            args, kwargs = run.call_args
            self.assertIn('--host=unix:///var/run/docker.sock', args[0])
            self.assertNotIn('--volumes', args[0])
            self.assertEqual(kwargs['timeout'], 60)
            self.assertTrue(kwargs['check'])


if __name__ == '__main__':
    unittest.main()
