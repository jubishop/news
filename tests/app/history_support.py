"""QMD executable fake: the worker still performs real sync and process I/O."""

from pathlib import Path
import sys


def fake_qmd(root):
    executable = Path(root) / "qmd"
    executable.write_text(f"#!{sys.executable}\n" + r'''
import json, os, pathlib, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
root = pathlib.Path(__file__).parent
settings = json.loads((root / "qmd-settings.json").read_text()) if (root / "qmd-settings.json").exists() else {}
if "--version" in sys.argv:
    print(settings.get("version", "qmd 2.8.3 (fixture)"))
    sys.exit(0)
config = pathlib.Path(os.environ["QMD_CONFIG_DIR"]) / "index.yml"
collection = json.loads(config.read_text())["collections"]["articles"]["path"]
index = pathlib.Path(os.environ["INDEX_PATH"])
with (root / "qmd-calls.jsonl").open("a") as log:
    log.write(json.dumps({"args": sys.argv[1:], "env": dict(os.environ), "index": str(index)}) + "\n")
if settings.get("fail") == sys.argv[1]:
    print("fixture command failure: " + sys.argv[1], file=sys.stderr, flush=True)
    sys.exit(7)
if sys.argv[1] == "update":
    if settings.get("skip_read"):
        print("Skipped 1 unreadable file(s)", file=sys.stderr)
    else:
        index.write_text(json.dumps({p.name:p.read_text() for p in pathlib.Path(collection).glob("*.md")}))
    sys.exit(0)
if sys.argv[1] in ("embed", "cleanup"):
    sys.exit(0)
if sys.argv[1] != "mcp":
    sys.exit(8)
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.loads(index.read_text())
        name = message.get("params", {}).get("name")
        args = message.get("params", {}).get("arguments", {})
        with (root / "qmd-requests.jsonl").open("a") as log:
            log.write(json.dumps({"name": name, "arguments": args}) + "\n")
        if message["method"] == "initialize":
            result = {"protocolVersion":"2025-03-26", "capabilities":{"tools":{}}, "serverInfo":{"name":"qmd", "version":"2.8.3"}}
        elif message["method"] == "tools/list":
            result = {"tools":[{"name":n,"description":n,"inputSchema":{"type":"object"}} for n in ("query", "get")]}
        elif name == "status":
            result = {"structuredContent": settings.get("status", {
                "totalDocuments": len(data), "needsEmbedding": 0, "hasVectorIndex": bool(data),
            })}
            if settings.get("status_error"):
                result = {"isError": True, "content": [{"type": "text", "text": "Index unavailable"}]}
        elif name == "query":
            result = {"content":[{"type":"text","text":"Search results"}],"structuredContent":{"results":[{"file":"qmd://articles/"+n,"snippet":v[:300]} for n,v in data.items()][:args.get("limit",5)]}}
            if data and "query_results" in settings:
                result["structuredContent"]["results"] = [{"file": "qmd://articles/" + identity + ".md"}
                    for identity in settings["query_results"][args["query"]]]
            if not data and settings.get("stale_empty_result"):
                result["structuredContent"]["results"] = [{"file": "qmd://articles/model-v21.md"}]
            if settings.get("model_warning"):
                print(settings["model_warning"] + ": fixture model failure", file=sys.stderr, flush=True)
            if settings.get("query_failure"):
                print(settings["query_failure"] + ": fixture model failure", file=sys.stderr, flush=True)
                result["structuredContent"]["results"] = []
        elif name == "get":
            text = data.get(args["file"].split("/")[-1])
            if text is None:
                result = {"isError": True, "content": [{"type": "text", "text": "Article not found"}]}
            else:
                text = text.replace(settings.get("omit_text", "\x00"), "")
                result = {"content":[{"type":"resource","resource":{"uri":args["file"],"mimeType":"text/markdown","text":text}}]}
        else:
            result = {}
        if settings.get("tool_error") == name:
            result = {"isError": True, "content": [{"type": "text", "text": "fixture tool failure"}]}
        response = json.dumps({"jsonrpc":"2.0","id":message.get("id"),"result":result}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(response)))
        self.end_headers()
        self.wfile.write(response)
port = int(sys.argv[sys.argv.index("--port")+1])
http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
(root / "qmd-pid").write_text(str(os.getpid()))
with (root / "qmd-pids.jsonl").open("a") as log:
    log.write(str(os.getpid()) + "\n")
print(f"QMD MCP server listening on http://127.0.0.1:{http.server_port}/mcp", file=sys.stderr, flush=True)
http.serve_forever()
''')
    executable.chmod(0o700)
    return [str(executable)]
