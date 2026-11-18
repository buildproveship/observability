"""Bounded local lifecycle and point-in-time checks; not a telemetry backend."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from observability.docker import ROOT, ComposeProject
from observability.prometheus import MAX_AGE_SECONDS, MAX_FUTURE_SKEW_SECONDS, fetch

if TYPE_CHECKING:
    from collections.abc import Callable

PORT = 19090
PROJECT = ComposeProject("rrdplat34-local", (ROOT / "compose.yaml",))
SELF_SOURCE = {"job": "baseline", "instance": "localhost:9090"}
READY_BODY = b"Prometheus Server is Ready."
SAMPLE_PATH = "/api/v1/query?" + urlencode({"query": 'timestamp(up{job="baseline"})'})
# Every way a read or an unexpected response shape can fail; anything else is a bug.
OBSERVATION_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError)
START_WAIT_SECONDS = 45
PROMTOOL_CHECK = (
    "run", "--rm", "--no-deps", "--entrypoint", "/bin/promtool", "prometheus",
    "check", "config", "/etc/prometheus/prometheus.yml",
)


def _get(path: str) -> bytes:
    return fetch(PORT, path)


def _age(now: float, stamp: float, clock: str) -> float:
    age = now - stamp
    if not math.isfinite(age) or age < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError(f"invalid {clock} clock")
    return age


def _self_target(targets: Any) -> Any:
    if targets["status"] != "success":
        raise ValueError("targets API failed")
    active = targets["data"]["activeTargets"]
    if len(active) != 1 or active[0]["labels"] != SELF_SOURCE:
        raise ValueError("expected exactly the baseline self-scrape")
    return active[0]


def _self_sample_time(sample: Any) -> float:
    if sample["status"] != "success" or sample.get("warnings"):
        raise ValueError("query unsuccessful or incomplete")
    if sample["data"]["resultType"] != "vector" or len(sample["data"]["result"]) != 1:
        raise ValueError("missing or ambiguous self-scrape sample")
    value = sample["data"]["result"][0]
    if value["metric"] != SELF_SOURCE:
        raise ValueError("unexpected sample source")
    return float(value["value"][1])


def _assess_scrape(result: dict[str, Any], get: Callable[[str], bytes], now: float) -> None:
    target = _self_target(json.loads(get("/api/v1/targets")))
    scraped = datetime.fromisoformat(target["lastScrape"]).timestamp()
    age = _age(now, scraped, "scrape")
    result["scrape_age_seconds"] = round(age, 3)
    if age > MAX_AGE_SECONDS:
        result.update(status="stale", reason="last scrape exceeds freshness window")
        return
    if target["health"] != "up":
        result.update(status="partial", reason="ready backend but self-scrape is not up")
        return
    age = _age(now, _self_sample_time(json.loads(get(SAMPLE_PATH))), "sample")
    result["sample_age_seconds"] = round(age, 3)
    if age > MAX_AGE_SECONDS:
        result.update(status="stale", reason="stored sample exceeds freshness window")
    else:
        result.update(status="healthy", reason="ready, self-scrape up, query sample fresh")


def assess(get: Callable[[str], bytes] = _get, now: float | None = None) -> dict[str, Any]:
    """Return one fresh health observation of the baseline itself (contract v1)."""
    now = time.time() if now is None else now
    result: dict[str, Any] = {
        "component": "prometheus",
        "status": "unavailable",
        "observed_at": datetime.fromtimestamp(now, UTC).isoformat(),
        "max_age_seconds": MAX_AGE_SECONDS,
        "scope": "local baseline self-scrape only",
    }
    try:
        if get("/-/ready").strip() != READY_BODY:
            raise ValueError("unexpected readiness response")
    except OBSERVATION_ERRORS as exc:
        result["reason"] = "readiness unavailable: " + type(exc).__name__
        return result
    result["status"] = "unknown"
    try:
        _assess_scrape(result, get, now)
    except OBSERVATION_ERRORS as exc:
        result["reason"] = "incomplete verification: " + type(exc).__name__
    return result


def _start() -> dict[str, Any]:
    PROJECT.run("config", "--quiet")
    PROJECT.run("pull", timeout=180)
    PROJECT.run("up", "-d", "--wait", "--wait-timeout", str(START_WAIT_SECONDS))
    deadline = time.monotonic() + START_WAIT_SECONDS
    while True:
        result = assess()
        if result["status"] == "healthy" or time.monotonic() >= deadline:
            return result
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop", "validate"])
    action = parser.parse_args().action
    try:
        if action == "stop":
            PROJECT.run("down", "--timeout", "10")  # Keep data/evidence; no volumes.
            return 0
        if action == "validate":
            PROJECT.run("config", "--quiet")
            PROJECT.run(*PROMTOOL_CHECK)
            return 0
        result = _start() if action == "start" else assess()
    except (subprocess.SubprocessError, OSError) as exc:
        failure = {
            "status": "unavailable",
            "reason": type(exc).__name__,
            "detail": "Local Docker operation failed; inspect command output. Data retained.",
        }
        print(json.dumps(failure))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
