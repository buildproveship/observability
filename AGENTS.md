# Agent instructions

These rules apply to every agent and contributor working in this repository.

## Tests and classification

- **Every new or changed piece of logic ships with tests in the same change.** Prefer end-to-end (E2E) tests that exercise the real user or service path. Where E2E is not possible yet, add the clearest lower-level test (integration, contract, component or unit) and say in the pull request why E2E was not possible.
- **Classify every test file.** Each new or changed test file starts with a header in its own comment syntax:

  ```text
  Test classification: unit | component | contract | integration | e2e
  Review status: Not Reviewed
  Evidence: synthetic | real
  Scope: one sentence on what the test exercises and what it does not
  ```

  The classification describes scope, not the runner. Use the most conservative category for mixed files. Call a test `e2e` only when it goes through the real user or service path. In-memory compositions with test doubles are `integration`.

- **Only the founder reviews tests.** Never set a review status other than `Not Reviewed`, and never describe tests as reviewed or approved. Tests are onboarded into ReleaseReady, where they start as Not Reviewed and the founder reviews and approves them there.
- **Tests prove real outcomes.** Each guard has a test that fails if the guard is removed. Use synthetic fixtures unless real evidence is stated in the header.

## Design before implementation

This is the owner's standing rule for every project. A project's own rules may add to it but never relax it.

- **Keep the design library current.** Every new or changed design (screen, flow, component, state or copy) goes into the project's design library or design source of truth in the same piece of work. If the project has none, say so and propose where it should live. Do not leave a design only in code, a chat message or a pull request.
- **Implement only approved designs.** Do not build a design into the real product (application code, shared components adopted by an app, deployment) until the design is approved and the approval is recorded against the exact version of the design. Until then it is a draft.
- **Label drafts.** Say "draft" or "proposal" wherever an unapproved design appears. Never describe a design as approved, shipped or live without a recorded approval. Previews and prototypes made to get a design reviewed count as design work, not implementation. They use synthetic data and say they are previews.
- **Approval is the owner's.** Silence, a green build, a merged pull request or an agent's own review is not approval. When a design is ready for review, say where it is and what is waiting for approval.
- **No approved design, no implementation.** If asked to implement something that has no approved design, add the design to the library first, mark it for review, and report that implementation is waiting on approval. Fixing a bug that does not change a design is not covered.

## Code quality (all changes)

Follow `skills/releaseready-code-quality/SKILL.md` before writing code and before saying a change is done: no legacy
or compatibility code without a named consumer; search PyPI, the standard library or the CLI before writing a
helper; import shared code from `@releaseready/test-management`, TDM `dev-fixtures`, `@releaseready/config`,
`@releaseready/ui-web` or `@releaseready/tokens`, never copy it; depend on published pinned versions only; never weaken
a lint rule, test or guard to go green, and give every disable comment a reason; READMEs describe today's code.
The check command is `sh scripts/check.sh` (ruff incl. PGH and BLE, mypy strict, vulture, pip-audit, unit tests);
`pr.yml` runs it and `releaseready-guardrails` on every PR.

## Defects we don't create

The rules come from the defects found in the 18 Nov 2026 cross-repo review. The full list and fixes are in the
`releaseready-code-quality` skill: https://github.com/releaseready/config/tree/main/skill/releaseready-code-quality

<!-- TODO(RRDSCRUM-438): replace this link with the docs page once it exists. -->

- No legacy or compatibility code without a named consumer.
- Search PyPI, the standard library or the CLI before writing a helper.
- Import shared code; never copy it between repos.
- Depend on published, pinned versions only.
- Never weaken a lint rule, test or guard to go green; give every disable comment a reason.
- Allow-list a guardrail finding only after review, and with a `reason`.
- Every fix adds the cheapest guard that fails the whole class next time.
- READMEs and docs describe today's code, not plans.
- Never commit secrets, credentials or real customer data; use synthetic data.

## Merging

- Never merge with a red or missing `pr.yml`.
- The owner's local `merge-guard.sh` is the merge gate.
- `main` is protected by the required `checks` job.
