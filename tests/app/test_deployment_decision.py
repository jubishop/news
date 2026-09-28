"""Exercise the CI deployment decision through its command and real commits."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


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

    def decide(self, message, event="push", ref="refs/heads/main"):
        self.git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-qm", message)
        revision = self.git("rev-parse", "HEAD")
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/deployment-decision"), event, ref, revision],
            cwd=self.directory, capture_output=True, text=True,
        )
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

    def test_incomplete_or_conflicting_decisions_keep_deployment(self):
        for trailers in (
            "News-Deploy: skip",
            "News-Deploy: skip\nNews-Deploy-Reason:",
            "News-Deploy: skip\nNews-Deploy: deploy\nNews-Deploy-Reason: Documentation.",
            "News-Deploy: maybe\nNews-Deploy-Reason: Documentation.",
        ):
            with self.subTest(trailers=trailers):
                self.assertEqual(self.decide("Change\n\n" + trailers).stdout, "deploy=true\n")

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
