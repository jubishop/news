#!/usr/bin/env python3
"""Opt-in real-QMD retrieval checks. Synthetic content; no reporting model or API."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback
from urllib import request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from news.worker_history import History
from news.worker_io import save_json
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from history_support import Archive


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
    output = cache / "history-search-smoke.json"
    report = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "queries": [], "diagnostics": {}, "errors": []}
    for check in ("article_read", "model_health", "empty_model_health", "empty_snapshot_and_removal", "incremental_refresh", "cleanup"):
        report[check] = "not_run"
    # Invalidate any older success before fixture loading or QMD preparation.
    save_json(output, report)

    def failure(label):
        report["errors"].append({"stage": label, "traceback": traceback.format_exc()})

    def verify(label, action):
        try:
            action()
            report[label] = "passed"
        except Exception:
            report[label] = "failed"
            failure(label)

    def search(history, case, client):
        started = time.monotonic()
        row = {"client": client, "query": case["query"], "expected": case["expected"],
               "first_any_of": case["first_any_of"], "ids": [], "status": "failed"}
        try:
            result = call(history, "query", {"query": case["query"], "limit": 5, "minScore": 0})
            row["result"] = result
            if result.get("isError"):
                raise RuntimeError(f"QMD query failed: {result}")
            row["ids"] = [Path(item["file"]).stem for item in result["structuredContent"]["results"]]
            missing = set(case["expected"]) - set(row["ids"])
            if missing:
                raise RuntimeError(f"Missing required articles: {sorted(missing)}; returned: {row['ids']}")
            if not row["ids"] or row["ids"][0] not in case["first_any_of"]:
                raise RuntimeError(f"Expected first article in {case['first_any_of']}; returned: {row['ids']}")
            row["status"] = "passed"
        except Exception:
            row["error"] = traceback.format_exc()
        row["seconds"] = round(time.monotonic() - started, 3)
        return row

    def read_article(history):
        article = call(history, "get", {"file": "articles/model-v21.md", "maxLines": 80})
        report["article"] = article
        if article.get("isError"):
            raise RuntimeError(f"QMD article read failed: {article}")
        body = "\n".join(c["resource"]["text"] if c["type"] == "resource" else c.get("text", "") for c in article["content"])
        for expected in ("id: model-v21", "reporter_id: fixture", "reporter_name: Fixture reporter",
                         "article_date: 2026-09-27", "coverage_start: 2026-09-26", "coverage_end: 2026-09-27",
                         "https://example.com/model-v21"):
            if expected not in body:
                raise RuntimeError(f"Article read is missing {expected!r}")

    def empty_archive(history):
        result = call(history, "query", {"query": "Orion structured output", "limit": 5})
        report["empty_query"] = result
        if result.get("isError") or result["structuredContent"]["results"] != []:
            raise RuntimeError(f"Expected successful empty search: {result}")
        missing = call(history, "get", {"file": "articles/model-v21.md", "maxLines": 80})
        report["deleted_article"] = missing
        if not missing.get("isError"):
            raise RuntimeError(f"Deleted article still readable: {missing}")

    try:
        fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("article-history.json").read_text())
        report["corpus_size"] = len(fixture["articles"])
        with tempfile.TemporaryDirectory(prefix="history-smoke-", dir=cache) as directory:
            report["temporary_directory"] = directory
            settings = {"state_dir": directory}
            if args.qmd_command:
                settings["qmd_command"] = args.qmd_command
            for phase, articles in (("populated", fixture["articles"]), ("unchanged", fixture["articles"]), ("empty", [])):
                history = History(settings)
                try:
                    api = Archive(articles)
                    history.prepare(api)
                    if phase == "populated":
                        # Keep every client's evidence even when another fails.
                        with ThreadPoolExecutor(max_workers=8) as pool:
                            futures = [pool.submit(search, history, case, client)
                                       for client, case in enumerate((fixture["queries"] * 2)[:8], 1)]
                            for future in as_completed(futures):
                                row = future.result()
                                report["queries"].append(row)
                                report["queries"].sort(key=lambda item: item["client"])
                                if row["status"] == "failed":
                                    report["errors"].append({"stage": f"client {row['client']}", "traceback": row["error"]})
                                save_json(output, report)
                        verify("article_read", lambda: read_article(history))
                    elif phase == "unchanged":
                        if api.bodies:
                            raise RuntimeError("Unchanged refresh downloaded article bodies")
                        read_article(history)
                        history.check()
                        report["incremental_refresh"] = "passed"
                    else:
                        verify("empty_snapshot_and_removal", lambda: empty_archive(history))
                    if phase != "unchanged":
                        verify("model_health" if phase == "populated" else "empty_model_health", history.check)
                finally:
                    try:
                        history.close()
                    except Exception:
                        report["cleanup"] = "failed"
                        raise
                    finally:
                        # The next preparation overwrites logs; copy them before
                        # that happens and before the temporary index is removed.
                        report["diagnostics"][phase] = {
                            name: (history.root / name).read_text(errors="replace")
                            for name in ("indexing.log", "search.log") if (history.root / name).exists()
                        }
                        save_json(output, report)
        report["cleanup"] = "passed"
    except (Exception, KeyboardInterrupt):
        failure("run")
        directory = report.get("temporary_directory")
        if report["cleanup"] != "failed" and directory and not Path(directory).exists():
            report["cleanup"] = "passed"
    report["status"] = "failed" if report["errors"] else "passed"
    if report["errors"]:
        report["error"] = "\n".join(item["traceback"] for item in report["errors"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_json(output, report)
    if report["status"] == "failed":
        print(f"Real QMD checks failed. Results and diagnostics: {output}", file=sys.stderr)
        print(report["error"], file=sys.stderr)
        return 1
    print(f"Real QMD checks passed: eight clients, six retrieval cases, article read, deletion, and empty archive. Results: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
