#!/bin/sh
# The repository's one merge gate: lint, format, types, dead code, dependency audit, unit tests.
set -eu
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture
uv run pip-audit
uv run python -m unittest discover -s tests -t .
