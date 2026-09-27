"""Authenticated worker HTTP and durable private files."""

from http.client import HTTPException
import json
import os
from pathlib import Path
import tempfile
import time
from urllib import error, parse, request


class WorkerError(Exception):
    pass


class APIError(WorkerError):
    def __init__(self, status, code="request_failed"):
        self.status = status
        self.code = code
        super().__init__(f"News API request failed (HTTP {status}, {code}).")


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def remove_file(path):
    path.unlink()
    sync_directory(path.parent)


class NewsAPI:
    def __init__(self, settings):
        url = settings["server_url"].rstrip("/")
        parsed = parse.urlsplit(url)
        if (parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1", "localhost")
        )) or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise WorkerError("server_url must be an HTTPS origin (HTTP loopback is allowed for tests).")
        self.base = url + "/api/v1/worker"
        self.headers = {
            "CF-Access-Client-Id": settings["client_id"],
            "CF-Access-Client-Secret": settings["client_secret"],
            "Accept": "application/json", "Content-Type": "application/json",
        }
        if not all(isinstance(v, str) and v and "\n" not in v and "\r" not in v for v in self.headers.values()):
            raise WorkerError("Worker service credentials are required.")
        self.delays = settings.get("http_retry_delays", [0, 1, 5])
        self.timeout = settings.get("http_timeout_seconds", 30)

    def call(self, route, payload=None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if payload is not None else None
        if body and len(body) > 2_000_000:
            raise WorkerError("Worker request exceeds the server's 2 MB limit.")
        for index, delay in enumerate(self.delays):
            if delay:
                time.sleep(delay)
            req = request.Request(self.base + route, data=body, headers=self.headers)
            try:
                with request.build_opener(NoRedirect).open(req, timeout=self.timeout) as response:
                    raw = response.read(50_000_001)
                if len(raw) > 50_000_000:
                    raise WorkerError("News API response exceeds 50 MB.")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError()
                return result
            except error.HTTPError as exc:
                status = exc.code
                exc.close()
                failure = APIError(status)
                if status != 429 and status < 500:
                    raise failure from None
            except (error.URLError, HTTPException, TimeoutError, ConnectionError, OSError):
                failure = APIError(0, "connection_failed")
            except (ValueError, UnicodeError):
                failure = APIError(0, "invalid_response")
            if index == len(self.delays) - 1:
                raise failure from None
        raise WorkerError("At least one HTTP attempt is required.")

    def pages(self, route, field):
        separator = "&" if "?" in route else "?"
        for page in range(1, 100_001):
            result = self.call(f"{route}{separator}page={page}&limit=100")
            items, more = result.get(field), result.get("has_more")
            if not isinstance(items, list) or type(more) is not bool:
                raise WorkerError("News API returned an invalid archive page.")
            yield from items
            if not more:
                return
        raise WorkerError("News archive exceeds the API pagination limit.")
