"""Strict interpretation tests for owned fixture results, not live source health.

Test classification: component
Review status: Not Reviewed
Evidence: synthetic
Scope: the probe PromQL filter, the strict result decoder and the fixture Compose
argv/env with synthetic payloads; it does not start Docker, Prometheus or the
blackbox exporter.
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any
from unittest.mock import patch

from tests import tdm_probe_runtime as probe
from tests.fixtures import tdm_health


class ListenerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample: Any = {
            "metric": dict(probe.LABELS, __name__="probe_success"),
            "value": [1800000000, "1"],
        }
        self.payload: Any = {
            "status": "success",
            "data": {"resultType": "vector", "result": [self.sample]},
        }

    def test_available_and_observed_failure_are_distinct(self) -> None:
        self.assertEqual(probe.decode(self.payload), "available")
        self.sample["value"][1] = "0"
        self.assertEqual(probe.decode(self.payload), "probe-failed")

    def test_absent_or_duplicate_is_unknown(self) -> None:
        self.payload["data"]["result"] = []
        self.assertEqual(probe.decode(self.payload), "unknown")
        self.payload["data"]["result"] = [self.sample, copy.deepcopy(self.sample)]
        self.assertEqual(probe.decode(self.payload), "unknown")

    def test_wrong_or_private_labels_are_rejected(self) -> None:
        for key, value in [
            ("source", "live"),
            ("instance", "http://foreign/health"),
            ("customer", "synthetic"),
        ]:
            with self.subTest(key=key):
                payload = copy.deepcopy(self.payload)
                payload["data"]["result"][0]["metric"][key] = value
                self.assertEqual(probe.decode(payload), "unknown")

    def test_invalid_nonfinite_and_nonbinary_values_are_unknown(self) -> None:
        for value in ["NaN", "Inf", "-1", "0.5", "bad", None]:
            self.sample["value"][1] = value
            self.assertEqual(probe.decode(self.payload), "unknown")

    def test_malformed_value_pairs_are_unknown(self) -> None:
        for pair in ["11", [1], [float("nan"), "1"], [True, "1"], [1, 1], [1, "1", 2]]:
            self.sample["value"] = pair
            self.assertEqual(probe.decode(self.payload), "unknown")

    def test_incomplete_or_malformed_query_is_unknown(self) -> None:
        for payload in [
            {},
            {"status": "error"},
            {"status": "success", "data": []},
            {"status": "success", "data": {"resultType": "scalar"}},
        ]:
            self.assertEqual(probe.decode(payload), "unknown")
        for key in ["warnings", "infos"]:
            payload = copy.deepcopy(self.payload)
            payload[key] = ["incomplete synthetic query"]
            self.assertEqual(probe.decode(payload), "unknown")

    def test_exporter_query_connection_failure_is_unknown(self) -> None:
        with patch.object(probe, "query", side_effect=TimeoutError):
            self.assertEqual(probe.observation(), "unknown")

    def test_no_remote_target_or_case_injection(self) -> None:
        with patch("observability.docker.subprocess.run") as run:
            with self.assertRaises(ValueError):
                probe.compose("up", case="http://foreign")
            run.assert_not_called()

    def test_compose_is_bounded_local_and_fixed_project(self) -> None:
        with (
            patch.dict(
                os.environ, {"DOCKER_CONTEXT": "remote", "COMPOSE_PROFILES": "other"}
            ),
            patch("observability.docker.subprocess.run") as run,
        ):
            probe.compose("down", "--timeout", "5")
            args, kwargs = run.call_args
            self.assertIn("--host=unix:///var/run/docker.sock", args[0])
            self.assertIn("rrdplat35-fixture", args[0])
            self.assertIn("fixture-only", args[0])
            self.assertNotIn("DOCKER_CONTEXT", kwargs["env"])
            self.assertNotIn("COMPOSE_PROFILES", kwargs["env"])
            self.assertEqual(kwargs["timeout"], 60)

    def test_known_filter_uses_shared_freshness_limits(self) -> None:
        self.assertIn("<= 45)", probe.KNOWN)
        self.assertIn(">= -5)", probe.KNOWN)
        self.assertNotIn("or vector(0)", probe.KNOWN)
        selector = (
            '{job="tdm-listener-fixture",instance="tdm-fixture",'
            'service="tdm",source="synthetic-fixture"}'
        )
        self.assertEqual(probe.SUCCESS, "probe_success" + selector)
        self.assertEqual(probe.KNOWN.count("time() - timestamp("), 6)

    def test_driver_and_fixture_share_one_case_list(self) -> None:
        with patch("observability.docker.subprocess.run") as run:
            for case in tdm_health.CASES:
                probe.compose("config", case=case)
                self.assertEqual(run.call_args.kwargs["env"]["FIXTURE_CASE"], case)
        with self.assertRaises(ValueError):
            tdm_health.handler_for("unlisted")


if __name__ == "__main__":
    unittest.main()
