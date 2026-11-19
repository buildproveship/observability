"""Opt-in runtime test. Owns only the documented rr-observability-baseline project.

Test classification: e2e
Review status: Not Reviewed
Evidence: synthetic
Scope: starts the real pinned Prometheus through Docker and checks healthy, a
deliberately broken self-scrape (partial), recovery and unavailable after stop;
it uses no product, customer or external data.
"""

from __future__ import annotations

import json
import time

from observability import baseline
from observability.docker import ROOT, ComposeProject, inspect

PARTIAL = ComposeProject(
    baseline.PROJECT.name,
    (*baseline.PROJECT.files, ROOT / "tests/partial.compose.yaml"),
)
WAIT = ("up", "-d", "--wait", "--wait-timeout", "30")


def expect(status: str) -> None:
    deadline = time.monotonic() + 45
    while True:
        result = baseline.assess()
        if result["status"] == status:
            print(json.dumps({"expected": status, "actual": result}), flush=True)
            return
        if time.monotonic() >= deadline:
            raise AssertionError(result)
        time.sleep(1)


def main() -> None:
    try:
        baseline.PROJECT.run(*WAIT)
        expect("healthy")
        ports = inspect("rr-observability-baseline-prometheus-1")["NetworkSettings"][
            "Ports"
        ]
        expected = {
            "9090/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(baseline.PORT)}]
        }
        if ports != expected:
            raise AssertionError(ports)
        print(json.dumps({"published_ports": ports}), flush=True)
        PARTIAL.run(*WAIT, "--force-recreate")
        expect("partial")
        baseline.PROJECT.run(*WAIT, "--force-recreate")
        expect("healthy")
    finally:
        baseline.PROJECT.run("down", "--timeout", "10")
    expect("unavailable")


if __name__ == "__main__":
    main()
