# RRDPLAT-34 local verification — 2026-11-05 UTC

Executed in the selected ephemeral cloud task, Linux x86-64, Docker Engine 29.9.2,
Compose 2.40.3, Python 3.12.14. No BuildProveShip service/database was started.

Repository audit before implementation: GitHub size 0, default branch name main,
zero branches and open PRs; `git ls-remote` empty. Local repository had no commits
or files/instructions. No competing owner found. An empty root commit initializes
main solely as the PR comparison base; implementation is on the feature branch.

## Checks

- 17 standard-library unit tests passed, including a timed slow HTTP read and
  redirect rejection. [Output](unit-tests.txt)
- `python3 -m compileall -q scripts tests` passed; no external lint/types/build
  pipeline exists in this previously empty repository.
- Compose configuration validation and pinned upstream `promtool check config`
  passed. [Output](config-validation.txt)
- Real pinned Prometheus started, self-scraped and answered freshness queries.
- Docker inspect asserted the sole published port is `127.0.0.1:19090`.
- Real test-only invalid self-scrape produced partial, restored config recovered
  to healthy, shutdown produced unavailable. [Full runtime output](runtime.txt)
- Stale/missing/future/nonfinite/malformed data tested with owned synthetic API
  fixtures only; not claimed as live source measurements.
- [Upstream executable version](prometheus-version.txt) records actual image version.

## Review and limitations

A separate final code review checked pinning, no external telemetry/credentials,
loopback publication, no remote Docker selection, explicit sample freshness,
finite HTTP/process timeouts, failure exit codes, and teardown/data retention.
It added a hard whole-exchange timer so a trickling HTTP response cannot prolong
status indefinitely, plus a regression test.

Initial runtime failures were diagnosed rather than reported as healthy: the
workspace umask made config unreadable by the non-root image (fixed via documented
chmod); Docker internal bridge did not publish the port (switched to a dedicated
normal bridge). The configured collection remains self-only, not a firewall.

Runtime tests stop/remove the project's containers/network and preserve its data
volume and evidence. No production, multi-tenant authorization, Grafana dashboards,
service instrumentation, CI activation or hosted readiness is claimed. RRDPLAT-35,
33 and 32 remain separate work. Upstream image licensing is Apache-2.0; this repo
does not select a new license for the owner's implementation.
