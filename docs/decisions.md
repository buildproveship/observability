# Decisions

Owner decisions that change how this repository is built, checked or released. Newest first.

## 18 November 2026: light pull request checks in GitHub Actions

- **Decided by:** the owner, choosing "Apply all six (Recommended)" for the cross-repo programme (recommendations 1 and 2).
- **Scope:** `.github/workflows/pr.yml` runs, on GitHub-hosted `ubuntu-24.04` (owner decision of 20 November 2026; the self-hosted `rr-local-mac` runner only serves macOS-only nightly tests in ReleaseReady), `scripts/check.sh` (ruff lint and format, mypy strict, vulture, unit tests) on every pull request to `main`. The Docker runtime tests (`tests.runtime`, `tests.tdm_probe_runtime`) run only on demand (`workflow_dispatch`) and weekly on hosted ubuntu (skipped when main has no new commit since the last successful run) (they need Docker), in `.github/workflows/runtime.yml`.
- **Replaces:** the 12 November 2026 decision that routine checks do not run in GitHub Actions (RRDPLAT-44), for this light set only. Everything else stays as that decision set it, including the manual code-quality scan workflow.
- **Tooling:** the JS/TS repos share `@releaseready/config`; a Python repo cannot consume an npm package, so the equivalent ruff and mypy settings stay in `pyproject.toml`. Renovate uses the shared preset (`github>buildproveship/config`).
