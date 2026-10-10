"""Archive synchronization through the authenticated Flask/SQLite contract."""

from pathlib import Path
import sqlite3

from news.db import migrate, transaction
from support import ServerFixture


class ManifestTests(ServerFixture):
    def test_upgrade_from_populated_v1_preserves_articles_and_initializes_revisions(self):
        identity = self.publish()
        old = Path(self.database).with_name("version1.sqlite3")
        with sqlite3.connect(old) as connection:
            connection.executescript(Path("news/schema.sql").read_text())
            connection.execute("ATTACH DATABASE ? AS current", (self.database,))
            for table in ("reporters", "runs", "run_attempts", "articles"):
                columns = ",".join(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
                connection.execute(f"INSERT INTO {table}({columns}) SELECT {columns} FROM current.{table}")
        self.app.config["DATABASE"] = str(old)
        migrate(old)
        manifest = self.manifest().json
        self.assertEqual(manifest["articles"][0]["id"], identity)
        self.assertEqual(len(manifest["articles"][0]["revision"]), 32)
        with sqlite3.connect(old) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
        upgraded = self.client.get(f"/api/v1/worker/articles/{identity}", headers=self.worker).json
        self.assertEqual(upgraded["title"], "This week in research")
        self.assertIsNone(upgraded["lead_image"])
        migrate(old)
        self.assertEqual(self.manifest().json, manifest)
        self.form(f"/newsroom/articles/{identity}/delete")
        self.assertEqual(self.manifest(version=manifest["version"]).status_code, 409)

    def publish(self):
        _, run = self.due()
        result = self.result(run, self.envelope(self.claim(run)))
        self.assertEqual(result.status_code, 200)
        return result.json["article_ids"][0]

    def manifest(self, **params):
        return self.client.get("/api/v1/worker/articles/manifest", headers=self.worker, query_string=params)

    def test_manifest_is_authenticated_bounded_and_has_no_bodies(self):
        identity = self.publish()
        response = self.manifest(limit=1)
        self.assertEqual(response.status_code, 200)
        page = response.json
        self.assertEqual(page["total"], 1)
        self.assertFalse(page["has_more"])
        self.assertEqual(set(page["articles"][0]), {"id", "revision"})
        self.assertEqual(page["articles"][0]["id"], identity)
        self.assertEqual(len(page["version"]), 32)
        for headers, status in (({}, 401), (self.owner, 403)):
            self.assertEqual(self.client.get("/api/v1/worker/articles/manifest", headers=headers).status_code, status)
        for params in ({"limit": 101}, {"page": 0}, {"page": 2}, {"version": "bad"}):
            self.assertEqual(self.manifest(**params).status_code, 422)

    def test_versions_guard_pages_and_bodies_and_cover_all_article_changes(self):
        identity = self.publish()
        page = self.manifest().json
        self.assertIn("version", page)
        changes = {"title": "Changed", "summary": "New summary", "body_markdown": "New body",
                   "reporter_name": "New attribution", "article_date": "2026-09-25",
                   "coverage_start": "2026-08-01", "coverage_end": "2026-10-01",
                   "sources_json": '[{"title":"Changed source","url":"https://example.com/new"}]',
                   "published_at": 123.0,
                   "lead_image_json": '{"alt":"A photo","credit":"Example","credit_url":"https://example.com/",'
                                      '"url":"https://example.com/photo.jpg"}'}
        for column, value in changes.items():
            with self.subTest(column=column):
                with transaction(self.database, write=True) as connection:
                    connection.execute(f"UPDATE articles SET {column}=? WHERE id=?", (value, identity))
                stale = self.manifest(version=page["version"])
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(stale.json["error"], "archive_changed")
                self.assertEqual(self.client.get(f"/api/v1/worker/articles/{identity}", headers=self.worker,
                                                query_string={"version": page["version"]}).status_code, 409)
                updated = self.manifest().json
                self.assertNotEqual(updated["articles"][0]["revision"], page["articles"][0]["revision"])
                body = self.client.get(f"/api/v1/worker/articles/{identity}", headers=self.worker,
                                       query_string={"version": updated["version"]})
                self.assertEqual(body.status_code, 200)
                self.assertEqual(body.json["revision"], updated["articles"][0]["revision"])
                page = updated
        self.form(f"/newsroom/articles/{identity}/delete")
        self.assertEqual(self.manifest(version=page["version"]).status_code, 409)
        self.assertEqual(self.manifest().json["articles"], [])
        self.form(f"/newsroom/articles/{identity}/restore")
        self.assertEqual(self.manifest().json["articles"][0]["id"], identity)

    def test_multiple_pages_are_stable_until_publication(self):
        identity = self.publish()
        with transaction(self.database, write=True) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(articles)") if row[1] != "id"]
            for number in range(205):
                connection.execute(f"INSERT INTO articles(id,{','.join(columns)}) SELECT ?,{','.join(columns)} FROM articles WHERE id=?",
                                   (f"copy{number:03}", identity))
        first = self.manifest(limit=100).json
        self.assertIn("version", first)
        second = self.manifest(limit=100, page=2, version=first["version"]).json
        third = self.manifest(limit=100, page=3, version=first["version"]).json
        rows = first["articles"] + second["articles"] + third["articles"]
        self.assertEqual(len({row["id"] for row in rows}), 206)
        self.assertEqual([len(p["articles"]) for p in (first, second, third)], [100, 100, 6])
        self.assertFalse(third["has_more"])
        with transaction(self.database, write=True) as connection:
            connection.execute(f"INSERT INTO articles(id,{','.join(columns)}) SELECT ?,{','.join(columns)} FROM articles WHERE id=?",
                               ("new-publication", identity))
        self.assertEqual(self.manifest(page=2, version=first["version"]).status_code, 409)
