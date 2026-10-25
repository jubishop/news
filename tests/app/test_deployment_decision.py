"""Exercise the CI deployment decision through its command and real commits."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CO_AUTHOR = "Co-Authored-By: Claude <noreply@anthropic.com>"
READABLE = (
    "Clarify project instructions\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Documentation only.\n" + CO_AUTHOR
)
# A blank line puts the co-author in a final paragraph of its own, as in #56's head commit.
SEPARATE_CO_AUTHOR = (
    "Fix worker output\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Mac reporting worker only.\n\n" + CO_AUTHOR
)
# GitHub's default squash of several commits ends with its co-authors alone, as on e4e3689.
GITHUB_SQUASH = (
    "Fix worker images (#54)\n\n"
    "* Fix worker images\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Mac reporting worker only.\n" + CO_AUTHOR + "\n\n"
    "* Record the review decision\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Review ledger only.\n" + CO_AUTHOR + "\n\n"
    "---------\n\n"
    "Co-authored-by: Claude <noreply@anthropic.com>"
)
# A squash body rebuilt to end with the head commit's trailers keeps earlier commits' decisions above them.
REBUILT_SQUASH = (
    "Fix worker images (#54)\n\n"
    "* Fix worker images\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Mac reporting worker only.\n" + CO_AUTHOR + "\n\n"
    "* Record the review decision\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Review ledger only.\n" + CO_AUTHOR
)
# A "---" line ends a patch email's message, but a commit message has no patch to divide.
BELOW_DASHES = (
    "Clarify project instructions\n\n"
    "Before\n---\nAfter\n\n"
    "News-Deploy: skip\nNews-Deploy-Reason: Documentation only.\n" + CO_AUTHOR
)
UNREAD = "that Git doesn't read as trailers"
INVALID = "don't form a valid skip"
# Each readable but invalid decision, with the problem its error must name.
INVALID_DECISIONS = (
    ("News-Deploy: skip", "no News-Deploy-Reason"),
    ("News-Deploy: skip\nNews-Deploy-Reason:", "an empty News-Deploy-Reason"),
    ("News-Deploy: skip\nNews-Deploy-Reason: Docs.\nNews-Deploy-Reason: Tests.",
     "2 News-Deploy-Reason trailers"),
    ("News-Deploy: skip\nNews-Deploy: deploy\nNews-Deploy-Reason: Documentation.",
     "2 News-Deploy trailers (skip, deploy)"),
    ("News-Deploy: maybe\nNews-Deploy-Reason: Documentation.", 'News-Deploy is "maybe"'),
    ("News-Deploy-Reason: Documentation.", "no News-Deploy"),
)


class DeploymentDecisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.com")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.directory, check=True, capture_output=True, text=True
        ).stdout.strip()

    def run_decision(self, message, event="push", ref="refs/heads/main", actions=False):
        self.git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-qm", message)
        revision = self.git("rev-parse", "HEAD")
        environment = {key: value for key, value in os.environ.items() if key != "GITHUB_ACTIONS"}
        if actions:
            environment["GITHUB_ACTIONS"] = "true"
        return subprocess.run(
            [sys.executable, str(ROOT / "bin/deployment-decision"), event, ref, revision],
            cwd=self.directory, env=environment, capture_output=True, text=True,
        )

    def decide(self, message, event="push", ref="refs/heads/main", actions=False):
        result = self.run_decision(message, event, ref, actions)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_push_deploys_by_default(self):
        self.assertEqual(self.decide("Change server behavior").stdout, "deploy=true\n")

    def test_reviewed_immaterial_change_skips_only_deployment(self):
        result = self.decide(
            "Clarify project instructions\n\n"
            "News-Deploy: skip\n"
            "News-Deploy-Reason: Instructions only; production already contains all material changes."
        )
        self.assertEqual(result.stdout, "deploy=false\n")
        self.assertIn("Instructions only", result.stderr)

    def test_decision_shares_the_final_paragraph_with_co_authors(self):
        result = self.decide(READABLE)
        self.assertEqual(result.stdout, "deploy=false\n")
        self.assertNotIn(UNREAD, result.stderr)

    def test_dash_line_in_the_body_keeps_the_final_trailers(self):
        for event, ref in (("push", "refs/heads/main"), ("pull_request", "refs/pull/1/merge")):
            with self.subTest(event=event):
                result = self.decide(BELOW_DASHES, event, ref)
                self.assertEqual(result.stdout, "deploy=false\n")
                self.assertNotIn(UNREAD, result.stderr)

    def test_push_warns_and_deploys_when_git_does_not_read_the_decision(self):
        for name, message in (("separate co-author", SEPARATE_CO_AUTHOR), ("GitHub squash", GITHUB_SQUASH)):
            with self.subTest(name):
                result = self.decide(message)
                self.assertEqual(result.stdout, "deploy=true\n")
                self.assertIn(UNREAD, result.stderr)

    def test_push_warning_is_a_github_annotation_in_actions(self):
        result = self.decide(SEPARATE_CO_AUTHOR, actions=True)
        self.assertEqual(result.stdout, "deploy=true\n")
        self.assertTrue(result.stderr.startswith("::warning::"), result.stderr)

    def test_push_reads_final_trailers_below_earlier_commits_decisions(self):
        result = self.decide(REBUILT_SQUASH)
        self.assertEqual(result.stdout, "deploy=false\n")
        self.assertIn("Review ledger only", result.stderr)
        self.assertNotIn(UNREAD, result.stderr)

    def test_pull_request_fails_when_git_does_not_read_the_decision(self):
        for name, message in (("separate co-author", SEPARATE_CO_AUTHOR), ("GitHub squash", GITHUB_SQUASH)):
            with self.subTest(name):
                result = self.run_decision(message, "pull_request", "refs/pull/1/merge")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(UNREAD, result.stderr)

    def test_pull_request_accepts_unmarked_and_readable_decisions(self):
        for message in (
            "Change server behavior",
            READABLE,
            "Document the News-Deploy: skip convention\n\n"
            "Use News-Deploy-Reason: to explain an immaterial change.",
        ):
            with self.subTest(message=message):
                result = self.decide(message, "pull_request", "refs/pull/1/merge")
                self.assertEqual(result.stdout, "deploy=false\n")

    def test_push_warns_and_deploys_when_the_decision_is_invalid(self):
        for trailers, problem in INVALID_DECISIONS:
            with self.subTest(trailers=trailers):
                result = self.decide("Change\n\n" + trailers, actions=True)
                self.assertEqual(result.stdout, "deploy=true\n")
                self.assertTrue(result.stderr.startswith("::warning::"), result.stderr)
                self.assertIn(INVALID, result.stderr)
                self.assertIn(problem, result.stderr)

    def test_pull_request_fails_when_the_decision_is_invalid(self):
        for trailers, problem in INVALID_DECISIONS:
            with self.subTest(trailers=trailers):
                result = self.run_decision("Change\n\n" + trailers, "pull_request", "refs/pull/1/merge")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(INVALID, result.stderr)
                self.assertIn(problem, result.stderr)

    def test_pull_request_names_unread_and_invalid_decisions_together(self):
        message = "Change\n\nNews-Deploy: skip\nNews-Deploy-Reason: Docs.\n\nNews-Deploy: maybe"
        result = self.run_decision(message, "pull_request", "refs/pull/1/merge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(UNREAD, result.stderr)
        self.assertIn('News-Deploy is "maybe"', result.stderr)

    def test_skip_value_compares_case_insensitively(self):
        message = "Documentation\n\nNews-Deploy: Skip\nNews-Deploy-Reason: Documentation only."
        for event, ref, expected in (
            ("push", "refs/heads/main", "deploy=false\n"),
            ("pull_request", "refs/pull/1/merge", "deploy=false\n"),
        ):
            with self.subTest(event=event):
                result = self.decide(message, event, ref)
                self.assertEqual(result.stdout, expected)
                self.assertNotIn(INVALID, result.stderr)
        self.assertIn("Documentation only", self.decide(message).stderr)

    def test_mentioning_the_trailer_in_prose_is_not_a_decision(self):
        result = self.decide(
            "Document the News-Deploy: skip convention\n\n"
            "Use News-Deploy-Reason: to explain an immaterial change."
        )
        self.assertEqual(result.stdout, "deploy=true\n")

    def test_manual_main_run_deploys_even_when_the_commit_skips(self):
        result = self.decide(
            "Documentation\n\nNews-Deploy: skip\nNews-Deploy-Reason: Documentation only.",
            event="workflow_dispatch",
        )
        self.assertEqual(result.stdout, "deploy=true\n")

    def test_pull_requests_and_other_branches_never_deploy(self):
        for event, ref in (
            ("pull_request", "refs/heads/main"),
            ("push", "refs/heads/feature"),
            ("workflow_dispatch", "refs/heads/feature"),
        ):
            with self.subTest(event=event, ref=ref):
                self.assertEqual(self.decide("Change", event, ref).stdout, "deploy=false\n")

    def test_unreadable_revision_fails_without_a_deployment_decision(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/deployment-decision"),
             "push", "refs/heads/main", "a" * 40],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
