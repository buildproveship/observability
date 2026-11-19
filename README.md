# Local OSS observability baseline

A small, standalone Prometheus baseline, independent of ReleaseReady, its database,
and application runtimes. It collects **only Prometheus's own operational metrics**.
Prometheus supplies storage, PromQL and its built-in query UI. There is no custom
telemetry store, dashboard framework, hosted service or application integration.

## Prerequisites and versions

- A Linux local Docker Engine with `/var/run/docker.sock` accessible to your user;
  verified with Engine **29.9.2**, Compose **2.40.3**, Linux x86-64.
- Python **3.12 or newer** is required (3.12.14 was verified); standard library only,
  no runtime pip dependencies. Run every command from the repository root.
- Prometheus **3.10.0**, pinned to the immutable multi-platform image digest
  `sha256:4a61322ac1103a0e3aea2a61ef1718422a48fa046441f299d71e660a3bc71ae9`.
  This is an exact tested pin, not a claim to be the newest release. Version upgrades
  require repeating validation and failure tests with a new reviewed digest.
- Access to Docker Hub for the initial image pull and free loopback port **19090**.
  Allow approximately 1 GB disk for image/data and 512 MB RAM initially. These are
  planning allowances, not enforced limits or a guarantee for larger workloads.
- This script deliberately selects the local Linux socket and ignores inherited
  remote Docker endpoint/context/TLS selectors. It does not install Docker, change
  host settings, request access, or operate a remote daemon. Mac execution is not
  part of this task's verification.

## Reproduce

Run from this repository on your chosen local Linux task environment:

```sh
# The non-root upstream image must be able to read the synthetic configuration.
chmod 644 prometheus.yml tests/fixtures/partial.yml
python3 -m unittest discover -s tests -t . -v
python3 -m observability.baseline validate
python3 -m observability.baseline start
python3 -m observability.baseline status
```

`validate` runs Compose validation and upstream `promtool check config` in the
pinned image. `start` allows 180 seconds to pull, 60 seconds for Compose operations,
and approximately 51 seconds for readiness polling (45 seconds plus at most three
2-second complete HTTP exchange deadlines (Linux main-thread timer)). It exits nonzero on failure and leaves diagnostics
and data available. Fix the reported prerequisite and rerun; a failed attempt does
not mean healthy. A stalled Compose command is bounded by a subprocess timeout;
a daemon-side operation might still finish, so inspect `compose ps` before retrying.

Open <http://127.0.0.1:19090> to use the upstream Prometheus UI. For example, query
`up{job="baseline"}` and `time() - timestamp(up{job="baseline"})` to inspect
collection and sample age. No dashboards or UX designs are introduced here.

```sh
# Inspect only this baseline's resources.
docker --host=unix:///var/run/docker.sock compose -p rr-observability-baseline ps -a
docker --host=unix:///var/run/docker.sock compose -p rr-observability-baseline logs --tail=50
# Stop/remove this project's containers and network, retain its data volume.
python3 -m observability.baseline stop
# Expected: unavailable, exit code 1 after shutdown.
python3 -m observability.baseline status
```

The fixed Compose project name `rr-observability-baseline` identifies owned task resources.
Do not share that project name between checkouts or run the lifecycle/integration
commands concurrently. Stop does **not** remove volumes, evidence or unrelated
resources. Data remains in `rr-observability-baseline_prometheus-data`. There is deliberately
no automatic purge command. Retention is 24 hours / 256 MB of TSDB blocks;
WAL, head and temporary files can exceed the block limit. Logs rotate at 2 × 5 MB.

## Health contract v1

`status` emits a fresh JSON observation and returns **0 only for healthy**; all
other results return **1**. The fields include observation time, scope, reason,
45-second maximum age, and sample/scrape ages when known. It neither saves nor
reuses a previous successful observation. It checks `/-/ready`, `/api/v1/targets`, and a PromQL `timestamp(up{job="baseline"})` query.
The PromQL sample timestamp is used rather than the instant-query evaluation time.

| Status | Meaning |
| --- | --- |
| healthy | Backend ready, exactly the expected self-target up, scrape and stored sample no older than 45 seconds |
| unavailable | Readiness connection, timeout, HTTP or response validation failed |
| partial | Backend ready and target freshly checked, but self-scrape not up |
| stale | Scrape or stored sample exceeds the freshness window, even if a historical check said up |
| unknown | Missing/extra target or sample, malformed/incomplete query, warning, unexpected source, invalid or future clock |

This is a point-in-time check of the **baseline itself**, not health of any product,
customer, run outcome, restoration correctness or business process. The 45-second
window allows three 15-second scrape intervals; clocks must be synchronized
(with 5 seconds tolerated for skew). Missing data is never converted to healthy zero.
Do not cache this output as ongoing health: rerun the bounded command when needed.

## Safety boundary

The only published interface is `127.0.0.1:19090`; Prometheus listens on all
interfaces **inside its container** for that explicit loopback mapping. It has
no authentication and is suitable only for this synthetic local baseline. Other
local processes and containers on the dedicated bridge can reach it. No host
networking, Docker socket mounts, remote write, tracing, alert destinations,
exporters, telemetry credentials or customer connections are configured.

A normal dedicated bridge is used: Docker 29's internal network did not publish
the loopback port in the verified environment. This is not an egress firewall;
the self-only scrape configuration is the collection boundary. Any exposure or
source change requires an explicit operator configuration/review and an appropriate
authentication/access design; merely changing the bind address is not safe for
shared or hosted use. No credentials or grants are generated here.

This is not production readiness or a promise of free infrastructure. OSS software
still needs compute, storage and operations. No cloud resources, subscription,
paid service, hosted activation or Mac services were created.

## Tests and actual evidence

The merge gate is one command. It needs [uv](https://docs.astral.sh/uv/), which
installs the pinned dev tools from `pyproject.toml`/`uv.lock` (ruff with the shared
scanner's ruleset, ruff format, mypy strict, vulture) and runs the unit tests:

```sh
scripts/check.sh
```

```sh
python3 -m unittest discover -s tests -t . -v
# Opt-in: starts/recreates/stops only rr-observability-baseline; preserves data.
python3 -m tests.runtime
```

Unit tests use owned synthetic API responses, **not actual health metrics**. They
cover stale scrape/sample, absence, bad clocks, NaN, wrong sources, partial query,
malformed response, connection failure, and bounded local lifecycle execution.
The loopback reader is tested against a real in-process HTTP server: redirects
are not followed, oversized bodies are rejected and a slow body hits the deadline.
The runtime test checks actual healthy → intentionally broken self-scrape →
healthy recovery → unavailable after stop. Its test-only configuration calls a
nonexistent path on the same container and sends no external data.

See [recorded verification](evidence/rrdplat34/verification.md), [unit output](evidence/rrdplat34/unit-tests.txt)
and [runtime output](evidence/rrdplat34/runtime.txt). Static validation and synthetic tests
alone must not be reported as a successful startup.

## Adjacent backlog boundary

RRDPLAT-35 must agree low-cardinality metrics and freshness contracts with each
source owner before instrumentation. RRDPLAT-33 owns future Grafana OSS dashboards
and requires approved designs. RRDPLAT-32 owns versioned consumer authorization
and compatibility checks. None is implemented or implied by this local baseline;
no central, frontend or cloud-platform files are changed.

Upstream references: [Docker installation](https://prometheus.io/docs/prometheus/latest/installation/),
[configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/),
[storage limits](https://prometheus.io/docs/prometheus/latest/storage/),
[3.10.0 release](https://github.com/prometheus/prometheus/releases/tag/v3.10.0).
