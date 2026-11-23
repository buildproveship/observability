# Claude Code instructions

Follow the shared agent rules in AGENTS.md.

@AGENTS.md

## Code quality (all changes)

Follow `skills/buildproveship-code-quality/SKILL.md` before writing code and before saying a change is done: no legacy
or compatibility code without a named consumer; search PyPI, the standard library or the CLI before writing a
helper; import shared code from `@buildproveship/test-management`, TDM `dev-fixtures`, `@buildproveship/config`,
`@buildproveship/ui-web` or `@buildproveship/tokens`, never copy it; depend on published pinned versions only; never weaken
a lint rule, test or guard to go green, and give every disable comment a reason; READMEs describe today's code.
The check command is `sh scripts/check.sh` (ruff incl. PGH and BLE, mypy strict, vulture, pip-audit, unit tests);
`pr.yml` runs it and `releaseready-guardrails` on every PR.
