"""Bounded loopback reads of the Prometheus HTTP API and the shared freshness limits."""

from __future__ import annotations

import json
import signal
from http import HTTPStatus
from http.client import HTTPConnection
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlencode

if TYPE_CHECKING:
    from types import FrameType

LOOPBACK = "127.0.0.1"
# Freshness contract shared by the baseline check and the probe PromQL filter.
MAX_AGE_SECONDS = 45
MAX_FUTURE_SKEW_SECONDS = 5
HTTP_TIMEOUT_SECONDS = 2.0
RESPONSE_LIMIT_BYTES = 1024 * 1024


def _deadline_exceeded(_signum: int, _frame: FrameType | None) -> NoReturn:
    raise TimeoutError("HTTP observation deadline exceeded")


def fetch(port: int, path: str) -> bytes:
    """GET one loopback path; only HTTP 200 is accepted.

    `http.client` never follows redirects or reads proxy settings, so a read
    cannot leave the loopback port. Its timeout bounds single socket operations
    only, so a real-time timer bounds the whole exchange, including slow bodies
    (POSIX main thread only).
    """
    previous = signal.signal(signal.SIGALRM, _deadline_exceeded)
    signal.setitimer(signal.ITIMER_REAL, HTTP_TIMEOUT_SECONDS)
    connection = HTTPConnection(LOOPBACK, port, timeout=HTTP_TIMEOUT_SECONDS)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != HTTPStatus.OK:
            raise ValueError(f"unexpected HTTP status {response.status}")
        data = response.read(RESPONSE_LIMIT_BYTES + 1)
        if len(data) > RESPONSE_LIMIT_BYTES:
            raise ValueError("response exceeds limit")
        return data
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        connection.close()


def query(port: int, expression: str, at: float | None = None) -> Any:
    """Run an instant PromQL query and return the decoded JSON response."""
    params = {"query": expression}
    if at is not None:
        params["time"] = str(at)
    return json.loads(fetch(port, "/api/v1/query?" + urlencode(params)))
