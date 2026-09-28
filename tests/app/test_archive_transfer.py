"""Measure real HTTP payloads and verify cache reconciliation with the server."""

from pathlib import Path
import json

from news.db import transaction
from news.worker_history import History
from news.worker_io import NewsAPI
from history_support import fake_qmd
from test_worker_contract import WorkerHTTPFixture


class ArchiveTransferTests(WorkerHTTPFixture):
    def external_http(self, request, **kwargs):
        response = super().external_http(request, **kwargs)
        if hasattr(self, "transfers") and request.full_url.startswith("https://news.example.com"):
            self.transfers.append((request.full_url, len(response.getvalue())))
        return response

    def test_large_archive_transfer_and_trash_restore_purge(self):
        _, run = self.due()
        receipt = self.result(run, self.envelope(self.claim(run), articles=[self.article(body_markdown="News coverage. " * 1500)]))
        self.assertEqual(receipt.status_code, 200)
        identity = receipt.json["article_ids"][0]
        with transaction(self.database, write=True) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(articles)") if row[1] not in ("id", "revision")]
            for number in range(204):
                connection.execute(f"INSERT INTO articles(id,{','.join(columns)}) SELECT ?,{','.join(columns)} FROM articles WHERE id=?",
                                   (f"copy{number:03}", identity))
        root = Path(self.database).parent
        settings = {"server_url": "https://news.example.com", "client_id": "fixture-id", "client_secret": "fixture-secret",
                    "state_dir": str(root / "state"), "qmd_command": fake_qmd(root)}
        api = NewsAPI(settings)
        measurements = {}

        def refresh(label, bodies):
            self.transfers = []
            history = History(settings)
            try:
                history.prepare(api)
            finally:
                history.close()
            downloaded = [url.split("/articles/")[1].split("?")[0] for url, _ in self.transfers if "/manifest?" not in url]
            self.assertEqual(set(downloaded), set(bodies))
            self.assertEqual(len(downloaded), len(bodies))
            measurements[label] = {"requests": len(self.transfers), "bodies": len(downloaded),
                                   "bytes": sum(size for _, size in self.transfers),
                                   "metadata_bytes": sum(size for url, size in self.transfers if "/manifest?" in url)}
            return history

        expected = {identity} | {f"copy{n:03}" for n in range(204)}
        self.transfers = []
        self.assertEqual({a["id"] for a in api.pages("/articles/search", "articles")}, expected)
        measurements["full_search"] = {"requests": len(self.transfers), "bodies": len(expected),
                                       "bytes": sum(size for _, size in self.transfers)}
        refresh("initial", expected)
        refresh("unchanged", [])
        with transaction(self.database, write=True) as connection:
            connection.execute("UPDATE articles SET summary='Revised summary' WHERE id=?", (identity,))
        refresh("one_change", [identity])
        self.assertEqual(measurements["unchanged"]["requests"], 4)
        self.assertEqual(measurements["one_change"]["requests"], 5)
        self.assertLess(measurements["unchanged"]["bytes"], measurements["initial"]["bytes"] // 100)
        self.assertLess(measurements["one_change"]["bytes"], measurements["initial"]["bytes"] // 50)
        with transaction(self.database, write=True) as connection:
            connection.execute(f"INSERT INTO articles(id,{','.join(columns)}) SELECT ?,{','.join(columns)} FROM articles WHERE id=?",
                               ("added", identity))
        refresh("one_addition", ["added"])
        self.form(f"/newsroom/articles/{identity}/delete")
        refresh("trash", [])
        self.assertFalse((root / f"state/history/current/articles/{identity}.md").exists())
        self.form(f"/newsroom/articles/{identity}/restore")
        refresh("restore", [identity])
        self.form(f"/newsroom/articles/{identity}/delete")
        self.at("2026-10-27T12:00:00-07:00")
        result = self.app.test_cli_runner().invoke(args=["maintain"])
        self.assertEqual(result.exit_code, 0, result.output)
        refresh("purge", [])
        self.assertFalse((root / f"state/history/current/articles/{identity}.md").exists())
        print("Archive transfer measurements: " + json.dumps(measurements, sort_keys=True))
