"""History snapshot and search lifecycle through API and process boundaries."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib import request
from unittest.mock import patch

from news.worker_history import History
from news.worker_io import WorkerError
from history_support import Archive, fake_qmd
from test_worker import ARTICLE


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="news history ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = {"state_dir": str(self.root / "state"), "qmd_command": fake_qmd(self.root)}
        self.api = Archive([dict(ARTICLE, id="old", reporter_id="reporter", reporter_name="Original reporter")])

    def history(self):
        history = History(self.settings)
        self.addCleanup(history.close)
        return history

    def call(self, history, name, arguments):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}).encode()
        req = request.Request(history.endpoint, data=body, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        with request.urlopen(req, timeout=5) as response:
            return json.load(response)["result"]

    def test_snapshot_is_shared_and_articles_are_readable_with_attribution(self):
        history = self.history()
        history.prepare(self.api)
        self.api.articles.append(dict(ARTICLE, id="new", reporter_id="other"))
        history.prepare(self.api)
        self.assertEqual(self.api.downloads, 1)
        found = self.call(history, "query", {"query": "prior reporting", "limit": 5})
        self.assertEqual(len(found["structuredContent"]["results"]), 1)
        article = self.call(history, "get", {"file": "qmd://articles/old.md", "maxLines": 80})["content"][0]["resource"]["text"]
        for value in ("id: old", "reporter_name: Original reporter", "coverage_start: 2026-09-26", "https://example.com/story"):
            self.assertIn(value, article)
        self.assertEqual(history.snapshot["article_count"], 1)
        self.assertNotIn("body_markdown", history.summaries["reporter"][0])

    def test_next_batch_reconciles_addition_deletion_restoration_and_unchanged_files(self):
        history = self.history()
        history.prepare(self.api)
        history.close()
        unchanged = self.root / "state/history/current/articles/old.md"
        stamp = unchanged.stat().st_mtime_ns
        other = dict(ARTICLE, id="other", reporter_id="another")
        self.api.articles.append(other)
        next_batch = self.history()
        next_batch.prepare(self.api)
        self.assertEqual(unchanged.stat().st_mtime_ns, stamp)
        next_batch.close()
        self.api.articles = [other]
        deletion = self.history()
        deletion.prepare(self.api)
        self.assertFalse(unchanged.exists())
        self.assertTrue(self.call(deletion, "get", {"file": "qmd://articles/old.md"}).get("isError"))
        deletion.close()
        self.api.articles.append(dict(ARTICLE, id="old", reporter_id="reporter"))
        restoration = self.history()
        restoration.prepare(self.api)
        self.assertTrue(unchanged.exists())
        self.assertEqual(restoration.snapshot["article_count"], 2)

    def test_unchanged_refresh_downloads_no_bodies_and_repairs_only_missing_files(self):
        self.api.articles[0]["body_markdown"] = "First café paragraph.\r\n\r\nSecond paragraph."
        first = self.history()
        first.prepare(self.api)
        first.close()
        self.api.bodies.clear()
        second = self.history()
        second.prepare(self.api)
        second.close()
        self.assertEqual(self.api.bodies, [])
        (self.root / "state/history/current/articles/old.md").unlink()
        repaired = self.history()
        repaired.prepare(self.api)
        self.assertEqual(self.api.bodies, ["old"])

    def test_changes_corruption_and_missing_cache_records_fetch_only_affected_articles(self):
        self.api.articles.append(dict(ARTICLE, id="other", reporter_id="other"))
        initial = self.history()
        initial.prepare(self.api)
        initial.close()
        cache = self.root / "state/history/current"
        for mutation in ("body", "metadata", "file", "record"):
            with self.subTest(mutation=mutation):
                if mutation == "body":
                    self.api.articles[0]["body_markdown"] = "A changed body"
                elif mutation == "metadata":
                    self.api.articles[0]["reporter_name"] = "Corrected attribution"
                elif mutation == "file":
                    (cache / "articles/old.md").write_text("Damaged Markdown")
                else:
                    records = json.loads((cache / "cache.json").read_text())
                    del records["articles"]["old"]
                    (cache / "cache.json").write_text(json.dumps(records))
                self.api.bodies.clear()
                history = self.history()
                history.prepare(self.api)
                history.close()
                self.assertEqual(self.api.bodies, ["old"])
                self.assertIn("A changed body", (cache / "articles/old.md").read_text())
        (cache / "cache.json").write_text("broken JSON")
        self.api.bodies.clear()
        rebuilt = self.history()
        rebuilt.prepare(self.api)
        rebuilt.close()
        self.assertEqual(self.api.bodies, ["old", "other"])
        (cache / "index.sqlite").write_bytes(b"broken index")
        self.api.bodies.clear()
        self.history().prepare(self.api)
        self.assertEqual(self.api.bodies, [])

    def test_unreadable_cached_article_is_repaired_without_refetching_other_records(self):
        self.api.articles.append(dict(ARTICLE, id="other", reporter_id="other"))
        initial = self.history()
        initial.prepare(self.api)
        initial.close()
        damaged = self.root / "state/history/current/articles/old.md"
        read_bytes = Path.read_bytes

        def read_cached(path):
            if path.resolve() == damaged.resolve():
                raise PermissionError("Cached article is unreadable")
            return read_bytes(path)

        for changed in (False, True):
            with self.subTest(changed=changed):
                if changed:
                    self.api.articles[0]["summary"] = "Updated summary"
                self.api.bodies.clear()
                repaired = self.history()
                with patch.object(Path, "read_bytes", read_cached):
                    repaired.prepare(self.api)
                self.assertEqual(self.api.bodies, ["old"])
                self.assertEqual(repaired.snapshot["article_count"], 2)
                article = self.call(repaired, "get", {"file": "qmd://articles/old.md"})["content"][0]["resource"]["text"]
                self.assertIn(self.api.articles[0]["summary"], article)
                repaired.close()

    def test_legacy_cache_upgrade_reuses_index_and_removes_obsolete_layout(self):
        initial = self.history()
        initial.prepare(self.api)
        initial.close()
        root = self.root / "state/history"
        generation = (root / "current").resolve()
        (root / "current").unlink()
        for name in ("articles", "index.sqlite", "config", "snapshot.json"):
            (generation / name).rename(root / name)
        self.api.bodies.clear()
        upgraded = self.history()
        upgraded.prepare(self.api)
        self.assertEqual(self.api.bodies, ["old"])
        self.assertTrue(self.call(upgraded, "query", {"query": "prior"})["structuredContent"]["results"])
        self.assertFalse((root / "articles").exists())
        self.assertFalse((root / "index.sqlite").exists())
        self.assertFalse(generation.exists())

    def test_malformed_or_truncated_manifest_never_removes_valid_cached_content(self):
        initial = self.history()
        initial.prepare(self.api)
        initial.close()
        current = self.root / "state/history/current"
        previous = current.resolve()
        original = self.api.call
        for change in ({"articles": []}, {"total": 0}, {"has_more": True}, {"version": None}, {"page": 2}, {"limit": True}):
            with self.subTest(change=change):
                self.api.call = lambda route: original(route) | change if "/manifest?" in route else original(route)
                failed = self.history()
                with self.assertRaises(WorkerError):
                    failed.prepare(self.api)
                self.assertFalse(failed.ready)
                self.assertEqual(current.resolve(), previous)
                self.assertTrue((current / "articles/old.md").exists())
        self.api.call = original

    def test_changes_during_pages_body_fetch_and_final_guard_retry_complete_snapshot(self):
        self.api.articles = [dict(ARTICLE, id=f"story{n}", reporter_id="reporter") for n in range(101)]
        for phase in ("page", "body", "final"):
            with self.subTest(phase=phase):
                changed = False
                def mutate(route):
                    nonlocal changed
                    match = {"page": "page=2", "body": "/articles/story0?", "final": "limit=1&"}[phase]
                    if not changed and match in route:
                        changed = True
                        self.api.articles.append(dict(ARTICLE, id="added-" + phase, reporter_id="reporter"))
                self.api.before_call = mutate
                # Require story0 to be fetched in each phase.
                self.api.articles[0]["summary"] = phase
                history = self.history()
                history.prepare(self.api)
                history.close()
                self.assertTrue(changed)
                self.assertEqual(history.snapshot["article_count"], len(self.api.articles))
                self.assertEqual({p.stem for p in (self.root / "state/history/current/articles").glob("*.md")},
                                 {a["id"] for a in self.api.articles})

    def test_interrupted_or_unstable_refresh_preserves_entire_last_snapshot(self):
        old = self.history()
        old.prepare(self.api)
        old.close()
        current = self.root / "state/history/current"
        previous = current.resolve()
        snapshot = (current / "snapshot.json").read_bytes()
        self.api.articles = [dict(ARTICLE, id=f"story{n}", reporter_id="reporter") for n in range(101)]
        for phase in ("page=2", "/articles/story0?", "limit=1&", "unstable"):
            with self.subTest(phase=phase):
                def interrupt(route):
                    if phase in route:
                        raise WorkerError("Interrupted request")
                    if phase == "unstable" and "version=" in route:
                        self.api.articles[0]["summary"] += "."
                self.api.before_call = interrupt
                history = self.history()
                with self.assertRaises(WorkerError):
                    history.prepare(self.api)
                self.assertFalse(history.ready)
                self.assertIsNone(history.endpoint)
                self.assertEqual(current.resolve(), previous)
                self.assertEqual((current / "snapshot.json").read_bytes(), snapshot)
                self.assertEqual({p.stem for p in (current / "articles").glob("*.md")}, {"old"})
        self.api.before_call = None
        recovered = self.history()
        recovered.prepare(self.api)
        self.assertEqual(recovered.snapshot["article_count"], 101)

    def test_failed_index_or_atomic_switch_retains_previous_snapshot_and_recovers(self):
        old = self.history()
        old.prepare(self.api)
        old.close()
        current = self.root / "state/history/current"
        previous = current.resolve()
        old_body = (current / "articles/old.md").read_bytes()
        self.api.articles[0]["summary"] = "Changed"
        (self.root / "qmd-settings.json").write_text(json.dumps({"fail": "embed"}))
        with self.assertRaisesRegex(WorkerError, "embed failed"):
            self.history().prepare(self.api)
        self.assertEqual(current.resolve(), previous)
        self.assertEqual((current / "articles/old.md").read_bytes(), old_body)
        (self.root / "qmd-settings.json").unlink()
        replace = os.replace
        def fail_switch(source, target):
            if Path(target).name == "current" and Path(target).parent.resolve() == current.parent.resolve():
                raise OSError("Disk failure")
            return replace(source, target)
        with patch("os.replace", side_effect=fail_switch):
            with self.assertRaises(WorkerError):
                self.history().prepare(self.api)
        self.assertEqual(current.resolve(), previous)
        recovered = self.history()
        recovered.prepare(self.api)
        self.assertIn("Changed", self.call(recovered, "get", {"file": "qmd://articles/old.md"})["content"][0]["resource"]["text"])

    def test_failed_download_preserves_previous_files_but_does_not_serve_them(self):
        history = self.history()
        history.prepare(self.api)
        history.close()
        self.api.articles = [dict(ARTICLE, id="new", reporter_id="reporter")]
        self.api.error = True
        failed = self.history()
        for _ in range(2):
            with self.assertRaisesRegex(WorkerError, "Page two failed"):
                failed.prepare(self.api)
        self.assertEqual(self.api.downloads, 2)
        self.assertIsNone(failed.endpoint)
        files = {p.name for p in (self.root / "state/history/current/articles").iterdir()}
        self.assertEqual(files, {"old.md"})

    def test_invalid_archive_records_are_failures_before_indexing(self):
        for changed in ({"id": "../escape"}, {"body_markdown": None}, {"coverage_start": "bad"}, {"deleted_at": 1}):
            with self.subTest(changed=changed):
                self.api.articles = [dict(ARTICLE, id="old", reporter_id="reporter") | changed]
                with self.assertRaises(WorkerError):
                    self.history().prepare(self.api)
        self.assertFalse((self.root / "qmd-calls.jsonl").exists())

    def test_index_failure_never_starts_search_or_uses_stale_index(self):
        old = self.history()
        old.prepare(self.api)
        old.close()
        (self.root / "qmd-calls.jsonl").unlink()
        (self.root / "qmd-settings.json").write_text(json.dumps({"fail": "embed"}))
        with self.assertRaisesRegex(WorkerError, "embed failed"):
            self.history().prepare(self.api)
        calls = [json.loads(line)["args"][0] for line in (self.root / "qmd-calls.jsonl").read_text().splitlines()]
        self.assertEqual(calls, ["update", "cleanup", "embed"])

    def test_empty_archive_has_working_search_and_no_recent_summaries(self):
        self.api.articles = []
        history = self.history()
        history.prepare(self.api)
        self.assertEqual(self.call(history, "query", {"query": "anything"})["structuredContent"]["results"], [])
        self.assertEqual(history.summaries, {})
        self.assertEqual(history.snapshot["article_count"], 0)

    def test_zero_exit_qmd_with_incomplete_index_is_a_cached_failure(self):
        complete = {"totalDocuments": 1, "needsEmbedding": 0, "hasVectorIndex": True}
        for changed in (
            {"needsEmbedding": 1}, {"totalDocuments": 0}, {"hasVectorIndex": False},
            {"needsEmbedding": None},
        ):
            with self.subTest(changed=changed):
                (self.root / "qmd-settings.json").write_text(json.dumps({"status": complete | changed}))
                history = self.history()
                for _ in range(2):
                    with self.assertRaisesRegex(WorkerError, "incomplete"):
                        history.prepare(self.api)
                self.assert_process_stopped(int((self.root / "qmd-pid").read_text()))

    def test_status_tool_failure_is_not_ready_history(self):
        (self.root / "qmd-settings.json").write_text(json.dumps({"status_error": True}))
        with self.assertRaises(WorkerError):
            self.history().prepare(self.api)
        self.assert_process_stopped(int((self.root / "qmd-pid").read_text()))

    def test_zero_exit_skipped_read_cannot_serve_old_article(self):
        old = self.history()
        old.prepare(self.api)
        old.close()
        self.api.articles[0]["summary"] = "An updated summary"
        (self.root / "qmd-settings.json").write_text(json.dumps({"skip_read": True}))
        for _ in range(2):
            with self.assertRaisesRegex(WorkerError, "skipped"):
                self.history().prepare(self.api)

    def test_recent_summaries_are_bounded_and_keep_api_order(self):
        self.api.articles = [dict(ARTICLE, id=f"story{i}", reporter_id="reporter") for i in range(25)]
        history = self.history()
        history.prepare(self.api)
        self.assertEqual([a["id"] for a in history.summaries["reporter"]], [f"story{i}" for i in range(20)])
        self.assertEqual(history.snapshot["article_count"], 25)

    def test_qmd_below_minimum_fails_before_fetching_archive(self):
        (self.root / "qmd-settings.json").write_text(json.dumps({"version": "qmd 2.8.2"}))
        with self.assertRaisesRegex(WorkerError, "QMD 2.8.3 or later"):
            self.history().prepare(self.api)
        self.assertEqual(self.api.downloads, 0)

    def test_newer_qmd_major_is_accepted(self):
        (self.root / "qmd-settings.json").write_text(json.dumps({"version": "qmd 3.0.0"}))
        self.history().prepare(self.api)
        self.assertEqual(self.api.downloads, 1)

    def test_search_start_failure_is_reported(self):
        (self.root / "qmd-settings.json").write_text(json.dumps({"fail": "mcp"}))
        with self.assertRaisesRegex(WorkerError, "did not become ready"):
            self.history().prepare(self.api)

    def test_search_process_exits_when_history_closes(self):
        history = self.history()
        history.prepare(self.api)
        pid = int((self.root / "qmd-pid").read_text())
        history.close()
        self.assert_process_stopped(pid)

    def assert_process_stopped(self, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.02)
        self.fail(f"Search process {pid} remained alive")

    def test_supervisor_death_stops_shared_search(self):
        fixture = self.root / "fixture.json"
        fixture.write_text(json.dumps({"settings": self.settings, "articles": self.api.articles}))
        code = '''
import json, pathlib, sys, time
from news.worker_history import History
fixture = json.loads(pathlib.Path(sys.argv[1]).read_text())
sys.path.insert(0, str(pathlib.Path.cwd() / "tests/app"))
from history_support import Archive
history = History(fixture["settings"])
history.prepare(Archive(fixture["articles"]))
pathlib.Path(sys.argv[1]+".ready").touch()
time.sleep(30)
'''
        process = subprocess.Popen([sys.executable, "-B", "-c", code, str(fixture)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 5
        while not Path(str(fixture) + ".ready").exists():
            self.assertIsNone(process.poll())
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.02)
        pid = int((self.root / "qmd-pid").read_text())
        process.kill()
        process.wait(timeout=5)
        self.assert_process_stopped(pid)
