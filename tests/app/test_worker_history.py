"""History snapshot and search lifecycle through API and process boundaries."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib import request

from news.worker_history import History
from news.worker_io import WorkerError
from history_support import fake_qmd
from test_worker import ARTICLE


class Archive:
    def __init__(self, articles):
        self.articles = articles
        self.downloads = 0
        self.error = False

    def pages(self, route, field):
        self.downloads += 1
        yield from self.articles
        if self.error:
            raise WorkerError("Page two failed.")


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
        unchanged = self.root / "state/history/articles/old.md"
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
        self.assertNotIn("old.md", json.loads((self.root / "state/history/index.sqlite").read_text()))
        deletion.close()
        self.api.articles.append(dict(ARTICLE, id="old", reporter_id="reporter"))
        restoration = self.history()
        restoration.prepare(self.api)
        self.assertTrue(unchanged.exists())
        self.assertEqual(restoration.snapshot["article_count"], 2)

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
        files = {p.name for p in (self.root / "state/history/articles").iterdir()}
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

    def test_incompatible_qmd_fails_before_fetching_archive(self):
        (self.root / "qmd-settings.json").write_text(json.dumps({"version": "qmd 3.0.0"}))
        with self.assertRaisesRegex(WorkerError, "QMD >=2.8.3,<3"):
            self.history().prepare(self.api)
        self.assertEqual(self.api.downloads, 0)

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
class API:
    def pages(self, route, field):
        yield from fixture["articles"]
history = History(fixture["settings"])
history.prepare(API())
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
