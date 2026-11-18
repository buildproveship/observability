#!/bin/sh
# The repository's one merge gate: lint, format, types, dead code, unit tests.
set -eu
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture
uv run python -m unittest discover -s tests -t .
