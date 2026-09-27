#!/usr/bin/env python3
"""Opt-in real-QMD retrieval checks. Synthetic content; no reporting model or API."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib import request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from news.worker_history import History


def call(history, name, arguments):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}).encode()
    req = request.Request(history.endpoint, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
    })
    with request.urlopen(req, timeout=180) as response:
        raw = response.read().decode()
    # QMD supports JSON and the legacy SSE transport used by Codex.
    value = json.loads(next(line[6:] for line in raw.splitlines() if line.startswith("data: "))) if raw.startswith("event:") else json.loads(raw)
    if "error" in value:
        raise RuntimeError(value["error"])
    return value["result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qmd-command", nargs="+")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent.parent
    cache = checkout / ".cache"
    cache.mkdir(exist_ok=True)
    fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("article-history.json").read_text())

    class API:
        articles = fixture["articles"]

        def pages(self, route, field):
            yield from self.articles

    api = API()
    report = {"corpus_size": len(api.articles), "queries": []}
    with tempfile.TemporaryDirectory(prefix="history-smoke-", dir=cache) as directory:
        settings = {"state_dir": directory}
        if args.qmd_command:
            settings["qmd_command"] = args.qmd_command
        history = History(settings)
        try:
            history.prepare(api)
            def search(case):
                started = time.monotonic()
                result = call(history, "query", {"query": case["query"], "limit": 5, "minScore": 0})
                assert not result.get("isError"), result
                rows = result["structuredContent"]["results"]
                ids = [Path(row["file"]).stem for row in rows]
                assert ids[0] == case["expected"][0], (case, ids)
                assert set(case["expected"]) <= set(ids), (case, ids)
                return {"query": case["query"], "ids": ids, "seconds": round(time.monotonic() - started, 3)}
            # Exercise eight clients sharing a cold model process.
            with ThreadPoolExecutor(max_workers=8) as pool:
                report["queries"] = list(pool.map(search, (fixture["queries"] * 2)[:8]))
            article = call(history, "get", {"file": "articles/model-v21.md", "maxLines": 80})
            body = "\n".join(c["resource"]["text"] if c["type"] == "resource" else c.get("text", "") for c in article["content"])
            for expected in ("id: model-v21", "Fixture reporter", "2026-09-26", "https://example.com/model-v21"):
                assert expected in body, (expected, body)
        finally:
            history.close()
        # A subsequent empty snapshot must remove all indexed content and still
        # answer queries successfully. This also exercises QMD removal cleanup.
        api.articles = []
        empty = History(settings)
        try:
            empty.prepare(api)
            result = call(empty, "query", {"query": "Orion structured output", "limit": 5})
            assert not result.get("isError"), result
            assert result["structuredContent"]["results"] == [], result
            missing = call(empty, "get", {"file": "articles/model-v21.md", "maxLines": 80})
            assert missing.get("isError"), missing
        finally:
            empty.close()
    report["empty_snapshot_and_removal"] = "passed"
    output = cache / "history-search-smoke.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Real QMD checks passed: eight clients, six retrieval cases, article read, deletion, and empty archive. Results: {output}")


if __name__ == "__main__":
    main()
