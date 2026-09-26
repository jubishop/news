"""HTTP journeys through the real app, SQLite, JWT verifier, and renderer."""

import io
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from news import create_app
from news.db import migrate


class ServerFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update(kid="fixture", alg="RS256", use="sig")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / "news.sqlite3")
        migrate(self.database)
        self.clock = self.enterContext(patch("time.time", return_value=1790276400.0))
        self.at("2026-09-25T12:00:00-07:00")
        self.http = self.enterContext(
            patch("urllib.request.urlopen", side_effect=self.external_http)
        )
        self.enterContext(
            patch(
                "urllib.request.OpenerDirector.open",
                autospec=True,
                side_effect=lambda opener, request, **kwargs: self.external_http(
                    request, **kwargs
                ),
            )
        )
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database,
                "SECRET_KEY": "fixture-secret-with-at-least-32-characters",
                "BASE_URL": "https://news.example.com",
                "ACCESS_ISSUER": "https://access.example.com",
                "OWNER_AUD": "owner-aud",
                "WORKER_AUD": "worker-aud",
                "OWNER_EMAIL": "owner@example.com",
                "MONITOR_WORKER": False,
            }
        )
        self.client = self.app.test_client()
        self.owner = {
            "Cf-Access-Jwt-Assertion": self.token(
                "owner-aud", email="owner@example.com"
            )
        }
        self.worker = {
            "Cf-Access-Jwt-Assertion": self.token(
                "worker-aud", common_name="fixture-service"
            )
        }
        response = self.client.get("/newsroom", headers=self.owner)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.csrf = session["csrf_token"]

    def external_http(self, request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        self.assertEqual(url, "https://access.example.com/cdn-cgi/access/certs")
        return io.BytesIO(json.dumps({"keys": [self.jwk]}).encode())

    def token(self, audience, **claims):
        return jwt.encode(
            {
                "iss": "https://access.example.com",
                "aud": [audience],
                "iat": 1,
                "exp": 2_000_000_000,
                "sub": "fixture",
                **claims,
            },
            self.key,
            algorithm="RS256",
            headers={"kid": "fixture"},
        )

    def at(self, value):
        self.clock.return_value = datetime.fromisoformat(value).timestamp()

    def form(self, path, **data):
        self.client.get("/newsroom", headers=self.owner)
        with self.client.session_transaction() as session:
            self.csrf = session["csrf_token"]
        return self.client.post(
            path, headers=self.owner, data={"csrf_token": self.csrf, **data}
        )

    def reporter(self, cadence="daily", **values):
        response = self.form(
            "/newsroom/reporters",
            name="Science desk",
            prompt="Report new research since your last article.",
            cadence=cadence,
            **values,
        )
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        return response.headers["Location"].rsplit("/", 1)[-1]

    def edit(self, reporter, **values):
        return self.form(
            "/newsroom/reporters/" + reporter,
            name="Science desk",
            prompt=values.pop("prompt", "Report new research since your last article."),
            cadence=values.pop("cadence", "daily"),
            **values,
        )

    def work(self):
        response = self.client.post(
            "/api/v1/worker/check-ins",
            headers=self.worker,
            json={"request_id": secrets.token_hex(16)},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json["runs"]

    def claim(self, run, **extra):
        body = {
            "request_id": secrets.token_hex(16),
            "ownership_token": secrets.token_urlsafe(32),
            **extra,
        }
        response = self.client.post(
            f"/api/v1/worker/runs/{run}/claim", headers=self.worker, json=body
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def article(self, **extra):
        return {
            "title": "This week in research",
            "summary": "A concise summary.",
            "article_date": "2026-09-26",
            "coverage_start": "2026-09-01",
            "coverage_end": "2026-09-30",
            "body_markdown": "## Findings\n\nA [source](https://example.com/research).",
            "sources": [{"title": "The study", "url": "https://example.com/research"}],
            **extra,
        }

    def envelope(self, claim, **extra):
        return {
            "submission_id": secrets.token_hex(16),
            "attempt_id": claim["attempt_id"],
            "ownership_token": claim["ownership_token"],
            "outcome": "published",
            "articles": [self.article()],
            **extra,
        }

    def result(self, run, body):
        return self.client.post(
            f"/api/v1/worker/runs/{run}/result", headers=self.worker, json=body
        )

    def due(self, **values):
        reporter = self.reporter(**values)
        self.at("2026-09-26T12:00:00-07:00")
        return reporter, self.work()[0]["id"]
