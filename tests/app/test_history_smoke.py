"""Run the smoke CLI with QMD replaced only at its executable boundary."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from history_support import fake_qmd

ROOT = Path(__file__).resolve().parents[2]


class HistorySmokeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="smoke-test-", dir=ROOT / ".cache")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        tests = self.root / "tests"
        (tests / "fixtures").mkdir(parents=True)
        shutil.copy2(ROOT / "tests/history_search_smoke.py", tests)
        shutil.copy2(ROOT / "tests/fixtures/article-history.json", tests / "fixtures")
        (self.root / "news").symlink_to(ROOT / "news", target_is_directory=True)
        self.fixture = json.loads((tests / "fixtures/article-history.json").read_text())
        self.settings = {"query_results": {case["query"]: case["expected"] for case in self.fixture["queries"]}}
        self.command = fake_qmd(self.root)
        self.output = self.root / ".cache/history-search-smoke.json"

    def run_smoke(self):
        (self.root / "qmd-settings.json").write_text(json.dumps(self.settings))
        result = subprocess.run([sys.executable, "-B", str(self.root / "tests/history_search_smoke.py"),
                                 "--qmd-command", *self.command], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(list((self.root / ".cache").glob("history-smoke-*")), [])
        pids = self.root / "qmd-pids.jsonl"
        if pids.exists():
            for pid in pids.read_text().splitlines():
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid), 0)
        return result

    def report(self, status):
        self.assertTrue(self.output.exists(), "The current run must always save its report")
        report = json.loads(self.output.read_text())
        self.assertEqual(report["status"], status)
        return report

    def test_relevant_followup_can_rank_first_and_all_checks_still_run(self):
        query = self.fixture["queries"][0]["query"]
        observed = ["obesity-followup", "obesity", "apnea", "model-v2", "ev-charging"]
        self.settings["query_results"][query] = observed
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.report("passed")
        self.assertEqual(len(report["queries"]), 8)
        self.assertEqual(len({row["query"] for row in report["queries"]}), 6)
        self.assertTrue(all(row["status"] == "passed" for row in report["queries"]))
        self.assertEqual(next(row["ids"] for row in report["queries"] if row["query"] == query), observed)
        for check in ("article_read", "model_health", "empty_model_health", "empty_snapshot_and_removal", "cleanup"):
            self.assertEqual(report[check], "passed")

    def test_missing_related_article_fails_and_retains_every_client_result(self):
        query = self.fixture["queries"][0]["query"]
        self.settings["query_results"][query] = ["obesity", "obesity-followup"]
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        self.assertEqual(len(report["queries"]), 8)
        failed = [row for row in report["queries"] if row["status"] == "failed"]
        self.assertEqual(len(failed), 2)
        self.assertTrue(all("apnea" in row["error"] for row in failed))
        self.assertIn("QMD MCP server listening", report["diagnostics"]["populated"]["search.log"])

    def test_exact_version_must_still_rank_first(self):
        self.settings["query_results"]["Orion 2.1 JSON bug fix"] = ["model-v2", "model-v21"]
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        row = next(row for row in report["queries"] if row["query"] == "Orion 2.1 JSON bug fix")
        self.assertEqual(row["ids"], ["model-v2", "model-v21"])
        self.assertEqual(row["status"], "failed")

    def test_broad_query_still_requires_a_relevant_first_result(self):
        query = self.fixture["queries"][0]["query"]
        self.settings["query_results"][query] = ["model-v2", "obesity", "obesity-followup", "apnea"]
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        row = next(row for row in self.report("failed")["queries"] if row["query"] == query)
        self.assertIn("Expected first article", row["error"])

    def test_failed_preparation_replaces_an_older_success_and_keeps_logs(self):
        self.output.parent.mkdir()
        self.output.write_text(json.dumps({"status": "passed", "old_run": True}))
        self.settings["fail"] = "embed"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        self.assertNotIn("old_run", report)
        self.assertIn("fixture command failure: embed", report["diagnostics"]["populated"]["indexing.log"])
        self.assertIn("embed failed", report["error"])

    def test_hidden_model_failure_rejects_relevant_results_and_retains_diagnostic(self):
        self.settings["model_warning"] = "Reranker unavailable"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        self.assertIn("model failed", report["error"])
        self.assertIn("Reranker unavailable", report["diagnostics"]["populated"]["search.log"])

    def test_tool_errors_are_retained_without_hiding_other_clients(self):
        self.settings["tool_error"] = "query"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        self.assertEqual(len(report["queries"]), 8)
        self.assertTrue(all("fixture tool failure" in row["error"] for row in report["queries"]))

    def test_article_read_checks_both_coverage_dates_and_source(self):
        for omitted in ("coverage_end: 2026-09-27", "https://example.com/model-v21"):
            with self.subTest(omitted=omitted):
                self.settings["omit_text"] = omitted
                result = self.run_smoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(omitted, self.report("failed")["error"])

    def test_empty_archive_cannot_return_deleted_article(self):
        self.settings["stale_empty_result"] = True
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        report = self.report("failed")
        self.assertIn("model-v21", report["error"])
        self.assertIn("QMD MCP server listening", report["diagnostics"]["empty"]["search.log"])
