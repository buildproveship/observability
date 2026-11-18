"""Opt-in synthetic adapter verification, never a live TDM health command.

Test classification: e2e
Review status: Not Reviewed
Evidence: synthetic
Scope: drives the real pinned Prometheus and blackbox exporter against the owned
synthetic TDM listener fixture through Docker; it never contacts a live TDM source.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from typing import Any

from observability import prometheus
from observability.docker import ROOT, ComposeProject, inspect
from observability.prometheus import MAX_AGE_SECONDS, MAX_FUTURE_SKEW_SECONDS
from tests.fixtures.tdm_health import CASES

PORT = 19091
FILES = (ROOT / "compose.probes.fixture.yaml",)
LABELS = {
    "job": "tdm-listener-fixture",
    "instance": "tdm-fixture",
    "service": "tdm",
    "source": "synthetic-fixture",
}
SELECTOR = "{" + ",".join(f'{key}="{value}"' for key, value in LABELS.items()) + "}"
SUCCESS = "probe_success" + SELECTOR
DURATION = "probe_duration_seconds" + SELECTOR
UP = "up" + SELECTOR
# Filtering retains zero-valued observed failures; no `or vector(0)` fallback.
KNOWN = SUCCESS
for metric in (SUCCESS, DURATION, UP):
    KNOWN += f" and (time() - timestamp({metric}) <= {MAX_AGE_SECONDS})"
    KNOWN += f" and (time() - timestamp({metric}) >= -{MAX_FUTURE_SKEW_SECONDS})"
KNOWN += f" and ({UP} == 1) and ({DURATION} >= 0)"
RETAINED = {"probe_success", "probe_duration_seconds", "up"}
TIMEOUT_PROBE_SECONDS = (1.5, 3.0)


def _require(condition: bool, detail: object) -> None:
    if not condition:
        raise AssertionError(detail)


def compose(
    *args: str, case: str = "available", profile: bool = True, timeout: float = 60
) -> str:
    """Run Compose for the fixed fixture project with one known synthetic case."""
    if case not in CASES:
        raise ValueError("Unknown synthetic case")
    project = ComposeProject(
        "rrdplat35-fixture",
        FILES,
        ("fixture-only",) if profile else (),
        {"FIXTURE_CASE": case},
    )
    return project.run(*args, timeout=timeout, capture=True)


def query(expression: str, at: float | None = None) -> Any:
    return prometheus.query(PORT, expression, at)


def _probe_value(payload: Any) -> float:
    if (
        payload["status"] != "success"
        or payload.get("warnings")
        or payload.get("infos")
    ):
        raise ValueError("query unsuccessful or incomplete")
    samples = payload["data"]["result"]
    if payload["data"]["resultType"] != "vector" or len(samples) != 1:
        raise ValueError("missing or ambiguous sample")
    if samples[0]["metric"] != dict(LABELS, __name__="probe_success"):
        raise ValueError("unexpected sample labels")
    match samples[0]["value"]:
        case [int() | float() as stamp, str() as raw] if type(
            stamp
        ) is not bool and math.isfinite(stamp):
            value = float(raw)
        case _:
            raise ValueError("malformed value pair")
    if value not in (0, 1):
        raise ValueError("non-binary probe value")
    return value


def decode(payload: Any) -> str:
    """Strict test/CLI interpretation of the freshness-filtered PromQL result."""
    try:
        value = _probe_value(payload)
    except (KeyError, TypeError, ValueError, IndexError):
        return "unknown"
    return "available" if value == 1 else "probe-failed"


def observation(at: float | None = None) -> str:
    try:
        return decode(query(KNOWN, at))
    except (OSError, ValueError):
        return "unknown"


def wait_for(expected: str, after: float = 0, timeout: float = 25) -> str:
    deadline = time.monotonic() + timeout
    state = "unknown"
    while time.monotonic() < deadline:
        state = observation()
        try:
            stamps = query("timestamp(" + SUCCESS + ")")["data"]["result"]
            fresh = len(stamps) == 1 and float(stamps[0]["value"][1]) >= after
        except (OSError, ValueError, KeyError, IndexError):
            fresh = False
        if state == expected and (expected == "unknown" or fresh):
            return state
        time.sleep(0.5)
    raise AssertionError(f"Expected {expected}, last state {state}")


def validate() -> None:
    services = compose("config", "--services", profile=False).strip()
    _require(not services, "profile must default off")
    compose("config", "--quiet")
    compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "/bin/promtool",
        "prometheus-fixture",
        "check",
        "config",
        "/etc/prometheus/prometheus.yml",
    )
    compose(
        "run",
        "--rm",
        "--no-deps",
        "blackbox-fixture",
        "--config.file=/config/tdm-listener.yml",
        "--config.check",
    )
    print(
        "default-off profile, promtool and blackbox config validation passed",
        flush=True,
    )


def _check_isolation() -> None:
    config = json.loads(compose("config", "--format", "json"))
    for name, service in config["services"].items():
        _require("@sha256:" in service["image"], name)
        if name != "prometheus-fixture":
            _require(not service.get("ports"), name)
    ports = inspect("rrdplat35-fixture-prometheus-fixture-1")["NetworkSettings"][
        "Ports"
    ]
    expected = {"9090/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
    _require(ports == expected, ports)


def _check_cases() -> None:
    for case in CASES:
        compose(
            "up",
            "-d",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "20",
            "tdm-health-fixture",
            case=case,
        )
        changed_at = time.time()
        expected = "available" if case == "available" else "probe-failed"
        wait_for(expected, after=changed_at)
        if case == "timeout":
            duration = float(query(DURATION)["data"]["result"][0]["value"][1])
            low, high = TIMEOUT_PROBE_SECONDS
            _require(low <= duration <= high, duration)
        result = {
            "fixture_case": case,
            "observed": expected,
            "source": "synthetic-fixture",
        }
        print(json.dumps(result), flush=True)


def _check_labels_and_staleness() -> None:
    samples = query('{job="tdm-listener-fixture"}')["data"]["result"]
    names = {s["metric"]["__name__"] for s in samples}
    _require(names >= RETAINED, names)
    # Prometheus generates a fixed set of scrape bookkeeping metrics itself.
    _require(all(n in RETAINED or n.startswith("scrape_") for n in names), names)
    labels = [
        {k: v for k, v in s["metric"].items() if k != "__name__"} for s in samples
    ]
    _require(all(found == LABELS for found in labels), samples)
    absent = SUCCESS.replace("tdm-listener-fixture", "absent-fixture")
    _require(not query(absent)["data"]["result"], "absent source returned samples")
    absent_known = KNOWN.replace("tdm-listener-fixture", "absent-fixture")
    _require(decode(query(absent_known)) == "unknown", "absent source not unknown")
    # Simulated evaluation instant against real stored fixture samples.
    stale_at = time.time() + MAX_AGE_SECONDS + 1
    _require(observation(at=stale_at) == "unknown", "stale evaluation not unknown")


def runtime() -> None:
    try:
        compose("up", "-d", "--wait", "--wait-timeout", "30")
        wait_for("available")
        _check_isolation()
        _check_cases()
        compose(
            "up",
            "-d",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "20",
            "tdm-health-fixture",
        )
        wait_for("available", after=time.time())
        _check_labels_and_staleness()
        print(
            "fixed labels, metric allowlist, absent-source and simulated stale-time "
            "checks passed",
            flush=True,
        )
        compose("stop", "--timeout", "5", "blackbox-fixture")
        wait_for("unknown")
        print("exporter stopped => unknown (not healthy zero)", flush=True)
    finally:
        compose("down", "--timeout", "5")
    _require(observation() == "unknown", "stopped backend not unknown")
    print(
        "query backend stopped => unknown; task containers/networks removed", flush=True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["validate", "test", "start", "status", "stop"]
    )
    action = parser.parse_args().action
    if action == "validate":
        validate()
    elif action == "test":
        runtime()
    elif action == "start":
        compose("up", "-d", "--wait", "--wait-timeout", "30")
        wait_for("available")
        print("synthetic-fixture available; no live TDM source")
    elif action == "stop":
        compose("down", "--timeout", "5")
    else:
        state = observation()
        print(json.dumps({"source": "synthetic-fixture", "state": state}))
        return 0 if state == "available" else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        sys.exit(1)
