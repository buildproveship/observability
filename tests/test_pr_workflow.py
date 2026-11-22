"""The pull request workflow reports the required check on docs-only changes.

Test classification: unit
Review status: Not Reviewed
Evidence: synthetic
Scope: the text of .github/workflows/pr.yml (a required check that never starts
stays pending, so docs-only pull requests are skipped inside the workflow); it
does not run the workflow.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pr.yml"
DOCS_ONLY = "needs.changes.outputs.docs_only != 'true'"


def job_text(text: str, name: str) -> str:
    """The lines of one top-level job, up to the next job."""
    match = re.search(
        rf"^  {name}:\n(.*?)(?=^  [a-z]+:\n|\Z)", text, re.DOTALL | re.MULTILINE
    )
    if match is None:
        raise AssertionError(f"no job named {name} in pr.yml")
    return match.group(1)


class PullRequestWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_no_paths_ignore_so_the_required_check_always_starts(self) -> None:
        self.assertIsNone(re.search(r"^\s+paths(-ignore)?:", self.text, re.MULTILINE))

    def test_every_step_of_checks_is_skipped_for_docs_only_changes(self) -> None:
        checks = job_text(self.text, "checks")
        steps = re.findall(r"^      - (?:name|uses):.*$", checks, re.MULTILINE)
        guards = re.findall(
            rf"^        if: {re.escape(DOCS_ONLY)}$", checks, re.MULTILINE
        )
        self.assertGreater(len(steps), 0)
        self.assertEqual(len(steps), len(guards))
        self.assertIn("needs: changes", checks)

    def test_the_security_scan_is_skipped_for_docs_only_changes(self) -> None:
        self.assertIn(DOCS_ONLY, job_text(self.text, "security"))
