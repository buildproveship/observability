"""Owned synthetic API fixtures: never presented as actual component health.

Test classification: component
Review status: Not Reviewed
Evidence: synthetic
Scope: the baseline health assessment against synthetic Prometheus API payloads,
the loopback HTTP reader against a real in-process HTTP server, and the Compose
argv/env; it does not start Docker or Prometheus.
"""

from __future__ import annotations

import copy
import json
import threading
import time
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from observability import baseline, docker, prometheus

NOW = 1800000000


@contextmanager
def loopback_server(handler: type[BaseHTTPRequestHandler]) -> Iterator[int]:
    server = ThreadingHTTPServer((prometheus.LOOPBACK, 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        """Keep test output clean."""


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target: dict[str, Any] = {
            "labels": dict(baseline.SELF_SOURCE),
            "health": "up",
            "lastScrape": self.stamp(NOW - 1),
        }
        self.targets: Any = {
            "status": "success",
            "data": {"activeTargets": [self.target]},
        }
        sample = {"metric": dict(baseline.SELF_SOURCE), "value": [NOW, str(NOW - 1)]}
        self.query: dict[str, Any] = {
            "status": "success",
            "data": {"resultType": "vector", "result": [sample]},
        }

    @staticmethod
    def stamp(value: float) -> str:
        return datetime.fromtimestamp(value, UTC).isoformat()

    def get(self, path: str) -> bytes:
        if path == "/-/ready":
            return b"Prometheus Server is Ready.\n"
        if path == "/api/v1/targets":
            return json.dumps(self.targets).encode()
        self.assertEqual(path, baseline.SAMPLE_PATH)
        return json.dumps(self.query).encode()

    def status(self) -> str:
        status: str = baseline.assess(self.get, NOW)["status"]
        return status

    def test_healthy_requires_all_checks(self) -> None:
        self.assertEqual(self.status(), "healthy")

    def test_prometheus_nanosecond_utc_timestamp_is_parsed(self) -> None:
        self.target["lastScrape"] = "2027-01-15T08:00:00.123456789Z"
        result = baseline.assess(self.get, 1800000000.5)
        self.assertEqual(result["status"], "healthy")
        self.assertAlmostEqual(result["scrape_age_seconds"], 0.377, places=3)

    def test_connection_failure(self) -> None:
        def unavailable(_path: str) -> bytes:
            raise TimeoutError

        self.assertEqual(baseline.assess(unavailable, NOW)["status"], "unavailable")

    def test_partial_scrape_failure(self) -> None:
        self.target["health"] = "down"
        self.assertEqual(self.status(), "partial")

    def test_stale_scrape(self) -> None:
        self.target["lastScrape"] = self.stamp(NOW - 46)
        self.assertEqual(self.status(), "stale")

    def test_stale_sample_despite_fresh_target(self) -> None:
        self.query["data"]["result"][0]["value"][1] = str(NOW - 46)
        self.assertEqual(self.status(), "stale")

    def test_missing_targets_and_samples_are_unknown(self) -> None:
        self.targets["data"]["activeTargets"] = []
        self.assertEqual(self.status(), "unknown")
        self.targets["data"]["activeTargets"] = [self.target]
        self.query["data"]["result"] = []
        self.assertEqual(self.status(), "unknown")

    def test_extra_or_foreign_target_is_unknown(self) -> None:
        self.targets["data"]["activeTargets"].append(copy.deepcopy(self.target))
        self.assertEqual(self.status(), "unknown")
        self.targets["data"]["activeTargets"].pop()
        self.target["labels"]["job"] = "customer"
        self.assertEqual(self.status(), "unknown")

    def test_malformed_api_is_unknown(self) -> None:
        for malformed in [{}, [], {"status": "success", "data": None}, "text"]:
            with self.subTest(malformed=malformed):
                self.targets = malformed
                self.assertEqual(self.status(), "unknown")

    def test_nonfinite_or_future_sample_is_unknown(self) -> None:
        for value in ["NaN", "Inf", str(NOW + 6)]:
            with self.subTest(value=value):
                self.query["data"]["result"][0]["value"][1] = value
                self.assertEqual(self.status(), "unknown")

    def test_warning_is_unknown(self) -> None:
        self.query["warnings"] = ["partial query"]
        self.assertEqual(self.status(), "unknown")

    def test_bad_clock_is_unknown(self) -> None:
        self.target["lastScrape"] = self.stamp(NOW + 6)
        self.assertEqual(self.status(), "unknown")

    def test_query_failure_is_unknown(self) -> None:
        self.query["status"] = "error"
        self.assertEqual(self.status(), "unknown")

    def test_query_source_must_match(self) -> None:
        self.query["data"]["result"][0]["metric"]["job"] = "other"
        self.assertEqual(self.status(), "unknown")

    def test_readiness_body_is_verified(self) -> None:
        self.assertEqual(baseline.assess(lambda _: b"ok", NOW)["status"], "unavailable")

    def test_programming_errors_are_not_reported_as_health(self) -> None:
        def broken(_path: str) -> bytes:
            raise RuntimeError

        with self.assertRaises(RuntimeError):
            baseline.assess(broken, NOW)


class LoopbackReadTests(unittest.TestCase):
    def test_reads_ok_response(self) -> None:
        class Ok(Quiet):
            def do_GET(self) -> None:
                body = b"Prometheus Server is Ready."
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with loopback_server(Ok) as port:
            self.assertEqual(prometheus.fetch(port, "/-/ready"), b"Prometheus Server is Ready.")

    def test_redirects_are_not_followed(self) -> None:
        followed: list[str] = []

        class Redirect(Quiet):
            def do_GET(self) -> None:
                if self.path == "/elsewhere":
                    followed.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()

        with loopback_server(Redirect) as port, self.assertRaises(ValueError):
            prometheus.fetch(port, "/-/ready")
        self.assertEqual(followed, [])

    def test_oversized_response_is_rejected(self) -> None:
        class Oversized(Quiet):
            def do_GET(self) -> None:
                body = b" " * (prometheus.RESPONSE_LIMIT_BYTES + 1)
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with loopback_server(Oversized) as port, self.assertRaises(ValueError):
            prometheus.fetch(port, "/api/v1/targets")

    def test_entire_slow_http_exchange_is_bounded(self) -> None:
        # Each byte arrives within the per-socket timeout; only the whole-exchange
        # deadline can stop the read.
        class Trickle(Quiet):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The client gave up at its deadline, as intended.

        with (
            loopback_server(Trickle) as port,
            patch.object(prometheus, "HTTP_TIMEOUT_SECONDS", 0.2),
        ):
            started = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "deadline"):
                prometheus.fetch(port, "/-/ready")
            self.assertLess(time.monotonic() - started, 1)


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_bounded_and_local(self) -> None:
        remote = {"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "tcp://remote:2376"}
        with (
            patch.dict(docker.os.environ, remote),
            patch.object(docker.subprocess, "run") as run,
        ):
            baseline.PROJECT.run("down", "--timeout", "10")
        args, kwargs = run.call_args
        self.assertIn("--host=unix:///var/run/docker.sock", args[0])
        self.assertIn("rrdplat34-local", args[0])
        self.assertNotIn("--volumes", args[0])
        self.assertNotIn("DOCKER_CONTEXT", kwargs["env"])
        self.assertNotIn("DOCKER_HOST", kwargs["env"])
        self.assertEqual(kwargs["timeout"], 60)
        self.assertTrue(kwargs["check"])


if __name__ == "__main__":
    unittest.main()
