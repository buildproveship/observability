# TDM listener probe contract v1 — fixture-only RRDPLAT-35 slice

This adapter consumes **listener availability**, not service readiness or business
outcomes. It uses standard Prometheus blackbox exporter metrics; it adds no TDM
endpoint, custom telemetry storage, visualization, authentication or live connection.

## Source ownership and exact evidence

Source owner: the `releaseready/test-data-management` HTTP transport lane. Source pin:
`43cd9feb2436fa99450d0100f211c528cf4db033`.

- [`src/http/server.ts`](https://github.com/releaseready/test-data-management/blob/43cd9feb2436fa99450d0100f211c528cf4db033/src/http/server.ts)
  implements `GET /health`, HTTP 200 with `{"status":"available"}`. It runs after
  Host/Origin/concurrency gates and before bearer authentication.
- [`openapi/tdm.mjs`](https://github.com/releaseready/test-data-management/blob/43cd9feb2436fa99450d0100f211c528cf4db033/openapi/tdm.mjs)
  documents process availability only, explicitly not vault or authority readiness.
- A locked vault can coexist with a successful listener probe. An HTTP 403 can
  reflect the transport/concurrency gate; it is not proof of a storage failure.

The parent coordinated this fixture-only consumer: no active TDM lane or open PR
was found at assessment. This is **not approval for live activation**. No TDM files,
settings, host gates, identities, credentials or runtimes are changed or started.
Real consumption requires source-owner agreement on network placement and rechecking
this pinned contract. Do not weaken the existing Host gate to enable a scrape.

## Metrics and interpretation

Retain only upstream `probe_success` and `probe_duration_seconds`. Prometheus adds
`up` and its bounded `scrape_*` bookkeeping series. Every series uses fixed labels:

```
job="tdm-listener-fixture"
instance="tdm-fixture"
service="tdm"
source="synthetic-fixture"
```

No target URL, run/customer/project identifier, token, payload, arbitrary status
string or diagnostic becomes a metric label. The fixed scrape parameter points
only at `http://tdm-health-fixture:3102/health`; there is no real URL or credential
selection. The exporter is not published on a host interface. Its `/probe` API is
an upstream multi-target interface and must not be exposed as a public proxy.

| Observation | Meaning |
| --- | --- |
| Fresh `probe_success=1`, fresh `up=1`, fresh duration | Synthetic listener response matches HTTP 200 and the one-field JSON body |
| Fresh `probe_success=0`, fresh `up=1`, fresh duration | Probe failed; could be denial, timeout, redirect, malformed/oversized response or connection failure |
| Missing series, exporter scrape failure, stale sample, incomplete query | Unknown; never healthy zero activity |
| `probe_duration_seconds` | Duration of this HTTP probe, **not** execution, business or queue duration |

Maximum sample age is 45 seconds, with at most five seconds of future clock skew.
The executable PromQL filter is `KNOWN` in
[`tests/tdm_probe_runtime.py`](../../tests/tdm_probe_runtime.py). It requires fresh
success, duration and exporter `up` samples, and `up == 1`; it retains observed
zero probe values. It never uses `or vector(0)` or fills missing values with zero.
The test/CLI decoder rejects duplicates, wrong labels, nonfinite/nonbinary values,
query warnings and malformed responses. The JSON observation is a fixture test
result, not a new health API or ongoing health assertion.

The fixture scrape interval is five seconds, scrape timeout three seconds, and
probe timeout two seconds. Body processing is limited to 1 KB; redirects and
IPv6 fallback are disabled. JSON must contain exactly `status: "available"`.

## Reproduce in a local Linux task environment

Requires the baseline's local Docker socket, Compose and Python prerequisites.
Verified versions: Docker 29.9.2, Compose 2.40.3, Python 3.12.14. Dependencies:

| Component | Version | Immutable image digest |
| --- | --- | --- |
| blackbox exporter | 0.29.1 | `sha256:ea1c7aa3ef3f307cd03e85f34abb604478ccb90b567fc690da0cd9776da76b13` |
| Prometheus | 3.10.0 (baseline pin) | `sha256:4a61322ac1103a0e3aea2a61ef1718422a48fa046441f299d71e660a3bc71ae9` |
| Python synthetic fixture | 3.12.14-slim | `sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` |

From repository root:

```sh
chmod 644 probes/*.yml tests/fixtures/tdm_health.py
# Initial dependency pull is explicitly bounded; no builds or package installation.
timeout 180 docker --host=unix:///var/run/docker.sock compose \
  -p rrdplat35-fixture -f compose.probes.fixture.yaml --profile fixture-only pull
python3 -m unittest discover -s tests -v
python3 tests/tdm_probe_runtime.py validate
python3 tests/tdm_probe_runtime.py test
```

`validate` checks that the profile defaults off, runs upstream `promtool check
config` and blackbox `--config.check`. `test` starts only this fixture project,
waits for each fixture TCP listener before recording its scrape cutoff, checks
every synthetic response, simulates stale query time, stops the exporter,
and finally removes its containers/networks. It does not remove baseline data or
repository evidence. Fixture TSDB data is ephemeral tmpfs, deliberately discarded
with the fixture container; preserve desired output before teardown.

For manual inspection only:

```sh
python3 tests/tdm_probe_runtime.py start
python3 tests/tdm_probe_runtime.py status
python3 tests/tdm_probe_runtime.py stop
```

Status exits zero only for fixture `available`; observed failure/unknown returns
one. Read the standard Prometheus query UI at `http://127.0.0.1:19091` if needed.
There are no new dashboards or visual design decisions. Only that loopback port is
published. Fixture and exporter share an internal network; Prometheus also joins a
separate bridge for its loopback query port. This isolation is for local synthetic
verification, not a multi-tenant authorization guarantee.

Use this Compose file standalone, not merged with the baseline `compose.yaml`.
All three services have the explicit `fixture-only` profile. Ordinary baseline
startup does not start them. Do not concurrently use the same fixed project name
`rrdplat35-fixture` from multiple checkouts. Each Compose invocation has a 60-second
subprocess deadline; readiness/observation polls have 25-second windows; local query
HTTP exchanges have two-second hard deadlines. A timed-out daemon command may still
finish: inspect this project's resources before retrying. If an image is missing,
run the bounded pull first. No global Docker prune or volume deletion is performed.

## Verification and deliberate limits

The fixture includes available, 403 denial, redirect-to-success trap, malformed JSON,
unexpected extra field, delayed response and oversized response cases. These are
owned synthetic bytes and **never actual TDM availability measurements**. Runtime
checks assert metric/label allowlists and loopback publication, test missing series,
and evaluate stored fixture samples at a simulated time 46 seconds ahead to prove
stale data becomes unknown. They do not claim a live TDM service became stale.
Exporter shutdown and backend shutdown are actual task-local failure checks.

[Recorded evidence](../../evidence/rrdplat35/verification.md) distinguishes those
checks. No real target was probed. No credentials were generated, no hosted CI or
service was activated, and no Mac settings or live customer resources were touched.

This delivers only the first fixture adapter slice of RRDPLAT-35. Source-owner
activation, other service contracts, run failures/timeouts, queue duration and
TDM restoration/quarantine signals remain unimplemented. Existing provider
contracts and synthetic conformance fixtures are not operational source metrics.
RRDPLAT-33's Grafana designs remain with Copilot; RRDPLAT-32 authorization and
compatibility adoption are separate work.

Upstream: [blackbox 0.29.1 configuration](https://github.com/prometheus/blackbox_exporter/blob/v0.29.1/CONFIGURATION.md),
[release](https://github.com/prometheus/blackbox_exporter/releases/tag/v0.29.1),
[Prometheus multi-target pattern](https://prometheus.io/docs/guides/multi-target-exporter/).
