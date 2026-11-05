# RRDPLAT-35 fixture adapter verification — 2026-11-05 UTC

This is a fixture-only first slice, not completion of all RRDPLAT-35 acceptance
criteria or a real TDM health measurement. Source: TDM HTTP transport contract at
`43cd9feb2436fa99450d0100f211c528cf4db033`. Source files were read, never edited.
The parent coordinated the source lane and authorized only synthetic consumption.

PR1 was confirmed merged before implementation. This branch starts from main
`46b6c35641a3b69aa2365d0dc4716530e19a5bb7`; no stacked dependency remains.

## Actual task-local checks

Environment: Linux x86-64 cloud task; Docker 29.9.2, Compose 2.40.3, Python 3.12.14.

- [26 unit tests passed](unit-tests.txt): 17 baseline regression tests and 9 adapter
  interpretation tests. Includes strict labels/cardinality, malformed/nonfinite
  samples, explicit failed versus unknown results, query transport failure, and
  fixed/bounded local Compose commands.
- [Configuration validation passed](config-validation.txt): default-off profile
  assertion, Compose validation, upstream Prometheus `promtool check config`, and
  blackbox exporter `--config.check`.
- `python3 -m compileall -q scripts tests` and `git diff --cached --check` passed.
- [Actual exporter version](exporter-version.txt): 0.29.1, pinned by digest alongside
  Prometheus 3.10.0 and the Python 3.12.14 synthetic responder.
- [Actual runtime](runtime.txt): available fixture succeeds; denial, redirect trap,
  malformed JSON, extra-field JSON, two-second probe timeout and oversized body all
  produce observed probe failures. Timeout duration is asserted between 1.5–3s.
- Actual Docker port inspection asserts only `127.0.0.1:19091` publication;
  exporter and fixture have no configured published ports.
- Real stored fixture series verify the exact low-cardinality label set and metric
  allowlist, including only Prometheus's own scrape bookkeeping in addition to
  the two retained blackbox metrics.
- Missing source query returns unknown. Evaluating real fixture series at a
  **simulated future query instant** (+46s) returns unknown; this is not a claim
  that a live TDM source was paused or became stale.
- Actual exporter shutdown becomes unknown; backend shutdown becomes unknown.
  Test teardown removes only this project's containers/networks. Fixture TSDB is
  ephemeral tmpfs; repository evidence and all baseline data are preserved.

## Independent final review

A separate final diff inspection checked: exact source semantics/pin, absence of
live targets/credentials, explicit fixture profile, no TDM edits, no new UI,
strict metric/label selection, hard HTTP deadlines, fresh exporter-success gating,
no missing-to-zero fallback, redirect rejection, and bounded body/probe sizes.
Review tightened malformed query value-pair validation and added a regression test;
all final checks above were repeated after that change. The test waits for a scrape
started after each replacement is confirmed listening by a bounded TCP healthcheck
and Compose --wait. This also resolves Gitar review thread discussion_r4475920121:
startup connection failures cannot satisfy an intended adversarial response test.

## Remaining scope

No live activation, real-source authorization/readiness, queue timing, run outcomes,
restoration or quarantine instrumentation is implemented. Source-owner coordination
and approved local network placement are required before real TDM consumption.
RRDPLAT-33 visual design remains with Copilot, and RRDPLAT-32 authorization/adoption
remains separate. No hosted CI was added or activated; no production readiness,
external integration or universal-free-infrastructure claim is made.
