# Decisions

Owner decisions that change how this repository is built, checked or released. Newest first.

## 18 November 2026: light pull request checks in GitHub Actions

- **Decided by:** the owner, choosing "Apply all six (Recommended)" for the cross-repo programme (recommendations 1 and 2).
- **Scope:** `.github/workflows/pr.yml` runs, on the org self-hosted macOS arm64 runner (`rr-local`, added 19 November 2026 because hosted minutes are exhausted), `scripts/check.sh` (ruff lint and format, mypy strict, vulture, unit tests) on every pull request to `main`. The Docker runtime tests (`tests.runtime`, `tests.tdm_probe_runtime`) run only on demand (`workflow_dispatch`) and nightly on hosted ubuntu (they need Docker), in `.github/workflows/runtime.yml`.
- **Replaces:** the 12 November 2026 decision that routine checks do not run in GitHub Actions (RRDPLAT-44), for this light set only. Everything else stays as that decision set it, including the manual code-quality scan workflow.
- **Tooling:** the JS/TS repos share `@releaseready/config`; a Python repo cannot consume an npm package, so the equivalent ruff and mypy settings stay in `pyproject.toml`. Renovate uses the shared preset (`github>releaseready/config`).
