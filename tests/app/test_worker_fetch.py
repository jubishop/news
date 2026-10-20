"""The reporters' page browser, driven over MCP stdio against a local web origin."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "news" / "worker_fetch.py"
LONG = "\n".join(f"<p>Sentence {n:04} explains one more detail of the long report.</p>" for n in range(600))


def minimal_pdf(text):
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 18 Tf 72 700 Td (" + text.encode() + b") Tj ET"
    objects[3] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    data, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets)
    return data + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class Origin(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        Origin.seen.append((self.headers.get("Host", ""), self.path))
        port = self.server.server_port
        pages = {
            "/article": ("text/html", f"""<!doctype html><title>Truck recall widens</title>
<nav>NAVIGATION MENU <a href="/a">Navigation link that is long enough to list</a></nav>
<main><h1>Truck recall widens</h1>
<p>{"The manufacturer recalled ten electric trucks for a battery defect. " * 10}</p>
<figure><img src="https://images.news.test/truck.jpg" width="800" height="600" alt="A recalled truck">
<figcaption>Photo: Example Agency</figcaption></figure>
<img src="http://127.0.0.1:{port}/pixel" width="800" height="600" alt="Local pixel">
<p><a href="/next-story">Regulators publish the full recall report today</a></p></main>
<footer>FOOTER TEXT</footer>"""),
            "/challenge": ("text/html", "<title>Just a moment...</title><p>Checking your browser.</p>"
                                        "<script>setTimeout(() => location.replace('/article'), 1500)</script>"),
            "/long": ("text/html", f"<title>Long report</title><main>{LONG}<p>END-OF-LONG-PAGE</p></main>"),
            "/japanese": ("text/html", "<title>長い記事</title><main><p>" + "電気自動車の新しいモデルが発表されました。" * 600 + "</p></main>"),
            "/abstract.txt": ("text/plain", "PMID 42864371. Vitamin D raised serum levels in children."),
            "/report.pdf": ("application/pdf", minimal_pdf("Recall 26V494 covers ten trucks")),
            "/secret": ("text/plain", "SECRET LOCAL DATA"),
            "/pixel": ("image/gif", b"GIF89a"),
        }
        if self.path.startswith("/flagged"):
            # Like Cloudflare, block a session that returns after its first page.
            returning = "visited=1" in self.headers.get("Cookie", "")
            body = b"<title>Attention Required! | Cloudflare</title>" if returning else b"<title>Story</title><p>Welcome.</p>"
            self.send_response(403 if returning else 200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "visited=1; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/blocked-once":
            # Like an intermittent bot block: the first visit is denied, a later one gets through.
            blocked = sum(path == self.path for _, path in Origin.seen) == 1
            body = b"<title>Access denied</title>" if blocked else b"<title>Story</title><p>Welcome back.</p>"
            self.send_response(403 if blocked else 200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/challenge")
            self.end_headers()
            return
        if self.path == "/to-local":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{port}/secret")
            self.end_headers()
            return
        kind, body = pages.get(self.path, ("text/html", "<title>Missing</title><p>Not here.</p>"))
        body = body.encode() if isinstance(body, str) else body
        self.send_response(200 if self.path in pages else 404)
        self.send_header("Content-Type", kind + "; charset=utf-8" if kind.startswith("text/") else kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PageBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        threading.Thread(target=cls.origin.serve_forever, kwargs={"poll_interval": .01}, daemon=True).start()
        cls.base = f"http://news.test:{cls.origin.server_port}"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).with_name("fetch_support")))
        cls.server = subprocess.Popen([sys.executable, "-B", str(SERVER)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, env=env, text=True)
        cls.next_id = 0
        cls.initialized = cls.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                     "clientInfo": {"name": "test", "version": "1"}})
        cls.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @classmethod
    def tearDownClass(cls):
        cls.server.stdin.close()
        cls.server.wait(timeout=30)
        cls.server.stdout.close()
        cls.origin.shutdown()
        cls.origin.server_close()

    @classmethod
    def send(cls, message):
        cls.server.stdin.write(json.dumps(message) + "\n")
        cls.server.stdin.flush()

    @classmethod
    def request(cls, method, params):
        cls.next_id += 1
        cls.send({"jsonrpc": "2.0", "id": cls.next_id, "method": method, "params": params})
        ready, _, _ = select.select([cls.server.stdout], [], [], 150)
        if not ready:
            raise AssertionError(f"No response to {method}")
        response = json.loads(cls.server.stdout.readline())
        assert response["id"] == cls.next_id, response
        return response

    def fetch(self, url, **arguments):
        result = self.request("tools/call", {"name": "fetch_page", "arguments": {"url": url, **arguments}})["result"]
        return result["content"][0]["text"], result["isError"]

    def test_mcp_handshake_lists_one_tool(self):
        self.assertEqual(self.initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", self.initialized["result"]["capabilities"])
        tools = self.request("tools/list", {})["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["fetch_page"])
        self.assertEqual(tools[0]["inputSchema"]["required"], ["url"])
        self.assertEqual(self.request("resources/list", {})["error"]["code"], -32601)

    def test_page_text_images_and_links_without_navigation(self):
        text, error = self.fetch(self.base + "/article")
        self.assertFalse(error)
        self.assertIn("Title: Truck recall widens", text)
        self.assertIn("HTTP status: 200", text)
        self.assertIn("The manufacturer recalled ten electric trucks", text)
        self.assertIn("- https://images.news.test/truck.jpg | alt: A recalled truck | caption: Photo: Example Agency", text)
        self.assertIn(f"- Regulators publish the full recall report today: {self.base}/next-story", text)
        for chrome in ("NAVIGATION MENU", "FOOTER TEXT", "Navigation link"):
            self.assertNotIn(chrome, text)

    def test_redirects_and_bot_checks_reach_the_page(self):
        text, error = self.fetch(self.base + "/moved")
        self.assertFalse(error)
        self.assertIn(f"URL: {self.base}/article", text)
        self.assertIn("The manufacturer recalled ten electric trucks", text)
        self.assertNotIn("Just a moment", text)

    def test_long_results_continue_from_start(self):
        chunks, start = [], 0
        while True:
            text, error = self.fetch(self.base + "/long", start=start)
            self.assertFalse(error)
            self.assertLess(len(text), 8_000)
            chunks.append(text)
            more = re.search(r"start=(\d+) for more", text)
            if not more:
                break
            start = int(more.group(1))
        self.assertGreater(len(chunks), 1)
        self.assertIn("Sentence 0000", chunks[0])
        self.assertIn("END-OF-LONG-PAGE", chunks[-1])
        joined = "".join(chunks)
        self.assertTrue(all(f"Sentence {n:04}" in joined for n in range(600)))
        self.assertEqual(sum(path == "/long" for _, path in Origin.seen), 1)
        text, error = self.fetch(self.base + "/long", start=10**6)
        self.assertIn("past its end", text)

    def test_non_latin_text_continues_sooner(self):
        text, error = self.fetch(self.base + "/japanese")
        self.assertFalse(error)
        self.assertLess(len(text), 3_000)
        self.assertIn("for more", text)

    def test_each_page_starts_a_fresh_session(self):
        for n in range(2):
            text, error = self.fetch(self.base + f"/flagged?n={n}")
            self.assertIn("HTTP status: 200", text)
            self.assertIn("Welcome.", text)

    def test_blocked_pages_load_again_when_retried(self):
        text, error = self.fetch(self.base + "/blocked-once")
        self.assertIn("HTTP status: 403", text)
        text, error = self.fetch(self.base + "/blocked-once")
        self.assertFalse(error)
        self.assertIn("HTTP status: 200", text)
        self.assertIn("Welcome back.", text)

    def test_plain_text_and_missing_pages(self):
        text, error = self.fetch(self.base + "/abstract.txt")
        self.assertFalse(error)
        self.assertIn("PMID 42864371. Vitamin D raised serum levels in children.", text)
        text, error = self.fetch(self.base + "/missing")
        self.assertFalse(error)
        self.assertIn("HTTP status: 404", text)
        self.assertIn("Not here.", text)

    @unittest.skipUnless(sys.platform == "darwin", "The worker reads PDFs with macOS PDFKit")
    def test_pdf_text_is_extracted(self):
        text, error = self.fetch(self.base + "/report.pdf")
        self.assertFalse(error, text)
        self.assertIn("Recall 26V494 covers ten trucks", text)

    def test_local_addresses_and_other_schemes_are_refused(self):
        port = self.origin.server_port
        for url in (f"http://127.0.0.1:{port}/secret", f"http://localhost:{port}/secret", "http://10.0.0.1/",
                    "http://[::1]/", "file:///etc/hosts", "chrome://version", "not a url", "http://[::1/",
                    "http://news.test:port/"):
            with self.subTest(url=url):
                text, error = self.fetch(url)
                self.assertTrue(error)
                self.assertNotIn("SECRET", text)
        text, _ = self.fetch(self.base + "/to-local")
        self.assertNotIn("SECRET", text)
        self.fetch(self.base + "/article")
        local = [path for host, path in Origin.seen if path in ("/secret", "/pixel")]
        self.assertEqual(local, [], "pages, redirects, and subresources must not reach local addresses")
        text, error = self.fetch(self.base + "/article", start=-1)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
